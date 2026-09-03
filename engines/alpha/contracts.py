from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One normalized SPY bar. Values are raw prices, volume is optional."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class AlphaInput:
    """Complete public input to Alpha.

    Bars and constituent close histories are ordered oldest -> newest and must contain
    only information known by ``as_of``. Constituent histories are optional and are
    used only for statistical covariance/correlation/dispersion measurements.
    """

    as_of: datetime
    spy_bars: tuple[PriceBar, ...]
    constituent_closes: dict[str, tuple[float, ...]] = field(default_factory=dict)
    horizons: tuple[int, ...] = (5, 15, 30)
    sample_lookback: int = 780


@dataclass(frozen=True, slots=True)
class ForecastDistribution:
    horizon_minutes: int
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
    realized_volatility_20m_annualized: float | None
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
class AlphaState:
    """Complete public output from Alpha.

    This is a measurement/forecast state only. It intentionally contains no action,
    trade, strategy, position, order, broker, sizing, or execution fields.
    """

    engine: str
    engine_version: str
    as_of: datetime
    spot: float
    return_1m: float | None
    return_5m: float | None
    return_15m: float | None
    regime: RegimeState
    cross_section: CrossSectionState
    forecasts: tuple[ForecastDistribution, ...]
    quality: DataQuality
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
