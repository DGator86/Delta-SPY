# Market Mechanics — Inertia Matrix

The Market Mechanics inertia surface uses the same nine canonical timeframes as the rest of Delta-SPY:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

Each timeframe column represents adjacent measurement windows rather than overlapping lookbacks.

For every native timeframe `T`:

```text
LOOKBACK   [-2T, -T]
CURRENT    [ -T,  0]
FORWARD    [  0, +T]
```

Examples:

```text
1m: lookback [-2m,-1m], current [-1m,0], forward [0,+1m]
5m: lookback [-10m,-5m], current [-5m,0], forward [0,+5m]
1h: lookback [-2h,-1h], current [-1h,0], forward [0,+1h]
5d: lookback [-10d,-5d], current [-5d,0], forward [0,+5d]
```

Day-scale windows use regular-session trading minutes internally: 1d=390, 3d=1170, 5d=1950.

## Rows

Directly estimated response-coefficient rows:

```text
beta_up
beta_down
beta_pp
beta_pm
beta_mp
beta_mm
```

Derived inertia rows:

```text
upside_inertia
downside_inertia
uptrend_braking_inertia
downtrend_braking_inertia
inertial_bias
```

Definitions:

```text
upside_inertia            = 1 / beta_up
downside_inertia          = 1 / beta_down
uptrend_braking_inertia   = 1 / abs(beta_pm)
downtrend_braking_inertia = 1 / abs(beta_mp)

inertial_bias =
    (downside_inertia - upside_inertia)
    / (downside_inertia + upside_inertia)
```

Nonpositive directional beta estimates are treated as unavailable rather than converted into fake negative inertia values.

## Phase-I causal beta estimator

`estimate_inertia_matrices()` accepts a synchronized stream of:

```text
trading_minute
log_price
net_force
```

`trading_minute` is a monotonic regular-session market clock. A complete regular session advances it by 390 minutes. This keeps weekend and closure time out of the mechanics geometry.

`log_price` must be a price estimate available live at that instant. Midpoint, microprice, or another causal efficient-price proxy is preferred over last-trade price.

`net_force` is a signed causal pressure input. In this first estimator it is supplied by the upstream pressure layer; this module does not yet claim that any particular force construction is correct.

The estimator derives velocity and acceleration causally from log price, then forms samples of the form:

```text
F_t, v_t  ->  a_(t+1)
```

The target acceleration is first observed after the force measurement. Same-period acceleration is not used as the response target.

For each non-overlapping timeframe window it fits:

```text
a_next = intercept + beta * F_t + velocity_control * v_t + error
```

separately for:

```text
positive force               -> beta_up
negative force               -> beta_down
v >= 0 and F > 0             -> beta_pp
v >= 0 and F < 0             -> beta_pm
v < 0 and F > 0              -> beta_mp
v < 0 and F < 0              -> beta_mm
```

Each coefficient carries its sample count and R-squared diagnostic. Insufficient samples remain unavailable rather than being filled.

By default, force, acceleration, and velocity are scaled within each window so the response coefficients are dimensionless and more comparable across regimes. Raw-unit estimation is retained for research and synthetic recovery tests.

## Linear walk-forward

The simple A->B one-T processor operates on the response coefficients, not directly on derived inertia.

For each beta row and timeframe:

```text
A = beta estimated from [-2T,-T]
B = beta estimated from [-T,0]
C = 2B - A
```

The forward inertia rows are then recomputed from C.

For example:

```text
beta_up(A) = 0.25
beta_up(B) = 0.50
beta_up(C) = 0.75

forward upside inertia = 1 / 0.75 = 1.3333...
```

The system explicitly does not compute:

```text
M(C) = 2*M(B) - M(A)
```

because inertia is mathematically dependent on the response coefficient. Walking beta and re-deriving inertia preserves the Market Mechanics model hierarchy.

## Current boundary

This is a Phase-I response estimator, not a validated market model. It estimates how a supplied causal pressure stream maps into subsequent price acceleration. The next empirical question is whether the supplied force construction is itself informative and whether the resulting inertia variables add out-of-sample information beyond raw force, liquidity, volatility, and conventional momentum.

The module has no action, trade, strategy, position, order, broker, sizing, or execution authority.
