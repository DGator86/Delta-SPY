# Market Mechanics — Phase-I Force Engine

The first Market Mechanics force engine constructs a causal SPY microstructure pressure stream. It is intentionally transparent and decomposed.

## Input

Each `MicrostructureObservation` contains information known at one monotonic regular-session `trading_minute`:

- best bid / ask price
- best bid / ask size
- optional buyer-initiated / seller-initiated volume
- optional bid / ask additions and cancellations

The force engine never uses future observations.

## Efficient price

Two causal price modes are supported:

```text
midpoint   = (bid + ask) / 2
microprice = (ask * bid_size + bid * ask_size) / (bid_size + ask_size)
```

Microprice is the default. The selected efficient-price proxy is converted to log price for the inertia estimator.

## Force components

### 1. Best-quote order-flow imbalance

A Cont-style best-quote event increment is computed from the previous and current quote state. Bid improvement/size gain contributes bullish pressure; bid deterioration contributes bearish pressure. Ask deterioration/removal contributes bullish pressure; ask improvement/size gain contributes bearish pressure.

Raw OFI is normalized by average total quoted depth across the two observations.

### 2. Signed aggressive trade imbalance

```text
trade_imbalance = (buyer_volume - seller_volume) / (buyer_volume + seller_volume)
```

This component is unavailable when aggressor-classified volume is unavailable.

### 3. Static depth imbalance

```text
depth_imbalance = (bid_size - ask_size) / (bid_size + ask_size)
```

This is a book-state pressure feature, not inertia itself.

### 4. Liquidity replenishment / cancellation pressure

Bullish liquidity events:

- bid additions
- ask cancellations

Bearish liquidity events:

- ask additions
- bid cancellations

```text
replenishment_pressure =
    (bullish_events - bearish_events)
    / total_liquidity_events
```

This component is unavailable when explicit add/cancel information is unavailable.

## Net force

The Phase-I composite is deliberately simple:

```text
net_force = sum(weight_i * component_i) / sum(abs(weight_i))
```

Only available, nonzero-weight components participate. Default weights are all `1.0`; they are a transparent baseline, not a claim of optimality.

Every output preserves the components separately:

```text
ofi_raw
ofi_pressure
trade_imbalance
depth_imbalance
replenishment_pressure
net_force
active_components
```

This allows every component and the composite to be kill-tested independently.

## Force matrices

Every time-dependent force row is now matricized across the same nine canonical timeframes:

```text
1m | 5m | 15m | 30m | 1h | 4h | 1d | 3d | 5d
```

with the same adjacent non-overlapping geometry:

```text
LOOKBACK = [-2T,-T]
CURRENT  = [-T,0]
FORWARD  = [0,+T]
```

The direct force rows are:

```text
ofi_pressure
trade_imbalance
depth_imbalance
replenishment_pressure
net_force
```

For each row and timeframe, A is the mean causal pressure state in the lookback window and B is the mean causal pressure state in the current window. The first forward processor walks the row one native T:

```text
C = 2B - A
```

Window samples use `(start,end]`, so adjacent windows share no force observations while the current window still includes the as-of state.

## Walk-forward dependency rule

The currently implemented direct AB rows are exactly:

```text
force rows + response-beta rows
```

That means the five force rows above and:

```text
beta_up
beta_down
beta_pp
beta_pm
beta_mp
beta_mm
```

are linearly walked one T.

Inertia is dependent state and is not independently extrapolated. Forward inertia is recomputed from forward beta:

```text
beta_C = 2B - A
M_C    = 1 / beta_C
```

The pipeline publishes this dependency split explicitly as `DIRECT_LINEAR_WALK_ROWS` and `DERIVED_MECHANICS_ROWS`.

## Direct inertia integration

`ForceState` adapts directly into the Phase-I response estimator as:

```text
trading_minute
efficient log price
net_force
```

The estimator then uses the causal relation:

```text
F_t, v_t -> a_(t+1)
```

inside the same non-overlapping mechanics windows.

`build_market_mechanics_pipeline()` now returns the raw force states, the three force matrices, and the response/inertia estimation from one causal microstructure input stream.

## Identification safeguard

A beta coefficient is not reported when the relevant force subset has no variation. A constant-force sample cannot identify responsiveness, even if regularized regression can numerically return a coefficient.

## Boundary

This is a baseline force construction for research. It does not establish that equal weighting is optimal, that each component is independently predictive, or that the resulting inertia state adds information beyond OFI, depth, volatility, or conventional momentum.

Future challengers should include learned or regime-conditioned weights, cross-market pressure, basket pressure, and options-derived pressure only after strict causal walk-forward validation.

No trade, strategy, order, position, sizing, broker, or execution authority exists in this module.
