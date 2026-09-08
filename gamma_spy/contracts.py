from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

OptionType = Literal["call", "put"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    aggressive_buy_volume: float | None = None
    aggressive_sell_volume: float | None = None


@dataclass(frozen=True)
class OptionObservation:
    strike: float
    expiration: datetime
    option_type: OptionType
    bid: float | None = None
    ask: float | None = None
    volume: float = 0.0
    open_interest: float = 0.0
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None


@dataclass(frozen=True)
class MarketInternals:
    advancers: float | None = None
    decliners: float | None = None
    up_volume: float | None = None
    down_volume: float | None = None
    new_highs: float | None = None
    new_lows: float | None = None
    pct_above_20d: float | None = None
    tick: float | None = None
    trin: float | None = None
    vix: float | None = None
    vvix: float | None = None
    vix9d: float | None = None
    vix3m: float | None = None
    spy_return: float | None = None
    sector_return: float | None = None
    hyg_return: float | None = None
    uup_return: float | None = None
    tlt_return: float | None = None


@dataclass(frozen=True)
class Positioning:
    short_interest_pct: float | None = None
    days_to_cover: float | None = None
    borrow_rate_pct: float | None = None
    long_crowding_score: float | None = None
    short_crowding_score: float | None = None
    anchored_vwap: float | None = None
    support_level: float | None = None
    resistance_level: float | None = None
    liquidity_score: float | None = None


@dataclass(frozen=True)
class CatalystObservation:
    sentiment: float | None = None
    surprise: float | None = None
    expected_move_pct: float | None = None
    actual_move_pct: float | None = None
    attention_z: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    ts: datetime
    bars: tuple[Bar, ...]
    bar_minutes: int = 1
    options: tuple[OptionObservation, ...] = ()
    internals: MarketInternals = field(default_factory=MarketInternals)
    positioning: Positioning = field(default_factory=Positioning)
    catalyst: CatalystObservation = field(default_factory=CatalystObservation)
    source: str = "normalized"
    source_latency_ms: float | None = None
    historical_iv: tuple[float, ...] = ()


@dataclass(frozen=True)
class SignalEvidence:
    name: str
    value: float | str | bool | None
    normalized: float | None
    direction: Literal["bullish", "bearish", "neutral", "mixed"]
    weight: float
    quality: float
    source: str
    explanation: str


@dataclass(frozen=True)
class PsychologyVector:
    fear: float
    greed: float
    fomo: float
    conviction: float
    uncertainty: float
    attention: float
    disagreement: float
    long_crowding: float
    short_crowding: float
    long_pain: float
    short_pain: float
    bull_exhaustion: float
    bear_exhaustion: float


@dataclass(frozen=True)
class ForcedBehaviorVector:
    short_squeeze: float
    long_liquidation: float
    gamma_acceleration: float
    capitulation: float
    breakout_continuation: float
    breakdown_continuation: float
    bullish_reversal: float
    bearish_reversal: float
    volatility_expansion: float
    mean_reversion: float


@dataclass(frozen=True)
class GammaStructure:
    signed_gex_proxy: float | None
    gamma_regime: Literal["positive", "negative", "neutral", "unknown"]
    gamma_flip: float | None
    call_wall: float | None
    put_wall: float | None
    call_gamma_load: float | None
    put_gamma_load: float | None
    vanna_proxy: float | None
    charm_proxy: float | None
    dealer_position_assumption: str


@dataclass(frozen=True)
class BehavioralState:
    schema_version: str
    engine_version: str
    symbol: str
    ts: datetime
    psychology: PsychologyVector
    forced_behavior: ForcedBehaviorVector
    gamma: GammaStructure
    regime_scores: dict[str, float]
    primary_regime: str
    secondary_regime: str | None
    bullish_pressure: float
    bearish_pressure: float
    directional_balance: float
    state_confidence: float
    data_quality: float
    transition_velocity: dict[str, float]
    features: dict[str, float | str | bool | None]
    evidence: tuple[SignalEvidence, ...]
    warnings: tuple[str, ...]
    trading_authority: bool = False
    execution_authority: bool = False
    generated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, tuple):
                return [encode(v) for v in value]
            if isinstance(value, list):
                return [encode(v) for v in value]
            if isinstance(value, dict):
                return {k: encode(v) for k, v in value.items()}
            return value

        return encode(asdict(self))
