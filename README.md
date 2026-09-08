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

See [`docs/GAMMA_BEHAVIORAL_ENGINE.md`](docs/GAMMA_BEHAVIORAL_ENGINE.md).

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

## Hard authority boundary

Every Gamma output contains:

```text
trading_authority = false
execution_authority = false
```

Gamma is a processor. Delta is the convergence processor. Any later bot or human consumer must be separate from these engines.

## Current repository status

This branch introduces the first production-shaped Gamma implementation and its tests/specification. Alpha and Beta remain logically independent and are not imported by Gamma. Delta convergence itself remains a later integration step.
