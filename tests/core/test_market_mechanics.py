from __future__ import annotations

import math

from core.market_mechanics import (
    ALL_INERTIA_MATRIX_ROWS,
    INERTIA_ROWS,
    RESPONSE_ROWS,
    build_inertia_matrices,
    mechanics_windows,
)
from core.timeframes import LOOKBACKS, TIMEFRAMES


def _responses(
    *,
    lookback_base: float,
    current_base: float,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    lookback: dict[str, dict[str, float]] = {}
    current: dict[str, dict[str, float]] = {}
    for row_index, row in enumerate(RESPONSE_ROWS):
        lookback[row] = {
            column: lookback_base + 0.01 * row_index + 0.001 * column_index
            for column_index, column in enumerate(LOOKBACKS)
        }
        current[row] = {
            column: current_base + 0.01 * row_index + 0.001 * column_index
            for column_index, column in enumerate(TIMEFRAMES)
        }
    return lookback, current


def test_mechanics_windows_are_adjacent_and_non_overlapping() -> None:
    lookback, current, forward = mechanics_windows()

    for lookback_label, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        a = lookback[lookback_label]
        b = current[timeframe]
        c = forward[timeframe]

        assert math.isclose(a.end_minutes, b.start_minutes)
        assert math.isclose(b.end_minutes, c.start_minutes)
        assert math.isclose(a.width_minutes, b.width_minutes)
        assert math.isclose(b.width_minutes, c.width_minutes)
        assert a.start_minutes == -2.0 * b.width_minutes
        assert a.end_minutes == -b.width_minutes
        assert b.start_minutes == -b.width_minutes
        assert b.end_minutes == 0.0
        assert c.start_minutes == 0.0
        assert c.end_minutes == c.width_minutes


def test_five_day_geometry_is_minus_10d_to_minus_5d_then_minus_5d_to_now() -> None:
    lookback, current, forward = mechanics_windows()

    assert lookback["-5d"].start_minutes == -3900.0
    assert lookback["-5d"].end_minutes == -1950.0
    assert current["5d"].start_minutes == -1950.0
    assert current["5d"].end_minutes == 0.0
    assert forward["5d"].start_minutes == 0.0
    assert forward["5d"].end_minutes == 1950.0


def test_inertia_matrices_are_rectangular_with_same_row_set() -> None:
    lookback_response, current_response = _responses(lookback_base=0.4, current_base=0.5)
    matrices = build_inertia_matrices(
        lookback_response=lookback_response,
        current_response=current_response,
    )

    assert tuple(matrices.lookback) == ALL_INERTIA_MATRIX_ROWS
    assert tuple(matrices.current) == ALL_INERTIA_MATRIX_ROWS
    assert tuple(matrices.forward) == ALL_INERTIA_MATRIX_ROWS

    for row in ALL_INERTIA_MATRIX_ROWS:
        assert tuple(matrices.lookback[row]) == LOOKBACKS
        assert tuple(matrices.current[row]) == TIMEFRAMES
        assert tuple(matrices.forward[row]) == TIMEFRAMES


def test_forward_projects_beta_then_recomputes_inertia() -> None:
    lookback_response, current_response = _responses(lookback_base=0.25, current_base=0.50)
    matrices = build_inertia_matrices(
        lookback_response=lookback_response,
        current_response=current_response,
    )

    timeframe = "1m"
    lookback = "-1m"
    beta_a = lookback_response["beta_up"][lookback]
    beta_b = current_response["beta_up"][timeframe]
    beta_c = 2.0 * beta_b - beta_a

    assert matrices.forward["beta_up"][timeframe] == beta_c
    assert matrices.forward["upside_inertia"][timeframe] == 1.0 / beta_c

    inertia_a = matrices.lookback["upside_inertia"][lookback]
    inertia_b = matrices.current["upside_inertia"][timeframe]
    direct_inertia_extrapolation = 2.0 * inertia_b - inertia_a
    assert not math.isclose(
        matrices.forward["upside_inertia"][timeframe],
        direct_inertia_extrapolation,
    )


def test_directional_and_braking_inertia_follow_white_paper_definitions() -> None:
    lookback_response, current_response = _responses(lookback_base=0.4, current_base=0.5)
    for timeframe in TIMEFRAMES:
        current_response["beta_up"][timeframe] = 0.5
        current_response["beta_down"][timeframe] = 0.25
        current_response["beta_pm"][timeframe] = -0.20
        current_response["beta_mp"][timeframe] = 0.10

    matrices = build_inertia_matrices(
        lookback_response=lookback_response,
        current_response=current_response,
    )

    for timeframe in TIMEFRAMES:
        assert matrices.current["upside_inertia"][timeframe] == 2.0
        assert matrices.current["downside_inertia"][timeframe] == 4.0
        assert matrices.current["uptrend_braking_inertia"][timeframe] == 5.0
        assert matrices.current["downtrend_braking_inertia"][timeframe] == 10.0
        assert math.isclose(matrices.current["inertial_bias"][timeframe], 1.0 / 3.0)


def test_nonpositive_directional_beta_does_not_create_fake_inertia() -> None:
    lookback_response, current_response = _responses(lookback_base=0.4, current_base=0.5)
    current_response["beta_up"]["15m"] = -0.1
    matrices = build_inertia_matrices(
        lookback_response=lookback_response,
        current_response=current_response,
    )

    assert matrices.current["upside_inertia"]["15m"] is None
    assert matrices.current["inertial_bias"]["15m"] is None


def test_row_taxonomy_is_explicit() -> None:
    assert RESPONSE_ROWS == (
        "beta_up",
        "beta_down",
        "beta_pp",
        "beta_pm",
        "beta_mp",
        "beta_mm",
    )
    assert INERTIA_ROWS == (
        "upside_inertia",
        "downside_inertia",
        "uptrend_braking_inertia",
        "downtrend_braking_inertia",
        "inertial_bias",
    )
