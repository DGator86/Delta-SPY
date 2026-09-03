from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

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

LOOKBACK_TO_TIMEFRAME = dict(zip(LOOKBACKS, TIMEFRAMES, strict=True))


def _bars(timeframe: str, count: int = 40) -> tuple[PriceBar, ...]:
    step = timedelta(minutes=STEP_MINUTES[timeframe])
    end = datetime(2026, 9, 3, 20, 0, tzinfo=UTC)
    start = end - step * (count - 1)
    output: list[PriceBar] = []
    price = 500.0
    for index in range(count):
        next_price = price + 0.25 + index * 0.001
        output.append(
            PriceBar(
                timestamp=start + step * index,
                open=price,
                high=max(price, next_price) + 0.05,
                low=min(price, next_price) - 0.05,
                close=next_price,
                volume=1_000_000.0 + index,
            )
        )
        price = next_price
    return tuple(output)


def _matrix() -> dict[str, tuple[PriceBar, ...]]:
    return {timeframe: _bars(timeframe) for timeframe in TIMEFRAMES}


def test_look_forward_matrix_has_first_linear_processor_across_all_columns() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )

    assert state.look_forward_columns == TIMEFRAMES
    assert tuple(state.look_forward.linear_ab_1t) == TIMEFRAMES
    assert state.engine_version == "alpha-0.5.0"


def test_linear_ab_1t_walks_prior_to_current_line_forward_one_native_t() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )

    for lookback, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        cell = state.look_forward.linear_ab_1t[timeframe]
        point_a = state.lookback.spot[lookback]
        point_b = state.current.spot[timeframe]

        assert cell.lookback == lookback
        assert cell.timeframe == timeframe
        assert cell.point_a == point_a
        assert cell.point_b == point_b
        assert math.isclose(cell.observed_delta, point_b - point_a)
        assert math.isclose(cell.projected_spot, 2.0 * point_b - point_a)


def test_linear_forward_is_not_a_trade_or_strategy_output() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )
    payload = state.as_dict()["look_forward"]
    serialized_keys = str(payload.keys()).lower() + str(payload).lower()
    for prohibited in ("buy", "sell", "trade", "strategy", "order", "position_size", "broker"):
        assert prohibited not in serialized_keys
