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

This is model-neutral geometry. Alpha, Beta, and Gamma may supply numeric A/B values, but the bridge itself has no model opinion and no decision authority.

A is the prior matching native state at `t-T`. B is the current matching native state at `t`:

```text
A = (-T, A)
B = ( 0, B)
```

The observed straight line is:

```text
m = (B - A) / T
b = B
f(x) = m*x + B
```

Properties:

```text
f(-T) = A
f(0)  = B
```

Walking the same line forward exactly one more native period gives:

```text
f(+T) = B + (B - A)
       = 2B - A
```

The implementation exposes:

- endpoint coordinates and values;
- slope per minute;
- observed A->B change;
- arithmetic midpoint of the observed segment;
- arbitrary line evaluation with `value_at(x)`;
- segment interpolation with `interpolate(fraction)` where 0=A and 1=B;
- `forward_one_t_value` for the deliberately naive one-T continuation.

Intraday coordinates are expressed in minutes. Daily/multi-day coordinates use regular-session trading minutes:

```text
1d = 390 minutes
3d = 1170 minutes
5d = 1950 minutes
```

This keeps the geometry aligned with trading-session time instead of calendar weekends or closures.

The bridge is descriptive mathematics. Using `forward_one_t_value` is a baseline extrapolation processor, not a trading signal, strategy recommendation, or execution instruction.
