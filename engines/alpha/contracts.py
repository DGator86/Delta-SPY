from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from core.timeframes import LOOKBACKS, TIMEFRAMES, Lookback, Timeframe


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

    ``spy_bars`` is the canonical nine-column current-state timeframe matrix:
    1m, 5m, 15m, 30m, 1h, 4h, 1d, 3d, and 5d. Each series is ordered oldest to
    newest and may contain only information known by ``as_of``.

    Alpha derives the lookback matrix from the same histories by evaluating each
    matching native timeframe one completed bar earlier. For example, ``-5m`` is
    the 5-minute processing state as it existed one completed 5-minute bar ago.

    ``constituent_closes`` is optional supporting data keyed by the same positive
    timeframe vocabulary. Missing constituent data never causes Alpha to invent a
    reading; the corresponding cross-sectional output remains explicitly unavailable.
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
class StateVelocityState:
    """First differences in measured Alpha state over one matching native bar."""

    trend_score_delta: float | None
    realized_volatility_delta: float | None
    expected_return_delta: float | None
    probability_up_delta: float | None
    dispersion_delta: float | None


@dataclass(frozen=True, slots=True)
class StateAccelerationState:
    """Second differences: change in state velocity over one matching native bar."""

    trend_score_second_difference: float | None
    realized_volatility_second_difference: float | None
    expected_return_second_difference: float | None
    probability_up_second_difference: float | None
    dispersion_second_difference: float | None


@dataclass(frozen=True, slots=True)
class PersistenceState:
    """Consecutive native bars for which the current statistical regime persists."""

    trend_streak_bars: int
    volatility_streak_bars: int
    joint_streak_bars: int
    joint_persistent: bool


@dataclass(frozen=True, slots=True)
class RegimeTransitionState:
    """Observed regime change from the prior matching native bar to this state."""

    from_trend: str | None
    to_trend: str | None
    from_volatility: str | None
    to_volatility: str | None
    trend_changed: bool | None
    volatility_changed: bool | None


@dataclass(frozen=True, slots=True)
class ForecastDriftState:
    """Change in the empirical forecast distribution versus the prior native state."""

    expected_return_delta: float | None
    probability_up_delta: float | None
    standard_deviation_delta: float | None
    median_delta: float | None
    expected_mfe_delta: float | None
    expected_mae_delta: float | None


@dataclass(frozen=True, slots=True)
class ConfidenceChangeState:
    """Change in Alpha regime confidence versus the prior matching native bar."""

    previous_confidence: float | None
    current_confidence: float | None
    delta: float | None


@dataclass(frozen=True, slots=True)
class LinearWalkForward1TState:
    """Auditable one-native-period linear continuation from prior A through current B."""

    lookback: Lookback
    timeframe: Timeframe
    point_a: float
    point_b: float
    observed_delta: float
    slope_per_minute: float
    projected_spot: float


@dataclass(frozen=True, slots=True)
class AlphaRows:
    """Current Alpha processing-unit rows across positive timeframe columns."""

    spot: dict[Timeframe, float]
    observed_return: dict[Timeframe, float | None]
    regime: dict[Timeframe, RegimeState]
    cross_section: dict[Timeframe, CrossSectionState]
    forecast: dict[Timeframe, ForecastDistribution]
    quality: dict[Timeframe, DataQuality]
    state_velocity: dict[Timeframe, StateVelocityState] = field(default_factory=dict)
    state_acceleration: dict[Timeframe, StateAccelerationState] = field(default_factory=dict)
    persistence: dict[Timeframe, PersistenceState] = field(default_factory=dict)
    regime_transition: dict[Timeframe, RegimeTransitionState] = field(default_factory=dict)
    forecast_drift: dict[Timeframe, ForecastDriftState] = field(default_factory=dict)
    confidence_change: dict[Timeframe, ConfidenceChangeState] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlphaLookbackRows:
    """The same Alpha processing-unit rows evaluated one matching native bar earlier."""

    spot: dict[Lookback, float]
    observed_return: dict[Lookback, float | None]
    regime: dict[Lookback, RegimeState]
    cross_section: dict[Lookback, CrossSectionState]
    forecast: dict[Lookback, ForecastDistribution]
    quality: dict[Lookback, DataQuality]
    state_velocity: dict[Lookback, StateVelocityState] = field(default_factory=dict)
    state_acceleration: dict[Lookback, StateAccelerationState] = field(default_factory=dict)
    persistence: dict[Lookback, PersistenceState] = field(default_factory=dict)
    regime_transition: dict[Lookback, RegimeTransitionState] = field(default_factory=dict)
    forecast_drift: dict[Lookback, ForecastDriftState] = field(default_factory=dict)
    confidence_change: dict[Lookback, ConfidenceChangeState] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlphaLookForwardRows:
    """Forward-processing rows across the canonical positive timeframe columns."""

    linear_ab_1t: dict[Timeframe, LinearWalkForward1TState] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AlphaState:
    """Complete public output from Alpha.

    ``current`` rows use columns:
    1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d

    ``lookback`` rows use columns:
    -1m | -5m | -15m | -30m | -1h | -4h | -1d | -3d | -5d

    ``look_forward`` rows use the positive timeframe columns as forecast horizons.
    They are processor outputs, not trade or strategy decisions.
    """

    engine: str
    engine_version: str
    as_of: datetime
    current: AlphaRows
    lookback: AlphaLookbackRows
    look_forward: AlphaLookForwardRows = field(default_factory=AlphaLookForwardRows)
    current_columns: tuple[Timeframe, ...] = TIMEFRAMES
    lookback_columns: tuple[Lookback, ...] = LOOKBACKS
    look_forward_columns: tuple[Timeframe, ...] = TIMEFRAMES
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
