from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from engines.alpha import LOOKBACKS, TIMEFRAMES, AlphaEngine, AlphaInput, PriceBar

STEP_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "3d": 4320,
    "5d": 7200,
}

LOOKBACK_TO_TIMEFRAME = {
    "-1m": "1m",
    "-5m": "5m",
    "-15m": "15m",
    "-30m": "30m",
    "-1h": "1h",
    "-4h": "4h",
    "-1d": "1d",
    "-3d": "3d",
    "-5d": "5d",
}


def _bars(timeframe: str, count: int = 180) -> tuple[PriceBar, ...]:
    step = timedelta(minutes=STEP_MINUTES[timeframe])
    end = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)
    start = end - step * (count - 1)
    price = 640.0
    output: list[PriceBar] = []
    for index in range(count):
        drift = 0.00018 + math.sin(index / 7.0) * 0.00004
        next_price = price * (1.0 + drift)
        high = max(price, next_price) * 1.00015
        low = min(price, next_price) * 0.99985
        output.append(
            PriceBar(
                timestamp=start + step * index,
                open=price,
                high=high,
                low=low,
                close=next_price,
                volume=1_000_000 + index,
            )
        )
        price = next_price
    return tuple(output)


def _matrix(count: int = 180) -> dict[str, tuple[PriceBar, ...]]:
    return {timeframe: _bars(timeframe, count) for timeframe in TIMEFRAMES}


def _constituents(
    matrix: dict[str, tuple[PriceBar, ...]],
) -> dict[str, dict[str, tuple[float, ...]]]:
    output: dict[str, dict[str, tuple[float, ...]]] = {}
    for timeframe, bars in matrix.items():
        spy = [bar.close for bar in bars]
        output[timeframe] = {
            "AAA": tuple(value * (1.0 + 0.00002 * math.sin(i / 5.0)) for i, value in enumerate(spy)),
            "BBB": tuple(value * (1.0 - 0.00003 * math.cos(i / 9.0)) for i, value in enumerate(spy)),
            "CCC": tuple(value * (1.0 + 0.00001 * math.sin(i / 3.0)) for i, value in enumerate(spy)),
        }
    return output


def _assert_columns(mapping: dict, expected: tuple[str, ...]) -> None:
    assert tuple(mapping) == expected


def _current_rows(state) -> tuple[dict, ...]:
    return (
        state.current.spot,
        state.current.observed_return,
        state.current.regime,
        state.current.cross_section,
        state.current.forecast,
        state.current.quality,
        state.current.state_velocity,
        state.current.state_acceleration,
        state.current.persistence,
        state.current.regime_transition,
        state.current.forecast_drift,
        state.current.confidence_change,
    )


def _lookback_rows(state) -> tuple[dict, ...]:
    return (
        state.lookback.spot,
        state.lookback.observed_return,
        state.lookback.regime,
        state.lookback.cross_section,
        state.lookback.forecast,
        state.lookback.quality,
        state.lookback.state_velocity,
        state.lookback.state_acceleration,
        state.lookback.persistence,
        state.lookback.regime_transition,
        state.lookback.forecast_drift,
        state.lookback.confidence_change,
    )


def test_alpha_is_deterministic_and_emits_current_and_lookback_matrices() -> None:
    matrix = _matrix()
    input_state = AlphaInput(
        as_of=matrix["1m"][-1].timestamp,
        spy_bars=matrix,
        constituent_closes=_constituents(matrix),
    )
    engine = AlphaEngine()
    first = engine.process(input_state)
    second = engine.process(input_state)

    assert first == second
    assert first.engine == "ALPHA"
    assert first.engine_version == "alpha-0.4.0"
    assert first.current_columns == TIMEFRAMES
    assert first.lookback_columns == LOOKBACKS

    for row in _current_rows(first):
        _assert_columns(row, TIMEFRAMES)
    for row in _lookback_rows(first):
        _assert_columns(row, LOOKBACKS)

    for timeframe in TIMEFRAMES:
        assert first.current.spot[timeframe] == matrix[timeframe][-1].close
        assert first.current.regime[timeframe].trend == "UP"
        assert first.current.cross_section[timeframe].symbol_count == 3
        assert first.current.forecast[timeframe].timeframe == timeframe
        assert first.current.forecast[timeframe].samples == 179
        assert first.current.forecast[timeframe].probability_up is not None
        assert first.current.forecast[timeframe].probability_up > 0.9
        assert first.current.persistence[timeframe].trend_streak_bars >= 1

    for lookback in LOOKBACKS:
        timeframe = LOOKBACK_TO_TIMEFRAME[lookback]
        assert first.lookback.spot[lookback] == matrix[timeframe][-2].close
        assert first.lookback.regime[lookback].trend == "UP"
        assert first.lookback.cross_section[lookback].symbol_count == 3
        assert first.lookback.forecast[lookback].timeframe == timeframe
        assert first.lookback.forecast[lookback].samples == 178
        assert first.lookback.persistence[lookback].trend_streak_bars >= 1


