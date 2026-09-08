# Gamma-SPY Behavioral Market Engine

## Status

Gamma-SPY is an **independent market-behavior state estimator** designed to converge with Alpha and Beta only inside Delta.

```text
Normalized point-in-time market observations
                    |
                    v
             GammaInput
                    |
        +-----------+-----------+
        |           |           |
      Price       Flow       Options
        |           |           |
   Volatility    Breadth    Positioning
        |           |           |
        +-----------+-----------+
                    |
              Feature layer
                    |
                    v
           Psychology vector
                    |
                    v
          Behavioral regimes
                    |
                    v
        Forced-behavior pressures
                    |
                    v
             GammaState
                    |
                    v
                  Delta
```

Gamma **does not** select strategies, size positions, place orders, route orders, manage positions, or communicate with a broker. `trading_authority=false` and `execution_authority=false` are hard output invariants.

---

## 1. What Gamma is estimating

Gamma treats market psychology as a latent state inferred from observable behavior. It does not claim to read trader intent directly.

The causal model is:

```text
information
  -> expectation
  -> belief / emotion
  -> positioning
  -> pain / urgency
  -> orders
  -> market microstructure
  -> price
  -> feedback into belief / positioning
```

The engine therefore focuses on the measurable middle of that loop:

- price response;
- participation;
- aggressive flow;
- options demand;
- volatility demand;
- breadth;
- crowding;
- key holder pain levels;
- catalyst response;
- mechanical options-hedging proxies.

The most important downstream question is not simply `bullish or bearish?` It is:

> **Which participant class is becoming increasingly constrained, and what market behavior is likely if its pain/hedging threshold is crossed?**

---

## 2. Input contract

Gamma consumes a frozen `MarketSnapshot`.

### 2.1 Bars

Each bar contains:

- timestamp;
- OHLC;
- volume;
- optional aggressive buy volume;
- optional aggressive sell volume.

The aggressive-flow fields allow CVD. When unavailable Gamma does **not** manufacture true order flow; CVD-dependent features are disabled and data quality falls.

Recommended minimum history is 20 bars. Production research should normally provide substantially more.

### 2.2 Options

Each option observation may contain:

- strike;
- expiration;
- call/put;
- bid/ask;
- volume;
- open interest;
- IV;
- delta;
- gamma;
- vega;
- theta.

Gamma derives:

- put/call volume ratio;
- put/call OI ratio;
- approximate 25-delta skew;
- near-ATM IV;
- IV rank when historical IV is supplied;
- GEX proxy;
- call wall proxy;
- put wall proxy;
- gamma-flip proxy;
- vanna proxy;
- charm proxy.

### Critical dealer-position caveat

Open interest does not reveal who is long or short each contract. Gamma's current v1 GEX convention assigns call OI positive and put OI negative for a **structural sensitivity proxy**. This must never be represented as actual dealer inventory.

The assumption string is carried inside every `GammaStructure` output.

A future provider that supplies signed dealer positioning may replace this proxy while preserving the same public output contract and provenance label.

### 2.3 Market internals

Supported fields include:

- advancers / decliners;
- up volume / down volume;
- new highs / new lows;
- percent above 20-day average;
- TICK;
- TRIN;
- VIX;
- VVIX;
- VIX9D;
- VIX3M;
- SPY return;
- sector return;
- HYG return;
- UUP return;
- TLT return.

Not every field is mandatory. Missing groups lower data quality and remove the affected evidence from scoring.

### 2.4 Positioning

Supported slow/structural inputs include:

- short-interest percentage;
- days to cover;
- borrow rate;
- external long-crowding score;
- external short-crowding score;
- anchored VWAP;
- support level;
- resistance level;
- liquidity score.

These values can have different update frequencies. The upstream normalizer must preserve their true observation timestamp and must never forward-fill them as though they were real-time measurements without provenance.

### 2.5 Catalysts

Supported catalyst fields:

- sentiment;
- surprise;
- expected move;
- actual move;
- attention anomaly z-score.

Gamma calculates a `news_reaction_residual` when expected and actual reaction are available. The key concept is **reaction relative to expectation**, not headline polarity alone.

---

## 3. Feature layer

### Price / candle structure

| Feature | Meaning |
|---|---|
| `return_1/3/5` | multi-window price direction |
| `momentum_accel_atr` | change in short momentum scaled by ATR |
| `atr14` | local absolute movement scale |
| `atr_expansion` | urgency relative to recent range history |
| `rvol` | current participation versus recent volume |
| `clv` | close location in current bar range |
| `body_fraction` | directional body strength |
| `upper_wick_fraction` | buy-side rejection |
| `lower_wick_fraction` | sell-side rejection |
| `hammer` | candidate sell-side rejection |
| `shooting_star` | candidate buy-side rejection |
| `doji` | local disagreement/equilibrium |
| `bullish_engulfing` | abrupt demand dominance candidate |
| `bearish_engulfing` | abrupt supply dominance candidate |
| `inside_bar` | compression |
| `outside_bar` | expansion/disagreement |
| `distance_vwap_atr` | control/extension versus recent VWAP |
| `compression` | short-range contraction versus longer range |

