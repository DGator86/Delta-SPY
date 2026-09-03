from __future__ import annotations

from dataclasses import dataclass

from .timeframes import LOOKBACK_TO_TIMEFRAME, LOOKBACKS, Lookback, Timeframe

# Canonical A -> B pairs. A is the prior native state at t-T; B is the
# matching current native state at t.
LINEAR_PAIRS: tuple[tuple[Lookback, Timeframe], ...] = tuple(
    (lookback, LOOKBACK_TO_TIMEFRAME[lookback]) for lookback in LOOKBACKS
)

# Common coordinate basis. Intraday columns use elapsed minutes. Daily and
# multi-day columns use regular-session trading minutes so weekends/closures do
# not alter the geometry.
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
    """Straight line through prior state A at t-T and current state B at t."""

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
        """Arithmetic midpoint on the observed A -> B segment."""

        return (self.y_a + self.y_b) / 2.0

    @property
    def total_change(self) -> float:
        return self.y_b - self.y_a

    @property
    def forward_one_t_value(self) -> float:
        """Continue the A -> B line one more matching native period T."""

        distance = self.x_b_minutes - self.x_a_minutes
        return self.value_at(self.x_b_minutes + distance)

    def value_at(self, x_minutes: float) -> float:
        """Evaluate the unbounded line y = m*x + b at x_minutes."""

        return self.slope_per_minute * x_minutes + self.intercept

    def interpolate(self, fraction: float) -> float:
        """Interpolate on observed segment A->B where 0=A and 1=B."""

        return self.y_a + fraction * (self.y_b - self.y_a)


def linear_bridge(lookback: Lookback, y_a: float, y_b: float) -> LinearBridge:
    """Build the canonical line from prior A at t-T to current B at t.

    Coordinates are:

        A = (-T, y_a)
        B = ( 0, y_b)

    Therefore:

        slope = (B - A) / T
        intercept = B
        f(x) = slope*x + B
        f(+T) = B + (B - A) = 2B - A
    """

    timeframe = LOOKBACK_TO_TIMEFRAME[lookback]
    distance = TIMEFRAME_DISTANCE_MINUTES[timeframe]
    slope = (y_b - y_a) / distance
    return LinearBridge(
        lookback=lookback,
        timeframe=timeframe,
        x_a_minutes=-distance,
        x_b_minutes=0.0,
        y_a=y_a,
        y_b=y_b,
        slope_per_minute=slope,
        intercept=y_b,
    )


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
