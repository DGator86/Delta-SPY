from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from itertools import pairwise

from core.timeframes import (
    LOOKBACK_TO_TIMEFRAME,
    LOOKBACKS,
    PERIODS_PER_YEAR,
    TIMEFRAMES,
    Lookback,
    Timeframe,
    require_lookback_columns,
    require_timeframe_columns,
)

from .contracts import (
    AlphaInput,
    AlphaLookbackRows,
    AlphaRows,
    AlphaState,
    CrossSectionState,
    DataQuality,
    ForecastDistribution,
    PriceBar,
    RegimeState,
)

ENGINE_VERSION = "alpha-0.3.0"


def _simple_return(start: float, end: float) -> float | None:
    if start <= 0 or end <= 0:
        return None
    return end / start - 1.0


def _returns_from_closes(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for previous, current in pairwise(closes):
        value = _simple_return(previous, current)
        if value is not None and math.isfinite(value):
            out.append(value)
    return out


def _sample_std(values: Sequence[float]) -> float | None:
    return statistics.stdev(values) if len(values) >= 2 else None


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _one_bar_samples(
    bars: Sequence[PriceBar],
    lookback: int,
) -> tuple[list[float], list[float], list[float]]:
    """Completed one-column-period paths only; never uses unfinished future data."""

    returns: list[float] = []
    mfes: list[float] = []
    maes: list[float] = []
    if len(bars) < 2:
        return returns, mfes, maes

    first_anchor = max(0, len(bars) - 1 - max(lookback, 1))
    for anchor in range(first_anchor, len(bars) - 1):
        start = bars[anchor].close
        next_bar = bars[anchor + 1]
        terminal = _simple_return(start, next_bar.close)
        if terminal is None or start <= 0:
            continue
        returns.append(terminal)
        mfes.append(next_bar.high / start - 1.0)
        maes.append(next_bar.low / start - 1.0)
    return returns, mfes, maes


def _forecast_distribution(
    timeframe: Timeframe,
    bars: Sequence[PriceBar],
    lookback: int,
) -> ForecastDistribution:
    returns, mfes, maes = _one_bar_samples(bars, lookback)
    probability_up = sum(value > 0 for value in returns) / len(returns) if returns else None
    return ForecastDistribution(
        timeframe=timeframe,
        samples=len(returns),
        probability_up=probability_up,
        expected_return=_mean(returns),
        standard_deviation=_sample_std(returns),
        p05=_quantile(returns, 0.05),
        p25=_quantile(returns, 0.25),
        median=_quantile(returns, 0.50),
        p75=_quantile(returns, 0.75),
        p95=_quantile(returns, 0.95),
        expected_mfe=_mean(mfes),
        expected_mae=_mean(maes),
    )


def _realized_volatility_annualized(
    timeframe: Timeframe,
    bars: Sequence[PriceBar],
    window: int = 20,
) -> float | None:
    returns = _returns_from_closes([bar.close for bar in bars if bar.close > 0])
    if len(returns) < 2:
        return None
    sigma = _sample_std(returns[-window:])
    if sigma is None:
        return None
    return sigma * math.sqrt(PERIODS_PER_YEAR[timeframe])


def _rolling_volatility_history(
    timeframe: Timeframe,
    bars: Sequence[PriceBar],
    window: int = 20,
) -> list[float]:
    returns = _returns_from_closes([bar.close for bar in bars if bar.close > 0])
    output: list[float] = []
    if len(returns) < window:
        return output
    annualizer = math.sqrt(PERIODS_PER_YEAR[timeframe])
    for end in range(window, len(returns) + 1):
        sigma = _sample_std(returns[end - window : end])
        if sigma is not None:
            output.append(sigma * annualizer)
    return output


def _percentile_rank(history: Sequence[float], value: float | None) -> float | None:
    if value is None or not history:
        return None
    return sum(item <= value for item in history) / len(history)


def _return_over_bars(bars: Sequence[PriceBar], periods: int) -> float | None:
    if periods <= 0 or len(bars) <= periods:
        return None
    return _simple_return(bars[-1 - periods].close, bars[-1].close)


def _regime_state(timeframe: Timeframe, bars: Sequence[PriceBar]) -> RegimeState:
    realized = _realized_volatility_annualized(timeframe, bars, 20)
    vol_history = _rolling_volatility_history(timeframe, bars, 20)
    percentile = _percentile_rank(vol_history[:-1] or vol_history, realized)

    returns = _returns_from_closes([bar.close for bar in bars if bar.close > 0])
    recent_sigma = _sample_std(returns[-60:])
    three_bar_return = _return_over_bars(bars, 3)
    trend_score: float | None = None
    if three_bar_return is not None and recent_sigma is not None and recent_sigma > 0:
        trend_score = three_bar_return / (recent_sigma * math.sqrt(3.0))

    if trend_score is None:
        trend = "UNKNOWN"
        confidence = 0.0
    elif trend_score >= 0.75:
        trend = "UP"
        confidence = min(abs(trend_score) / 2.0, 1.0)
    elif trend_score <= -0.75:
        trend = "DOWN"
        confidence = min(abs(trend_score) / 2.0, 1.0)
    else:
        trend = "RANGE"
        confidence = min((0.75 - abs(trend_score)) / 0.75, 1.0)

    if percentile is None:
        volatility = "UNKNOWN"
    elif percentile < 1.0 / 3.0:
        volatility = "LOW"
    elif percentile > 2.0 / 3.0:
        volatility = "HIGH"
    else:
        volatility = "NORMAL"

    return RegimeState(
        trend=trend,
        trend_score=trend_score,
        volatility=volatility,
        realized_volatility_annualized=realized,
        volatility_percentile=percentile,
        confidence=confidence,
    )


def _covariance(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    return sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)) / (
        len(left) - 1
    )