Candlestick patterns are never sufficient alone. They become meaningful only when flow, volume, location and context agree.

### Flow

| Feature | Meaning |
|---|---|
| `cvd` | cumulative aggressive buy minus aggressive sell volume |
| `cvd_change_5` | recent directional aggressive-flow change |
| `cvd_divergence` | disagreement between price and CVD direction |
| `flow_efficiency` | price response per unit of current net aggressive flow |
| `obv` | signed volume accumulation proxy |

Important interpretations:

```text
price up + CVD up      = demand confirmation
price down + CVD down  = supply confirmation
price down + CVD up    = bullish absorption/exhaustion candidate
price up + CVD down    = bearish absorption/distribution candidate
```

### Volatility

| Feature | Meaning |
|---|---|
| `realized_vol` | annualized realized volatility from supplied bar cadence |
| `vix` | market implied-volatility context |
| `vvix` | volatility-of-volatility context |
| `vix9d_vix3m_ratio` | front/back stress structure |
| `iv_rv_spread` | option implied volatility minus recent realized volatility |

### Breadth / cross-asset

| Feature | Meaning |
|---|---|
| `breadth` | advancers / all advancing+declining issues |
| `up_down_volume` | participation strength by volume |
| `new_high_low_ratio` | cross-sectional trend health |
| `pct_above_20d` | participation above intermediate trend |
| `relative_strength_spy` | symbol performance minus SPY |
| `relative_strength_sector` | symbol performance minus sector |
| `hyg_return` | credit-risk proxy context |
| `uup_return` | dollar proxy context |
| `tlt_return` | duration/Treasury proxy context |

### Options / gamma structure

| Feature | Meaning |
|---|---|
| `put_call_volume` | current option demand mix |
| `put_call_oi` | existing option-position mix |
| `skew_25d` | downside versus upside IV demand |
| `atm_iv` | near-money implied volatility |
| `iv_rank` | current IV location in supplied IV history |
| `signed_gex_proxy` | signed structural gamma proxy |
| `gamma_regime` | positive / negative / neutral / unknown |
| `gamma_flip` | nearest scanned proxy sign-change level |
| `call_wall` | strike with largest call gamma load proxy |
| `put_wall` | strike with largest put gamma load proxy |
| `vanna_proxy` | OI-weighted IV/delta sensitivity proxy |
| `charm_proxy` | OI-weighted time/delta sensitivity proxy |

### Pain / crowding

| Feature | Meaning |
|---|---|
| `short_interest_pct` | slow-moving short fuel |
| `days_to_cover` | short-exit capacity proxy |
| `borrow_rate_pct` | scarcity/crowding proxy |
| `anchor_distance_atr` | distance from event/holder anchored VWAP |
| `breakout_distance_atr` | price displacement beyond supplied resistance |
| `breakdown_distance_atr` | price displacement below supplied support |

---

## 4. Psychology vector

Gamma emits a 0-100 **evidence score**, not a calibrated probability, for:

```text
fear
greed
fomo
conviction
uncertainty
attention
disagreement
long_crowding
short_crowding
long_pain
short_pain
bull_exhaustion
bear_exhaustion
```

### Examples

`fear` combines downside momentum/acceleration, RVOL, ATR expansion, VIX/VVIX, put demand, skew, breadth deterioration and negative-gamma context.

`fomo` combines upside acceleration, participation, call bias, distance from VWAP, attention anomaly and aggressive buying.

`bull_exhaustion` combines upper-wick rejection, price/CVD bearish divergence, distance from VWAP, high RVOL and FOMO.

`bear_exhaustion` mirrors this with lower-wick rejection, bullish CVD divergence, downside extension, RVOL and fear.

---

## 5. Named behavioral regimes

Gamma v1 evaluates the following fuzzy regimes simultaneously. They are **not mutually exclusive**.

```text
extreme_fear
panic
capitulation
despair
disbelief
cautious_optimism
confidence
complacency
greed
fomo
euphoria
exhaustion
distribution
denial
uncertainty
indecision
crowded_bullish
crowded_bearish
short_squeeze
long_squeeze
dip_buying
failed_dip_buying
breakout_conviction
false_breakout
breakdown_conviction
bear_trap
risk_on
risk_off
relief_rally
dead_cat_bounce
accumulation
absorption
distribution_exhaustion
```

