from __future__ import annotations

from typing import Literal, TypeVar

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "3d", "5d"]
Lookback = Literal["-1m", "-5m", "-15m", "-30m", "-1h", "-4h", "-1d", "-3d", "-5d"]

TIMEFRAMES: tuple[Timeframe, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
    "3d",
    "5d",
)

LOOKBACKS: tuple[Lookback, ...] = (
    "-1m",
    "-5m",
    "-15m",
    "-30m",
    "-1h",
    "-4h",
    "-1d",
    "-3d",
    "-5d",
)

LOOKBACK_TO_TIMEFRAME: dict[Lookback, Timeframe] = {
    "-1m": "1m",
    "-5m": "5m",
    "-15m": "15m",
    "-30m": "30m",
    "-1h": "1h",
    "-4h": "4h",
    "-1d": "1d",
    "-3d": "3d",
    "-5d": "5d",
}

# Approximate regular-session observations per trading year for annualizing
# per-bar volatility at each canonical column. Multi-day columns are expressed
# in trading days rather than calendar days.
PERIODS_PER_YEAR: dict[Timeframe, float] = {
    "1m": 252.0 * 390.0,
    "5m": 252.0 * 78.0,
    "15m": 252.0 * 26.0,
    "30m": 252.0 * 13.0,
    "1h": 252.0 * 6.5,
    "4h": 252.0 * (6.5 / 4.0),
    "1d": 252.0,
    "3d": 252.0 / 3.0,
    "5d": 252.0 / 5.0,
}

T = TypeVar("T")


def require_timeframe_columns(mapping: dict[Timeframe, T], *, label: str) -> None:
    """Require the exact canonical nine-column current-state timeframe matrix."""

    expected = set(TIMEFRAMES)
    actual = set(mapping)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"{label} must contain exactly {TIMEFRAMES}; missing={missing}, extra={extra}")


def require_lookback_columns(mapping: dict[Lookback, T], *, label: str) -> None:
    """Require the exact canonical nine-column lookback matrix."""

    expected = set(LOOKBACKS)
    actual = set(mapping)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"{label} must contain exactly {LOOKBACKS}; missing={missing}, extra={extra}")
