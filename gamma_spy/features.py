from __future__ import annotations

import math
from collections import defaultdict
from statistics import fmean, pstdev
from typing import Iterable

from .contracts import GammaStructure, MarketSnapshot, OptionObservation

EPS = 1e-12


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if abs(den) > EPS else default


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return fmean(values) if values else 0.0


def _std(values: Iterable[float]) -> float:
    values = list(values)
    return pstdev(values) if len(values) > 1 else 0.0


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for a, b in zip(closes, closes[1:]):
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def _true_ranges(snapshot: MarketSnapshot) -> list[float]:
    bars = snapshot.bars
    if not bars:
        return []
    out: list[float] = []
    prev_close = bars[0].close
    for bar in bars:
        out.append(max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close)))
        prev_close = bar.close
    return out


def _vwap(snapshot: MarketSnapshot, window: int = 30) -> float | None:
    bars = snapshot.bars[-window:]
    total_volume = sum(max(0.0, b.volume) for b in bars)
    if not bars or total_volume <= EPS:
        return None
    dollars = sum(((b.high + b.low + b.close) / 3.0) * max(0.0, b.volume) for b in bars)
    return dollars / total_volume


def _obv(snapshot: MarketSnapshot) -> float:
    bars = snapshot.bars
    if len(bars) < 2:
        return 0.0
    total = 0.0
    for prev, cur in zip(bars, bars[1:]):
        if cur.close > prev.close:
            total += cur.volume
        elif cur.close < prev.close:
            total -= cur.volume
    return total


def _cvd_series(snapshot: MarketSnapshot) -> list[float]:
    cvd: list[float] = []
    running = 0.0
    for bar in snapshot.bars:
        if bar.aggressive_buy_volume is None or bar.aggressive_sell_volume is None:
            cvd.append(running)
            continue
        running += bar.aggressive_buy_volume - bar.aggressive_sell_volume
        cvd.append(running)
    return cvd


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_d1(spot: float, strike: float, t: float, sigma: float, rate: float) -> float:
    if spot <= 0 or strike <= 0 or t <= 0 or sigma <= 0:
        return 0.0
    return (math.log(spot / strike) + (rate + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))


def _bs_delta(kind: str, spot: float, strike: float, t: float, sigma: float, rate: float) -> float:
    d1 = _bs_d1(spot, strike, t, sigma, rate)
    if kind == "call":
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


def _bs_gamma(spot: float, strike: float, t: float, sigma: float, rate: float) -> float:
    if spot <= 0 or t <= 0 or sigma <= 0:
        return 0.0
    d1 = _bs_d1(spot, strike, t, sigma, rate)
    return _norm_pdf(d1) / (spot * sigma * math.sqrt(t))


def _option_t_years(snapshot: MarketSnapshot, option: OptionObservation) -> float:
    seconds = max(60.0, (option.expiration - snapshot.ts).total_seconds())
    return seconds / (365.0 * 24.0 * 3600.0)


def _signed_option_load(
    snapshot: MarketSnapshot,
    option: OptionObservation,
    spot: float,
    rate: float,
) -> tuple[float, float, float]:
    """Return signed gamma, vanna and charm proxies.

    The sign convention is deliberately a proxy: call OI is assigned +1 and put OI -1.
    It is NOT a claim about actual dealer inventory. Delta/Gamma consumers must preserve that label.
    """
    t = _option_t_years(snapshot, option)
    sigma = option.iv if option.iv and option.iv > 0 else None
    if sigma is None:
        return 0.0, 0.0, 0.0
    sign = 1.0 if option.option_type == "call" else -1.0
    oi_contracts = max(0.0, option.open_interest)
    multiplier = 100.0
    gamma = _bs_gamma(spot, option.strike, t, sigma, rate)
    gamma_load = sign * gamma * oi_contracts * multiplier * spot * spot * 0.01

    sigma_step = max(0.0025, sigma * 0.01)
    d_up = _bs_delta(option.option_type, spot, option.strike, t, sigma + sigma_step, rate)
    d_dn = _bs_delta(option.option_type, spot, option.strike, t, max(0.001, sigma - sigma_step), rate)
    vanna = safe_div(d_up - d_dn, 2.0 * sigma_step)
    vanna_load = sign * vanna * oi_contracts * multiplier

    one_day = 1.0 / 365.0
    t_next = max(1.0 / (365.0 * 24.0), t - one_day)
    d_now = _bs_delta(option.option_type, spot, option.strike, t, sigma, rate)
    d_next = _bs_delta(option.option_type, spot, option.strike, t_next, sigma, rate)
    charm_per_day = d_next - d_now
    charm_load = sign * charm_per_day * oi_contracts * multiplier
    return gamma_load, vanna_load, charm_load


