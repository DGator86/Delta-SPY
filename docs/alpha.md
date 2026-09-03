# Alpha Engine v0.3

Alpha is a pure statistical market engine.

## Public interface

```text
AlphaInput -> AlphaEngine.process() -> AlphaState
```

Alpha accepts normalized observations only. It does not know about Tradier, brokers,
accounts, positions, orders, strategies, Beta, Gamma, or Delta.

## Canonical current-state matrix

Every model in this repository will use the same fixed positive timeframe columns:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

Rows are processing units. Columns are timeframes.

For Alpha, the current rows are:

```text
                    1m   5m   15m   30m   1h   4h   1d   3d   5d
spot                 x    x     x     x    x    x    x    x    x
observed_return      x    x     x     x    x    x    x    x    x
regime               x    x     x     x    x    x    x    x    x
cross_section        x    x     x     x    x    x    x    x    x
forecast             x    x     x     x    x    x    x    x    x
quality              x    x     x     x    x    x    x    x    x
```

The nine-column shape is mandatory. Missing SPY timeframe columns are rejected.

## Canonical lookback matrix

Alpha also emits a second matrix with the exact same processing rows and negative
lookback columns:

```text
-1m | -5m | -15m | -30m | -1h | -4h | -1d | -3d | -5d
```

```text
                   -1m  -5m  -15m  -30m  -1h  -4h  -1d  -3d  -5d
spot                 x    x     x     x     x     x     x     x     x
observed_return      x    x     x     x     x     x     x     x     x
regime               x    x     x     x     x     x     x     x     x
cross_section        x    x     x     x     x     x     x     x     x
forecast             x    x     x     x     x     x     x     x     x
quality              x    x     x     x     x     x     x     x     x
```

A negative lookback is not wall-clock subtraction. It is the same native processing
state evaluated one completed matching bar earlier:

- `-1m`: 1-minute state one completed 1-minute bar ago.
- `-5m`: 5-minute state one completed 5-minute bar ago.
- `-15m`: 15-minute state one completed 15-minute bar ago.
- `-30m`: 30-minute state one completed 30-minute bar ago.
- `-1h`: 1-hour state one completed 1-hour bar ago.
- `-4h`: 4-hour state one completed 4-hour bar ago.
- `-1d`: daily state one completed daily bar ago.
- `-3d`: 3-day state one completed 3-day bar ago.
- `-5d`: 5-day state one completed 5-day bar ago.

This preserves market-session semantics across weekends and closures and makes the
lookback state causal and replayable.

## Input

`AlphaInput` contains:

- `as_of`: information cutoff timestamp.
- `spy_bars`: normalized SPY OHLCV history for every positive canonical timeframe.
- `constituent_closes`: optional constituent histories, organized by positive timeframe.
- `sample_lookback`: maximum completed historical native bars used for each forecast cell.

Each timeframe series is strictly ordered oldest to newest. No bar may occur after
`as_of`. At least two bars are required in each timeframe so the matching historical
lookback cell can be computed without fabrication.

## Output

`AlphaState` contains:

- `current`: `AlphaRows` across the nine positive timeframe columns.
- `lookback`: `AlphaLookbackRows` across the nine negative lookback columns.

Both matrices expose the same row vocabulary.

For each current timeframe Alpha emits:

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

The lookback matrix recomputes those same processing units from the historical data
cutoff rather than copying today's reading backward.

Therefore the current `5m` forecast cell means the next completed five-minute bar from
now, while the `-5m` forecast cell is the forecast distribution Alpha would have
published at the prior completed five-minute cutoff.

All return values are decimal fractions (`0.01 == 1%`).

## Causality

Forecast distributions use only completed historical native-timeframe bars ending on
or before the relevant current or lookback cutoff. No future bar relative to a state
cutoff is used.

Later Alpha research may add walk-forward conditional models, lifecycle/survival
models, richer covariance structures, and calibrated uncertainty. Those additions must
preserve both matrices and remain statistical outputs rather than decisions.

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
