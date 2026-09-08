from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import fmean


@dataclass(frozen=True)
class ScoreObservation:
    score: float
    outcome: bool


@dataclass(frozen=True)
class ReliabilityBin:
    low: float
    high: float
    count: int
    mean_score: float | None
    observed_rate: float | None


def reliability_bins(observations: list[ScoreObservation], bins: int = 10) -> list[ReliabilityBin]:
    """Summarize how an uncalibrated 0-100 research score relates to a pre-defined outcome."""
    if bins < 2:
        raise ValueError("bins must be >= 2")
    grouped: list[list[ScoreObservation]] = [[] for _ in range(bins)]
    for observation in observations:
        score = max(0.0, min(100.0, observation.score))
        idx = min(bins - 1, int(score / 100.0 * bins))
        grouped[idx].append(ScoreObservation(score=score, outcome=observation.outcome))
    result: list[ReliabilityBin] = []
    for idx, group in enumerate(grouped):
        low = idx * 100.0 / bins
        high = (idx + 1) * 100.0 / bins
        result.append(
            ReliabilityBin(
                low=low,
                high=high,
                count=len(group),
                mean_score=fmean(x.score for x in group) if group else None,
                observed_rate=fmean(float(x.outcome) for x in group) if group else None,
            )
        )
    return result


def brier_score(probabilities: list[float], outcomes: list[bool]) -> float:
    """Evaluate already-calibrated probabilities. Raw Gamma scores must not be passed directly."""
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be non-empty and equal length")
    if any(p < 0.0 or p > 1.0 for p in probabilities):
        raise ValueError("probabilities must be within [0, 1]")
    return fmean((p - float(y)) ** 2 for p, y in zip(probabilities, outcomes))


def wilson_interval(successes: int, count: int, z: float = 1.96) -> tuple[float, float]:
    if count <= 0:
        return 0.0, 1.0
    p = successes / count
    denom = 1.0 + z * z / count
    center = (p + z * z / (2.0 * count)) / denom
    margin = z * sqrt((p * (1.0 - p) + z * z / (4.0 * count)) / count) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def non_overlapping_indices(total: int, horizon_bars: int, offset: int = 0) -> list[int]:
    """Return deterministic anchor indices for dependence-aware primary evidence."""
    if horizon_bars <= 0:
        raise ValueError("horizon_bars must be positive")
    return list(range(max(0, offset), max(0, total), horizon_bars))
