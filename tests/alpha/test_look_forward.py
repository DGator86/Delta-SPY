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
    assert state.engine_version == "alpha-0.6.0"


def test_linear_ab_1t_walks_every_numeric_temporal_component_forward_one_t() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )

    required_paths = {
        "spot",
        "observed_return",
        "regime.trend_score",
        "regime.realized_volatility_annualized",
        "regime.volatility_percentile",
        "regime.confidence",
        "forecast.expected_return",
        "forecast.probability_up",
        "forecast.standard_deviation",
        "quality.completeness",
        "state_velocity.expected_return_delta",
        "state_acceleration.expected_return_second_difference",
        "persistence.trend_streak_bars",
        "forecast_drift.expected_return_delta",
        "confidence_change.delta",
    }

    for lookback, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        cell = state.look_forward.linear_ab_1t[timeframe]
        assert cell.lookback == lookback
        assert cell.timeframe == timeframe
        assert required_paths <= set(cell.components)

        spot = cell.components["spot"]
        point_a = state.lookback.spot[lookback]
        point_b = state.current.spot[timeframe]
        assert spot.point_a == point_a
        assert spot.point_b == point_b
        assert math.isclose(spot.observed_delta, point_b - point_a)
        assert math.isclose(spot.projected_value, 2.0 * point_b - point_a)
        assert math.isclose(cell.projected_spot, spot.projected_value)

        for component in cell.components.values():
            if component.point_a is None or component.point_b is None:
                assert component.projected_value is None
                continue
            assert component.observed_delta == component.point_b - component.point_a
            assert component.projected_value == 2.0 * component.point_b - component.point_a


def test_categorical_temporal_items_are_explicitly_non_projectable() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )
    cell = state.look_forward.linear_ab_1t["15m"]

    assert "regime.trend" in cell.non_projectable_paths
    assert "regime.volatility" in cell.non_projectable_paths
    assert "persistence.joint_persistent" in cell.non_projectable_paths
    assert "quality.warnings" in cell.non_projectable_paths
    assert "regime_transition.trend_changed" in cell.non_projectable_paths


def test_linear_forward_is_not_a_trade_or_strategy_output() -> None:
    matrix = _matrix()
    state = AlphaEngine().process(
        AlphaInput(as_of=matrix["1m"][-1].timestamp, spy_bars=matrix)
    )
    payload = state.as_dict()["look_forward"]
    serialized_keys = str(payload.keys()).lower() + str(payload).lower()
    for prohibited in ("buy", "sell", "trade", "strategy", "order", "position_size", "broker"):
        assert prohibited not in serialized_keys
