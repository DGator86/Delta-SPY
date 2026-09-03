# Delta-SPY

A market-intelligence monorepo built around independent quantitative engines.

## Architecture rule

Alpha, Beta, and Gamma are independent engines housed in one repository. They may share infrastructure later, but they do not import or call one another. Their first point of convergence will be Delta.

Development begins with **Alpha only**.

## Alpha principle

Alpha is a statistical market engine.

It accepts normalized historical market observations and emits a versioned statistical state. It has **no decision-making, strategy-selection, position-sizing, order, broker, or execution authority**.

Public contract:

```text
AlphaInput -> AlphaEngine -> AlphaState
```

Beta, Gamma, and Delta are intentionally not implemented yet.
