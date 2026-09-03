from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .linear_bridge import TIMEFRAME_DISTANCE_MINUTES
from .timeframes import (
    LOOKBACKS,
    TIMEFRAMES,
    Lookback,
    Timeframe,
    require_lookback_columns,
    require_timeframe_columns,
)

WindowKind = Literal["lookback", "current", "forward"]

# Response coefficients are the directly time-dependent quantities. Inertia rows
# are derived from them so the forward matrix remains mechanically coherent.
RESPONSE_ROWS: tuple[str, ...] = (
    "beta_up",
    "beta_down",
    "beta_pp",
    "beta_pm",
    "beta_mp",
    "beta_mm",
)

INERTIA_ROWS: tuple[str, ...] = (
    "upside_inertia",
    "downside_inertia",
    "uptrend_braking_inertia",
    "downtrend_braking_inertia",
    "inertial_bias",
)

ALL_INERTIA_MATRIX_ROWS: tuple[str, ...] = RESPONSE_ROWS + INERTIA_ROWS


@dataclass(frozen=True, slots=True)
class MechanicsWindow:
    """One non-overlapping native-timeframe measurement window."""

    timeframe: Timeframe
    kind: WindowKind
    start_minutes: float
    end_minutes: float

    @property
    def width_minutes(self) -> float:
        return self.end_minutes - self.start_minutes


@dataclass(frozen=True, slots=True)
class InertiaMatrices:
    """Lookback/current/forward inertia row matrices with canonical window geometry.

    Lookback rows are measured over [-2T, -T].
    Current rows are measured over [-T, 0].
    Forward rows describe [0, +T].

    Forward response coefficients use the simple one-T A->B continuation:
    beta_C = 2*beta_B - beta_A. Derived inertia rows are then recomputed from
    beta_C; inertia itself is not independently extrapolated.
    """

    lookback: dict[str, dict[Lookback, float | None]]
    current: dict[str, dict[Timeframe, float | None]]
    forward: dict[str, dict[Timeframe, float | None]]
    lookback_windows: dict[Lookback, MechanicsWindow]
    current_windows: dict[Timeframe, MechanicsWindow]
    forward_windows: dict[Timeframe, MechanicsWindow]


def mechanics_windows() -> tuple[
    dict[Lookback, MechanicsWindow],
    dict[Timeframe, MechanicsWindow],
    dict[Timeframe, MechanicsWindow],
]:
    """Return canonical adjacent lookback/current/forward windows for all timeframes."""

    lookback_windows: dict[Lookback, MechanicsWindow] = {}
    current_windows: dict[Timeframe, MechanicsWindow] = {}
    forward_windows: dict[Timeframe, MechanicsWindow] = {}

    for lookback, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        distance = TIMEFRAME_DISTANCE_MINUTES[timeframe]
        lookback_windows[lookback] = MechanicsWindow(
            timeframe=timeframe,
            kind="lookback",
            start_minutes=-2.0 * distance,
            end_minutes=-distance,
        )
        current_windows[timeframe] = MechanicsWindow(
            timeframe=timeframe,
            kind="current",
            start_minutes=-distance,
            end_minutes=0.0,
        )
        forward_windows[timeframe] = MechanicsWindow(
            timeframe=timeframe,
            kind="forward",
            start_minutes=0.0,
            end_minutes=distance,
        )

    return lookback_windows, current_windows, forward_windows


def _inverse_positive(value: float | None, epsilon: float) -> float | None:
    if value is None or value <= epsilon:
        return None
    return 1.0 / value


def _inverse_abs(value: float | None, epsilon: float) -> float | None:
    if value is None or abs(value) <= epsilon:
        return None
    return 1.0 / abs(value)


def _inertial_bias(
    upside_inertia: float | None,
    downside_inertia: float | None,
    epsilon: float,
) -> float | None:
    if upside_inertia is None or downside_inertia is None:
        return None
    denominator = downside_inertia + upside_inertia
    if abs(denominator) <= epsilon:
        return None
    return (downside_inertia - upside_inertia) / denominator