def test_temporal_rows_are_causal_first_and_second_differences() -> None:
    matrix = _matrix(100)
    constituents = _constituents(matrix)
    state = AlphaEngine().process(
        AlphaInput(
            as_of=matrix["1m"][-1].timestamp,
            spy_bars=matrix,
            constituent_closes=constituents,
        )
    )

    timeframe = "15m"
    lookback = "-15m"
    current_forecast = state.current.forecast[timeframe]
    prior_forecast = state.lookback.forecast[lookback]
    drift = state.current.forecast_drift[timeframe]
    velocity = state.current.state_velocity[timeframe]

    assert drift.expected_return_delta == pytest.approx(
        current_forecast.expected_return - prior_forecast.expected_return
    )
    assert drift.probability_up_delta == pytest.approx(
        current_forecast.probability_up - prior_forecast.probability_up
    )
    assert velocity.expected_return_delta == pytest.approx(drift.expected_return_delta)
    assert velocity.probability_up_delta == pytest.approx(drift.probability_up_delta)

    current_confidence = state.current.regime[timeframe].confidence
    prior_confidence = state.lookback.regime[lookback].confidence
    confidence_change = state.current.confidence_change[timeframe]
    assert confidence_change.previous_confidence == prior_confidence
    assert confidence_change.current_confidence == current_confidence
    assert confidence_change.delta == pytest.approx(current_confidence - prior_confidence)

    transition = state.current.regime_transition[timeframe]
    assert transition.from_trend == state.lookback.regime[lookback].trend
    assert transition.to_trend == state.current.regime[timeframe].trend
    assert transition.trend_changed is False

    # Current acceleration is Δ(current-prior) - Δ(prior-prior_prior).
    acceleration = state.current.state_acceleration[timeframe]
    previous_velocity = state.lookback.state_velocity[lookback]
    assert acceleration.expected_return_second_difference == pytest.approx(
        velocity.expected_return_delta - previous_velocity.expected_return_delta
    )


def test_every_forecast_cell_uses_completed_native_timeframe_paths() -> None:
    matrix = _matrix(80)
    state = AlphaEngine().process(
        AlphaInput(
            as_of=matrix["1m"][-1].timestamp,
            spy_bars=matrix,
        )
    )

    for timeframe in TIMEFRAMES:
        forecast = state.current.forecast[timeframe]
        assert forecast.samples == 79
        assert forecast.expected_mfe is not None
        assert forecast.expected_mae is not None
        assert forecast.expected_mfe >= forecast.expected_return
        assert forecast.expected_mae <= 0.0

    for lookback in LOOKBACKS:
        forecast = state.lookback.forecast[lookback]
        assert forecast.samples == 78
        assert forecast.expected_mfe is not None
        assert forecast.expected_mae is not None


def test_lookback_is_prior_native_state_not_wall_clock_subtraction() -> None:
    matrix = _matrix(40)
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )

    assert state.lookback.spot["-1m"] == matrix["1m"][-2].close
    assert state.lookback.spot["-5m"] == matrix["5m"][-2].close
    assert state.lookback.spot["-1d"] == matrix["1d"][-2].close
    assert state.lookback.spot["-3d"] == matrix["3d"][-2].close
    assert state.lookback.spot["-5d"] == matrix["5d"][-2].close


def test_alpha_rejects_missing_timeframe_column() -> None:
    matrix = _matrix(40)
    matrix.pop("3d")
    with pytest.raises(ValueError, match="must contain exactly"):
        AlphaEngine().process(
            AlphaInput(
                as_of=datetime(2026, 9, 3, 20, 0, tzinfo=UTC),
                spy_bars=matrix,
            )
        )


def test_alpha_requires_prior_bar_for_lookback_matrix() -> None:
    matrix = _matrix(40)
    matrix["5d"] = matrix["5d"][-1:]
    with pytest.raises(ValueError, match="requires at least two bars for lookback state"):
        AlphaEngine().process(
            AlphaInput(
                as_of=datetime(2026, 9, 3, 20, 0, tzinfo=UTC),
                spy_bars=matrix,
            )
        )


def test_insufficient_history_keeps_dynamics_cells_without_inventing_values() -> None:
    matrix = _matrix(2)
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )

    for timeframe in TIMEFRAMES:
        acceleration = state.current.state_acceleration[timeframe]
        assert acceleration.expected_return_second_difference is None
    for lookback in LOOKBACKS:
        velocity = state.lookback.state_velocity[lookback]
        assert velocity.expected_return_delta is None


def test_alpha_rejects_future_information_in_any_column() -> None:
    matrix = _matrix(40)
    as_of = matrix["1m"][-1].timestamp
    bad = list(matrix["1h"])
    last = bad[-1]
    bad[-1] = PriceBar(
        timestamp=as_of + timedelta(hours=1),
        open=last.open,
        high=last.high,
        low=last.low,
        close=last.close,
        volume=last.volume,
    )
    matrix["1h"] = tuple(bad)

    with pytest.raises(ValueError, match="after AlphaInput.as_of"):
        AlphaEngine().process(AlphaInput(as_of=as_of, spy_bars=matrix))


def test_alpha_handles_missing_cross_section_without_inventing_it() -> None:
    matrix = _matrix(60)
    state = AlphaEngine().process(
        AlphaInput(
            as_of=matrix["1m"][-1].timestamp,
            spy_bars=matrix,
        )
    )

    for timeframe in TIMEFRAMES:
        cross = state.current.cross_section[timeframe]
        assert cross.symbol_count == 0
        assert cross.mean_correlation_to_spy is None
        assert "cross_section_unavailable" in state.current.quality[timeframe].warnings

    for lookback in LOOKBACKS:
        cross = state.lookback.cross_section[lookback]
        assert cross.symbol_count == 0
        assert cross.mean_correlation_to_spy is None
        assert "cross_section_unavailable" in state.lookback.quality[lookback].warnings
