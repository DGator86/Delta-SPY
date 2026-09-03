from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from .timeframes import LOOKBACK_TO_TIMEFRAME, LOOKBACKS, Lookback, Timeframe

# Canonical symmetric A -> B pairs. Point A is the negative lookback column;
# point B is the matching positive current-state column.
LINEAR_PAIRS: tuple[tuple[Lookback, Timeframe], ...] = tuple(
    (lookback, LOOKBACK_TO_TIMEFRAME[lookback]) for lookback in LOOKBACKS
)

# Common coordinate basis for the straight-line function. Intraday columns use
# elapsed minutes. Daily and multi-day columns use regular-session trading minutes
# so weekends/closures do not alter the geometry.
TIMEFRAME_DISTANCE_MINUTES: dict[Timeframe, float] = {
    "1m": 1.0,
    "5m": 5.0,
    "15m": 15.0,
    "30m": 30.0,
    "1h": 60.0,
    "4h": 240.0,
    "1d": 390.0,
    "3d": 3.0 * 390.0,
    "5d": 5.0 * 390.0,
}


@dataclass(frozen=True, slots=True)
class LinearBridge:
    """Straight line through a symmetric negative-time point A and positive-time point B."""

    lookback: Lookback
    timeframe: Timeframe
    x_a_minutes: float
    x_b_minutes: float
    y_a: float
    y_b: float
    slope_per_minute: float
    intercept: float

    @property
    def midpoint_value(self) -> float:
        """Value at x=0; symmetry makes this the arithmetic mean of A and B."""

        return self.intercept

    @property
    def total_change(self) -> float:
        return self.y_b - self.y_a

    def value_at(self, x_minutes: float) -> float:
        """Evaluate the unbounded line y = m*x + b at x_minutes."""

        return self.slope_per_minute * x_minutes + self.intercept

    def interpolate(self, fraction: float) -> float:
        """Interpolate on segment A->B where 0=A, 0.5=midpoint, 1=B."""

        return self.y_a + fraction * (self.y_b - self.y_a)


def linear_bridge(lookback: Lookback, y_a: float, y_b: float) -> LinearBridge:
    """Build the canonical straight line from -T value A to +T value B.

    For symmetric endpoints (-T, A) and (+T, B):

        slope = (B - A) / (2T)
        intercept = (A + B) / 2
        f(x) = slope*x + intercept
    """

    timeframe = LOOKBACK_TO_TIMEFRAME[lookback]
    distance = TIMEFRAME_DISTANCE_MINUTES[timeframe]
    slope = (y_b - y_a) / (2.0 * distance)
    intercept = (y_a + y_b) / 2.0
    return LinearBridge(
        lookback=lookback,
        timeframe=timeframe,
        x_a_minutes=-distance,
        x_b_minutes=distance,
        y_a=y_a,
        y_b=y_b,
        slope_per_minute=slope,
        intercept=intercept,
    )


T = TypeVar("T", bound=float)


def build_linear_bridges(
    lookback_values: dict[Lookback, float | None],
    current_values: dict[Timeframe, float | None],
) -> dict[Timeframe, LinearBridge | None]:
    """Build all nine A->B bridges; unavailable numeric endpoints remain None."""

    output: dict[Timeframe, LinearBridge | None] = {}
    for lookback, timeframe in LINEAR_PAIRS:
        y_a = lookback_values.get(lookback)
        y_b = current_values.get(timeframe)
        output[timeframe] = (
            None if y_a is None or y_b is None else linear_bridge(lookback, y_a, y_b)
        )
    return output