def _derive_timeframe_inertia_rows(
    response_rows: dict[str, dict[Timeframe, float | None]],
    *,
    epsilon: float,
) -> dict[str, dict[Timeframe, float | None]]:
    output = {row: dict(values) for row, values in response_rows.items()}
    upside: dict[Timeframe, float | None] = {}
    downside: dict[Timeframe, float | None] = {}
    brake_up: dict[Timeframe, float | None] = {}
    brake_down: dict[Timeframe, float | None] = {}
    bias: dict[Timeframe, float | None] = {}

    for timeframe in TIMEFRAMES:
        upside[timeframe] = _inverse_positive(response_rows["beta_up"][timeframe], epsilon)
        downside[timeframe] = _inverse_positive(response_rows["beta_down"][timeframe], epsilon)
        brake_up[timeframe] = _inverse_abs(response_rows["beta_pm"][timeframe], epsilon)
        brake_down[timeframe] = _inverse_abs(response_rows["beta_mp"][timeframe], epsilon)
        bias[timeframe] = _inertial_bias(upside[timeframe], downside[timeframe], epsilon)

    output["upside_inertia"] = upside
    output["downside_inertia"] = downside
    output["uptrend_braking_inertia"] = brake_up
    output["downtrend_braking_inertia"] = brake_down
    output["inertial_bias"] = bias
    return output


def _derive_lookback_inertia_rows(
    response_rows: dict[str, dict[Lookback, float | None]],
    *,
    epsilon: float,
) -> dict[str, dict[Lookback, float | None]]:
    output = {row: dict(values) for row, values in response_rows.items()}
    upside: dict[Lookback, float | None] = {}
    downside: dict[Lookback, float | None] = {}
    brake_up: dict[Lookback, float | None] = {}
    brake_down: dict[Lookback, float | None] = {}
    bias: dict[Lookback, float | None] = {}

    for lookback in LOOKBACKS:
        upside[lookback] = _inverse_positive(response_rows["beta_up"][lookback], epsilon)
        downside[lookback] = _inverse_positive(response_rows["beta_down"][lookback], epsilon)
        brake_up[lookback] = _inverse_abs(response_rows["beta_pm"][lookback], epsilon)
        brake_down[lookback] = _inverse_abs(response_rows["beta_mp"][lookback], epsilon)
        bias[lookback] = _inertial_bias(upside[lookback], downside[lookback], epsilon)

    output["upside_inertia"] = upside
    output["downside_inertia"] = downside
    output["uptrend_braking_inertia"] = brake_up
    output["downtrend_braking_inertia"] = brake_down
    output["inertial_bias"] = bias
    return output


def build_inertia_matrices(
    *,
    lookback_response: dict[str, dict[Lookback, float | None]],
    current_response: dict[str, dict[Timeframe, float | None]],
    epsilon: float = 1e-9,
) -> InertiaMatrices:
    """Build the canonical inertia row set from adjacent response-estimation windows.

    Callers supply response-coefficient estimates for the immediately preceding
    non-overlapping window and the current window. This function does not estimate
    beta from price alone; it only enforces matrix geometry, derives inertia, and
    performs the deliberately naive one-T linear walk-forward of beta coefficients.
    """

    if set(lookback_response) != set(RESPONSE_ROWS):
        raise ValueError(f"lookback_response must contain exactly {RESPONSE_ROWS}")
    if set(current_response) != set(RESPONSE_ROWS):
        raise ValueError(f"current_response must contain exactly {RESPONSE_ROWS}")

    for row in RESPONSE_ROWS:
        require_lookback_columns(lookback_response[row], label=f"lookback_response.{row}")
        require_timeframe_columns(current_response[row], label=f"current_response.{row}")

    lookback = _derive_lookback_inertia_rows(lookback_response, epsilon=epsilon)
    current = _derive_timeframe_inertia_rows(current_response, epsilon=epsilon)

    forward_response: dict[str, dict[Timeframe, float | None]] = {
        row: {} for row in RESPONSE_ROWS
    }
    for row in RESPONSE_ROWS:
        for lookback_label, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
            point_a = lookback_response[row][lookback_label]
            point_b = current_response[row][timeframe]
            forward_response[row][timeframe] = (
                None if point_a is None or point_b is None else 2.0 * point_b - point_a
            )

    forward = _derive_timeframe_inertia_rows(forward_response, epsilon=epsilon)
    lookback_windows, current_windows, forward_windows = mechanics_windows()

    return InertiaMatrices(
        lookback=lookback,
        current=current,
        forward=forward,
        lookback_windows=lookback_windows,
        current_windows=current_windows,
        forward_windows=forward_windows,
    )