`primary_regime` and `secondary_regime` are simply the two highest rule scores. A high `uncertainty` plus small separation between top regimes lowers `state_confidence`.

---

## 6. Forced-behavior vector

This is Gamma's primary downstream value.

```text
short_squeeze
long_liquidation
gamma_acceleration
capitulation
breakout_continuation
breakdown_continuation
bullish_reversal
bearish_reversal
volatility_expansion
mean_reversion
```

Again, these are uncalibrated evidence scores in v1.

### Short-squeeze pressure

Evidence includes:

- short crowding;
- short pain;
- upside acceleration;
- positive aggressive flow;
- resistance break;
- negative-gamma amplification proxy.

### Long-liquidation pressure

Evidence includes:

- long crowding;
- long pain;
- downside acceleration;
- negative aggressive flow;
- support break;
- negative-gamma amplification proxy.

### Gamma acceleration

The v1 score rises when:

- GEX proxy is negative;
- price is near the proxy gamma flip;
- price acceleration rises;
- RVOL rises.

### Mean reversion

The v1 score rises when:

- GEX proxy is positive;
- range is compressed;
- participation is not extreme.

---

## 7. Directional pressure

Gamma emits:

```text
bullish_pressure
bearish_pressure
directional_balance = bullish_pressure - bearish_pressure
```

These are **behavioral pressure summaries**, not expected returns, trade recommendations or probabilities.

Delta should consume both sides rather than only the difference. A 75/70 state represents high conflict; a 75/20 state represents much cleaner behavioral asymmetry.

---

## 8. Transition velocity

Static state is less important than state change.

For each psychology dimension Gamma calculates:

```text
velocity = (current_score - prior_score) / elapsed_minutes
```

Examples:

```text
fear 40 -> 80 rapidly      = deterioration acceleration
fear 90 -> 70 rapidly      = fear deceleration / possible stabilization
fomo 35 -> 85 rapidly      = chase phase emerging
bull_exhaustion 20 -> 70   = momentum may be entering late-stage distribution
```

The caller may provide an explicit prior state, or the engine can remember the prior state by symbol in a live process. Replay should generally supply the prior state explicitly for deterministic control.

---

## 9. Multi-horizon construction

Gamma supports independent frozen snapshots:

```text
5m
15m
30m
60m
120m
EOD
1D
5D
```

The engine does not silently resample one horizon into another. Upstream research should construct each point-in-time horizon and call `evaluate_horizons()`.

This prevents hidden future leakage and allows Delta to reason about:

- micro fear against swing confidence;
- intraday squeeze inside structural distribution;
- short-term capitulation inside a larger risk-off state;
- cross-horizon alignment.

---

## 10. Data-quality contract

`data_quality` is a weighted coverage score. Missing sources generate explicit warnings.

Current warning classes include:

```text
BAR_HISTORY_THIN
FLOW_PROXY_MISSING
OPTIONS_MISSING
DEALER_GAMMA_IS_PROXY
BREADTH_MISSING
VOLATILITY_CONTEXT_MISSING
SHORT_INTEREST_MISSING
STALE_SOURCE
SCORES_NOT_PROBABILITIES
```

Delta should be allowed to reject or down-weight Gamma when quality is below its governance threshold.

---

## 11. Evidence ledger

Gamma outputs a machine-readable `evidence[]` array containing:

- feature name;
- raw value;
- normalized value where meaningful;
- directional interpretation;
- rule weight;
- quality;
- source;
- explanation.

This exists so Delta and later audit/replay tooling can answer:

> Why did Gamma classify this state as panic / squeeze / exhaustion?

A state without traceable evidence should not be promoted.

---

## 12. Candlestick-to-behavior matrix

| Candle / structure | Behavioral hypothesis | Required confirmation |
|---|---|---|
| Hammer | sell pressure rejected / absorption candidate | RVOL + lower location + CVD improvement |
| Shooting star | buy pressure rejected / distribution candidate | RVOL + upper location + CVD deterioration |
| Bullish engulfing | abrupt demand dominance | positive CVD + participation |
| Bearish engulfing | abrupt supply dominance | negative CVD + participation |
| Doji | disagreement / temporary equilibrium | volatility + context |
| Inside bar | compression | later expansion trigger |
| Outside bar | disagreement / expansion | close location + flow |
| Gap hold | catalyst accepted | VWAP/opening-range hold + flow |
| Gap fade | catalyst rejected / priced in | opening-range loss + flow |
| Failed breakdown | trapped sellers | reclaim + sell-flow absorption |
| Failed breakout | trapped buyers | rejection + buy-flow absorption |

No candlestick is a standalone forecast.

---

## 13. Psychology-to-observable matrix

