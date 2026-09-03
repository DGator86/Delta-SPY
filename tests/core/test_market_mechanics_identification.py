from __future__ import annotations

from core.market_mechanics_estimator import MechanicsObservation, estimate_inertia_matrices


def test_constant_force_subset_does_not_produce_fake_beta() -> None:
    observations = tuple(
        MechanicsObservation(
            trading_minute=float(index - 20),
            log_price=6.0 + 0.0001 * index + 0.000001 * index * index,
            net_force=0.5,
        )
        for index in range(21)
    )

    estimation = estimate_inertia_matrices(
        observations,
        min_direction_samples=3,
        min_quadrant_samples=3,
        standardize=False,
    )

    assert estimation.current_estimates["5m"].beta_up.value is None
    assert estimation.matrices.current["upside_inertia"]["5m"] is None
