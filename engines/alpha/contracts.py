from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from core.timeframes import TIMEFRAMES, Timeframe


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One normalized market bar at the timeframe supplied by its matrix column."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class AlphaInput:
    """Complete public input to Alpha.

    ``spy_bars`` is a seven-column timeframe matrix. Every canonical timeframe must
    be present: 1m, 5m, 15m, 30m, 1h, 4h, and 1d. Each series is ordered oldest to
    newest and may contain only information known by ``as_of``.

    ``constituent_closes`` is optional supporting data keyed by the same timeframe
    vocabulary. Missing constituent data never causes Alpha to invent a reading;
    the corresponding cross-sectional output remains explicitly unavailable.
    """

    as_of: datetime
    spy_bars: dict[Timeframe, tuple[PriceBar, ...]]
    constituent_closes: dict[Timeframe, dict[str, tuple[float, ...]]] = field(default_factory=dict)
    sample_lookback: int = 780


@dataclass(frozen=True, slots=True)
class ForecastDistribution:
    timeframe: Timeframe
    samples: int
    probability_up: float | None
    expected_return: float | None
    standard_deviation: float | None
    p05: float | None
    p25: float | None
    median: float | None
    p75: float | None
    p95: float | None
    expected_mfe: float | None
    expected_mae: float | None


@dataclass(frozen=True, slots=True)
class RegimeState:
    trend: str
    trend_score: float | None
    volatility: str
    realized_volatility_annualized: float | None
    volatility_percentile: float | None
    confidence: float


@dataclass(frozen=True, slots=True)
class CrossSectionState:
    symbol_count: int
    mean_correlation_to_spy: float | None
    mean_covariance_to_spy: float | None
    latest_return_dispersion: float | None


@dataclass(frozen=True, slots=True)
class DataQuality:
    bars_received: int
    usable_returns: int
    aligned_constituents: int
    completeness: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlphaRows:
    """Alpha processing units as rows across the canonical timeframe columns."""

    spot: dict[Timeframe, float]
    observed_return: dict[Timeframe, float | None]
    regime: dict[Timeframe, RegimeState]
    cross_section: dict[Timeframe, CrossSectionState]
    forecast: dict[Timeframe, ForecastDistribution]
    quality: dict[Timeframe, DataQuality]


@dataclass(frozen=True, slots=True)
class AlphaState:
    """Complete public output from Alpha.

    Rows are Alpha processing units. Columns are always exactly:
    1m | 5m | 15m | 30m | 1h | 4h | 1d.

    This is a measurement/forecast state only. It intentionally contains no action,
    trade, strategy, position, order, broker, sizing, or execution fields.
    """

    engine: str
    engine_version: str
    as_of: datetime
    rows: AlphaRows
    columns: tuple[Timeframe, ...] = TIMEFRAMES
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
