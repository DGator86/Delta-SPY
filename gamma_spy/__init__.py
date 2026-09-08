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

__all__ = [
    "Bar",
    "BehavioralState",
    "CatalystObservation",
    "GammaBehavioralEngine",
    "MarketInternals",
    "MarketSnapshot",
    "OptionObservation",
    "Positioning",
]
