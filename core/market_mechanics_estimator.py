from __future__ import annotations

import math
from dataclasses import dataclass

from .market_mechanics import InertiaMatrices, MechanicsWindow, build_inertia_matrices, mechanics_windows
from .timeframes import LOOKBACKS, TIMEFRAMES, Lookback, Timeframe


@dataclass(frozen=True, slots=True)
class MechanicsObservation:
    """One synchronized Market Mechanics observation on a trading-minute clock.

    ``trading_minute`` is monotonic regular-session market time. One full regular
    session advances this coordinate by 390 minutes, so weekends and closures do
    not create artificial elapsed mechanics time.

    ``log_price`` should be a causal efficient-price proxy (for example midpoint,
    microprice, or another live-available estimate). ``net_force`` is a signed,
    causal directional-pressure estimate. This estimator deliberately starts with
    one composite force; force decomposition can be added later without changing
    the response/inertia matrix contract.
    """

    trading_minute: float
    log_price: float
    net_force: float


@dataclass(frozen=True, slots=True)
class CoefficientFit:
    value: float | None
    samples: int
    r_squared: float | None


@dataclass(frozen=True, slots=True)
class ResponseWindowEstimate:
    """Auditable response-coefficient estimates for one mechanics window."""

    beta_up: CoefficientFit
    beta_down: CoefficientFit
    beta_pp: CoefficientFit
    beta_pm: CoefficientFit
    beta_mp: CoefficientFit
    beta_mm: CoefficientFit
    usable_samples: int
    force_scale: float | None
    acceleration_scale: float | None
    velocity_scale: float | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MechanicsEstimation:
    """Estimated response coefficients, derived inertia matrices, and diagnostics."""

    matrices: InertiaMatrices
    lookback_estimates: dict[Lookback, ResponseWindowEstimate]
    current_estimates: dict[Timeframe, ResponseWindowEstimate]
    as_of_trading_minute: float
    standardized: bool


@dataclass(frozen=True, slots=True)
class _KinematicSample:
    force_time: float
    target_time: float
    force: float
    velocity: float
    next_acceleration: float


def _sample_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    if variance <= 0.0:
        return None
    return math.sqrt(variance)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    n = len(vector)
    augmented = [row[:] + [rhs] for row, rhs in zip(matrix, vector, strict=True)]

    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= 1e-12:
            return None
        if pivot != column:
            augmented[column], augmented[pivot] = augmented[pivot], augmented[column]

        pivot_value = augmented[column][column]
        for j in range(column, n + 1):
            augmented[column][j] /= pivot_value

        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for j in range(column, n + 1):
                augmented[row][j] -= factor * augmented[column][j]

    return [augmented[row][n] for row in range(n)]


def _ols_force_response(
    samples: list[_KinematicSample],
    *,
    min_samples: int,
    force_scale: float,
    acceleration_scale: float,
    velocity_scale: float,
    ridge: float,
) -> CoefficientFit:
    """Fit a_next ~ intercept + beta*F_t + velocity_control*v_t."""

    if len(samples) < min_samples:
        return CoefficientFit(value=None, samples=len(samples), r_squared=None)

    rows: list[list[float]] = []
    targets: list[float] = []
    for sample in samples:
        rows.append(
            [
                1.0,
                sample.force / force_scale,
                sample.velocity / velocity_scale,
            ]
        )
        targets.append(sample.next_acceleration / acceleration_scale)

    p = 3
    xtx = [[0.0 for _ in range(p)] for _ in range(p)]
    xty = [0.0 for _ in range(p)]
    for row, target in zip(rows, targets, strict=True):
        for i in range(p):
            xty[i] += row[i] * target
            for j in range(p):
                xtx[i][j] += row[i] * row[j]

    for index in range(1, p):
        xtx[index][index] += ridge

    coefficients = _solve_linear_system(xtx, xty)
    if coefficients is None:
        return CoefficientFit(value=None, samples=len(samples), r_squared=None)

    predictions = [sum(c * x for c, x in zip(coefficients, row, strict=True)) for row in rows]
    target_mean = sum(targets) / len(targets)
    ss_tot = sum((target - target_mean) ** 2 for target in targets)
    ss_res = sum((target - prediction) ** 2 for target, prediction in zip(targets, predictions, strict=True))
    r_squared = None if ss_tot <= 1e-15 else 1.0 - ss_res / ss_tot

    return CoefficientFit(value=coefficients[1], samples=len(samples), r_squared=r_squared)


