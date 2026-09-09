from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from typing import Mapping

from .contracts import BehavioralState, MarketSnapshot, PsychologyVector
from .features import extract_features
from .states import (
    build_evidence,
    infer_forced_behavior,
    infer_psychology,
    infer_regimes,
    pressure_scores,
)

ENGINE_VERSION = "gamma-behavioral-v1.0.0"
SCHEMA_VERSION = "gamma-state-v1"


class GammaBehavioralEngine:
    """Independent behavioral state estimator.

    Gamma has no strategy-selection, sizing, broker, order or execution authority. Its outputs are
    state estimates and evidence for a downstream convergence engine such as Delta.
    """

    def __init__(self, *, risk_free_rate: float = 0.04, remember_state: bool = True) -> None:
        self.risk_free_rate = risk_free_rate
        self.remember_state = remember_state
        self._last_state: dict[str, BehavioralState] = {}

    def reset(self, symbol: str | None = None) -> None:
        if symbol is None:
            self._last_state.clear()
        else:
            self._last_state.pop(symbol.upper(), None)

    def _data_quality(self, snapshot: MarketSnapshot, features: dict[str, object]) -> tuple[float, list[str]]:
        warnings: list[str] = []
        weighted: list[tuple[bool, float]] = []

        weighted.append((len(snapshot.bars) >= 20, 0.20))
        weighted.append((features.get("rvol") is not None and features.get("atr14") is not None, 0.10))
        weighted.append((features.get("cvd_change_5") is not None, 0.15))
        weighted.append((bool(snapshot.options), 0.15))
        weighted.append((features.get("breadth") is not None, 0.10))
        weighted.append((features.get("vix") is not None, 0.10))
        weighted.append((features.get("short_interest_pct") is not None or features.get("long_crowding_external") is not None, 0.08))
        weighted.append((features.get("anchor_distance_atr") is not None, 0.05))
        weighted.append((features.get("attention_z") is not None or features.get("news_reaction_residual") is not None, 0.04))
        weighted.append((snapshot.source_latency_ms is None or snapshot.source_latency_ms <= 5_000, 0.03))

        quality = sum(weight for present, weight in weighted if present) / sum(weight for _, weight in weighted)

        if len(snapshot.bars) < 20:
            warnings.append("BAR_HISTORY_THIN: fewer than 20 bars; RVOL/ATR context is less stable.")
        if features.get("cvd_change_5") is None:
            warnings.append("FLOW_PROXY_MISSING: no aggressive buy/sell volume; CVD states are disabled.")
        if not snapshot.options:
            warnings.append("OPTIONS_MISSING: skew, walls, GEX/vanna/charm proxies are unavailable.")
        else:
            warnings.append("DEALER_GAMMA_IS_PROXY: OI does not reveal actual dealer inventory; preserve proxy labeling.")
        if features.get("breadth") is None:
            warnings.append("BREADTH_MISSING: cross-sectional confirmation is unavailable.")
        if features.get("vix") is None:
            warnings.append("VOLATILITY_CONTEXT_MISSING: VIX-based fear/uncertainty evidence is unavailable.")
        if features.get("short_interest_pct") is None:
            warnings.append("SHORT_INTEREST_MISSING: squeeze-fuel estimate relies on other inputs.")
        if snapshot.source_latency_ms is not None and snapshot.source_latency_ms > 5_000:
            warnings.append(f"STALE_SOURCE: reported source latency is {snapshot.source_latency_ms:.0f} ms.")
        return round(100.0 * quality, 2), warnings

    @staticmethod
    def _transition_velocity(current: PsychologyVector, previous: BehavioralState | None, ts: datetime) -> dict[str, float]:
        if previous is None or ts <= previous.ts:
            return {field.name: 0.0 for field in fields(PsychologyVector)}
        minutes = max((ts - previous.ts).total_seconds() / 60.0, 1.0 / 60.0)
        out: dict[str, float] = {}
        for field in fields(PsychologyVector):
            now = float(getattr(current, field.name))
            before = float(getattr(previous.psychology, field.name))
            out[field.name] = round((now - before) / minutes, 4)
        return out

    @staticmethod
    def _confidence(
        regime_scores: Mapping[str, float],
        psychology: PsychologyVector,
        data_quality: float,
    ) -> float:
        ordered = sorted(regime_scores.values(), reverse=True)
        top = ordered[0] if ordered else 0.0
        second = ordered[1] if len(ordered) > 1 else 0.0
        margin = max(0.0, top - second)
        separation = min(1.0, margin / 35.0)
        strength = min(1.0, top / 85.0)
        disagreement_penalty = 1.0 - 0.40 * (psychology.disagreement / 100.0)
        score = (data_quality / 100.0) * (0.35 + 0.35 * strength + 0.30 * separation) * disagreement_penalty
        return round(max(0.0, min(100.0, score * 100.0)), 2)

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        previous_state: BehavioralState | None = None,
    ) -> BehavioralState:
        if snapshot.bar_minutes <= 0:
            raise ValueError("bar_minutes must be positive")
        if len(snapshot.bars) < 2:
            raise ValueError("at least two bars are required")
        symbol = snapshot.symbol.upper()
        previous = previous_state or self._last_state.get(symbol)

        features, gamma = extract_features(snapshot, rate=self.risk_free_rate)
        psychology = infer_psychology(features)
        regime_scores = infer_regimes(features, psychology)
        forced = infer_forced_behavior(features, psychology, regime_scores)
        bullish, bearish = pressure_scores(features, psychology, forced)
        quality, warnings = self._data_quality(snapshot, features)

        ordered = sorted(regime_scores.items(), key=lambda item: item[1], reverse=True)
        primary = ordered[0][0] if ordered else "unknown"
        secondary = ordered[1][0] if len(ordered) > 1 else None
        confidence = self._confidence(regime_scores, psychology, quality)
        velocity = self._transition_velocity(psychology, previous, snapshot.ts)

        # These are evidence-weighted directional pressure scores, NOT calibrated return probabilities.
        balance = round(bullish - bearish, 2)
        warnings.append("SCORES_NOT_PROBABILITIES: regime/pressure/forced-behavior values require calibration before probabilistic interpretation.")

        state = BehavioralState(
            schema_version=SCHEMA_VERSION,
            engine_version=ENGINE_VERSION,
            symbol=symbol,
            ts=snapshot.ts,
            psychology=psychology,
            forced_behavior=forced,
            gamma=gamma,
            regime_scores=regime_scores,
            primary_regime=primary,
            secondary_regime=secondary,
            bullish_pressure=bullish,
            bearish_pressure=bearish,
            directional_balance=balance,
            state_confidence=confidence,
            data_quality=quality,
            transition_velocity=velocity,
            features=features,
            evidence=build_evidence(features),
            warnings=tuple(warnings),
            trading_authority=False,
            execution_authority=False,
        )
        if self.remember_state:
            self._last_state[symbol] = state
        return state

    def evaluate_many(self, snapshots: list[MarketSnapshot]) -> list[BehavioralState]:
        return [self.evaluate(snapshot) for snapshot in snapshots]

    def evaluate_horizons(self, snapshots: Mapping[str, MarketSnapshot]) -> dict[str, BehavioralState]:
        """Evaluate independently normalized snapshots such as 5m/15m/30m/60m/EOD.

        Gamma does not silently resample or leak future observations between horizons. The caller owns
        point-in-time horizon construction and passes each frozen snapshot explicitly.
        """
        return {horizon: self.evaluate(snapshot) for horizon, snapshot in snapshots.items()}
