from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .market_mechanics_estimator import MechanicsObservation

PriceMode = Literal["midpoint", "microprice"]


@dataclass(frozen=True, slots=True)
class MicrostructureObservation:
    """One causal SPY microstructure snapshot/interval on the trading-minute clock.

    Bid/ask prices and sizes are required. Aggressive trade volumes and explicit
    liquidity-add/cancel fields are optional because not every feed exposes them.
    Every field must describe information known at ``trading_minute``.
    """

    trading_minute: float
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    buyer_initiated_volume: float | None = None
    seller_initiated_volume: float | None = None
    bid_additions: float | None = None
    bid_cancellations: float | None = None
    ask_additions: float | None = None
    ask_cancellations: float | None = None


@dataclass(frozen=True, slots=True)
class ForceWeights:
    """Transparent baseline weights for available micro-force components."""

    ofi: float = 1.0
    trade_imbalance: float = 1.0
    depth_imbalance: float = 1.0
    replenishment: float = 1.0


@dataclass(frozen=True, slots=True)
class ForceState:
    """Auditable directional-pressure state at one observation time."""

    trading_minute: float
    efficient_price: float
    log_price: float
    ofi_raw: float | None
    ofi_pressure: float | None
    trade_imbalance: float | None
    depth_imbalance: float
    replenishment_pressure: float | None
    net_force: float
    active_components: tuple[str, ...]


def _validate_observation(observation: MicrostructureObservation) -> None:
    required = (
        observation.trading_minute,
        observation.bid_price,
        observation.ask_price,
        observation.bid_size,
        observation.ask_size,
    )
    if not all(math.isfinite(value) for value in required):
        raise ValueError("microstructure observations must contain finite quote values")
    if observation.bid_price <= 0.0 or observation.ask_price <= 0.0:
        raise ValueError("bid/ask prices must be positive")
    if observation.bid_price > observation.ask_price:
        raise ValueError("bid price may not exceed ask price")
    if observation.bid_size < 0.0 or observation.ask_size < 0.0:
        raise ValueError("bid/ask sizes must be nonnegative")
    if observation.bid_size + observation.ask_size <= 0.0:
        raise ValueError("at least one side of quoted depth must be positive")

    optional_nonnegative = (
        observation.buyer_initiated_volume,
        observation.seller_initiated_volume,
        observation.bid_additions,
        observation.bid_cancellations,
        observation.ask_additions,
        observation.ask_cancellations,
    )
    for value in optional_nonnegative:
        if value is not None and (not math.isfinite(value) or value < 0.0):
            raise ValueError("optional microstructure flow fields must be finite and nonnegative")


def _efficient_price(observation: MicrostructureObservation, price_mode: PriceMode) -> float:
    midpoint = 0.5 * (observation.bid_price + observation.ask_price)
    if price_mode == "midpoint":
        return midpoint
    if price_mode != "microprice":
        raise ValueError(f"unsupported price_mode: {price_mode}")

    total_depth = observation.bid_size + observation.ask_size
    if total_depth <= 0.0:
        return midpoint
    return (
        observation.ask_price * observation.bid_size
        + observation.bid_price * observation.ask_size
    ) / total_depth


def _ofi(
    previous: MicrostructureObservation,
    current: MicrostructureObservation,
) -> tuple[float, float]:
    """Best-quote order-flow imbalance using the Cont-style event increment."""

    bid_event = 0.0
    if current.bid_price >= previous.bid_price:
        bid_event += current.bid_size
    if current.bid_price <= previous.bid_price:
        bid_event -= previous.bid_size

    ask_event = 0.0
    if current.ask_price <= previous.ask_price:
        ask_event -= current.ask_size
    if current.ask_price >= previous.ask_price:
        ask_event += previous.ask_size

    raw = bid_event + ask_event
    average_total_depth = 0.5 * (
        previous.bid_size
        + previous.ask_size
        + current.bid_size
        + current.ask_size
    )
    normalized = raw / average_total_depth if average_total_depth > 0.0 else 0.0
    return raw, normalized


def _trade_imbalance(observation: MicrostructureObservation) -> float | None:
    buy = observation.buyer_initiated_volume
    sell = observation.seller_initiated_volume
    if buy is None or sell is None:
        return None
    total = buy + sell
    if total <= 0.0:
        return 0.0
    return (buy - sell) / total


