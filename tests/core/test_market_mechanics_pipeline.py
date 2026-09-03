from __future__ import annotations

import math

from core.market_mechanics import INERTIA_ROWS, RESPONSE_ROWS
from core.market_mechanics_force import ForceState, ForceWeights, MicrostructureObservation
from core.market_mechanics_force_matrix import FORCE_ROWS, build_force_matrices
from core.market_mechanics_pipeline import (
    DERIVED_MECHANICS_ROWS,
    DIRECT_LINEAR_WALK_ROWS,
    build_market_mechanics_pipeline,
)
from core.timeframes import LOOKBACKS, TIMEFRAMES


def _force_state(t: float) -> ForceState:
    return ForceState(
        trading_minute=t,
        efficient_price=500.0,
        log_price=math.log(500.0),
        ofi_raw=t,
        ofi_pressure=t,
        trade_imbalance=t,
        depth_imbalance=t,
        replenishment_pressure=t,
        net_force=t,
        active_components=(
            "ofi",
            "trade_imbalance",
            "depth_imbalance",
            "replenishment",
        ),
    )


def test_force_rows_are_matricized_on_adjacent_nonoverlapping_windows() -> None:
    states = tuple(_force_state(float(t)) for t in range(-10, 1))
    matrices = build_force_matrices(states, as_of_trading_minute=0.0)

    assert tuple(matrices.lookback_windows) == LOOKBACKS
    assert tuple(matrices.current_windows) == TIMEFRAMES
    assert tuple(matrices.forward_windows) == TIMEFRAMES

    for row in FORCE_ROWS:
        assert tuple(matrices.lookback[row]) == LOOKBACKS
        assert tuple(matrices.current[row]) == TIMEFRAMES
        assert tuple(matrices.forward[row]) == TIMEFRAMES

        # 5m uses lookback (-10,-5] = {-9,-8,-7,-6,-5} and
        # current (-5,0] = {-4,-3,-2,-1,0}. No sample is shared.
        point_a = matrices.lookback[row]["-5m"]
        point_b = matrices.current[row]["5m"]
        point_c = matrices.forward[row]["5m"]
        assert point_a is not None
        assert point_b is not None
        assert point_c is not None
        assert math.isclose(point_a, -7.0)
        assert math.isclose(point_b, -2.0)
        assert math.isclose(point_c, 3.0)
        assert math.isclose(point_c, 2.0 * point_b - point_a)

    five_minute_lookback = matrices.lookback_windows["-5m"]
    five_minute_current = matrices.current_windows["5m"]
    five_minute_forward = matrices.forward_windows["5m"]
    assert (five_minute_lookback.start_minutes, five_minute_lookback.end_minutes) == (
        -10.0,
        -5.0,
    )
    assert (five_minute_current.start_minutes, five_minute_current.end_minutes) == (-5.0, 0.0)
    assert (five_minute_forward.start_minutes, five_minute_forward.end_minutes) == (0.0, 5.0)


def test_walkforward_dependency_sets_are_explicit() -> None:
    assert DIRECT_LINEAR_WALK_ROWS == FORCE_ROWS + RESPONSE_ROWS
    assert DERIVED_MECHANICS_ROWS == INERTIA_ROWS
    assert set(DIRECT_LINEAR_WALK_ROWS).isdisjoint(DERIVED_MECHANICS_ROWS)


def _trade_volumes(force: float) -> tuple[float, float]:
    base = 100.0
    return base * (1.0 + force), base * (1.0 - force)


def _synthetic_microstructure() -> tuple[MicrostructureObservation, ...]:
    times = list(range(-40, 1))
    force_pattern = (0.15, -0.35, 0.55, -0.75, 0.30, -0.60, 0.70, -0.20)
    forces = [force_pattern[index % len(force_pattern)] for index in range(len(times))]

    gamma = -0.03
    velocity = 0.0
    log_price = math.log(500.0)
    observations: list[MicrostructureObservation] = []

    for index, trading_minute in enumerate(times):
        price = math.exp(log_price)
        buy, sell = _trade_volumes(forces[index])
        observations.append(
            MicrostructureObservation(
                trading_minute=float(trading_minute),
                bid_price=price - 0.005,
                ask_price=price + 0.005,
                bid_size=100.0,
                ask_size=100.0,
                buyer_initiated_volume=buy,
                seller_initiated_volume=sell,
            )
        )
        if index == len(times) - 1:
            break

        beta = 0.0012 if trading_minute < -15 else 0.0024
        next_acceleration = beta * forces[index] + gamma * velocity
        velocity += next_acceleration
        log_price += velocity

    return tuple(observations)


def test_end_to_end_pipeline_exposes_force_and_inertia_matrices_with_correct_rules() -> None:
    pipeline = build_market_mechanics_pipeline(
        _synthetic_microstructure(),
        weights=ForceWeights(
            ofi=0.0,
            trade_imbalance=1.0,
            depth_imbalance=0.0,
            replenishment=0.0,
        ),
        price_mode="midpoint",
        min_direction_samples=5,
        min_quadrant_samples=3,
        standardize=False,
        ridge=1e-12,
    )

    for row in FORCE_ROWS:
        assert tuple(pipeline.force_matrices.lookback[row]) == LOOKBACKS
        assert tuple(pipeline.force_matrices.current[row]) == TIMEFRAMES
        assert tuple(pipeline.force_matrices.forward[row]) == TIMEFRAMES

    # The active force component is walked directly.
    force_a = pipeline.force_matrices.lookback["trade_imbalance"]["-15m"]
    force_b = pipeline.force_matrices.current["trade_imbalance"]["15m"]
    force_c = pipeline.force_matrices.forward["trade_imbalance"]["15m"]
    assert force_a is not None
    assert force_b is not None
    assert force_c is not None
    assert math.isclose(force_c, 2.0 * force_b - force_a, rel_tol=1e-12)

    # Beta is also walked directly.
    inertia = pipeline.inertia_estimation.matrices
    beta_a = inertia.lookback["beta_up"]["-15m"]
    beta_b = inertia.current["beta_up"]["15m"]
    beta_c = inertia.forward["beta_up"]["15m"]
    assert beta_a is not None
    assert beta_b is not None
    assert beta_c is not None
    assert math.isclose(beta_c, 2.0 * beta_b - beta_a, rel_tol=1e-12)

    # Inertia is not independently walked; it is re-derived from forward beta.
    inertia_c = inertia.forward["upside_inertia"]["15m"]
    assert inertia_c is not None
    assert math.isclose(inertia_c, 1.0 / beta_c, rel_tol=1e-12)

    inertia_a = inertia.lookback["upside_inertia"]["-15m"]
    inertia_b = inertia.current["upside_inertia"]["15m"]
    assert inertia_a is not None
    assert inertia_b is not None
    assert not math.isclose(inertia_c, 2.0 * inertia_b - inertia_a, rel_tol=1e-6, abs_tol=1e-6)
