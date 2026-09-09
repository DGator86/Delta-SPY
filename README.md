# Delta-SPY

A market-intelligence monorepo built around independent quantitative engines that converge only at Delta.

## Architecture rule

Alpha, Beta, and Gamma are independent engines. They may share normalized infrastructure, but they do **not** import or call one another. Their first point of convergence is Delta.

```text
AlphaState -----+
                |
BetaState ------+--> Delta --> downstream analytical consumers
                |
GammaState -----+
```

No engine gets broker, order-routing or execution authority inside this architecture.

## Engine responsibilities

### Alpha

Statistical market engine.

```text
AlphaInput -> AlphaEngine -> AlphaState
```

### Beta

Independent complementary quantitative engine.

```text
BetaInput -> BetaEngine -> BetaState
```

### Gamma — implemented on this branch

Behavioral / market-psychology state engine. Gamma converts measurable price action, candlestick structure, volume, aggressive flow, options positioning, volatility, breadth, crowding, holder-pain levels and catalyst response into an auditable behavioral state.

```text
MarketSnapshot -> GammaBehavioralEngine -> BehavioralState
```

Gamma outputs:

- fear / greed / FOMO;
- conviction / uncertainty / disagreement;
- attention;
- long/short crowding;
- long/short pain;
- bull/bear exhaustion;
- 30+ simultaneous behavioral-regime scores;
- short-squeeze pressure;
- long-liquidation pressure;
- gamma-acceleration pressure;
- capitulation pressure;
- breakout/breakdown continuation pressure;
- reversal pressure;
- volatility-expansion / mean-reversion pressure;
- GEX, gamma-flip, call-wall, put-wall, vanna and charm **proxies**;
- bullish and bearish behavioral pressure;
- transition velocity;
- data quality, warnings and evidence ledger.

Gamma scores are evidence scores, **not calibrated probabilities**. The output preserves proxy assumptions and missing-data warnings.

## Whole-market / SPY behavioral field

`GammaUniverseEngine` evaluates a frozen constituent universe and quality/index-weight aggregates:

- psychology vectors;
- forced-behavior vectors;
- bullish/bearish pressure;
- behavioral dispersion;
- top short-squeeze names;
- top long-liquidation names;
- top FOMO names;
- top bull/bear exhaustion names.

`select_top_weight_mass()` identifies the smallest descending-weight constituent set reaching a requested percentage of total index weight. `synthesize_index_field()` then compares direct SPY behavior with the weighted constituent field and measures alignment/divergence.

```text
SPY direct state --------------------+
                                      |
S&P constituent Gamma states --------+--> IndexBehavioralField --> Delta
        |                             |
        +--> index-weight aggregation+
```

## Live market-data path

Gamma contains a **market-data-only** Tradier adapter. There are no account, order, position or execution endpoints in it.

```text
Tradier REST
  |-- Time & Sales -> historical/recent bars
  |-- options chain -> IV/Greeks/OI
  +-- market stream session

Tradier WebSocket (single shared market-data session)
  -> timesale events
  -> quote/tick-rule aggressor proxy
  -> 1-minute OHLCV + buy/sell-volume proxy
  -> GammaRuntime
  -> frozen MarketSnapshot
  -> GammaBehavioralEngine
```

Install live support:

```bash
pip install -e '.[live]'
```

## Point-in-time runtime and replay

`GammaRuntime` maintains bounded rolling bars and separately timestamped options, internals, positioning and catalyst context. It freezes immutable snapshots before evaluation.

`JsonlTapeWriter` records both inputs and outputs into an append-only JSONL tape with SHA-256 payload fingerprints. This gives Gamma a deterministic forward-collected corpus for replay and later out-of-sample validation instead of relying on reconstructed historical option/flow data.

## Data provenance

Gamma distinguishes direct observations from deterministic derivations and structural proxies.

Important examples:

- Tradier REST aggregate bars: direct OHLCV, no fabricated aggressive flow;
- streaming CVD: quote/tick-rule aggressor **proxy**;
- option IV/Greeks: provider observations normalized from the option chain;
- GEX/gamma flip/walls/vanna/charm: explicitly labeled **structural proxies** because OI does not expose actual dealer inventory;
- short interest, borrow, point-in-time index weights, catalysts and other context: explicit external inputs when unavailable from the chosen provider.

See:

- [`docs/GAMMA_BEHAVIORAL_ENGINE.md`](docs/GAMMA_BEHAVIORAL_ENGINE.md)
- [`docs/GAMMA_DATA_SOURCES.md`](docs/GAMMA_DATA_SOURCES.md)

## Gamma quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest
pytest
```

CLI:

```bash
gamma-spy --input snapshot.json --output gamma_state.json
```

Python:

```python
from gamma_spy import GammaBehavioralEngine

state = GammaBehavioralEngine().evaluate(snapshot)
print(state.primary_regime)
print(state.psychology.fear)
print(state.forced_behavior.short_squeeze)
```

## Validation discipline

Gamma v1 is a fully specified **state-estimation hypothesis**, not a claim of proven predictive edge. The repository includes reliability-bin, Wilson-interval, non-overlapping-sample and calibrated-probability scoring utilities, but raw Gamma scores are deliberately not treated as probabilities.

Promotion requires point-in-time captured data, frozen outcome definitions, walk-forward testing, non-overlapping primary evidence, calibration checks, baseline comparisons, regime breakdowns, replay determinism and zero look-ahead violations.

## Hard authority boundary

Every Gamma output contains:

```text
trading_authority = false
execution_authority = false
```

Gamma is a processor. Delta is the convergence processor. Any later bot or human consumer must be separate from these engines.

## Current repository status

This branch implements the production-shaped Gamma behavioral engine, whole-universe aggregation, SPY constituent-field synthesis, market-data normalization, live streaming collection, rolling runtime state, append-only replay capture, research metrics, tests, CI and operating documentation. Alpha and Beta remain logically independent and are not imported by Gamma. Delta convergence itself remains a later integration step.