def _depth_imbalance(observation: MicrostructureObservation) -> float:
    total = observation.bid_size + observation.ask_size
    return (observation.bid_size - observation.ask_size) / total


def _replenishment_pressure(observation: MicrostructureObservation) -> float | None:
    fields = (
        observation.bid_additions,
        observation.bid_cancellations,
        observation.ask_additions,
        observation.ask_cancellations,
    )
    if any(value is None for value in fields):
        return None

    bid_add = observation.bid_additions or 0.0
    bid_cancel = observation.bid_cancellations or 0.0
    ask_add = observation.ask_additions or 0.0
    ask_cancel = observation.ask_cancellations or 0.0
    total = bid_add + bid_cancel + ask_add + ask_cancel
    if total <= 0.0:
        return 0.0

    # Bid additions and ask cancellations are bullish pressure; ask additions and
    # bid cancellations are bearish pressure.
    bullish = bid_add + ask_cancel
    bearish = ask_add + bid_cancel
    return (bullish - bearish) / total


def _combine_components(
    *,
    ofi_pressure: float | None,
    trade_imbalance: float | None,
    depth_imbalance: float,
    replenishment_pressure: float | None,
    weights: ForceWeights,
) -> tuple[float, tuple[str, ...]]:
    candidates = (
        ("ofi", ofi_pressure, weights.ofi),
        ("trade_imbalance", trade_imbalance, weights.trade_imbalance),
        ("depth_imbalance", depth_imbalance, weights.depth_imbalance),
        ("replenishment", replenishment_pressure, weights.replenishment),
    )

    numerator = 0.0
    denominator = 0.0
    active: list[str] = []
    for name, value, weight in candidates:
        if value is None or weight == 0.0:
            continue
        if not math.isfinite(weight):
            raise ValueError("force weights must be finite")
        numerator += weight * value
        denominator += abs(weight)
        active.append(name)

    if denominator <= 0.0:
        raise ValueError("at least one force component must have a nonzero weight")
    return numerator / denominator, tuple(active)


def build_micro_force(
    observations: tuple[MicrostructureObservation, ...],
    *,
    weights: ForceWeights | None = None,
    price_mode: PriceMode = "microprice",
) -> tuple[ForceState, ...]:
    """Construct a causal, decomposed SPY micro-force stream.

    The baseline composite is the absolute-weight-normalized mean of whichever
    components are actually available. No price return enters the force score.
    """

    if not observations:
        raise ValueError("microstructure observations are required")
    resolved_weights = ForceWeights() if weights is None else weights

    previous_time: float | None = None
    output: list[ForceState] = []
    for index, observation in enumerate(observations):
        _validate_observation(observation)
        if previous_time is not None and observation.trading_minute <= previous_time:
            raise ValueError("microstructure observations must be strictly increasing in trading time")
        previous_time = observation.trading_minute

        ofi_raw: float | None = None
        ofi_pressure: float | None = None
        if index > 0:
            ofi_raw, ofi_pressure = _ofi(observations[index - 1], observation)

        trade = _trade_imbalance(observation)
        depth = _depth_imbalance(observation)
        replenishment = _replenishment_pressure(observation)
        net_force, active = _combine_components(
            ofi_pressure=ofi_pressure,
            trade_imbalance=trade,
            depth_imbalance=depth,
            replenishment_pressure=replenishment,
            weights=resolved_weights,
        )
        price = _efficient_price(observation, price_mode)
        output.append(
            ForceState(
                trading_minute=observation.trading_minute,
                efficient_price=price,
                log_price=math.log(price),
                ofi_raw=ofi_raw,
                ofi_pressure=ofi_pressure,
                trade_imbalance=trade,
                depth_imbalance=depth,
                replenishment_pressure=replenishment,
                net_force=net_force,
                active_components=active,
            )
        )

    return tuple(output)


def to_mechanics_observations(states: tuple[ForceState, ...]) -> tuple[MechanicsObservation, ...]:
    """Adapt force-engine output directly into the inertia estimator contract."""

    return tuple(
        MechanicsObservation(
            trading_minute=state.trading_minute,
            log_price=state.log_price,
            net_force=state.net_force,
        )
        for state in states
    )
