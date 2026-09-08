from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Mapping

from .contracts import BehavioralState
from .universe import UniverseBehavioralState


@dataclass(frozen=True)
class IndexBehavioralField:
    index_symbol: str
    direct_balance: float
    constituent_balance: float
    field_divergence: float
    alignment: float
    constituent_squeeze_pressure: float
    constituent_liquidation_pressure: float
    constituent_volatility_pressure: float
    direct_gamma_regime: str
    direct_gamma_flip: float | None
    confidence: float
    quality: float
    interpretation: str

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "index_symbol": self.index_symbol,
            "direct_balance": self.direct_balance,
            "constituent_balance": self.constituent_balance,
            "field_divergence": self.field_divergence,
            "alignment": self.alignment,
            "constituent_squeeze_pressure": self.constituent_squeeze_pressure,
            "constituent_liquidation_pressure": self.constituent_liquidation_pressure,
            "constituent_volatility_pressure": self.constituent_volatility_pressure,
            "direct_gamma_regime": self.direct_gamma_regime,
            "direct_gamma_flip": self.direct_gamma_flip,
            "confidence": self.confidence,
            "quality": self.quality,
            "interpretation": self.interpretation,
        }


def select_top_weight_mass(
    weights: Mapping[str, float],
    *,
    fraction: float = 0.25,
) -> tuple[str, ...]:
    """Select the smallest descending-weight set reaching `fraction` of total index mass."""
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be within (0, 1]")
    cleaned = [(symbol.upper(), max(0.0, float(weight))) for symbol, weight in weights.items()]
    total = sum(weight for _, weight in cleaned)
    if total <= 0:
        return ()
    target = total * fraction
    cumulative = 0.0
    selected: list[str] = []
    for symbol, weight in sorted(cleaned, key=lambda row: row[1], reverse=True):
        if weight <= 0:
            continue
        selected.append(symbol)
        cumulative += weight
        if cumulative >= target:
            break
    return tuple(selected)


def synthesize_index_field(
    direct_state: BehavioralState,
    universe: UniverseBehavioralState,
) -> IndexBehavioralField:
    """Compare the direct index/ETF tape with the weighted behavioral field underneath it."""
    direct = direct_state.directional_balance
    constituents = universe.aggregate_bullish_pressure - universe.aggregate_bearish_pressure
    divergence = constituents - direct

    # Cosine-like directional agreement in one dimension, softened near zero where direction is weak.
    magnitude = sqrt(direct * direct + constituents * constituents)
    if magnitude < 1e-9:
        alignment = 0.0
    else:
        same_sign = 1.0 if direct * constituents > 0 else (-1.0 if direct * constituents < 0 else 0.0)
        strength = min(1.0, (abs(direct) + abs(constituents)) / 100.0)
        alignment = round(100.0 * same_sign * strength, 2)

    quality = round((direct_state.data_quality + universe.quality_weighted_coverage) / 2.0, 2)
    confidence = round(
        min(
            100.0,
            max(
                0.0,
                (direct_state.state_confidence * 0.5)
                + (universe.quality_weighted_coverage * 0.3)
                + (max(0.0, alignment) * 0.2),
            ),
        ),
        2,
    )

    squeeze = universe.aggregate_forced_behavior.short_squeeze
    liquidation = universe.aggregate_forced_behavior.long_liquidation
    vol = universe.aggregate_forced_behavior.volatility_expansion

    if direct > 15 and constituents > 15:
        interpretation = "direct_and_constituent_behavior_bullishly_aligned"
    elif direct < -15 and constituents < -15:
        interpretation = "direct_and_constituent_behavior_bearishly_aligned"
    elif abs(divergence) >= 25:
        interpretation = "index_constituent_behavioral_divergence"
    elif squeeze >= 65 and squeeze > liquidation:
        interpretation = "constituent_short_squeeze_field_elevated"
    elif liquidation >= 65 and liquidation > squeeze:
        interpretation = "constituent_long_liquidation_field_elevated"
    else:
        interpretation = "mixed_or_low_conviction_behavioral_field"

    return IndexBehavioralField(
        index_symbol=direct_state.symbol,
        direct_balance=round(direct, 2),
        constituent_balance=round(constituents, 2),
        field_divergence=round(divergence, 2),
        alignment=alignment,
        constituent_squeeze_pressure=round(squeeze, 2),
        constituent_liquidation_pressure=round(liquidation, 2),
        constituent_volatility_pressure=round(vol, 2),
        direct_gamma_regime=direct_state.gamma.gamma_regime,
        direct_gamma_flip=direct_state.gamma.gamma_flip,
        confidence=confidence,
        quality=quality,
        interpretation=interpretation,
    )