| State | Price/candle | Flow | Options/gamma | Vol/breadth | Structural clue |
|---|---|---|---|---|---|
| Panic | wide red bars near lows | strongly negative CVD | put demand + negative GEX proxy | VIX/VVIX up, breadth collapse | support failure |
| Capitulation | climax bar + hammer/reclaim | selling loses price efficiency | puts remain rich | VIX fails to confirm new price low | volume climax |
| FOMO | breakout / range expansion | aggressive buying | short-dated call demand | breadth expansion | high attention |
| Euphoria | parabolic extension | flow remains extreme but less efficient | call crowding | breadth may narrow | distance from VWAP extreme |
| Distribution | repeated upper rejection | price up / CVD down | quiet hedging rise | breadth deteriorates | good news stops working |
| Short squeeze | resistance break | CVD acceleration | call demand + gamma amplification proxy | RVOL up | SI/DTC/borrow elevated |
| Long squeeze | support break | sell cascade | put demand + gamma amplification proxy | VIX up | crowded longs / holder pain |
| Absorption | price refuses to fall | CVD down while price stable | put demand may persist | volatility stabilizes | support/AVWAP defense |
| Bear trap | failed breakdown + reclaim | CVD turns up | put holders trapped | fear stops rising | support recovered |
| Breakout conviction | strong close above resistance | CVD confirms | options not necessarily euphoric | breadth confirms | RVOL expands |
| False breakout | upper rejection back below level | CVD fails | calls chase ineffective move | breadth fails | trapped breakout buyers |

---

## 14. Delta integration contract

Delta should receive the full `BehavioralState`, not a single Gamma score.

Recommended Delta inputs:

```text
psychology.*
forced_behavior.*
gamma.gamma_regime
gamma.gamma_flip
gamma.call_wall
gamma.put_wall
primary_regime
secondary_regime
bullish_pressure
bearish_pressure
directional_balance
state_confidence
data_quality
transition_velocity.*
evidence[]
warnings[]
```

Delta should preserve Alpha/Beta/Gamma independence. Gamma must never import Alpha or Beta.

A suggested convergence pattern is:

```text
AlphaState ---------+
                    |
BetaState ----------+--> Delta normalization --> agreement/conflict --> DeltaState
                    |
GammaState ---------+
```

Delta may infer that a statistical forecast is more fragile when Gamma reports crowded positioning, negative gamma and rising pain, but Delta—not Gamma—owns that convergence logic.

---

## 15. Validation requirements before predictive use

Gamma v1 scores are engineered hypotheses. They must not be marketed or consumed as calibrated probabilities until validated on point-in-time data.

Minimum research program:

1. Capture immutable point-in-time snapshots.
2. Freeze every upstream observation timestamp.
3. Define objective forward outcomes per horizon.
4. Prevent overlapping samples from inflating significance.
5. Run walk-forward tests only.
6. Separate score construction from calibration.
7. Measure by regime and horizon, not only aggregate performance.
8. Compare against naive baselines.
9. Track data-source degradation separately from model error.
10. Preserve every model/version/config fingerprint.

Suggested objective labels include:

- forward +1.0/+1.5/+2.0 ATR excursion;
- forward -1.0/-1.5/-2.0 ATR excursion;
- touch-before-touch path labels;
- range expansion;
- breakout hold versus failure;
- breakdown hold versus reclaim;
- squeeze-like move after high short-crowding state;
- liquidation-like move after high long-crowding state;
- reversal after exhaustion state.

Metrics should include:

- base rate;
- lift versus base rate;
- Brier score after legitimate calibration;
- calibration curves;
- precision/recall by score band;
- ROC-AUC only where class balance and use case make it meaningful;
- expected forward return/range conditional on score band;
- Wilson confidence intervals;
- sample count;
- regime stability;
- out-of-sample decay.

### Non-overlap rule

If validating a 30-minute outcome, primary statistical evidence should use anchors spaced at least 30 minutes apart unless a method explicitly models dependence. Thousands of overlapping minute-by-minute forecasts must not be treated as thousands of independent observations.

---

## 16. Promotion gates

A future Gamma release should not be called validated until all required signals satisfy predefined gates. Example governance categories:

- minimum market sessions;
- minimum non-overlapping observations per horizon;
- minimum data-quality coverage;
- minimum source-timestamp integrity;
- positive lift versus base rate;
- stable calibration;
- acceptable confidence-interval width;
- no material performance collapse in major regime buckets;
- deterministic replay;
- zero look-ahead violations;
- explicit proxy labeling retained in every exported state.

The exact numerical thresholds should be frozen before the validation sample is inspected to reduce threshold shopping.

---

## 17. Public contract

```text
MarketSnapshot -> GammaBehavioralEngine -> BehavioralState
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

The output intentionally includes enough raw features and evidence for Delta, audit, replay, research, and later calibration without granting Gamma execution authority.