def _build_kinematic_samples(observations: tuple[MechanicsObservation, ...]) -> list[_KinematicSample]:
    velocities: list[float | None] = [None] * len(observations)
    accelerations: list[float | None] = [None] * len(observations)

    for index in range(1, len(observations)):
        previous = observations[index - 1]
        current = observations[index]
        dt = current.trading_minute - previous.trading_minute
        velocities[index] = (current.log_price - previous.log_price) / dt

    for index in range(2, len(observations)):
        previous_velocity = velocities[index - 1]
        current_velocity = velocities[index]
        if previous_velocity is None or current_velocity is None:
            continue
        dt = observations[index].trading_minute - observations[index - 1].trading_minute
        accelerations[index] = (current_velocity - previous_velocity) / dt

    output: list[_KinematicSample] = []
    for index in range(2, len(observations) - 1):
        velocity = velocities[index]
        next_acceleration = accelerations[index + 1]
        if velocity is None or next_acceleration is None:
            continue
        output.append(
            _KinematicSample(
                force_time=observations[index].trading_minute,
                target_time=observations[index + 1].trading_minute,
                force=observations[index].net_force,
                velocity=velocity,
                next_acceleration=next_acceleration,
            )
        )
    return output


def _estimate_window(
    samples: list[_KinematicSample],
    window: MechanicsWindow,
    *,
    as_of_trading_minute: float,
    min_direction_samples: int,
    min_quadrant_samples: int,
    standardize: bool,
    ridge: float,
) -> ResponseWindowEstimate:
    start = as_of_trading_minute + window.start_minutes
    end = as_of_trading_minute + window.end_minutes
    window_samples = [
        sample
        for sample in samples
        if sample.force_time >= start and sample.target_time <= end
    ]

    warnings: list[str] = []
    if not window_samples:
        warnings.append("no_usable_lagged_force_response_samples")

    force_scale = 1.0
    acceleration_scale = 1.0
    velocity_scale = 1.0
    if standardize and window_samples:
        estimated_force_scale = _sample_std([sample.force for sample in window_samples])
        estimated_acceleration_scale = _sample_std(
            [sample.next_acceleration for sample in window_samples]
        )
        estimated_velocity_scale = _sample_std([sample.velocity for sample in window_samples])
        if estimated_force_scale is None:
            warnings.append("force_scale_unavailable")
        else:
            force_scale = estimated_force_scale
        if estimated_acceleration_scale is None:
            warnings.append("acceleration_scale_unavailable")
        else:
            acceleration_scale = estimated_acceleration_scale
        if estimated_velocity_scale is None:
            warnings.append("velocity_scale_unavailable")
        else:
            velocity_scale = estimated_velocity_scale

    positive = [sample for sample in window_samples if sample.force > 0.0]
    negative = [sample for sample in window_samples if sample.force < 0.0]
    pp = [sample for sample in positive if sample.velocity >= 0.0]
    pm = [sample for sample in negative if sample.velocity >= 0.0]
    mp = [sample for sample in positive if sample.velocity < 0.0]
    mm = [sample for sample in negative if sample.velocity < 0.0]

    kwargs = {
        "force_scale": force_scale,
        "acceleration_scale": acceleration_scale,
        "velocity_scale": velocity_scale,
        "ridge": ridge,
    }
    return ResponseWindowEstimate(
        beta_up=_ols_force_response(positive, min_samples=min_direction_samples, **kwargs),
        beta_down=_ols_force_response(negative, min_samples=min_direction_samples, **kwargs),
        beta_pp=_ols_force_response(pp, min_samples=min_quadrant_samples, **kwargs),
        beta_pm=_ols_force_response(pm, min_samples=min_quadrant_samples, **kwargs),
        beta_mp=_ols_force_response(mp, min_samples=min_quadrant_samples, **kwargs),
        beta_mm=_ols_force_response(mm, min_samples=min_quadrant_samples, **kwargs),
        usable_samples=len(window_samples),
        force_scale=None if not window_samples else force_scale,
        acceleration_scale=None if not window_samples else acceleration_scale,
        velocity_scale=None if not window_samples else velocity_scale,
        warnings=tuple(warnings),
    )


