from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from engines.alpha import AlphaEngine, AlphaInput, PriceBar


def _bars(count: int = 180) -> tuple[PriceBar, ...]:
    start = datetime(2026, 9, 3, 13, 30, tzinfo=UTC)
    price = 640.0
    output: list[PriceBar] = []
    for index in range(count):
        drift = 0.00018 + math.sin(index / 7.0) * 0.00004
        next_price = price * (1.0 + drift)
        high = max(price, next_price) * 1.00015
        low = min(price, next_price) * 0.99985
        output.append(
            PriceBar(
                timestamp=start + timedelta(minutes=index),
                open=price,
                high=high,
                low=low,
                close=next_price,
                volume=1_000_000 + index,
            )
        )
        price = next_price
    return tuple(output)


def _constituents(bars: tuple[PriceBar, ...]) -> dict[str, tuple[float, ...]]:
    spy = [bar.close for bar in bars]
    return {
        "AAA": tuple(value * (1.0 + 0.00002 * math.sin(i / 5.0)) for i, value in enumerate(spy)),
        "BBB": tuple(value * (1.0 - 0.00003 * math.cos(i / 9.0)) for i, value in enumerate(spy)),
        "CCC": tuple(value * (1.0 + 0.00001 * math.sin(i / 3.0)) for i, value in enumerate(spy)),
    }


def test_alpha_is_deterministic_and_emits_statistical_state() -> None:
    bars = _bars()
    input_state = AlphaInput(
        as_of=bars[-1].timestamp,
        spy_bars=bars,
        constituent_closes=_constituents(bars),
    )
    engine = AlphaEngine()
    first = engine.process(input_state)
    second = engine.process(input_state)

    assert first == second
    assert first.engine == "ALPHA"
    assert first.spot == bars[-1].close
    assert first.regime.trend == "UP"
    assert first.cross_section.symbol_count == 3
    assert [forecast.horizon_minutes for forecast in first.forecasts] == [5, 15, 30]
    assert all(forecast.samples > 0 for forecast in first.forecasts)
    assert all(
        forecast.probability_up is not None and forecast.probability_up > 0.9
        for forecast in first.forecasts
    )


def test_forecasts_use_completed_historical_paths() -> None:
    bars = _bars(80)
    state = AlphaEngine().process(AlphaInput(as_of=bars[-1].timestamp, spy_bars=bars))
    forecasts = {item.horizon_minutes: item for item in state.forecasts}

    assert forecasts[5].samples == 75
    assert forecasts[15].samples == 65
    assert forecasts[30].samples == 50
    assert forecasts[15].expected_mfe is not None
    assert forecasts[15].expected_mae is not None
    assert forecasts[15].expected_mfe >= forecasts[15].expected_return
    assert forecasts[15].expected_mae <= 0.0


def test_alpha_rejects_future_information() -> None:
    bars = _bars(40)
    with pytest.raises(ValueError, match="after AlphaInput.as_of"):
        AlphaEngine().process(
            AlphaInput(
                as_of=bars[-2].timestamp,
                spy_bars=bars,
            )
        )


def test_alpha_handles_missing_cross_section_without_inventing_it() -> None:
    bars = _bars(60)
    state = AlphaEngine().process(AlphaInput(as_of=bars[-1].timestamp, spy_bars=bars))

    assert state.cross_section.symbol_count == 0
    assert state.cross_section.mean_correlation_to_spy is None
    assert "cross_section_unavailable" in state.quality.warnings
