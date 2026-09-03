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

For any numeric component with point A = `(-T, A)` and point B = `(+T, B)`, the unique straight line is:

```text
m = (B - A) / (2T)
b = (A + B) / 2
f(x) = m*x + b
```

Properties:

```text
f(-T) = A
f(0)  = (A + B) / 2
f(+T) = B
```

The implementation exposes:

- endpoint coordinates;
- endpoint values;
- slope per minute;
- intercept / midpoint value;
- total A->B change;
- arbitrary line evaluation with `value_at(x)`;
- segment interpolation with `interpolate(fraction)` where 0=A and 1=B.

Intraday coordinates are expressed in minutes. Daily/multi-day coordinates use regular-session trading minutes:

```text
1d = 390 minutes
3d = 1170 minutes
5d = 1950 minutes
```

This keeps the geometry aligned with trading-session time instead of calendar weekends or closures.

The bridge is descriptive mathematics only. It is not an extrapolation mandate, trading signal, recommendation, or execution instruction.
