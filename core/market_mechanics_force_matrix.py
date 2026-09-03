from __future__ import annotations

from dataclasses import dataclass

from .market_mechanics import MechanicsWindow, mechanics_windows
from .market_mechanics_force import ForceState
from .timeframes import (
    LOOKBACKS,
    TIMEFRAMES,
    Lookback,
    Timeframe,
    require_lookback_columns,
    require_timeframe_columns,
)

FORCE_ROWS: tuple[str, ...] = (
    "ofi_pressure",
    "trade_imbalance",
    "depth_imbalance",
    "replenishment_pressure",
    "net_force",
)


@dataclass(frozen=True, slots=True)
class ForceMatrices:
    """Lookback/current/forward force matrices on adjacent native windows.

    Lookback cells summarize pressure over ``[-2T,-T]``.
    Current cells summarize pressure over ``[-T,0]``.
    Forward cells are the deliberately naive one-T linear continuation
    ``C = 2B - A`` into ``[0,+T]``.

    Force rows are primitive temporal measurements for walk-forward purposes.
    They are therefore extrapolated directly rather than re-derived from inertia.
    """

    lookback: dict[str, dict[Lookback, float | None]]
    current: dict[str, dict[Timeframe, float | None]]
    forward: dict[str, dict[Timeframe, float | None]]
    lookback_windows: dict[Lookback, MechanicsWindow]
    current_windows: dict[Timeframe, MechanicsWindow]
    forward_windows: dict[Timeframe, MechanicsWindow]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _window_mean(
    states: tuple[ForceState, ...],
    *,
    row: str,
    start: float,
    end: float,
) -> float | None:
    """Mean a force state over ``(start,end]`` without boundary overlap.

    ``ForceState`` values are timestamped at the end of the event/snapshot interval,
    so assigning the shared boundary to the earlier window keeps adjacent windows
    disjoint while allowing the current window to include the as-of state.
    """

    values: list[float] = []
    for state in states:
        if not (start < state.trading_minute <= end):
            continue
        value = getattr(state, row)
        if value is not None:
            values.append(value)
    return _mean(values)


def build_force_matrices(
    states: tuple[ForceState, ...],
    *,
    as_of_trading_minute: float | None = None,
) -> ForceMatrices:
    """Matricize causal force states and linearly walk every force row one T.

    The five force rows are treated as direct temporal state for this baseline:
    OFI pressure, aggressive-trade imbalance, depth imbalance, replenishment
    pressure, and the transparent composite net force.
    """

    if not states:
        raise ValueError("force states are required")

    resolved_as_of = states[-1].trading_minute if as_of_trading_minute is None else as_of_trading_minute
    previous_time: float | None = None
    for state in states:
        if previous_time is not None and state.trading_minute <= previous_time:
            raise ValueError("force states must be strictly increasing in trading time")
        if state.trading_minute > resolved_as_of:
            raise ValueError("force states may not extend beyond as_of_trading_minute")
        previous_time = state.trading_minute

    lookback_windows, current_windows, forward_windows = mechanics_windows()
    lookback: dict[str, dict[Lookback, float | None]] = {row: {} for row in FORCE_ROWS}
    current: dict[str, dict[Timeframe, float | None]] = {row: {} for row in FORCE_ROWS}
    forward: dict[str, dict[Timeframe, float | None]] = {row: {} for row in FORCE_ROWS}

    for lookback_label, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        lookback_window = lookback_windows[lookback_label]
        current_window = current_windows[timeframe]
        lookback_start = resolved_as_of + lookback_window.start_minutes
        lookback_end = resolved_as_of + lookback_window.end_minutes
        current_start = resolved_as_of + current_window.start_minutes
        current_end = resolved_as_of + current_window.end_minutes

        for row in FORCE_ROWS:
            point_a = _window_mean(
                states,
                row=row,
                start=lookback_start,
                end=lookback_end,
            )
            point_b = _window_mean(
                states,
                row=row,
                start=current_start,
                end=current_end,
            )
            lookback[row][lookback_label] = point_a
            current[row][timeframe] = point_b
            forward[row][timeframe] = (
                None if point_a is None or point_b is None else 2.0 * point_b - point_a
            )

    for row in FORCE_ROWS:
        require_lookback_columns(lookback[row], label=f"force.lookback.{row}")
        require_timeframe_columns(current[row], label=f"force.current.{row}")
        require_timeframe_columns(forward[row], label=f"force.forward.{row}")

    return ForceMatrices(
        lookback=lookback,
        current=current,
        forward=forward,
        lookback_windows=lookback_windows,
        current_windows=current_windows,
        forward_windows=forward_windows,
    )
