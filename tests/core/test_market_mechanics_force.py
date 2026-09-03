from __future__ import annotations

import math

from core.market_mechanics_estimator import estimate_inertia_matrices
from core.market_mechanics_force import (
    ForceWeights,
    MicrostructureObservation,
    build_micro_force,
    to_mechanics_observations,
)


def _obs(
    t: float,
    *,
    bid: float = 100.0,
    ask: float = 101.0,
    bid_size: float = 100.0,
    ask_size: float = 100.0,
    buy: float | None = 50.0,
    sell: float | None = 50.0,
    bid_add: float | None = 0.0,
    bid_cancel: float | None = 0.0,
    ask_add: float | None = 0.0,
    ask_cancel: float | None = 0.0,
) -> MicrostructureObservation:
    return MicrostructureObservation(
        trading_minute=t,
        bid_price=bid,
        ask_price=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        buyer_initiated_volume=buy,
        seller_initiated_volume=sell,
        bid_additions=bid_add,
        bid_cancellations=bid_cancel,
        ask_additions=ask_add,
        ask_cancellations=ask_cancel,
    )


def test_force_components_have_expected_direction_and_transparent_composite() -> None:
    observations = (
        _obs(0.0),
        _obs(
            1.0,
            bid_size=120.0,
            ask_size=80.0,
            buy=80.0,
            sell=20.0,
            bid_add=40.0,
            ask_cancel=20.0,
        ),
    )
    states = build_micro_force(observations, price_mode="midpoint")
    state = states[1]

    assert math.isclose(state.ofi_raw or 0.0, 40.0)
    assert math.isclose(state.ofi_pressure or 0.0, 0.2)
    assert math.isclose(state.trade_imbalance or 0.0, 0.6)
    assert math.isclose(state.depth_imbalance, 0.2)
    assert math.isclose(state.replenishment_pressure or 0.0, 1.0)
    assert math.isclose(state.net_force, 0.5)
    assert state.active_components == (
        "ofi",
        "trade_imbalance",
        "depth_imbalance",
        "replenishment",
    )


def test_bearish_book_trade_and_cancellation_pressure_is_negative() -> None:
    observations = (
        _obs(0.0),
        _obs(
            1.0,
            bid_size=80.0,
            ask_size=120.0,
            buy=20.0,
            sell=80.0,
            bid_cancel=40.0,
            ask_add=20.0,
        ),
    )
    state = build_micro_force(observations, price_mode="midpoint")[1]

    assert math.isclose(state.ofi_pressure or 0.0, -0.2)
    assert math.isclose(state.trade_imbalance or 0.0, -0.6)
    assert math.isclose(state.depth_imbalance, -0.2)
    assert math.isclose(state.replenishment_pressure or 0.0, -1.0)
    assert math.isclose(state.net_force, -0.5)


def test_missing_optional_flow_components_do_not_create_fake_zero_pressure() -> None:
    observations = (
        _obs(
            0.0,
            bid_size=120.0,
            ask_size=80.0,
            buy=None,
            sell=None,
            bid_add=None,
            bid_cancel=None,
            ask_add=None,
            ask_cancel=None,
        ),
    )
    state = build_micro_force(observations)[0]

    assert state.ofi_pressure is None
    assert state.trade_imbalance is None
    assert state.replenishment_pressure is None
    assert state.active_components == ("depth_imbalance",)
    assert math.isclose(state.net_force, 0.2)


def test_force_prefix_is_invariant_to_future_observations() -> None:
    prefix = (
        _obs(0.0),
        _obs(1.0, bid_size=110.0, ask_size=90.0, buy=70.0, sell=30.0),
        _obs(2.0, bid_size=90.0, ask_size=110.0, buy=30.0, sell=70.0),
    )
    future = _obs(3.0, bid=102.0, ask=103.0, bid_size=200.0, ask_size=10.0, buy=99.0, sell=1.0)

    prefix_states = build_micro_force(prefix)
    extended_states = build_micro_force(prefix + (future,))

    assert extended_states[: len(prefix_states)] == prefix_states


def _trade_volumes(force: float) -> tuple[float, float]:
    base = 100.0
    return base * (1.0 + force), base * (1.0 - force)


def _synthetic_microstructure() -> tuple[MicrostructureObservation, ...]:
    times = list(range(-40, 1))
    force_pattern = (0.15, -0.35, 0.55, -0.75, 0.30, -0.60, 0.70, -0.20)
    forces = [force_pattern[index % len(force_pattern)] for index in range(len(times))]

    gamma = -0.03
    velocity = 0.0
    log_price = math.log(500.0)
    observations: list[MicrostructureObservation] = []

    for index, trading_minute in enumerate(times):
        price = math.exp(log_price)
        buy, sell = _trade_volumes(forces[index])
        observations.append(
            MicrostructureObservation(
                trading_minute=float(trading_minute),
                bid_price=price - 0.005,
                ask_price=price + 0.005,
                bid_size=100.0,
                ask_size=100.0,
                buyer_initiated_volume=buy,
                seller_initiated_volume=sell,
            )
        )
        if index == len(times) - 1:
            break

        beta = 0.0012 if trading_minute < -15 else 0.0024
        next_acceleration = beta * forces[index] + gamma * velocity
        velocity += next_acceleration
        log_price += velocity

    return tuple(observations)


def test_force_engine_feeds_inertia_estimator_and_recovers_known_15m_beta_shift() -> None:
    raw = _synthetic_microstructure()
    force_states = build_micro_force(
        raw,
        weights=ForceWeights(ofi=0.0, trade_imbalance=1.0, depth_imbalance=0.0, replenishment=0.0),
        price_mode="midpoint",
    )
    mechanics = to_mechanics_observations(force_states)
    estimation = estimate_inertia_matrices(
        mechanics,
        min_direction_samples=5,
        min_quadrant_samples=3,
        standardize=False,
        ridge=1e-12,
    )

    beta_a = estimation.matrices.lookback["beta_up"]["-15m"]
    beta_b = estimation.matrices.current["beta_up"]["15m"]
    beta_c = estimation.matrices.forward["beta_up"]["15m"]

    assert beta_a is not None
    assert beta_b is not None
    assert beta_c is not None
    assert math.isclose(beta_a, 0.0012, rel_tol=0.03, abs_tol=2e-5)
    assert math.isclose(beta_b, 0.0024, rel_tol=0.03, abs_tol=2e-5)
    assert math.isclose(beta_c, 2.0 * beta_b - beta_a, rel_tol=1e-12)
    assert math.isclose(
        estimation.matrices.forward["upside_inertia"]["15m"] or 0.0,
        1.0 / beta_c,
        rel_tol=1e-12,
    )
