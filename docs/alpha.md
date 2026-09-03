# Alpha Engine v0.5

Alpha is a pure statistical market engine.

## Public interface

```text
AlphaInput -> AlphaEngine.process() -> AlphaState
```

Alpha accepts normalized observations only. It does not know about brokers, accounts,
positions, orders, strategies, Beta, Gamma, or Delta.

## Canonical current-state matrix

Every model in this repository uses the same fixed positive timeframe columns:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

Rows are processing units. Columns are timeframes.

Alpha rows:

```text
state / measurement       1m   5m  15m  30m   1h   4h   1d   3d   5d
spot                       x    x    x    x    x    x    x    x    x
observed_return            x    x    x    x    x    x    x    x    x
regime                     x    x    x    x    x    x    x    x    x
cross_section              x    x    x    x    x    x    x    x    x
forecast                   x    x    x    x    x    x    x    x    x
quality                    x    x    x    x    x    x    x    x    x
state_velocity             x    x    x    x    x    x    x    x    x
state_acceleration         x    x    x    x    x    x    x    x    x
persistence                x    x    x    x    x    x    x    x    x
regime_transition          x    x    x    x    x    x    x    x    x
forecast_drift             x    x    x    x    x    x    x    x    x
confidence_change          x    x    x    x    x    x    x    x    x
```

## Canonical lookback matrix

The lookback matrix uses the exact same row vocabulary and fixed negative columns:

```text
-1m | -5m | -15m | -30m | -1h | -4h | -1d | -3d | -5d
```

A negative lookback is native-bar based, not wall-clock subtraction. For example,
`-5m` is the 5-minute Alpha state as it existed one completed 5-minute bar earlier.
The lookback row is recomputed from information available at that cutoff.

## Canonical A -> B linear bridge

The shared platform pairs each negative lookback column with the matching positive
current-state column:

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

For any numeric Alpha component with A at `-T` and B at `+T`, the shared model-neutral
straight line is:

```text
m = (B - A) / (2T)
b = (A + B) / 2
f(x) = m*x + b
```

The bridge exposes endpoints, slope, midpoint/intercept, total change, arbitrary line
evaluation, and interpolation. It is shared core geometry rather than an Alpha opinion.
See `docs/linear_bridge.md`.

## Temporal dynamics rows

These rows measure change in Alpha's statistical state. They do not express a market
action.

### state_velocity
First differences over one matching native bar:

- trend-score delta;
- annualized realized-volatility delta;
- expected-return delta;
- probability-up delta;
- cross-sectional dispersion delta.

### state_acceleration
Second differences of those same state components. This is the change in velocity from
one native state transition to the next.

### persistence
Counts consecutive native bars for which the current trend regime, volatility regime,
and joint trend+volatility regime have persisted.

### regime_transition
Records the observed prior -> current trend and volatility regime labels and whether
either changed.

### forecast_drift
Measures change in the empirical forecast distribution versus the prior native state:
expected return, probability up, standard deviation, median, expected MFE, and expected
MAE.

### confidence_change
Records prior regime confidence, current regime confidence, and their delta.

When history is insufficient for a causal first or second difference, the matrix cell
still exists but unavailable numeric components remain `None`; Alpha never fabricates a
change measurement.

## Input

`AlphaInput` contains:

- `as_of`: information cutoff timestamp;
- `spy_bars`: normalized SPY OHLCV history for every positive canonical timeframe;
- `constituent_closes`: optional constituent histories by positive timeframe;
- `sample_lookback`: maximum completed historical native bars used for forecast cells.

Each timeframe series is strictly ordered oldest to newest. No bar may occur after
`as_of`.

## Forecast semantics

Each current forecast cell is one native timeframe period ahead. For example, the `1h`
cell describes the next completed one-hour period and the `5d` cell describes the next
completed five-day period.

Each lookback forecast cell is the forecast Alpha would have emitted at the historical
native cutoff using only information available then.

All return values are decimal fractions (`0.01 == 1%`).

## Causality

Current temporal dynamics compare the current state with prior native states. Lookback
temporal dynamics are themselves evaluated from earlier states, so a lookback velocity
or acceleration never reaches forward into the current state.

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

Those concepts remain outside the Alpha engine boundary.
