# Delta-SPY

A market-intelligence monorepo built around independent quantitative engines.

## Architecture rule

Alpha, Beta, and Gamma are independent engines housed in one repository. They may share model-neutral contracts, but they do not import or call one another. Their first point of convergence will be Delta.

Development begins with **Alpha only**.

## Canonical timeframe matrix

Every model uses the same fixed columns:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d
```

Rows are model-specific processing units. Columns are always those seven timeframes.
A model therefore ingests all seven native timeframe series and emits every processing
row across those same seven columns.

## Alpha principle

Alpha is a statistical market engine.

It accepts normalized historical market observations and emits a versioned statistical state. It has **no decision-making, strategy-selection, position-sizing, order, broker, or execution authority**.

Public contract:

```text
AlphaInput -> AlphaEngine -> AlphaState
```

Beta, Gamma, and Delta are intentionally not implemented yet.
