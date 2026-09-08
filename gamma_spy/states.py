from __future__ import annotations

from dataclasses import fields
from typing import Iterable

from .contracts import ForcedBehaviorVector, PsychologyVector, SignalEvidence
from .features import clip

FeatureMap = dict[str, float | str | bool | None]


def _num(features: FeatureMap, key: str) -> float | None:
    value = features.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _bool(features: FeatureMap, key: str) -> float | None:
    value = features.get(key)
    return 1.0 if value is True else (0.0 if value is False else None)


def _rise(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if high == low:
        return float(value >= high)
    return clip((value - low) / (high - low))


def _fall(value: float | None, low: float, high: float) -> float | None:
    rising = _rise(value, low, high)
    return None if rising is None else 1.0 - rising


def _abs_rise(value: float | None, low: float, high: float) -> float | None:
    return _rise(abs(value), low, high) if value is not None else None


def _wm(parts: Iterable[tuple[float | None, float]], default: float = 0.5) -> float:
    total = 0.0
    weight = 0.0
    for value, w in parts:
        if value is None:
            continue
        total += clip(value) * w
        weight += w
    return total / weight if weight else default


def _pct(score: float) -> float:
    return round(100.0 * clip(score), 2)


def _directional_primitives(f: FeatureMap) -> dict[str, float | None]:
    spot = _num(f, "spot")
    atr = _num(f, "atr14")
    r5 = _num(f, "return_5")
    r3 = _num(f, "return_3")
    ret5_atr = (r5 * spot / atr) if r5 is not None and spot and atr and atr > 0 else None
    ret3_atr = (r3 * spot / atr) if r3 is not None and spot and atr and atr > 0 else None
    accel = _num(f, "momentum_accel_atr")
    clv = _num(f, "clv")
    breadth = _num(f, "breadth")
    cvd_div = _num(f, "cvd_divergence")
    cvd_change = _num(f, "cvd_change_5")
    up_down = _num(f, "up_down_volume")

    return {
        "up_momentum": _rise(ret5_atr, 0.15, 2.0),
        "down_momentum": _rise(-ret5_atr, 0.15, 2.0) if ret5_atr is not None else None,
        "up_short": _rise(ret3_atr, 0.10, 1.25),
        "down_short": _rise(-ret3_atr, 0.10, 1.25) if ret3_atr is not None else None,
        "up_accel": _rise(accel, 0.15, 1.75),
        "down_accel": _rise(-accel, 0.15, 1.75) if accel is not None else None,
        "high_close": _rise(clv, 0.55, 0.95),
        "low_close": _fall(clv, 0.05, 0.45),
        "breadth_up": _rise(breadth, 0.52, 0.82),
        "breadth_down": _fall(breadth, 0.18, 0.48),
        "cvd_bull_div": _rise(cvd_div, 0.25, 1.0),
        "cvd_bear_div": _rise(-cvd_div, 0.25, 1.0) if cvd_div is not None else None,
        "cvd_positive": 1.0 if cvd_change is not None and cvd_change > 0 else (0.0 if cvd_change is not None else None),
        "cvd_negative": 1.0 if cvd_change is not None and cvd_change < 0 else (0.0 if cvd_change is not None else None),
        "up_volume_breadth": _rise(up_down, 1.05, 3.0),
        "down_volume_breadth": _fall(up_down, 0.33, 0.95),
    }


def infer_psychology(features: FeatureMap) -> PsychologyVector:
    p = _directional_primitives(features)
    rvol = _num(features, "rvol")
    atr_exp = _num(features, "atr_expansion")
    vix = _num(features, "vix")
    vvix = _num(features, "vvix")
    put_call = _num(features, "put_call_volume")
    skew = _num(features, "skew_25d")
    iv_rv = _num(features, "iv_rv_spread")
    dist_vwap = _num(features, "distance_vwap_atr")
    attention_z = _num(features, "attention_z")
    upper_wick = _num(features, "upper_wick_fraction")
    lower_wick = _num(features, "lower_wick_fraction")
    breadth = _num(features, "breadth")
    rs_spy = _num(features, "relative_strength_spy")
    news_residual = _num(features, "news_reaction_residual")
    short_interest = _num(features, "short_interest_pct")
    dtc = _num(features, "days_to_cover")
    borrow = _num(features, "borrow_rate_pct")
    ext_long = _num(features, "long_crowding_external")
    ext_short = _num(features, "short_crowding_external")
    anchor = _num(features, "anchor_distance_atr")
    breakout = _num(features, "breakout_distance_atr")
    breakdown = _num(features, "breakdown_distance_atr")
    gamma_negative = 1.0 if features.get("gamma_regime") == "negative" else 0.0

    fear = _wm(
        [
            (p["down_momentum"], 1.2),
            (p["down_accel"], 0.9),
            (_rise(rvol, 1.1, 2.5), 0.7),
            (_rise(atr_exp, 1.05, 2.2), 0.8),
            (_rise(vix, 18.0, 38.0), 1.0),
            (_rise(vvix, 90.0, 145.0), 0.5),
            (_rise(put_call, 0.9, 2.2), 1.0),
            (_rise(skew, 0.01, 0.10), 0.7),
            (p["breadth_down"], 1.0),
            (gamma_negative, 0.3),
        ]
    )

    greed = _wm(
        [
            (p["up_momentum"], 1.1),
            (p["up_accel"], 0.8),
            (p["breadth_up"], 0.9),
            (_fall(put_call, 0.35, 0.95), 0.9),
            (_rise(dist_vwap, 0.25, 2.25), 0.8),
            (_fall(vix, 12.0, 22.0), 0.6),
            (p["high_close"], 0.6),
        ]
    )

    fomo = _wm(
        [
            (p["up_accel"], 1.2),
            (p["up_momentum"], 0.8),
            (_rise(rvol, 1.25, 3.0), 1.0),
            (_fall(put_call, 0.25, 0.75), 1.0),
            (_rise(dist_vwap, 0.75, 3.0), 1.0),
            (_rise(attention_z, 1.0, 4.0), 1.0),
            (p["cvd_positive"], 0.5),
        ],
        default=0.0,
    )

    direction_alignment = _wm(
        [
            (_wm([(p["up_momentum"], 1.0), (p["down_momentum"], 1.0)]), 1.0),
            (_wm([(p["cvd_positive"], 1.0), (p["cvd_negative"], 1.0)]), 0.7),
            (_wm([(p["breadth_up"], 1.0), (p["breadth_down"], 1.0)]), 0.7),
            (_abs_rise(((_num(features, "clv") or 0.5) - 0.5), 0.15, 0.45), 0.4),
        ],
        default=0.25,
    )
    contradiction = 0.0
    if p["up_momentum"] is not None and p["cvd_negative"] is not None:
        contradiction = max(contradiction, min(p["up_momentum"], p["cvd_negative"]))
    if p["down_momentum"] is not None and p["cvd_positive"] is not None:
        contradiction = max(contradiction, min(p["down_momentum"], p["cvd_positive"]))
    if p["up_momentum"] is not None and p["breadth_down"] is not None:
        contradiction = max(contradiction, min(p["up_momentum"], p["breadth_down"]))
    if p["down_momentum"] is not None and p["breadth_up"] is not None:
        contradiction = max(contradiction, min(p["down_momentum"], p["breadth_up"]))
    conviction = clip(direction_alignment * (1.0 - 0.65 * contradiction))

    disagreement = _wm(
        [
            (_abs_rise(_num(features, "cvd_divergence"), 0.25, 1.0), 1.2),
            (contradiction, 1.2),
            (_rise(upper_wick, 0.30, 0.70), 0.4),
            (_rise(lower_wick, 0.30, 0.70), 0.4),
            (_bool(features, "doji"), 0.5),
            (_abs_rise(rs_spy, 0.0025, 0.02), 0.4),
            (_abs_rise(news_residual, 0.5, 5.0), 0.6),
        ],
        default=0.0,
    )

    uncertainty = _wm(
        [
            (_rise(vix, 18.0, 40.0), 0.8),
            (_rise(vvix, 95.0, 150.0), 0.5),
            (_rise(iv_rv, 0.03, 0.25), 0.7),
            (disagreement, 1.2),
            (_bool(features, "doji"), 0.5),
            (_rise(upper_wick, 0.35, 0.75), 0.4),
            (_rise(lower_wick, 0.35, 0.75), 0.4),
        ],
        default=0.25,
    )

    attention = _wm(
        [
            (_rise(rvol, 1.0, 3.0), 1.0),
            (_rise(attention_z, 0.5, 4.0), 1.2),
            (_rise((_num(features, "call_volume") or 0.0) + (_num(features, "put_volume") or 0.0), 5_000.0, 500_000.0), 0.3),
            (_rise(atr_exp, 1.0, 2.0), 0.5),
        ],
        default=0.25,
    )

    long_crowding = _wm(
        [
            (_rise(ext_long, 50.0, 95.0), 1.3),
            (_fall(put_call, 0.25, 0.75), 0.9),
            (_rise(dist_vwap, 1.0, 3.5), 0.6),
            (greed, 0.4),
            (fomo, 0.5),
        ],
        default=0.2,
    )
    short_crowding = _wm(
        [
            (_rise(ext_short, 50.0, 95.0), 1.3),
            (_rise(short_interest, 5.0, 20.0), 1.0),
            (_rise(dtc, 1.0, 6.0), 0.8),
            (_rise(borrow, 2.0, 30.0), 0.7),
            (_rise(put_call, 1.0, 2.5), 0.5),
        ],
        default=0.15,
    )

    long_pain = _wm(
        [
            (_rise(-anchor, 0.25, 2.0) if anchor is not None else None, 1.0),
            (_rise(breakdown, 0.0, 1.5), 1.2),
            (p["down_momentum"], 0.8),
            (p["cvd_negative"], 0.6),
        ],
        default=0.1,
    )
    short_pain = _wm(
        [
            (_rise(anchor, 0.25, 2.0), 1.0),
            (_rise(breakout, 0.0, 1.5), 1.2),
            (p["up_momentum"], 0.8),
            (p["cvd_positive"], 0.6),
        ],
        default=0.1,
    )

    bull_exhaustion = _wm(
        [
            (_bool(features, "shooting_star"), 1.1),
            (_rise(upper_wick, 0.35, 0.75), 0.9),
            (p["cvd_bear_div"], 1.2),
            (_rise(dist_vwap, 1.5, 4.0), 0.8),
            (_rise(rvol, 1.5, 3.5), 0.5),
            (fomo, 0.5),
            (p["low_close"], 0.5),
        ],
        default=0.1,
    )
    bear_exhaustion = _wm(
        [
            (_bool(features, "hammer"), 1.1),
            (_rise(lower_wick, 0.35, 0.75), 0.9),
            (p["cvd_bull_div"], 1.2),
            (_rise(-dist_vwap, 1.5, 4.0) if dist_vwap is not None else None, 0.8),
            (_rise(rvol, 1.5, 3.5), 0.5),
            (fear, 0.5),
            (p["high_close"], 0.5),
        ],
        default=0.1,
    )

    return PsychologyVector(
        fear=_pct(fear),
        greed=_pct(greed),
        fomo=_pct(fomo),
        conviction=_pct(conviction),
        uncertainty=_pct(uncertainty),
        attention=_pct(attention),
        disagreement=_pct(disagreement),
        long_crowding=_pct(long_crowding),
        short_crowding=_pct(short_crowding),
        long_pain=_pct(long_pain),
        short_pain=_pct(short_pain),
        bull_exhaustion=_pct(bull_exhaustion),
        bear_exhaustion=_pct(bear_exhaustion),
    )


def infer_regimes(features: FeatureMap, psy: PsychologyVector) -> dict[str, float]:
    p = _directional_primitives(features)
    x = {field.name: getattr(psy, field.name) / 100.0 for field in fields(PsychologyVector)}
    rvol = _rise(_num(features, "rvol"), 1.1, 2.75)
    atr = _rise(_num(features, "atr_expansion"), 1.0, 2.25)
    compression = _num(features, "compression")
    gamma_neg = 1.0 if features.get("gamma_regime") == "negative" else 0.0
    gamma_pos = 1.0 if features.get("gamma_regime") == "positive" else 0.0
    breakout = _rise(_num(features, "breakout_distance_atr"), 0.0, 1.25)
    breakdown = _rise(_num(features, "breakdown_distance_atr"), 0.0, 1.25)
    news_resid = _num(features, "news_reaction_residual")
    positive_news_reject = _rise(-news_resid, 0.5, 5.0) if news_resid is not None else None
    negative_news_absorb = _rise(news_resid, 0.5, 5.0) if news_resid is not None else None

    rules: dict[str, float] = {
        "extreme_fear": _wm([(x["fear"], 1.5), (p["down_momentum"], 1.0), (rvol, 0.7), (p["breadth_down"], 0.8)]),
        "panic": _wm([(x["fear"], 1.3), (p["down_accel"], 1.2), (rvol, 0.8), (atr, 0.8), (gamma_neg, 0.5), (p["low_close"], 0.6)]),
        "capitulation": _wm([(x["fear"], 0.9), (x["bear_exhaustion"], 1.4), (rvol, 0.9), (p["cvd_bull_div"], 1.1), (_bool(features, "hammer"), 0.8)]),
        "despair": _wm([(x["fear"], 0.8), (_fall(_num(features, "rvol"), 0.7, 1.2), 0.6), (compression, 0.5), (x["attention"], 0.2)]),
        "disbelief": _wm([(x["fear"], 0.5), (p["up_short"], 1.0), (p["cvd_positive"], 0.8), (p["breadth_up"], 0.7), (x["short_crowding"], 0.4)]),
        "cautious_optimism": _wm([(p["up_momentum"], 0.8), (p["breadth_up"], 0.8), (x["conviction"], 0.7), (_fall(_num(features, "rvol"), 1.0, 2.5), 0.3)]),
        "confidence": _wm([(p["up_momentum"], 1.0), (x["conviction"], 1.0), (p["breadth_up"], 0.8), (p["cvd_positive"], 0.6)]),
        "complacency": _wm([(x["greed"], 0.6), (_fall(_num(features, "vix"), 12.0, 20.0), 0.9), (compression, 0.7), (x["long_crowding"], 0.8)]),
        "greed": _wm([(x["greed"], 1.4), (p["up_momentum"], 0.8), (p["breadth_up"], 0.5)]),
        "fomo": _wm([(x["fomo"], 1.5), (x["attention"], 0.8), (p["up_accel"], 0.8), (rvol, 0.7)]),
        "euphoria": _wm([(x["fomo"], 1.0), (x["greed"], 1.0), (x["long_crowding"], 0.8), (p["up_accel"], 0.8), (rvol, 0.5)]),
        "exhaustion": _wm([(x["bull_exhaustion"], 1.4), (x["fomo"], 0.5), (x["disagreement"], 0.6), (p["cvd_bear_div"], 0.8)]),
        "distribution": _wm([(x["bull_exhaustion"], 0.9), (p["cvd_bear_div"], 1.0), (_rise(_num(features, "upper_wick_fraction"), 0.35, 0.75), 0.7), (positive_news_reject, 0.6)]),
        "denial": _wm([(x["long_crowding"], 0.7), (x["long_pain"], 0.9), (p["down_short"], 0.8), (x["fear"], 0.5)]),
        "uncertainty": _wm([(x["uncertainty"], 1.4), (x["disagreement"], 1.0), (_bool(features, "doji"), 0.5)]),
        "indecision": _wm([(compression, 1.0), (_bool(features, "inside_bar"), 0.8), (_bool(features, "doji"), 0.8), (_fall(_num(features, "rvol"), 0.6, 1.1), 0.6)]),
        "crowded_bullish": _wm([(x["long_crowding"], 1.4), (x["greed"], 0.7), (p["breadth_down"], 0.5), (x["bull_exhaustion"], 0.5)]),
        "crowded_bearish": _wm([(x["short_crowding"], 1.4), (x["fear"], 0.6), (x["bear_exhaustion"], 0.6), (negative_news_absorb, 0.4)]),
        "short_squeeze": _wm([(x["short_crowding"], 1.1), (x["short_pain"], 1.2), (p["up_accel"], 0.8), (p["cvd_positive"], 0.7), (gamma_neg, 0.6), (breakout, 0.8)]),
        "long_squeeze": _wm([(x["long_crowding"], 1.0), (x["long_pain"], 1.2), (p["down_accel"], 0.8), (p["cvd_negative"], 0.7), (gamma_neg, 0.6), (breakdown, 0.8)]),
        "dip_buying": _wm([(_rise(_num(features, "lower_wick_fraction"), 0.25, 0.65), 0.8), (p["high_close"], 0.6), (p["cvd_positive"], 0.8), (x["conviction"], 0.5)]),
        "failed_dip_buying": _wm([(breakdown, 1.1), (p["down_accel"], 0.9), (p["cvd_negative"], 0.8), (rvol, 0.7), (x["long_pain"], 0.8)]),
        "breakout_conviction": _wm([(breakout, 1.2), (p["up_momentum"], 0.8), (p["cvd_positive"], 0.8), (p["breadth_up"], 0.7), (rvol, 0.7), (p["high_close"], 0.5)]),
        "false_breakout": _wm([(x["bull_exhaustion"], 1.0), (p["cvd_bear_div"], 0.9), (_rise(_num(features, "upper_wick_fraction"), 0.35, 0.75), 0.8), (x["disagreement"], 0.6)]),
        "breakdown_conviction": _wm([(breakdown, 1.2), (p["down_momentum"], 0.8), (p["cvd_negative"], 0.8), (p["breadth_down"], 0.7), (rvol, 0.7), (p["low_close"], 0.5)]),
        "bear_trap": _wm([(x["bear_exhaustion"], 1.1), (p["cvd_bull_div"], 1.0), (_bool(features, "hammer"), 0.8), (negative_news_absorb, 0.6)]),
        "risk_on": _wm([(p["breadth_up"], 1.0), (p["up_momentum"], 0.8), (_rise(_num(features, "hyg_return"), 0.0, 0.01), 0.5), (x["conviction"], 0.6)]),
        "risk_off": _wm([(p["breadth_down"], 1.0), (p["down_momentum"], 0.8), (_rise(-(_num(features, "hyg_return") or 0.0), 0.0, 0.01), 0.5), (x["fear"], 0.7)]),
        "relief_rally": _wm([(x["fear"], 0.5), (p["up_accel"], 0.9), (x["short_crowding"], 0.6), (_fall(_num(features, "vix9d_vix3m_ratio"), 0.8, 1.1), 0.4)]),
        "dead_cat_bounce": _wm([(p["up_short"], 0.8), (p["breadth_down"], 0.8), (x["fear"], 0.6), (x["conviction"], 0.3)]),
        "accumulation": _wm([(p["cvd_positive"], 0.9), (compression, 0.7), (_fall(_num(features, "atr_expansion"), 0.8, 1.2), 0.5), (p["up_short"], 0.4)]),
        "absorption": _wm([(p["cvd_bull_div"], 1.3), (x["bear_exhaustion"], 0.7), (_rise(_num(features, "lower_wick_fraction"), 0.25, 0.70), 0.6), (rvol, 0.6)]),
        "distribution_exhaustion": _wm([(x["bear_exhaustion"], 1.0), (p["cvd_bull_div"], 1.0), (x["fear"], 0.5), (rvol, 0.5)]),
    }
    return {name: _pct(score) for name, score in rules.items()}


def infer_forced_behavior(features: FeatureMap, psy: PsychologyVector, regimes: dict[str, float]) -> ForcedBehaviorVector:
    p = _directional_primitives(features)
    x = {field.name: getattr(psy, field.name) / 100.0 for field in fields(PsychologyVector)}
    gamma_neg = 1.0 if features.get("gamma_regime") == "negative" else 0.0
    gamma_pos = 1.0 if features.get("gamma_regime") == "positive" else 0.0
    near_flip = _fall(_abs_rise(_num(features, "gamma_flip_distance_atr"), 0.0, 2.0), 0.0, 1.0)
    rvol = _rise(_num(features, "rvol"), 1.1, 2.75)
    atr = _rise(_num(features, "atr_expansion"), 1.0, 2.25)
    compression = _num(features, "compression")
    breakout = _rise(_num(features, "breakout_distance_atr"), 0.0, 1.25)
    breakdown = _rise(_num(features, "breakdown_distance_atr"), 0.0, 1.25)

    short_squeeze = _wm([(x["short_crowding"], 1.2), (x["short_pain"], 1.2), (p["up_accel"], 0.9), (p["cvd_positive"], 0.7), (breakout, 0.8), (gamma_neg, 0.6)])
    long_liquidation = _wm([(x["long_crowding"], 1.1), (x["long_pain"], 1.2), (p["down_accel"], 0.9), (p["cvd_negative"], 0.7), (breakdown, 0.8), (gamma_neg, 0.6)])
    gamma_acceleration = _wm([(gamma_neg, 1.5), (near_flip, 0.5), (_wm([(p["up_accel"], 1.0), (p["down_accel"], 1.0)]), 0.8), (rvol, 0.5)])
    capitulation = _wm([(regimes.get("capitulation", 0.0) / 100.0, 1.5), (x["fear"], 0.6), (x["bear_exhaustion"], 0.9), (rvol, 0.6)])
    breakout_cont = _wm([(regimes.get("breakout_conviction", 0.0) / 100.0, 1.2), (p["up_accel"], 0.7), (p["breadth_up"], 0.7), (x["conviction"], 0.7)])
    breakdown_cont = _wm([(regimes.get("breakdown_conviction", 0.0) / 100.0, 1.2), (p["down_accel"], 0.7), (p["breadth_down"], 0.7), (x["conviction"], 0.7)])
    bullish_reversal = _wm([(x["bear_exhaustion"], 1.1), (p["cvd_bull_div"], 1.0), (x["short_crowding"], 0.5), (regimes.get("bear_trap", 0.0) / 100.0, 0.9)])
    bearish_reversal = _wm([(x["bull_exhaustion"], 1.1), (p["cvd_bear_div"], 1.0), (x["long_crowding"], 0.5), (regimes.get("false_breakout", 0.0) / 100.0, 0.9)])
    vol_expansion = _wm([(compression, 0.9), (x["uncertainty"], 0.8), (gamma_neg, 0.7), (near_flip, 0.6), (atr, 0.4)])
    mean_reversion = _wm([(gamma_pos, 1.2), (compression, 0.6), (x["uncertainty"], 0.3), (_fall(_num(features, "rvol"), 0.8, 1.5), 0.4)])

    return ForcedBehaviorVector(
        short_squeeze=_pct(short_squeeze),
        long_liquidation=_pct(long_liquidation),
        gamma_acceleration=_pct(gamma_acceleration),
        capitulation=_pct(capitulation),
        breakout_continuation=_pct(breakout_cont),
        breakdown_continuation=_pct(breakdown_cont),
        bullish_reversal=_pct(bullish_reversal),
        bearish_reversal=_pct(bearish_reversal),
        volatility_expansion=_pct(vol_expansion),
        mean_reversion=_pct(mean_reversion),
    )


def build_evidence(features: FeatureMap) -> tuple[SignalEvidence, ...]:
    definitions = [
        ("rvol", "neutral", 1.0, "Relative volume measures participation versus recent bars."),
        ("atr_expansion", "mixed", 0.8, "ATR expansion measures urgency and range expansion."),
        ("distance_vwap_atr", "mixed", 0.8, "VWAP displacement expresses directional control and extension."),
        ("cvd_divergence", "mixed", 1.2, "Price/CVD disagreement is evidence of absorption or exhaustion."),
        ("breadth", "mixed", 1.0, "Advance/decline participation tests whether index direction is broad."),
        ("put_call_volume", "mixed", 1.0, "Put/call activity approximates hedging/speculative demand."),
        ("skew_25d", "bearish", 0.8, "25-delta IV skew approximates the premium paid for downside protection."),
        ("gamma_flip_distance_atr", "mixed", 1.0, "Distance to the proxy gamma flip marks potential mechanical-regime change."),
        ("short_interest_pct", "mixed", 0.8, "Short interest is stored as slow-moving squeeze fuel, not an intraday signal."),
        ("anchor_distance_atr", "mixed", 0.8, "Distance from anchored VWAP approximates recent holder pain/profit."),
        ("news_reaction_residual", "mixed", 1.0, "Actual move minus expected catalyst response measures expectation mismatch."),
        ("attention_z", "neutral", 0.6, "Attention anomaly supports FOMO/participation inference."),
    ]
    evidence: list[SignalEvidence] = []
    for key, direction, weight, explanation in definitions:
        value = features.get(key)
        if value is None:
            continue
        normalized = None
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            normalized = max(-1.0, min(1.0, float(value)))
        evidence.append(
            SignalEvidence(
                name=key,
                value=value,
                normalized=normalized,
                direction=direction,  # type: ignore[arg-type]
                weight=weight,
                quality=1.0,
                source="normalized_market_snapshot",
                explanation=explanation,
            )
        )
    return tuple(evidence)


def pressure_scores(features: FeatureMap, psy: PsychologyVector, forced: ForcedBehaviorVector) -> tuple[float, float]:
    p = _directional_primitives(features)
    bull = _wm(
        [
            (p["up_momentum"], 1.0),
            (p["up_accel"], 0.8),
            (p["breadth_up"], 0.8),
            (p["cvd_positive"], 0.8),
            (psy.short_pain / 100.0, 0.5),
            (forced.short_squeeze / 100.0, 0.7),
            (forced.breakout_continuation / 100.0, 0.8),
            (forced.bullish_reversal / 100.0, 0.5),
        ],
        default=0.25,
    )
    bear = _wm(
        [
            (p["down_momentum"], 1.0),
            (p["down_accel"], 0.8),
            (p["breadth_down"], 0.8),
            (p["cvd_negative"], 0.8),
            (psy.long_pain / 100.0, 0.5),
            (forced.long_liquidation / 100.0, 0.7),
            (forced.breakdown_continuation / 100.0, 0.8),
            (forced.bearish_reversal / 100.0, 0.5),
        ],
        default=0.25,
    )
    return _pct(bull), _pct(bear)
