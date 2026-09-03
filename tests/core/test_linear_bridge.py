from __future__ import annotations

import math

from core import LINEAR_PAIRS, TIMEFRAME_DISTANCE_MINUTES, build_linear_bridges, linear_bridge

EXPECTED_PAIRS = (
    ("-1m", "1m"),
    ("-5m", "5m"),
    ("-15m", "15m"),
    ("-30m", "30m"),
    ("-1h", "1h"),
    ("-4h", "4h"),
    ("-1d", "1d"),
    ("-3d", "3d"),
    ("-5d", "5d"),
)


def test_canonical_linear_pairs_are_exact() -> None:
    assert LINEAR_PAIRS == EXPECTED_PAIRS


def test_linear_bridge_recovers_prior_current_and_one_t_forward() -> None:
    bridge = linear_bridge("-5m", y_a=100.0, y_b=110.0)

    assert bridge.x_a_minutes == -5.0
    assert bridge.x_b_minutes == 0.0
    assert math.isclose(bridge.slope_per_minute, 2.0)
    assert math.isclose(bridge.intercept, 110.0)
    assert math.isclose(bridge.value_at(-5.0), 100.0)
    assert math.isclose(bridge.value_at(0.0), 110.0)
    assert math.isclose(bridge.value_at(5.0), 120.0)
    assert math.isclose(bridge.forward_one_t_value, 120.0)
    assert math.isclose(bridge.midpoint_value, 105.0)
    assert math.isclose(bridge.interpolate(0.0), 100.0)
    assert math.isclose(bridge.interpolate(0.5), 105.0)
    assert math.isclose(bridge.interpolate(1.0), 110.0)


def test_every_pair_walks_forward_one_native_t() -> None:
    for lookback, timeframe in LINEAR_PAIRS:
        bridge = linear_bridge(lookback, y_a=2.0, y_b=8.0)
        distance = TIMEFRAME_DISTANCE_MINUTES[timeframe]
        assert bridge.timeframe == timeframe
        assert bridge.x_a_minutes == -distance
        assert bridge.x_b_minutes == 0.0
        assert math.isclose(bridge.value_at(-distance), 2.0)
        assert math.isclose(bridge.value_at(0.0), 8.0)
        assert math.isclose(bridge.value_at(distance), 14.0)
        assert math.isclose(bridge.forward_one_t_value, 14.0)


def test_one_t_forward_is_two_b_minus_a() -> None:
    for lookback, _ in LINEAR_PAIRS:
        bridge = linear_bridge(lookback, y_a=97.25, y_b=101.75)
        assert math.isclose(bridge.forward_one_t_value, 2.0 * 101.75 - 97.25)


def test_daily_pairs_use_trading_session_minutes() -> None:
    assert TIMEFRAME_DISTANCE_MINUTES["1d"] == 390.0
    assert TIMEFRAME_DISTANCE_MINUTES["3d"] == 1170.0
    assert TIMEFRAME_DISTANCE_MINUTES["5d"] == 1950.0


def test_build_linear_bridges_preserves_all_nine_columns() -> None:
    lookback_values = {lookback: float(index) for index, (lookback, _) in enumerate(LINEAR_PAIRS)}
    current_values = {
        timeframe: float(index + 10) for index, (_, timeframe) in enumerate(LINEAR_PAIRS)
    }

    bridges = build_linear_bridges(lookback_values, current_values)
    assert tuple(bridges) == tuple(timeframe for _, timeframe in LINEAR_PAIRS)
    assert all(bridge is not None for bridge in bridges.values())


def test_missing_endpoint_produces_unavailable_bridge() -> None:
    lookback_values = {lookback: 1.0 for lookback, _ in LINEAR_PAIRS}
    current_values = {timeframe: 2.0 for _, timeframe in LINEAR_PAIRS}
    lookback_values["-30m"] = None

    bridges = build_linear_bridges(lookback_values, current_values)
    assert bridges["30m"] is None
