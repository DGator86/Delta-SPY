"""Gamma-SPY behavioral market engine.

Gamma estimates observable market-behavior states for downstream research/convergence. It has no
trading, position-sizing, broker, order-routing or execution authority.
"""

from .contracts import (
    Bar,
    BehavioralState,
    CatalystObservation,
    MarketInternals,
    MarketSnapshot,
    OptionObservation,
    Positioning,
)
from .engine import GammaBehavioralEngine
from .index_field import IndexBehavioralField, select_top_weight_mass, synthesize_index_field
from .universe import GammaUniverseEngine, UniverseBehavioralState

__all__ = [
    "Bar",
    "BehavioralState",
    "CatalystObservation",
    "GammaBehavioralEngine",
    "GammaUniverseEngine",
    "IndexBehavioralField",
    "MarketInternals",
    "MarketSnapshot",
    "OptionObservation",
    "Positioning",
    "UniverseBehavioralState",
    "select_top_weight_mass",
    "synthesize_index_field",
]
