from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from statistics import pstdev
from typing import Mapping

from .contracts import BehavioralState, ForcedBehaviorVector, MarketSnapshot, PsychologyVector
from .engine import GammaBehavioralEngine


@dataclass(frozen=True)
class UniverseBehavioralState:
    symbol_count: int
    evaluated_count: int
    aggregate_psychology: PsychologyVector
    aggregate_forced_behavior: ForcedBehaviorVector
    aggregate_bullish_pressure: float
    aggregate_bearish_pressure: float
    behavioral_dispersion: float
    quality_weighted_coverage: float
    top_short_squeeze: tuple[tuple[str, float], ...]
    top_long_liquidation: tuple[tuple[str, float], ...]
    top_fomo: tuple[tuple[str, float], ...]
    top_bull_exhaustion: tuple[tuple[str, float], ...]
    top_bear_exhaustion: tuple[tuple[str, float], ...]
    states: tuple[BehavioralState, ...]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["states"] = [state.to_dict() for state in self.states]
        return payload


def _weighted_mean(values: list[tuple[float, float]]) -> float:
    total_w = sum(weight for _, weight in values)
    if total_w <= 0:
        return 0.0
    return sum(value * weight for value, weight in values) / total_w


def _aggregate_dataclass(cls, states: list[BehavioralState], weights: Mapping[str, float], attr: str):
    values = {}
    for field in fields(cls):
        pairs: list[tuple[float, float]] = []
        for state in states:
            base_weight = max(0.0, float(weights.get(state.symbol, 1.0)))
            quality_weight = base_weight * state.data_quality / 100.0
            vector = getattr(state, attr)
            pairs.append((float(getattr(vector, field.name)), quality_weight))
        values[field.name] = round(_weighted_mean(pairs), 2)
    return cls(**values)


class GammaUniverseEngine:
    """Quality-weighted behavioral aggregation over a frozen symbol universe.

    Market-cap/index weights may be supplied by the caller. Gamma never fetches or silently updates
    constituent membership; point-in-time universe construction belongs upstream.
    """

    def __init__(self, engine: GammaBehavioralEngine | None = None) -> None:
        self.engine = engine or GammaBehavioralEngine()

    def evaluate(
        self,
        snapshots: list[MarketSnapshot],
        *,
        weights: Mapping[str, float] | None = None,
        top_n: int = 15,
    ) -> UniverseBehavioralState:
        supplied_weights = {k.upper(): float(v) for k, v in (weights or {}).items()}
        states: list[BehavioralState] = []
        for snapshot in snapshots:
            states.append(self.engine.evaluate(snapshot))
        if not states:
            raise ValueError("at least one snapshot is required")

        effective_weights = {
            state.symbol: supplied_weights.get(state.symbol, 1.0) for state in states
        }
        psychology = _aggregate_dataclass(
            PsychologyVector, states, effective_weights, "psychology"
        )
        forced = _aggregate_dataclass(
            ForcedBehaviorVector, states, effective_weights, "forced_behavior"
        )

        bull_pairs: list[tuple[float, float]] = []
        bear_pairs: list[tuple[float, float]] = []
        quality_pairs: list[tuple[float, float]] = []
        balances: list[float] = []
        for state in states:
            base = max(0.0, effective_weights[state.symbol])
            q = state.data_quality / 100.0
            bull_pairs.append((state.bullish_pressure, base * q))
            bear_pairs.append((state.bearish_pressure, base * q))
            quality_pairs.append((state.data_quality, base))
            balances.append(state.directional_balance)

        def top(selector) -> tuple[tuple[str, float], ...]:
            rows = sorted(
                ((state.symbol, float(selector(state))) for state in states),
                key=lambda row: row[1],
                reverse=True,
            )
            return tuple(rows[: max(1, top_n)])

        dispersion = pstdev(balances) if len(balances) > 1 else 0.0
        return UniverseBehavioralState(
            symbol_count=len(snapshots),
            evaluated_count=len(states),
            aggregate_psychology=psychology,
            aggregate_forced_behavior=forced,
            aggregate_bullish_pressure=round(_weighted_mean(bull_pairs), 2),
            aggregate_bearish_pressure=round(_weighted_mean(bear_pairs), 2),
            behavioral_dispersion=round(dispersion, 2),
            quality_weighted_coverage=round(_weighted_mean(quality_pairs), 2),
            top_short_squeeze=top(lambda s: s.forced_behavior.short_squeeze),
            top_long_liquidation=top(lambda s: s.forced_behavior.long_liquidation),
            top_fomo=top(lambda s: s.psychology.fomo),
            top_bull_exhaustion=top(lambda s: s.psychology.bull_exhaustion),
            top_bear_exhaustion=top(lambda s: s.psychology.bear_exhaustion),
            states=tuple(states),
        )
