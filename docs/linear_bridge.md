# Canonical A -> B Linear Bridge

The platform pairs each negative lookback column with its matching positive current-state column:

```text
-1m  ->  1m
-5m  ->  5m
-15m -> 15m
-30m -> 30m
-1h  ->  1h
-4h  ->  4h
-1d  ->  1d
-3d  ->  3d
-5d  ->  5d
```

A is the prior matching native state at `t-T`. B is the current matching native state at `t`.

For any numeric temporal component:

```text
m = (B - A) / T
f(x) = m*x + B
f(+T) = B + (B-A) = 2B-A
```

This same operation is applied component-wise to every numeric temporal item exposed by Alpha's current/lookback state surfaces. Examples include spot, observed return, regime scores and confidence, realized volatility, cross-sectional numeric measurements, forecast distribution statistics, data-quality numeric measurements, state velocity, state acceleration, persistence counts, forecast drift, and confidence change.

Strings, booleans, identifiers, labels, and warning collections are explicitly non-projectable. They are never coerced into numbers merely to make the line function run.

The look-forward matrix remains organized as:

```text
rows    = forward processors
columns = 1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

Its first processor row is `linear_ab_1t`. Each timeframe cell contains the full set of numeric component projections plus the non-projectable component paths for auditability.

Intraday coordinates are expressed in minutes. Daily/multi-day coordinates use regular-session trading minutes:

```text
1d = 390 minutes
3d = 1170 minutes
5d = 1950 minutes
```

This is model-neutral descriptive/extrapolative mathematics only. It is not a trade action, strategy, recommendation, or execution instruction.