def estimate_gamma_structure(snapshot: MarketSnapshot, rate: float = 0.04) -> GammaStructure:
    if not snapshot.bars or not snapshot.options:
        return GammaStructure(
            signed_gex_proxy=None,
            gamma_regime="unknown",
            gamma_flip=None,
            call_wall=None,
            put_wall=None,
            call_gamma_load=None,
            put_gamma_load=None,
            vanna_proxy=None,
            charm_proxy=None,
            dealer_position_assumption="No options data; dealer gamma unknown.",
        )

    spot = snapshot.bars[-1].close
    signed = 0.0
    vanna = 0.0
    charm = 0.0
    call_by_strike: dict[float, float] = defaultdict(float)
    put_by_strike: dict[float, float] = defaultdict(float)

    usable: list[OptionObservation] = []
    for option in snapshot.options:
        if option.iv is None or option.iv <= 0 or option.open_interest <= 0:
            continue
        usable.append(option)
        g, v, c = _signed_option_load(snapshot, option, spot, rate)
        signed += g
        vanna += v
        charm += c
        if option.option_type == "call":
            call_by_strike[option.strike] += abs(g)
        else:
            put_by_strike[option.strike] += abs(g)

    if not usable:
        return GammaStructure(
            signed_gex_proxy=None,
            gamma_regime="unknown",
            gamma_flip=None,
            call_wall=None,
            put_wall=None,
            call_gamma_load=None,
            put_gamma_load=None,
            vanna_proxy=None,
            charm_proxy=None,
            dealer_position_assumption="Options present but insufficient IV/OI for GEX proxy.",
        )

    scale = sum(call_by_strike.values()) + sum(put_by_strike.values())
    neutral_band = max(1.0, scale * 0.02)
    regime = "neutral" if abs(signed) <= neutral_band else ("positive" if signed > 0 else "negative")
    call_wall = max(call_by_strike, key=call_by_strike.get) if call_by_strike else None
    put_wall = max(put_by_strike, key=put_by_strike.get) if put_by_strike else None

    # Scan a bounded spot grid for the nearest sign change in the same explicitly-labeled proxy.
    scan = [spot * (0.90 + i * 0.0025) for i in range(81)]
    values: list[tuple[float, float]] = []
    for scan_spot in scan:
        total = 0.0
        for option in usable:
            g, _, _ = _signed_option_load(snapshot, option, scan_spot, rate)
            total += g
        values.append((scan_spot, total))
    crossings: list[float] = []
    for (s1, g1), (s2, g2) in zip(values, values[1:]):
        if g1 == 0:
            crossings.append(s1)
        elif g1 * g2 < 0:
            frac = abs(g1) / (abs(g1) + abs(g2))
            crossings.append(s1 + frac * (s2 - s1))
    gamma_flip = min(crossings, key=lambda x: abs(x - spot)) if crossings else None

    return GammaStructure(
        signed_gex_proxy=signed,
        gamma_regime=regime,  # type: ignore[arg-type]
        gamma_flip=gamma_flip,
        call_wall=call_wall,
        put_wall=put_wall,
        call_gamma_load=sum(call_by_strike.values()) or None,
        put_gamma_load=sum(put_by_strike.values()) or None,
        vanna_proxy=vanna,
        charm_proxy=charm,
        dealer_position_assumption=(
            "Proxy convention: call OI contributes positive gamma and put OI negative gamma; "
            "actual dealer long/short inventory is unobserved."
        ),
    )


