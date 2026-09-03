# Alpha Engine v0.2

Alpha is a pure statistical market engine.

## Public interface

```text
AlphaInput -> AlphaEngine.process() -> AlphaState
```

Alpha accepts normalized observations only. It does not know about Tradier, brokers,
accounts, positions, orders, strategies, Beta, Gamma, or Delta.

## Canonical matrix

Every model in this repository will use the same fixed timeframe columns:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d
```

Rows are processing units. Columns are timeframes.

For Alpha, the current rows are:

```text
                    1m   5m   15m   30m   1h   4h   1d
spot                 x    x     x     x    x    x    x
observed_return      x    x     x     x    x    x    x
regime               x    x     x     x    x    x    x
cross_section        x    x     x     x    x    x    x
forecast             x    x     x     x    x    x    x
quality              x    x     x     x    x    x    x
```

The seven-column shape is mandatory. Missing SPY timeframe columns are rejected.

## Input

`AlphaInput` contains:

- `as_of`: information cutoff timestamp.
- `spy_bars`: normalized SPY OHLCV history for every canonical timeframe.
- `constituent_closes`: optional constituent histories, organized by timeframe.
- `sample_lookback`: maximum completed historical native bars used for each forecast cell.

Each timeframe series is strictly ordered oldest to newest. No bar may occur after
`as_of`.

## Output

`AlphaState` contains one `AlphaRows` matrix. Every processing row contains the same
seven timeframe keys.

For each timeframe Alpha emits:

- latest completed spot value;
- latest native-bar observed return;
- statistical trend/volatility regime;
- annualized realized volatility and volatility percentile;
- constituent correlation/covariance/dispersion when supplied;
- empirical one-native-bar-ahead return distribution;
- probability of positive terminal return;
- expected return and standard deviation;
- 5th/25th/50th/75th/95th return quantiles;
- expected historical maximum favorable excursion (MFE);
- expected historical maximum adverse excursion (MAE);
- explicit data-quality state.

Therefore the `5m` forecast cell means the next completed five-minute bar, the `1h`
forecast cell means the next completed one-hour bar, and the `1d` cell means the next
completed daily bar. The same semantic rule applies across all seven columns.

All return values are decimal fractions (`0.01 == 1%`).

## Causality

Forecast distributions use only completed historical native-timeframe bars ending on
or before the input cutoff. No future bar relative to `as_of` is accepted.

Later Alpha research may add walk-forward conditional models, lifecycle/survival
models, richer covariance structures, and calibrated uncertainty. Those additions must
preserve the seven-column matrix and remain statistical outputs rather than decisions.

## Prohibited responsibilities

Alpha never emits or accepts:

- trade actions;
- long/short recommendations;
- strategy or option-structure selection;
- strike selection;
- position sizing;
- entry/exit instructions;
- account state;
- broker instructions;
- order or execution state.

Those concepts are outside the Alpha engine boundary.