def _correlation(left: Sequence[float], right: Sequence[float]) -> float | None:
    covariance = _covariance(left, right)
    left_sigma = _sample_std(left)
    right_sigma = _sample_std(right)
    if covariance is None or left_sigma in (None, 0.0) or right_sigma in (None, 0.0):
        return None
    return covariance / (left_sigma * right_sigma)


def _cross_section(
    bars: Sequence[PriceBar],
    constituent_closes: dict[str, tuple[float, ...]],
) -> CrossSectionState:
    spy_returns = _returns_from_closes([bar.close for bar in bars])
    correlations: list[float] = []
    covariances: list[float] = []
    latest_returns: list[float] = []
    aligned_symbols = 0

    for closes in constituent_closes.values():
        constituent_returns = _returns_from_closes(closes)
        width = min(len(spy_returns), len(constituent_returns))
        if width < 2:
            continue
        aligned_symbols += 1
        left = spy_returns[-width:]
        right = constituent_returns[-width:]
        correlation = _correlation(left, right)
        covariance = _covariance(left, right)
        if correlation is not None and math.isfinite(correlation):
            correlations.append(correlation)
        if covariance is not None and math.isfinite(covariance):
            covariances.append(covariance)
        latest_returns.append(right[-1])

    dispersion = statistics.pstdev(latest_returns) if len(latest_returns) >= 2 else None
    return CrossSectionState(
        symbol_count=aligned_symbols,
        mean_correlation_to_spy=_mean(correlations),
        mean_covariance_to_spy=_mean(covariances),
        latest_return_dispersion=dispersion,
    )


def _quality(
    bars: Sequence[PriceBar],
    cross_section: CrossSectionState,
    sample_lookback: int,
) -> DataQuality:
    bar_count = len(bars)
    usable_returns = max(0, bar_count - 1)
    warnings: list[str] = []
    if bar_count < 21:
        warnings.append("insufficient_history_for_20_bar_statistics")
    if usable_returns < sample_lookback:
        warnings.append("forecast_history_shorter_than_requested_lookback")
    if cross_section.symbol_count == 0:
        warnings.append("cross_section_unavailable")
    completeness = min(1.0, usable_returns / max(sample_lookback, 1))
    return DataQuality(
        bars_received=bar_count,
        usable_returns=usable_returns,
        aligned_constituents=cross_section.symbol_count,
        completeness=completeness,
        warnings=tuple(warnings),
    )


def _validate_bar_series(timeframe: Timeframe, bars: Sequence[PriceBar], *, as_of) -> None:
    if len(bars) < 2:
        raise ValueError(
            f"AlphaInput.spy_bars[{timeframe!r}] requires at least two bars for lookback state"
        )
    previous_timestamp = None
    for bar in bars:
        if bar.close <= 0 or bar.high <= 0 or bar.low <= 0 or bar.open <= 0:
            raise ValueError(f"SPY {timeframe} bars must contain positive OHLC prices")
        if bar.low > min(bar.open, bar.close, bar.high):
            raise ValueError(f"SPY {timeframe} bar low is inconsistent with OHLC")
        if bar.high < max(bar.open, bar.close, bar.low):
            raise ValueError(f"SPY {timeframe} bar high is inconsistent with OHLC")
        if bar.timestamp > as_of:
            raise ValueError(f"SPY {timeframe} bar timestamp is after AlphaInput.as_of")
        if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
            raise ValueError(f"SPY {timeframe} bars must be strictly time ordered")
        previous_timestamp = bar.timestamp


def _validate(input_state: AlphaInput) -> None:
    require_timeframe_columns(input_state.spy_bars, label="AlphaInput.spy_bars")
    if input_state.sample_lookback <= 0:
        raise ValueError("AlphaInput.sample_lookback must be positive")
    for timeframe in TIMEFRAMES:
        _validate_bar_series(timeframe, input_state.spy_bars[timeframe], as_of=input_state.as_of)


