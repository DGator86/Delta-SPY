# Market Mechanics — Inertia Matrix

The Market Mechanics inertia surface uses the same nine canonical timeframes as the rest of Delta-SPY:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

The key distinction is that each timeframe column represents an adjacent measurement window rather than an overlapping lookback.

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

This module provides geometry and deterministic transformation only. It does not yet estimate beta from order flow, liquidity, or price data, and it has no trade or execution authority.
