from datetime import datetime, timedelta, timezone

from gamma_spy import (
    Bar,
    CatalystObservation,
    GammaBehavioralEngine,
    MarketInternals,
    MarketSnapshot,
    OptionObservation,
    Positioning,
)

UTC = timezone.utc


def make_bars(direction: float, *, buy_ratio: float, n: int = 40) -> tuple[Bar, ...]:
    start = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    price = 100.0
    bars = []
    for i in range(n):
        open_ = price
        close = open_ + direction * (0.08 + i * 0.001)
        high = max(open_, close) + 0.05
        low = min(open_, close) - 0.05
        volume = 100_000 + i * 3_000
        buy = volume * buy_ratio
        sell = volume - buy
        bars.append(
            Bar(
                ts=start + timedelta(minutes=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                aggressive_buy_volume=buy,
                aggressive_sell_volume=sell,
            )
        )
        price = close
    return tuple(bars)


def make_options(ts: datetime, spot: float, *, put_heavy: bool) -> tuple[OptionObservation, ...]:
    expiry = ts + timedelta(days=7)
    out = []
    for strike in (spot - 5, spot, spot + 5):
        out.append(
            OptionObservation(
                strike=strike,
                expiration=expiry,
                option_type="call",
                volume=2_000 if not put_heavy else 400,
                open_interest=4_000 if not put_heavy else 2_000,
                iv=0.30,
                delta=0.25 if strike > spot else 0.55,
            )
        )
        out.append(
            OptionObservation(
                strike=strike,
                expiration=expiry,
                option_type="put",
                volume=3_000 if put_heavy else 500,
                open_interest=8_000 if put_heavy else 2_000,
                iv=0.38 if put_heavy else 0.31,
                delta=-0.25 if strike < spot else -0.55,
            )
        )
    return tuple(out)


def test_panic_snapshot_scores_fear_above_greed_and_never_executes():
    bars = make_bars(-1.0, buy_ratio=0.20)
    ts = bars[-1].ts
    snapshot = MarketSnapshot(
        symbol="SPY",
        ts=ts,
        bars=bars,
        options=make_options(ts, bars[-1].close, put_heavy=True),
        internals=MarketInternals(
            advancers=70,
            decliners=430,
            up_volume=1.0,
            down_volume=7.0,
            pct_above_20d=15.0,
            tick=-1100,
            trin=2.1,
            vix=38.0,
            vvix=145.0,
            vix9d=42.0,
            vix3m=30.0,
            spy_return=-0.025,
            hyg_return=-0.01,
        ),
        positioning=Positioning(
            long_crowding_score=85.0,
            anchored_vwap=104.0,
            support_level=98.0,
            resistance_level=106.0,
        ),
        catalyst=CatalystObservation(sentiment=-0.8, surprise=-0.9, attention_z=3.0),
    )
    state = GammaBehavioralEngine(remember_state=False).evaluate(snapshot)
    assert state.psychology.fear > state.psychology.greed
    assert state.bearish_pressure > state.bullish_pressure
    assert state.forced_behavior.long_liquidation > 45.0
    assert state.trading_authority is False
    assert state.execution_authority is False
    assert any("DEALER_GAMMA_IS_PROXY" in warning for warning in state.warnings)


def test_squeeze_snapshot_detects_short_pressure():
    bars = make_bars(1.0, buy_ratio=0.82)
    ts = bars[-1].ts
    snapshot = MarketSnapshot(
        symbol="XYZ",
        ts=ts,
        bars=bars,
        options=make_options(ts, bars[-1].close, put_heavy=False),
        internals=MarketInternals(
            advancers=390,
            decliners=110,
            up_volume=5.0,
            down_volume=1.0,
            pct_above_20d=75.0,
            vix=18.0,
            spy_return=0.004,
            sector_return=0.003,
        ),
        positioning=Positioning(
            short_interest_pct=24.0,
            days_to_cover=7.0,
            borrow_rate_pct=22.0,
            short_crowding_score=92.0,
            anchored_vwap=101.0,
            resistance_level=102.0,
            support_level=98.0,
        ),
        catalyst=CatalystObservation(sentiment=0.8, surprise=0.8, attention_z=3.5),
    )
    state = GammaBehavioralEngine(remember_state=False).evaluate(snapshot)
    assert state.psychology.short_crowding > 70.0
    assert state.psychology.short_pain > 50.0
    assert state.forced_behavior.short_squeeze > 55.0
    assert state.bullish_pressure > state.bearish_pressure


def test_missing_optional_sources_reduce_quality_without_failure():
    bars = make_bars(0.2, buy_ratio=0.50, n=25)
    snapshot = MarketSnapshot(symbol="SPY", ts=bars[-1].ts, bars=bars)
    state = GammaBehavioralEngine(remember_state=False).evaluate(snapshot)
    assert 0.0 <= state.data_quality < 80.0
    assert state.gamma.gamma_regime == "unknown"
    assert any("OPTIONS_MISSING" in warning for warning in state.warnings)
    assert isinstance(state.to_dict(), dict)


def test_transition_velocity_uses_only_prior_state():
    engine = GammaBehavioralEngine(remember_state=True)
    down = make_bars(-0.4, buy_ratio=0.30)
    first = MarketSnapshot(symbol="SPY", ts=down[-1].ts, bars=down)
    state1 = engine.evaluate(first)
    up = make_bars(0.5, buy_ratio=0.75)
    shifted = tuple(
        Bar(
            ts=b.ts + timedelta(hours=1),
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
            aggressive_buy_volume=b.aggressive_buy_volume,
            aggressive_sell_volume=b.aggressive_sell_volume,
        )
        for b in up
    )
    second = MarketSnapshot(symbol="SPY", ts=shifted[-1].ts, bars=shifted)
    state2 = engine.evaluate(second)
    assert state1.transition_velocity["fear"] == 0.0
    assert state2.transition_velocity["fear"] != 0.0
