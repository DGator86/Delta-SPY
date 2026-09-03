from __future__ import annotations

import math

import pytest

from core.market_mechanics_estimator import MechanicsObservation, estimate_inertia_matrices
from core.timeframes import TIMEFRAMES


def _synthetic_mechanics() -> tuple[MechanicsObservation, ...]:
    """Generate exact causal dynamics with a known beta regime change at -15m."""

    dt = 0.125
    start = -3902.0
    steps = int((0.0 - start) / dt)
    velocity = 0.0
    log_price = math.log(600.0)
    output: list[MechanicsObservation] = []

    for index in range(steps + 1):
        trading_minute = start + index * dt
        phase = index % 16
        sign = 1.0 if phase < 8 else -1.0
        force = sign * (0.65 + 0.04 * (index % 7))
        output.append(
            MechanicsObservation(
                trading_minute=trading_minute,
                log_price=log_price,
                net_force=force,
            )
        )
        if index == steps:
            break

        if trading_minute < -15.0:
            beta_up = 0.30
            beta_down = 0.60
        else:
            beta_up = 0.80
            beta_down = 0.40

        beta = beta_up if force > 0.0 else beta_down
        next_acceleration = beta * force - 0.20 * velocity
        velocity = velocity + next_acceleration * dt
        log_price = log_price + velocity * dt

    return tuple(output)


def test_estimator_recovers_nonoverlapping_15m_beta_regimes_and_walks_forward() -> None:
    estimation = estimate_inertia_matrices(
        _synthetic_mechanics(),
        as_of_trading_minute=0.0,
        min_direction_samples=8,
        min_quadrant_samples=6,
        standardize=False,
        ridge=1e-10,
    )

    lookback = estimation.lookback_estimates["-15m"]
    current = estimation.current_estimates["15m"]

    assert lookback.beta_up.value == pytest.approx(0.30, abs=2e-4)
    assert lookback.beta_down.value == pytest.approx(0.60, abs=2e-4)
    assert current.beta_up.value == pytest.approx(0.80, abs=2e-4)
    assert current.beta_down.value == pytest.approx(0.40, abs=2e-4)
    assert lookback.beta_up.r_squared is not None and lookback.beta_up.r_squared > 0.999
    assert current.beta_up.r_squared is not None and current.beta_up.r_squared > 0.999

    matrices = estimation.matrices
    assert matrices.lookback["beta_up"]["-15m"] == pytest.approx(0.30, abs=2e-4)
    assert matrices.current["beta_up"]["15m"] == pytest.approx(0.80, abs=2e-4)
    assert matrices.forward["beta_up"]["15m"] == pytest.approx(1.30, abs=4e-4)
    assert matrices.current["upside_inertia"]["15m"] == pytest.approx(1.25, abs=5e-4)
    assert matrices.forward["upside_inertia"]["15m"] == pytest.approx(1.0 / 1.30, abs=5e-4)


def test_estimator_recovers_four_quadrant_response_when_samples_exist() -> None:
    estimation = estimate_inertia_matrices(
        _synthetic_mechanics(),
        as_of_trading_minute=0.0,
        min_direction_samples=8,
        min_quadrant_samples=6,
        standardize=False,
        ridge=1e-10,
    )
    current = estimation.current_estimates["15m"]

    assert current.beta_pp.value == pytest.approx(0.80, abs=3e-4)
    assert current.beta_mp.value == pytest.approx(0.80, abs=3e-4)
    assert current.beta_pm.value == pytest.approx(0.40, abs=3e-4)
    assert current.beta_mm.value == pytest.approx(0.40, abs=3e-4)
    assert estimation.matrices.current["uptrend_braking_inertia"]["15m"] == pytest.approx(
        2.5, abs=0.005
    )
    assert estimation.matrices.current["downtrend_braking_inertia"]["15m"] == pytest.approx(
        1.25, abs=0.005
    )


def test_default_standardization_produces_dimensionless_rectangular_estimates() -> None:
    estimation = estimate_inertia_matrices(
        _synthetic_mechanics(),
        as_of_trading_minute=0.0,
        min_direction_samples=8,
        min_quadrant_samples=6,
    )

    assert estimation.standardized is True
    for timeframe in TIMEFRAMES:
        estimate = estimation.current_estimates[timeframe]
        assert estimate.force_scale is not None
        assert estimate.acceleration_scale is not None
        assert estimate.velocity_scale is not None

    assert estimation.current_estimates["15m"].beta_up.value is not None
    assert estimation.current_estimates["15m"].beta_down.value is not None
    assert estimation.matrices.current["upside_inertia"]["15m"] is not None


def test_estimator_rejects_future_or_nonmonotonic_information() -> None:
    observations = _synthetic_mechanics()
    future = observations + (
        MechanicsObservation(trading_minute=0.125, log_price=observations[-1].log_price, net_force=1.0),
    )
    with pytest.raises(ValueError, match="beyond as_of"):
        estimate_inertia_matrices(future, as_of_trading_minute=0.0)

    bad_order = (observations[0], observations[2], observations[1], *observations[3:])
    with pytest.raises(ValueError, match="strictly increasing"):
        estimate_inertia_matrices(bad_order, as_of_trading_minute=0.0)


def test_estimator_never_uses_force_at_or_after_window_end_to_fit_that_window() -> None:
    observations = list(_synthetic_mechanics())
    estimation = estimate_inertia_matrices(
        tuple(observations),
        as_of_trading_minute=0.0,
        min_direction_samples=8,
        min_quadrant_samples=6,
        standardize=False,
        ridge=1e-10,
    )
    original = estimation.lookback_estimates["-15m"].beta_up.value

    # Alter only observations from -15m onward. The [-30,-15] lookback fit must not move.
    changed = [
        observation
        if observation.trading_minute < -15.0
        else MechanicsObservation(
            trading_minute=observation.trading_minute,
            log_price=observation.log_price,
            net_force=observation.net_force * 25.0,
        )
        for observation in observations
    ]
    changed_estimation = estimate_inertia_matrices(
        tuple(changed),
        as_of_trading_minute=0.0,
        min_direction_samples=8,
        min_quadrant_samples=6,
        standardize=False,
        ridge=1e-10,
    )
    assert changed_estimation.lookback_estimates["-15m"].beta_up.value == pytest.approx(
        original, abs=1e-10
    )
