# Delta-SPY

A market-intelligence monorepo built around independent quantitative engines.

## Architecture rule

Alpha, Beta, and Gamma are independent engines housed in one repository. They may share model-neutral contracts, but they do not import or call one another. Their first point of convergence will be Delta.

Development begins with **Alpha only**.

## Canonical current-state matrix

Every model uses the same fixed positive columns:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

Rows are model-specific processing units.

## Canonical lookback matrix

Every model also uses the same fixed negative columns:

```text
-1m | -5m | -15m | -30m | -1h | -4h | -1d | -3d | -5d
```

The negative columns represent prior matching native states, not wall-clock subtraction.

## Canonical A -> B linear bridge

Each negative column pairs with the matching positive column:

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

For numeric values A at `-T` and B at `+T`, the shared model-neutral straight line is:

```text
m = (B - A) / (2T)
b = (A + B) / 2
f(x) = m*x + b
```

This bridge is descriptive mathematics only. It has no trade, strategy, risk, broker, or execution authority.

## Alpha principle

Alpha is a statistical market engine.

It accepts normalized historical market observations and emits a versioned statistical state. It has **no decision-making, strategy-selection, position-sizing, order, broker, or execution authority**.

Public contract:

```text
AlphaInput -> AlphaEngine -> AlphaState
```

Beta, Gamma, and Delta are intentionally not implemented yet.
