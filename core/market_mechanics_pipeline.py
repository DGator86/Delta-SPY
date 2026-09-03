from __future__ import annotations

from dataclasses import dataclass

from .market_mechanics import INERTIA_ROWS, RESPONSE_ROWS
from .market_mechanics_estimator import MechanicsEstimation, estimate_inertia_matrices
from .market_mechanics_force import (
    ForceState,
    ForceWeights,
    MicrostructureObservation,
    PriceMode,
    build_micro_force,
    to_mechanics_observations,
)
from .market_mechanics_force_matrix import FORCE_ROWS, ForceMatrices, build_force_matrices

DIRECT_LINEAR_WALK_ROWS: tuple[str, ...] = FORCE_ROWS + RESPONSE_ROWS
DERIVED_MECHANICS_ROWS: tuple[str, ...] = INERTIA_ROWS


@dataclass(frozen=True, slots=True)
class MarketMechanicsPipeline:
    """Causal force -> response -> inertia pipeline with explicit walk-forward rules."""

    force_states: tuple[ForceState, ...]
    force_matrices: ForceMatrices
    inertia_estimation: MechanicsEstimation
    direct_linear_walk_rows: tuple[str, ...] = DIRECT_LINEAR_WALK_ROWS
    derived_rows: tuple[str, ...] = DERIVED_MECHANICS_ROWS


def build_market_mechanics_pipeline(
    observations: tuple[MicrostructureObservation, ...],
    *,
    weights: ForceWeights | None = None,
    price_mode: PriceMode = "microprice",
    as_of_trading_minute: float | None = None,
    min_direction_samples: int = 8,
    min_quadrant_samples: int = 6,
    standardize: bool = True,
    ridge: float = 1e-8,
) -> MarketMechanicsPipeline:
    """Build the currently implemented Market Mechanics matrices end to end.

    Direct one-T AB walk-forward:
    - OFI pressure
    - aggressive trade imbalance
    - depth imbalance
    - replenishment pressure
    - net force
    - all six response beta coefficients

    Recomputed from walked-forward beta rather than independently extrapolated:
    - upside/downside inertia
    - uptrend/downtrend braking inertia
    - inertial bias
    """

    force_states = build_micro_force(
        observations,
        weights=weights,
        price_mode=price_mode,
    )
    resolved_as_of = (
        force_states[-1].trading_minute
        if as_of_trading_minute is None
        else as_of_trading_minute
    )
    force_matrices = build_force_matrices(
        force_states,
        as_of_trading_minute=resolved_as_of,
    )
    inertia_estimation = estimate_inertia_matrices(
        to_mechanics_observations(force_states),
        as_of_trading_minute=resolved_as_of,
        min_direction_samples=min_direction_samples,
        min_quadrant_samples=min_quadrant_samples,
        standardize=standardize,
        ridge=ridge,
    )
    return MarketMechanicsPipeline(
        force_states=force_states,
        force_matrices=force_matrices,
        inertia_estimation=inertia_estimation,
    )
