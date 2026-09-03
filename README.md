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

Rows are model-specific processing units. Columns are those nine native timeframes.
Every model ingests all nine native timeframe series and emits every processing row
across those same nine columns.

## Canonical lookback matrix

Every model also uses the same fixed negative lookback columns:

```text
-1m | -5m | -15m | -30m | -1h | -4h | -1d | -3d | -5d
```

The lookback matrix has the same row vocabulary as the current-state matrix. A negative
column means the matching native processing state one completed bar earlier, not raw
wall-clock subtraction.

## Alpha principle

Alpha is a statistical market engine.

It accepts normalized historical market observations and emits versioned current and
lookback statistical matrices. It has **no decision-making, strategy-selection,
position-sizing, order, broker, or execution authority**.

Public contract:

```text
AlphaInput -> AlphaEngine -> AlphaState
```

Beta, Gamma, and Delta are intentionally not implemented yet.
