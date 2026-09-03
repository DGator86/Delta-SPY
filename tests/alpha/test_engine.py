from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from engines.alpha import TIMEFRAMES, AlphaEngine, AlphaInput, PriceBar

STEP_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
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


def _assert_columns(mapping: dict) -> None:
    assert tuple(mapping) == TIMEFRAMES


def test_alpha_is_deterministic_and_emits_seven_column_matrix() -> None:
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
    assert first.columns == TIMEFRAMES

    _assert_columns(first.rows.spot)
    _assert_columns(first.rows.observed_return)
    _assert_columns(first.rows.regime)
    _assert_columns(first.rows.cross_section)
    _assert_columns(first.rows.forecast)
    _assert_columns(first.rows.quality)

    for timeframe in TIMEFRAMES:
        assert first.rows.spot[timeframe] == matrix[timeframe][-1].close
        assert first.rows.regime[timeframe].trend == "UP"
        assert first.rows.cross_section[timeframe].symbol_count == 3
        assert first.rows.forecast[timeframe].timeframe == timeframe
        assert first.rows.forecast[timeframe].samples == 179
        assert first.rows.forecast[timeframe].probability_up is not None
        assert first.rows.forecast[timeframe].probability_up > 0.9


def test_every_forecast_column_uses_completed_native_timeframe_paths() -> None:
    matrix = _matrix(80)
    state = AlphaEngine().process(
        AlphaInput(
            as_of=matrix["1m"][-1].timestamp,
            spy_bars=matrix,
        )
    )

    for timeframe in TIMEFRAMES:
        forecast = state.rows.forecast[timeframe]
        assert forecast.samples == 79
        assert forecast.expected_mfe is not None
        assert forecast.expected_mae is not None
        assert forecast.expected_mfe >= forecast.expected_return
        assert forecast.expected_mae <= 0.0


def test_alpha_rejects_missing_timeframe_column() -> None:
    matrix = _matrix(40)
    matrix.pop("4h")
    with pytest.raises(ValueError, match="must contain exactly"):
        AlphaEngine().process(
            AlphaInput(
                as_of=datetime(2026, 9, 3, 20, 0, tzinfo=UTC),
                spy_bars=matrix,
            )
        )


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
        cross = state.rows.cross_section[timeframe]
        assert cross.symbol_count == 0
        assert cross.mean_correlation_to_spy is None
        assert "cross_section_unavailable" in state.rows.quality[timeframe].warnings