def _option_features(snapshot: MarketSnapshot, gamma: GammaStructure) -> dict[str, float | str | bool | None]:
    calls = [o for o in snapshot.options if o.option_type == "call"]
    puts = [o for o in snapshot.options if o.option_type == "put"]
    call_vol = sum(max(0.0, o.volume) for o in calls)
    put_vol = sum(max(0.0, o.volume) for o in puts)
    call_oi = sum(max(0.0, o.open_interest) for o in calls)
    put_oi = sum(max(0.0, o.open_interest) for o in puts)

    def delta25_iv(options: list[OptionObservation]) -> float | None:
        usable = [o for o in options if o.iv is not None and o.delta is not None]
        if not usable:
            return None
        target = 0.25
        chosen = min(usable, key=lambda o: abs(abs(float(o.delta)) - target))
        return float(chosen.iv) if chosen.iv is not None else None

    call25 = delta25_iv(calls)
    put25 = delta25_iv(puts)
    skew = (put25 - call25) if put25 is not None and call25 is not None else None

    spot = snapshot.bars[-1].close if snapshot.bars else 0.0
    atm = sorted(
        [o for o in snapshot.options if o.iv is not None],
        key=lambda o: abs(o.strike - spot),
    )[:6]
    atm_iv = _mean(float(o.iv) for o in atm if o.iv is not None) if atm else None
    iv_rank = None
    if atm_iv is not None and snapshot.historical_iv:
        low, high = min(snapshot.historical_iv), max(snapshot.historical_iv)
        iv_rank = 100.0 * safe_div(atm_iv - low, high - low, 0.5)
        iv_rank = max(0.0, min(100.0, iv_rank))

    gamma_flip_distance_atr = None
    if gamma.gamma_flip is not None:
        atr = _mean(_true_ranges(snapshot)[-14:])
        if atr > EPS:
            gamma_flip_distance_atr = (spot - gamma.gamma_flip) / atr

    return {
        "put_call_volume": safe_div(put_vol, call_vol, 1.0 if put_vol else 0.0),
        "put_call_oi": safe_div(put_oi, call_oi, 1.0 if put_oi else 0.0),
        "call_volume": call_vol,
        "put_volume": put_vol,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "skew_25d": skew,
        "atm_iv": atm_iv,
        "iv_rank": iv_rank,
        "gamma_regime": gamma.gamma_regime,
        "gamma_flip_distance_atr": gamma_flip_distance_atr,
        "call_wall": gamma.call_wall,
        "put_wall": gamma.put_wall,
    }


def _candle_features(snapshot: MarketSnapshot) -> dict[str, float | bool | None]:
    bars = snapshot.bars
    if not bars:
        return {}
    b = bars[-1]
    spread = max(EPS, b.high - b.low)
    body = abs(b.close - b.open)
    upper = b.high - max(b.open, b.close)
    lower = min(b.open, b.close) - b.low
    clv = (b.close - b.low) / spread
    bullish = b.close > b.open
    prior = bars[-2] if len(bars) >= 2 else b
    prev_body_hi = max(prior.open, prior.close)
    prev_body_lo = min(prior.open, prior.close)
    body_hi = max(b.open, b.close)
    body_lo = min(b.open, b.close)

    bullish_engulfing = bool(
        len(bars) >= 2 and prior.close < prior.open and bullish and body_lo <= prev_body_lo and body_hi >= prev_body_hi
    )
    bearish_engulfing = bool(
        len(bars) >= 2 and prior.close > prior.open and not bullish and body_lo <= prev_body_lo and body_hi >= prev_body_hi
    )
    hammer = bool(lower >= max(body * 2.0, spread * 0.45) and upper <= spread * 0.20 and clv >= 0.55)
    shooting_star = bool(upper >= max(body * 2.0, spread * 0.45) and lower <= spread * 0.20 and clv <= 0.45)
    doji = bool(body / spread <= 0.10)
    inside_bar = bool(len(bars) >= 2 and b.high < prior.high and b.low > prior.low)
    outside_bar = bool(len(bars) >= 2 and b.high > prior.high and b.low < prior.low)

    return {
        "clv": clv,
        "body_fraction": body / spread,
        "upper_wick_fraction": upper / spread,
        "lower_wick_fraction": lower / spread,
        "hammer": hammer,
        "shooting_star": shooting_star,
        "doji": doji,
        "bullish_engulfing": bullish_engulfing,
        "bearish_engulfing": bearish_engulfing,
        "inside_bar": inside_bar,
        "outside_bar": outside_bar,
    }


