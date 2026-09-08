from datetime import datetime, timedelta, timezone

from gamma_spy import (
    Bar,
    GammaBehavioralEngine,
    GammaUniverseEngine,
    MarketSnapshot,
    select_top_weight_mass,
    synthesize_index_field,
)

UTC = timezone.utc


def _snapshot(symbol: str, direction: float) -> MarketSnapshot:
    start = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    price = 100.0
    bars = []
    for i in range(30):
        open_ = price
        close = open_ + direction * 0.09
        volume = 100_000 + i * 2_000
        buy_ratio = 0.75 if direction > 0 else 0.25
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


def test_select_top_weight_mass_reaches_target_with_smallest_prefix():
    selected = select_top_weight_mass(
        {"A": 0.12, "B": 0.08, "C": 0.05, "D": 0.04, "E": 0.03},
        fraction=0.25,
    )
    assert selected == ("A", "B", "C")


def test_index_field_compares_direct_spy_with_constituent_field():
    state_engine = GammaBehavioralEngine(remember_state=False)
    spy = state_engine.evaluate(_snapshot("SPY", 1.0))
    universe = GammaUniverseEngine(state_engine).evaluate(
        [_snapshot("AAA", 1.0), _snapshot("BBB", 1.0), _snapshot("CCC", -1.0)],
        weights={"AAA": 0.60, "BBB": 0.25, "CCC": 0.15},
    )
    field = synthesize_index_field(spy, universe)
    assert field.index_symbol == "SPY"
    assert field.direct_balance > 0
    assert field.constituent_balance > 0
    assert field.alignment > 0
    assert field.quality >= 0
