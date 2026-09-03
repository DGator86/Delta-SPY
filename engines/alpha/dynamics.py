from __future__ import annotations

from dataclasses import dataclass

from core.timeframes import LOOKBACK_TO_TIMEFRAME, LOOKBACKS, TIMEFRAMES, Lookback, Timeframe

from .contracts import (
    AlphaInput,
    ConfidenceChangeState,
    ForecastDriftState,
    PersistenceState,
    RegimeState,
    RegimeTransitionState,
    StateAccelerationState,
    StateVelocityState,
)
from .engine import _cross_section, _forecast_distribution, _regime_state


@dataclass(frozen=True, slots=True)
class _Snapshot:
    regime: RegimeState
    expected_return: float | None
    probability_up: float | None
    standard_deviation: float | None
    median: float | None
    expected_mfe: float | None
    expected_mae: float | None
    dispersion: float | None


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _second_difference(
    current: float | None,
    previous: float | None,
    previous_previous: float | None,
) -> float | None:
    latest = _delta(current, previous)
    prior = _delta(previous, previous_previous)
    return _delta(latest, prior)


def _trim_constituents(
    constituents: dict[str, tuple[float, ...]],
    offset: int,
) -> dict[str, tuple[float, ...]]:
    if offset <= 0:
        return constituents
    return {
        symbol: closes[:-offset]
        for symbol, closes in constituents.items()
        if len(closes) > offset
    }


def _snapshot(
    input_state: AlphaInput,
    timeframe: Timeframe,
    offset: int,
) -> _Snapshot | None:
    all_bars = input_state.spy_bars[timeframe]
    if len(all_bars) <= offset:
        return None
    bars = all_bars if offset == 0 else all_bars[:-offset]
    if not bars:
        return None
    constituents = _trim_constituents(
        input_state.constituent_closes.get(timeframe, {}),
        offset,
    )
    regime = _regime_state(timeframe, bars)
    forecast = _forecast_distribution(timeframe, bars, input_state.sample_lookback)
    cross = _cross_section(bars, constituents)
    return _Snapshot(
        regime=regime,
        expected_return=forecast.expected_return,
        probability_up=forecast.probability_up,
        standard_deviation=forecast.standard_deviation,
        median=forecast.median,
        expected_mfe=forecast.expected_mfe,
        expected_mae=forecast.expected_mae,
        dispersion=cross.latest_return_dispersion,
    )


def _velocity(current: _Snapshot | None, previous: _Snapshot | None) -> StateVelocityState:
    return StateVelocityState(
        trend_score_delta=_delta(
            current.regime.trend_score if current else None,
            previous.regime.trend_score if previous else None,
        ),
        realized_volatility_delta=_delta(
            current.regime.realized_volatility_annualized if current else None,
            previous.regime.realized_volatility_annualized if previous else None,
        ),
        expected_return_delta=_delta(
            current.expected_return if current else None,
            previous.expected_return if previous else None,
        ),
        probability_up_delta=_delta(
            current.probability_up if current else None,
            previous.probability_up if previous else None,
        ),
        dispersion_delta=_delta(
            current.dispersion if current else None,
            previous.dispersion if previous else None,
        ),
    )


def _acceleration(
    current: _Snapshot | None,
    previous: _Snapshot | None,
    previous_previous: _Snapshot | None,
) -> StateAccelerationState:
    return StateAccelerationState(
        trend_score_second_difference=_second_difference(
            current.regime.trend_score if current else None,
            previous.regime.trend_score if previous else None,
            previous_previous.regime.trend_score if previous_previous else None,
        ),
        realized_volatility_second_difference=_second_difference(
            current.regime.realized_volatility_annualized if current else None,
            previous.regime.realized_volatility_annualized if previous else None,
            previous_previous.regime.realized_volatility_annualized
            if previous_previous
            else None,
        ),
        expected_return_second_difference=_second_difference(
            current.expected_return if current else None,
            previous.expected_return if previous else None,
            previous_previous.expected_return if previous_previous else None,
        ),
        probability_up_second_difference=_second_difference(
            current.probability_up if current else None,
            previous.probability_up if previous else None,
            previous_previous.probability_up if previous_previous else None,
        ),
        dispersion_second_difference=_second_difference(
            current.dispersion if current else None,
            previous.dispersion if previous else None,
            previous_previous.dispersion if previous_previous else None,
        ),
    )


def _transition(
    current: _Snapshot | None,
    previous: _Snapshot | None,
) -> RegimeTransitionState:
    current_regime = current.regime if current else None
    previous_regime = previous.regime if previous else None
    from_trend = previous_regime.trend if previous_regime else None
    to_trend = current_regime.trend if current_regime else None
    from_volatility = previous_regime.volatility if previous_regime else None
    to_volatility = current_regime.volatility if current_regime else None
    return RegimeTransitionState(
        from_trend=from_trend,
        to_trend=to_trend,
        from_volatility=from_volatility,
        to_volatility=to_volatility,
        trend_changed=(
            from_trend != to_trend
            if from_trend is not None and to_trend is not None
            else None
        ),
        volatility_changed=(
            from_volatility != to_volatility
            if from_volatility is not None and to_volatility is not None
            else None
        ),
    )


