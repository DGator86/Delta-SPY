from __future__ import annotations

from typing import Literal, TypeVar

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

TIMEFRAMES: tuple[Timeframe, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
)

# Approximate regular-session observations per trading year for annualizing
# per-bar volatility at each canonical column. 4h and 1h are fractional because
# a regular US equity session is 6.5 hours.
PERIODS_PER_YEAR: dict[Timeframe, float] = {
    "1m": 252.0 * 390.0,
    "5m": 252.0 * 78.0,
    "15m": 252.0 * 26.0,
    "30m": 252.0 * 13.0,
    "1h": 252.0 * 6.5,
    "4h": 252.0 * (6.5 / 4.0),
    "1d": 252.0,
}

T = TypeVar("T")


def require_timeframe_columns(mapping: dict[Timeframe, T], *, label: str) -> None:
    """Require the exact canonical 7-column timeframe matrix."""

    expected = set(TIMEFRAMES)
    actual = set(mapping)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"{label} must contain exactly {TIMEFRAMES}; missing={missing}, extra={extra}")
