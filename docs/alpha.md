# Alpha Engine v0.1

Alpha is a pure statistical market engine.

## Public interface

```text
AlphaInput -> AlphaEngine.process() -> AlphaState
```

Alpha accepts normalized observations only. It does not know about Tradier, brokers,
accounts, positions, orders, strategies, Beta, Gamma, or Delta.

## Input

`AlphaInput` contains:

- `as_of`: information cutoff timestamp.
- `spy_bars`: strictly ordered normalized SPY OHLCV bars, oldest to newest.
- `constituent_closes`: optional aligned constituent close histories, oldest to newest.
- `horizons`: statistical forecast horizons, default 5/15/30 minutes.
- `sample_lookback`: maximum number of completed historical anchors used per horizon.

No bar may occur after `as_of`.

## Output

`AlphaState` contains only measurements and statistical forecasts:

- spot and recent SPY returns;
- statistical trend/volatility regime;
- realized volatility and volatility percentile;
- constituent correlation/covariance/dispersion when supplied;
- empirical 5/15/30-minute return distributions;
- probability of positive terminal return;
- expected return and standard deviation;
- 5th/25th/50th/75th/95th return quantiles;
- expected historical maximum favorable excursion (MFE);
- expected historical maximum adverse excursion (MAE);
- explicit data-quality state.

All return values are decimal fractions (`0.01 == 1%`).

## Causality

Forecast distributions use only completed historical paths that end on or before the
input cutoff. No future bar relative to `as_of` is accepted.

v0.1 is intentionally transparent and unconditional. Later Alpha research may add
walk-forward conditional models, lifecycle/survival models, covariance structures,
and calibrated uncertainty, but those remain Alpha statistical outputs rather than
trade decisions.

## Prohibited responsibilities

Alpha never emits or accepts:

- trade actions;
- long/short recommendations;
- strategy or option-structure selection;
- strike selection;
- position size;
- entry/exit instructions;
- account state;
- broker instructions;
- order or execution state.

Those concepts are outside the Alpha engine boundary.
