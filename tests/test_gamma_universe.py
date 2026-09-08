from datetime import datetime, timedelta, timezone

from gamma_spy import Bar, GammaBehavioralEngine, GammaUniverseEngine, MarketSnapshot

UTC = timezone.utc


def _snapshot(symbol: str, direction: float) -> MarketSnapshot:
    start = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    price = 100.0
    bars = []
    for i in range(30):
        open_ = price
        close = open_ + direction * 0.08
        volume = 100_000 + i * 1_000
        buy_ratio = 0.70 if direction > 0 else 0.30
        bars.append(
            Bar(
                ts=start + timedelta(minutes=i),
                open=open_,
                high=max(open_, close) + 0.03,
                low=min(open_, close) - 0.03,
                close=close,
                volume=volume,
                aggressive_buy_volume=volume * buy_ratio,
                aggressive_sell_volume=volume * (1.0 - buy_ratio),
            )
        )
        price = close
    return MarketSnapshot(symbol=symbol, ts=bars[-1].ts, bars=tuple(bars))


def test_universe_aggregates_without_execution_authority():
    engine = GammaUniverseEngine(GammaBehavioralEngine(remember_state=False))
    result = engine.evaluate(
        [_snapshot("AAA", 1.0), _snapshot("BBB", -1.0), _snapshot("CCC", 1.0)],
        weights={"AAA": 0.6, "BBB": 0.2, "CCC": 0.2},
        top_n=2,
    )
    assert result.symbol_count == 3
    assert result.evaluated_count == 3
    assert len(result.top_fomo) == 2
    assert result.behavioral_dispersion >= 0.0
    assert all(state.execution_authority is False for state in result.states)
