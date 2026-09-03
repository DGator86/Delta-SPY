from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from itertools import pairwise

from .contracts import (
    AlphaInput,
    AlphaState,
    CrossSectionState,
    DataQuality,
    ForecastDistribution,
    PriceBar,
    RegimeState,
)

ENGINE_VERSION = "alpha-0.1.0"
TRADING_MINUTES_PER_YEAR = 252 * 390


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


def _rolling_horizon_samples(
    bars: Sequence[PriceBar],
    horizon: int,
    lookback: int,
) -> tuple[list[float], list[float], list[float]]:
    returns: list[float] = []
    mfes: list[float] = []
    maes: list[float] = []
    if horizon <= 0 or len(bars) <= horizon:
        return returns, mfes, maes
    first_anchor = max(0, len(bars) - horizon - max(lookback, 1))
    for anchor in range(first_anchor, len(bars) - horizon):
        start = bars[anchor].close
        if start <= 0:
            continue
        path = bars[anchor + 1 : anchor + horizon + 1]
        terminal = _simple_return(start, path[-1].close)
        if terminal is None:
            continue
        highs = [bar.high for bar in path if bar.high > 0]
        lows = [bar.low for bar in path if bar.low > 0]
        if not highs or not lows:
            continue
        returns.append(terminal)
        mfes.append(max(highs) / start - 1.0)
        maes.append(min(lows) / start - 1.0)
    return returns, mfes, maes


def _forecast_distribution(
    bars: Sequence[PriceBar],
    horizon: int,
    lookback: int,
) -> ForecastDistribution:
    returns, mfes, maes = _rolling_horizon_samples(bars, horizon, lookback)
    probability_up = sum(value > 0 for value in returns) / len(returns) if returns else None
    return ForecastDistribution(
        horizon_minutes=horizon,
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


def _realized_volatility_annualized(bars: Sequence[PriceBar], window: int = 20) -> float | None:
    closes = [bar.close for bar in bars if bar.close > 0]
    returns = _returns_from_closes(closes)
    if len(returns) < 2:
        return None
    recent = returns[-window:]
    sigma = _sample_std(recent)
    if sigma is None:
        return None
    return sigma * math.sqrt(TRADING_MINUTES_PER_YEAR)


def _rolling_volatility_history(bars: Sequence[PriceBar], window: int = 20) -> list[float]:
    closes = [bar.close for bar in bars if bar.close > 0]
    returns = _returns_from_closes(closes)
    output: list[float] = []
    if len(returns) < window:
        return output
    for end in range(window, len(returns) + 1):
        sigma = _sample_std(returns[end - window : end])
        if sigma is not None:
            output.append(sigma * math.sqrt(TRADING_MINUTES_PER_YEAR))
    return output


def _percentile_rank(history: Sequence[float], value: float | None) -> float | None:
    if value is None or not history:
        return None
    return sum(item <= value for item in history) / len(history)


def _return_over_bars(bars: Sequence[PriceBar], periods: int) -> float | None:
    if periods <= 0 or len(bars) <= periods:
        return None
    return _simple_return(bars[-1 - periods].close, bars[-1].close)


def _regime_state(bars: Sequence[PriceBar]) -> RegimeState:
    realized = _realized_volatility_annualized(bars, 20)
    vol_history = _rolling_volatility_history(bars, 20)
    percentile = _percentile_rank(vol_history[:-1] or vol_history, realized)

    one_minute_returns = _returns_from_closes([bar.close for bar in bars if bar.close > 0])
    recent_sigma = _sample_std(one_minute_returns[-60:])
    return_15m = _return_over_bars(bars, 15)
    trend_score: float | None = None
    if return_15m is not None and recent_sigma is not None and recent_sigma > 0:
        trend_score = return_15m / (recent_sigma * math.sqrt(15.0))

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
        realized_volatility_20m_annualized=realized,
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


def _cross_section(input_state: AlphaInput) -> CrossSectionState:
    spy_returns = _returns_from_closes([bar.close for bar in input_state.spy_bars])
    correlations: list[float] = []
    covariances: list[float] = []
    latest_returns: list[float] = []
    aligned_symbols = 0

    for closes in input_state.constituent_closes.values():
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


def _quality(input_state: AlphaInput, cross_section: CrossSectionState) -> DataQuality:
    bars = len(input_state.spy_bars)
    usable_returns = max(0, bars - 1)
    warnings: list[str] = []
    if bars < 31:
        warnings.append("insufficient_spy_history_for_full_30m_state")
    if cross_section.symbol_count == 0:
        warnings.append("cross_section_unavailable")
    completeness = min(1.0, usable_returns / 390.0)
    return DataQuality(
        bars_received=bars,
        usable_returns=usable_returns,
        aligned_constituents=cross_section.symbol_count,
        completeness=completeness,
        warnings=tuple(warnings),
    )


def _validate(input_state: AlphaInput) -> None:
    if not input_state.spy_bars:
        raise ValueError("AlphaInput.spy_bars must not be empty")
    previous_timestamp = None
    for bar in input_state.spy_bars:
        if bar.close <= 0 or bar.high <= 0 or bar.low <= 0 or bar.open <= 0:
            raise ValueError("SPY bars must contain positive OHLC prices")
        if bar.low > min(bar.open, bar.close, bar.high):
            raise ValueError("SPY bar low is inconsistent with OHLC")
        if bar.high < max(bar.open, bar.close, bar.low):
            raise ValueError("SPY bar high is inconsistent with OHLC")
        if bar.timestamp > input_state.as_of:
            raise ValueError("SPY bar timestamp is after AlphaInput.as_of")
        if previous_timestamp is not None and bar.timestamp <= previous_timestamp:
            raise ValueError("SPY bars must be strictly time ordered")
        previous_timestamp = bar.timestamp
    if any(horizon <= 0 for horizon in input_state.horizons):
        raise ValueError("forecast horizons must be positive integers")


class AlphaEngine:
    """Pure statistical engine: normalized observations in, AlphaState out."""

    version = ENGINE_VERSION

    def process(self, input_state: AlphaInput) -> AlphaState:
        _validate(input_state)
        bars = input_state.spy_bars
        cross_section = _cross_section(input_state)
        forecasts = tuple(
            _forecast_distribution(bars, horizon, input_state.sample_lookback)
            for horizon in sorted(set(input_state.horizons))
        )
        return AlphaState(
            engine="ALPHA",
            engine_version=self.version,
            as_of=input_state.as_of,
            spot=bars[-1].close,
            return_1m=_return_over_bars(bars, 1),
            return_5m=_return_over_bars(bars, 5),
            return_15m=_return_over_bars(bars, 15),
            regime=_regime_state(bars),
            cross_section=cross_section,
            forecasts=forecasts,
            quality=_quality(input_state, cross_section),
            metadata={
                "authority": "measurement_and_statistical_forecast_only",
                "input_contract": "AlphaInput",
                "output_contract": "AlphaState",
                "return_units": "decimal_fraction",
            },
        )