def _trim_constituents_one_bar(
    constituent_closes: dict[str, tuple[float, ...]],
) -> dict[str, tuple[float, ...]]:
    return {
        symbol: closes[:-1]
        for symbol, closes in constituent_closes.items()
        if len(closes) >= 2
    }


def _build_current_rows(input_state: AlphaInput) -> AlphaRows:
    spot: dict[Timeframe, float] = {}
    observed_return: dict[Timeframe, float | None] = {}
    regime: dict[Timeframe, RegimeState] = {}
    cross_section: dict[Timeframe, CrossSectionState] = {}
    forecast: dict[Timeframe, ForecastDistribution] = {}
    quality: dict[Timeframe, DataQuality] = {}

    for timeframe in TIMEFRAMES:
        bars = input_state.spy_bars[timeframe]
        constituents = input_state.constituent_closes.get(timeframe, {})
        cross = _cross_section(bars, constituents)
        spot[timeframe] = bars[-1].close
        observed_return[timeframe] = _return_over_bars(bars, 1)
        regime[timeframe] = _regime_state(timeframe, bars)
        cross_section[timeframe] = cross
        forecast[timeframe] = _forecast_distribution(
            timeframe,
            bars,
            input_state.sample_lookback,
        )
        quality[timeframe] = _quality(bars, cross, input_state.sample_lookback)

    require_timeframe_columns(spot, label="AlphaState.current.spot")
    require_timeframe_columns(observed_return, label="AlphaState.current.observed_return")
    require_timeframe_columns(regime, label="AlphaState.current.regime")
    require_timeframe_columns(cross_section, label="AlphaState.current.cross_section")
    require_timeframe_columns(forecast, label="AlphaState.current.forecast")
    require_timeframe_columns(quality, label="AlphaState.current.quality")

    return AlphaRows(
        spot=spot,
        observed_return=observed_return,
        regime=regime,
        cross_section=cross_section,
        forecast=forecast,
        quality=quality,
    )


def _build_lookback_rows(input_state: AlphaInput) -> AlphaLookbackRows:
    spot: dict[Lookback, float] = {}
    observed_return: dict[Lookback, float | None] = {}
    regime: dict[Lookback, RegimeState] = {}
    cross_section: dict[Lookback, CrossSectionState] = {}
    forecast: dict[Lookback, ForecastDistribution] = {}
    quality: dict[Lookback, DataQuality] = {}

    for lookback in LOOKBACKS:
        timeframe = LOOKBACK_TO_TIMEFRAME[lookback]
        bars = input_state.spy_bars[timeframe][:-1]
        constituents = _trim_constituents_one_bar(
            input_state.constituent_closes.get(timeframe, {})
        )
        cross = _cross_section(bars, constituents)
        spot[lookback] = bars[-1].close
        observed_return[lookback] = _return_over_bars(bars, 1)
        regime[lookback] = _regime_state(timeframe, bars)
        cross_section[lookback] = cross
        forecast[lookback] = _forecast_distribution(
            timeframe,
            bars,
            input_state.sample_lookback,
        )
        quality[lookback] = _quality(bars, cross, input_state.sample_lookback)

    require_lookback_columns(spot, label="AlphaState.lookback.spot")
    require_lookback_columns(observed_return, label="AlphaState.lookback.observed_return")
    require_lookback_columns(regime, label="AlphaState.lookback.regime")
    require_lookback_columns(cross_section, label="AlphaState.lookback.cross_section")
    require_lookback_columns(forecast, label="AlphaState.lookback.forecast")
    require_lookback_columns(quality, label="AlphaState.lookback.quality")

    return AlphaLookbackRows(
        spot=spot,
        observed_return=observed_return,
        regime=regime,
        cross_section=cross_section,
        forecast=forecast,
        quality=quality,
    )


class AlphaEngine:
    """Pure statistical engine: current and lookback matrices in one state."""

    version = ENGINE_VERSION

    def process(self, input_state: AlphaInput) -> AlphaState:
        _validate(input_state)
        return AlphaState(
            engine="ALPHA",
            engine_version=self.version,
            as_of=input_state.as_of,
            current=_build_current_rows(input_state),
            lookback=_build_lookback_rows(input_state),
            metadata={
                "authority": "measurement_and_statistical_forecast_only",
                "matrix_orientation": "rows=processing_units,columns=timeframes_or_lookbacks",
                "current_columns": "1m|5m|15m|30m|1h|4h|1d|3d|5d",
                "lookback_columns": "-1m|-5m|-15m|-30m|-1h|-4h|-1d|-3d|-5d",
                "lookback_semantics": "one_completed_matching_native_bar_earlier",
                "forecast_semantics": "one_completed_native_timeframe_bar_ahead",
                "return_units": "decimal_fraction",
            },
        )
