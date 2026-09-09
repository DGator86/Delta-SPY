# Gamma-SPY Data Sources and Provenance Policy

Verified against Tradier's official documentation on 2026-09-08. Provider behavior can change; re-verify before production promotion.

## Non-negotiable provenance rule

Every Gamma feature belongs to one of four categories:

1. **direct observation** — supplied directly by a market-data/provider payload;
2. **deterministic derivation** — calculated from direct observations;
3. **structural proxy** — calculated under an explicit assumption that cannot be directly observed;
4. **external context** — supplied by another point-in-time source.

Gamma must never relabel categories 2-4 as category 1.

---

## Tradier production versus sandbox

Current Tradier documentation states:

| Data | Brokerage/production | Sandbox |
|---|---|---|
| US equities | real-time | delayed |
| US options | real-time | delayed |
| indices | real-time with documented exceptions | unavailable |
| Greeks | hourly | unavailable |
| tick Time & Sales | available subject to history limits | unavailable |

Delayed market data is described by Tradier as industry-standard 15-minute delayed data.

**Gamma policy:** sandbox market data must never be labeled real-time. Sandbox can be used for integration testing, but not as authoritative live behavioral evidence.

---

## Tradier market-data adapter

`gamma_spy.tradier.TradierMarketDataClient` exposes only read-only market-data methods:

```text
quotes
option expirations
option chains
Time & Sales
create market-data streaming session
```

It deliberately contains no account, order, position or execution endpoint.

### Option chains

Tradier's option-chain endpoint can include Greeks and IV; Tradier states that the Greek/volatility data is supplied courtesy of ORATS.

Gamma normalizes:

- bid/ask;
- volume;
- open interest;
- IV;
- delta;
- gamma;
- vega;
- theta.

### Time & Sales history

Current documented history limits are approximately:

| Interval | Open-session history | All-session history |
|---|---:|---:|
| tick | 5 days | n/a |
| 1 minute | 20 days | 10 days |
| 5 minute | 40 days | 18 days |
| 15 minute | 40 days | 18 days |

This is not sufficient for a long historical intraday research corpus. Gamma therefore includes append-only forward capture.

---

## Live WebSocket collection

Tradier's current streaming documentation allows a market stream to contain from a single symbol to several hundred symbols, with the practical limit determined by throughput and the consumer's ability to keep up. Tradier does not publish a fixed symbol cap and prohibits opening more than one simultaneous market-data session.

Gamma therefore uses **one shared WebSocket market-data session**.

```text
one market session
    |
    +-- SPY
    +-- selected constituent universe
    +-- dynamically replaceable symbol subscription
    |
    v
streaming timesales
    |
    v
aggressor-side proxy
    |
    v
1-minute OHLCV + buy/sell-volume proxy
```

The collector requests valid ticks and drops events explicitly marked cancelled/corrected.

---

## Aggressor flow is a proxy

Tradier streaming timesales expose fields such as bid, ask, last and size, but Gamma does not receive a direct exchange-native `buyer initiated / seller initiated` field.

Gamma therefore classifies trade direction with:

```text
last >= ask -> buy proxy
last <= bid -> sell proxy
inside spread:
    last > prior trade -> buy proxy
    last < prior trade -> sell proxy
otherwise -> neutral
```

This is used to construct CVD-ready bars.

It must be labeled **aggressor-side proxy**, not direct order-flow truth.

REST aggregate Time & Sales bars do not receive fabricated buy/sell volume; their aggressive-volume fields remain `None`.

---

## Dealer gamma is a structural proxy

Open interest does not reveal actual dealer long/short inventory.

Gamma v1 therefore uses an explicit structural convention:

```text
call OI -> positive signed gamma contribution
put OI  -> negative signed gamma contribution
```

From that convention Gamma derives:

- signed GEX proxy;
- positive/negative/neutral gamma regime proxy;
- gamma-flip proxy;
- call-wall proxy;
- put-wall proxy;
- vanna proxy;
- charm proxy.

The output includes the assumption string. No downstream component may strip the `proxy` meaning.

A later signed-positioning provider can replace this implementation without changing the public `GammaStructure` contract.

---

## Whole-universe coverage strategy

Not every constituent needs the same input depth every minute.

Recommended hierarchy:

### Tier A — direct SPY

Highest refresh priority:

- streaming timesales;
- SPY option chains;
- gamma structure;
- volatility context;
- breadth;
- key pain levels;
- catalyst response.

### Tier B — highest index-weight mass

Deep constituent coverage for the smallest descending-weight group that makes up a configured portion of total S&P 500 weight (25% by default in the research workflow):

- live price/flow;
- options when practical;
- relative strength;
- crowding;
- catalysts.

### Tier C — remainder of S&P 500

Broad field coverage:

- price;
- volume;
- relative strength;
- behavioral state with degraded options-dependent dimensions when option chains are not refreshed.

Gamma's data-quality score ensures Tier C states are not silently treated as equivalent to deep Tier A/B states.

---

## External point-in-time inputs

The following are intentionally not fabricated by the Tradier adapter and remain explicit caller/provider inputs when unavailable:

- S&P 500 point-in-time constituent weights;
- short interest;
- days to cover;
- borrow rates;
- externally estimated long/short crowding;
- anchored VWAP/event anchors;
- support/resistance or volume-profile structural levels;
- market breadth when not derived from an authoritative universe feed;
- VIX/VVIX/VIX9D/VIX3M context when not supplied through a verified index feed;
- news/catalyst sentiment and surprise;
- attention/search/social anomalies.

Each slow-moving input should retain its true observation timestamp upstream. Never forward-fill a stale value and call it a real-time observation.

---

## Captured-tape policy

Gamma includes `JsonlTapeWriter` for immutable forward collection.

Every stored envelope contains:

```text
schema_version
record_type
observed_at
source
payload_sha256
payload
```

Captured records include both the **input snapshot** and resulting **behavioral state**. SHA-256 verification detects accidental or intentional payload modification.

Long-term validation should treat the captured point-in-time tape as authoritative rather than attempting to reconstruct missing historical option books or intraday flow after the fact.

---

## Freshness handling

`GammaRuntime` records observation times for:

- bars;
- options;
- internals;
- positioning;
- catalysts.

It exposes input age in seconds. Downstream orchestration should define hard freshness budgets for each class and withhold/degrade Gamma when those budgets are exceeded.

Recommended policy shape, to be empirically finalized before production promotion:

```text
bars          -> seconds/minutes
options       -> minutes, recognizing provider Greek refresh cadence
internals     -> seconds/minutes
catalysts     -> event-driven
positioning   -> source-specific daily/intraday cadence
```

Do not hard-code a false universal freshness standard for slow and fast data classes.