def extract_features(snapshot: MarketSnapshot, rate: float = 0.04) -> tuple[dict[str, float | str | bool | None], GammaStructure]:
    bars = list(snapshot.bars)
    if len(bars) < 2:
        raise ValueError("Gamma requires at least two bars; 20+ is recommended for stable features.")
    closes = [b.close for b in bars]
    volumes = [max(0.0, b.volume) for b in bars]
    trs = _true_ranges(snapshot)
    atr14 = _mean(trs[-14:])
    atr_baseline = _mean(trs[-60:-14]) if len(trs) > 20 else _mean(trs[:-1])
    atr_expansion = safe_div(atr14, atr_baseline, 1.0)
    prior_vol = _mean(volumes[-21:-1]) if len(volumes) >= 3 else _mean(volumes[:-1])
    rvol = safe_div(volumes[-1], prior_vol, 1.0)
    vwap = _vwap(snapshot)
    distance_vwap_atr = safe_div(closes[-1] - vwap, atr14) if vwap is not None else None

    log_returns = _returns(closes)
    bars_per_year = 252.0 * 390.0 / max(1, snapshot.bar_minutes)
    realized_vol = _std(log_returns[-60:]) * math.sqrt(bars_per_year) if log_returns else 0.0

    def ret(n: int) -> float:
        if len(closes) <= n or closes[-n - 1] == 0:
            return 0.0
        return closes[-1] / closes[-n - 1] - 1.0

    momentum_1 = ret(1)
    momentum_3 = ret(min(3, len(closes) - 1))
    momentum_5 = ret(min(5, len(closes) - 1))
    if len(closes) >= 7:
        prior3 = closes[-4] / closes[-7] - 1.0
    else:
        prior3 = 0.0
    momentum_accel_atr = safe_div((momentum_3 - prior3) * closes[-1], atr14)

    cvd = _cvd_series(snapshot)
    has_cvd = any(
        b.aggressive_buy_volume is not None and b.aggressive_sell_volume is not None for b in bars
    )
    lookback = min(5, len(bars) - 1)
    price_change = closes[-1] - closes[-1 - lookback]
    cvd_change = cvd[-1] - cvd[-1 - lookback] if has_cvd else 0.0
    price_direction = 1 if price_change > 0 else (-1 if price_change < 0 else 0)
    cvd_direction = 1 if cvd_change > 0 else (-1 if cvd_change < 0 else 0)
    cvd_divergence = (cvd_direction - price_direction) / 2.0 if has_cvd else 0.0
    current_net_flow = 0.0
    last = bars[-1]
    if last.aggressive_buy_volume is not None and last.aggressive_sell_volume is not None:
        current_net_flow = last.aggressive_buy_volume - last.aggressive_sell_volume
    flow_efficiency = safe_div(abs(last.close - last.open), abs(current_net_flow), 0.0) if has_cvd else None

    internals = snapshot.internals
    breadth = None
    if internals.advancers is not None and internals.decliners is not None:
        breadth = safe_div(internals.advancers, internals.advancers + internals.decliners, 0.5)
    up_down_volume = None
    if internals.up_volume is not None and internals.down_volume is not None:
        up_down_volume = safe_div(internals.up_volume, internals.down_volume, 1.0)
    high_low_ratio = None
    if internals.new_highs is not None and internals.new_lows is not None:
        high_low_ratio = safe_div(internals.new_highs, internals.new_lows, 1.0)

    gamma = estimate_gamma_structure(snapshot, rate=rate)
    option_features = _option_features(snapshot, gamma)

    relative_strength_spy = momentum_5 - internals.spy_return if internals.spy_return is not None else None
    relative_strength_sector = momentum_5 - internals.sector_return if internals.sector_return is not None else None
    iv_rv_spread = None
    if option_features.get("atm_iv") is not None:
        iv_rv_spread = float(option_features["atm_iv"]) - realized_vol

    p = snapshot.positioning
    breakout_distance_atr = safe_div(closes[-1] - p.resistance_level, atr14) if p.resistance_level is not None else None
    breakdown_distance_atr = safe_div(p.support_level - closes[-1], atr14) if p.support_level is not None else None
    anchor_distance_atr = safe_div(closes[-1] - p.anchored_vwap, atr14) if p.anchored_vwap is not None else None

    catalyst = snapshot.catalyst
    news_residual = None
    if catalyst.actual_move_pct is not None and catalyst.expected_move_pct is not None:
        directional_hint = catalyst.surprise if catalyst.surprise is not None else catalyst.sentiment
        expected_signed = abs(catalyst.expected_move_pct) * (1.0 if (directional_hint or 0.0) >= 0 else -1.0)
        news_residual = catalyst.actual_move_pct - expected_signed

    short_atr = _mean(trs[-5:])
    long_atr = _mean(trs[-30:]) if len(trs) >= 10 else atr14
    compression = 1.0 - clip(safe_div(short_atr, long_atr, 1.0) / 1.25)

    features: dict[str, float | str | bool | None] = {
        "spot": closes[-1],
        "return_1": momentum_1,
        "return_3": momentum_3,
        "return_5": momentum_5,
        "momentum_accel_atr": momentum_accel_atr,
        "atr14": atr14,
        "atr_expansion": atr_expansion,
        "rvol": rvol,
        "vwap": vwap,
        "distance_vwap_atr": distance_vwap_atr,
        "realized_vol": realized_vol,
        "obv": _obv(snapshot),
        "cvd": cvd[-1] if has_cvd else None,
        "cvd_change_5": cvd_change if has_cvd else None,
        "cvd_divergence": cvd_divergence if has_cvd else None,
        "flow_efficiency": flow_efficiency,
        "breadth": breadth,
        "up_down_volume": up_down_volume,
        "new_high_low_ratio": high_low_ratio,
        "pct_above_20d": internals.pct_above_20d,
        "tick": internals.tick,
        "trin": internals.trin,
        "vix": internals.vix,
        "vvix": internals.vvix,
        "vix9d_vix3m_ratio": safe_div(internals.vix9d, internals.vix3m, 1.0)
        if internals.vix9d is not None and internals.vix3m is not None
        else None,
        "relative_strength_spy": relative_strength_spy,
        "relative_strength_sector": relative_strength_sector,
        "hyg_return": internals.hyg_return,
        "uup_return": internals.uup_return,
        "tlt_return": internals.tlt_return,
        "short_interest_pct": p.short_interest_pct,
        "days_to_cover": p.days_to_cover,
        "borrow_rate_pct": p.borrow_rate_pct,
        "long_crowding_external": p.long_crowding_score,
        "short_crowding_external": p.short_crowding_score,
        "liquidity_score": p.liquidity_score,
        "breakout_distance_atr": breakout_distance_atr,
        "breakdown_distance_atr": breakdown_distance_atr,
        "anchor_distance_atr": anchor_distance_atr,
        "catalyst_sentiment": catalyst.sentiment,
        "catalyst_surprise": catalyst.surprise,
        "attention_z": catalyst.attention_z,
        "news_reaction_residual": news_residual,
        "compression": compression,
        "iv_rv_spread": iv_rv_spread,
    }
    features.update(_candle_features(snapshot))
    features.update(option_features)
    return features, gamma