def _validate_observations(
    observations: tuple[MechanicsObservation, ...],
    *,
    as_of_trading_minute: float,
) -> None:
    if len(observations) < 4:
        raise ValueError("Market Mechanics beta estimation requires at least four observations")

    previous_time: float | None = None
    for observation in observations:
        values = (observation.trading_minute, observation.log_price, observation.net_force)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Market Mechanics observations must contain only finite numeric values")
        if observation.trading_minute > as_of_trading_minute:
            raise ValueError("Market Mechanics observations may not extend beyond as_of_trading_minute")
        if previous_time is not None and observation.trading_minute <= previous_time:
            raise ValueError("Market Mechanics observations must be strictly increasing in trading time")
        previous_time = observation.trading_minute


def estimate_inertia_matrices(
    observations: tuple[MechanicsObservation, ...],
    *,
    as_of_trading_minute: float | None = None,
    min_direction_samples: int = 8,
    min_quadrant_samples: int = 6,
    standardize: bool = True,
    ridge: float = 1e-8,
) -> MechanicsEstimation:
    """Estimate directional/four-quadrant beta and derive all inertia matrices.

    Phase-I estimator semantics:

    * derive causal velocity and acceleration from log price;
    * use F_t and v_t only to estimate acceleration first observed at t+1;
    * estimate beta_up on positive-force samples and beta_down on negative-force samples;
    * estimate beta_pp/beta_pm/beta_mp/beta_mm by current velocity sign x force sign;
    * use adjacent non-overlapping windows [-2T,-T] and [-T,0];
    * linearly walk beta one T into [0,+T], then derive inertia from projected beta.

    No future observations, centered filters, trade decisions, or execution fields are used.
    """

    if min_direction_samples < 3 or min_quadrant_samples < 3:
        raise ValueError("minimum regression sample counts must be at least three")
    if ridge < 0.0:
        raise ValueError("ridge must be nonnegative")
    if not observations:
        raise ValueError("Market Mechanics observations are required")

    resolved_as_of = (
        observations[-1].trading_minute if as_of_trading_minute is None else as_of_trading_minute
    )
    _validate_observations(observations, as_of_trading_minute=resolved_as_of)
    kinematic_samples = _build_kinematic_samples(observations)
    lookback_windows, current_windows, _ = mechanics_windows()

    lookback_estimates: dict[Lookback, ResponseWindowEstimate] = {}
    current_estimates: dict[Timeframe, ResponseWindowEstimate] = {}

    for lookback, timeframe in zip(LOOKBACKS, TIMEFRAMES, strict=True):
        lookback_estimates[lookback] = _estimate_window(
            kinematic_samples,
            lookback_windows[lookback],
            as_of_trading_minute=resolved_as_of,
            min_direction_samples=min_direction_samples,
            min_quadrant_samples=min_quadrant_samples,
            standardize=standardize,
            ridge=ridge,
        )
        current_estimates[timeframe] = _estimate_window(
            kinematic_samples,
            current_windows[timeframe],
            as_of_trading_minute=resolved_as_of,
            min_direction_samples=min_direction_samples,
            min_quadrant_samples=min_quadrant_samples,
            standardize=standardize,
            ridge=ridge,
        )

    fit_names = ("beta_up", "beta_down", "beta_pp", "beta_pm", "beta_mp", "beta_mm")
    lookback_response: dict[str, dict[Lookback, float | None]] = {
        name: {} for name in fit_names
    }
    current_response: dict[str, dict[Timeframe, float | None]] = {
        name: {} for name in fit_names
    }

    for lookback, estimate in lookback_estimates.items():
        for name in fit_names:
            lookback_response[name][lookback] = getattr(estimate, name).value
    for timeframe, estimate in current_estimates.items():
        for name in fit_names:
            current_response[name][timeframe] = getattr(estimate, name).value

    matrices = build_inertia_matrices(
        lookback_response=lookback_response,
        current_response=current_response,
    )
    return MechanicsEstimation(
        matrices=matrices,
        lookback_estimates=lookback_estimates,
        current_estimates=current_estimates,
        as_of_trading_minute=resolved_as_of,
        standardized=standardize,
    )