def _forecast_drift(
    current: _Snapshot | None,
    previous: _Snapshot | None,
) -> ForecastDriftState:
    return ForecastDriftState(
        expected_return_delta=_delta(
            current.expected_return if current else None,
            previous.expected_return if previous else None,
        ),
        probability_up_delta=_delta(
            current.probability_up if current else None,
            previous.probability_up if previous else None,
        ),
        standard_deviation_delta=_delta(
            current.standard_deviation if current else None,
            previous.standard_deviation if previous else None,
        ),
        median_delta=_delta(
            current.median if current else None,
            previous.median if previous else None,
        ),
        expected_mfe_delta=_delta(
            current.expected_mfe if current else None,
            previous.expected_mfe if previous else None,
        ),
        expected_mae_delta=_delta(
            current.expected_mae if current else None,
            previous.expected_mae if previous else None,
        ),
    )


def _confidence_change(
    current: _Snapshot | None,
    previous: _Snapshot | None,
) -> ConfidenceChangeState:
    current_confidence = current.regime.confidence if current else None
    previous_confidence = previous.regime.confidence if previous else None
    return ConfidenceChangeState(
        previous_confidence=previous_confidence,
        current_confidence=current_confidence,
        delta=_delta(current_confidence, previous_confidence),
    )


def _persistence(
    input_state: AlphaInput,
    timeframe: Timeframe,
    base_offset: int,
    max_streak: int = 20,
) -> PersistenceState:
    base = _snapshot(input_state, timeframe, base_offset)
    if base is None:
        return PersistenceState(0, 0, 0, False)
    if base.regime.trend == "UNKNOWN" and base.regime.volatility == "UNKNOWN":
        return PersistenceState(0, 0, 0, False)

    trend_streak = 1 if base.regime.trend != "UNKNOWN" else 0
    volatility_streak = 1 if base.regime.volatility != "UNKNOWN" else 0
    joint_streak = 1 if trend_streak and volatility_streak else 0

    for step in range(1, max_streak):
        prior = _snapshot(input_state, timeframe, base_offset + step)
        if prior is None:
            break
        if trend_streak == step and prior.regime.trend == base.regime.trend:
            trend_streak += 1
        if volatility_streak == step and prior.regime.volatility == base.regime.volatility:
            volatility_streak += 1
        if (
            joint_streak == step
            and prior.regime.trend == base.regime.trend
            and prior.regime.volatility == base.regime.volatility
        ):
            joint_streak += 1

    return PersistenceState(
        trend_streak_bars=trend_streak,
        volatility_streak_bars=volatility_streak,
        joint_streak_bars=joint_streak,
        joint_persistent=joint_streak >= 2,
    )


def _dynamics_for(
    input_state: AlphaInput,
    timeframe: Timeframe,
    base_offset: int,
) -> tuple[
    StateVelocityState,
    StateAccelerationState,
    PersistenceState,
    RegimeTransitionState,
    ForecastDriftState,
    ConfidenceChangeState,
]:
    current = _snapshot(input_state, timeframe, base_offset)
    previous = _snapshot(input_state, timeframe, base_offset + 1)
    previous_previous = _snapshot(input_state, timeframe, base_offset + 2)
    return (
        _velocity(current, previous),
        _acceleration(current, previous, previous_previous),
        _persistence(input_state, timeframe, base_offset),
        _transition(current, previous),
        _forecast_drift(current, previous),
        _confidence_change(current, previous),
    )


def build_current_dynamics(
    input_state: AlphaInput,
) -> tuple[
    dict[Timeframe, StateVelocityState],
    dict[Timeframe, StateAccelerationState],
    dict[Timeframe, PersistenceState],
    dict[Timeframe, RegimeTransitionState],
    dict[Timeframe, ForecastDriftState],
    dict[Timeframe, ConfidenceChangeState],
]:
    velocity: dict[Timeframe, StateVelocityState] = {}
    acceleration: dict[Timeframe, StateAccelerationState] = {}
    persistence: dict[Timeframe, PersistenceState] = {}
    transition: dict[Timeframe, RegimeTransitionState] = {}
    forecast_drift: dict[Timeframe, ForecastDriftState] = {}
    confidence_change: dict[Timeframe, ConfidenceChangeState] = {}
    for timeframe in TIMEFRAMES:
        values = _dynamics_for(input_state, timeframe, 0)
        velocity[timeframe], acceleration[timeframe], persistence[timeframe] = values[:3]
        transition[timeframe], forecast_drift[timeframe], confidence_change[timeframe] = values[3:]
    return velocity, acceleration, persistence, transition, forecast_drift, confidence_change


def build_lookback_dynamics(
    input_state: AlphaInput,
) -> tuple[
    dict[Lookback, StateVelocityState],
    dict[Lookback, StateAccelerationState],
    dict[Lookback, PersistenceState],
    dict[Lookback, RegimeTransitionState],
    dict[Lookback, ForecastDriftState],
    dict[Lookback, ConfidenceChangeState],
]:
    velocity: dict[Lookback, StateVelocityState] = {}
    acceleration: dict[Lookback, StateAccelerationState] = {}
    persistence: dict[Lookback, PersistenceState] = {}
    transition: dict[Lookback, RegimeTransitionState] = {}
    forecast_drift: dict[Lookback, ForecastDriftState] = {}
    confidence_change: dict[Lookback, ConfidenceChangeState] = {}
    for lookback in LOOKBACKS:
        timeframe = LOOKBACK_TO_TIMEFRAME[lookback]
        values = _dynamics_for(input_state, timeframe, 1)
        velocity[lookback], acceleration[lookback], persistence[lookback] = values[:3]
        transition[lookback], forecast_drift[lookback], confidence_change[lookback] = values[3:]
    return velocity, acceleration, persistence, transition, forecast_drift, confidence_change
