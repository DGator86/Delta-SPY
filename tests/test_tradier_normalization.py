from datetime import timezone

from gamma_spy.tradier import (
    MinuteBarAccumulator,
    TimesaleAggressorClassifier,
    normalize_option_chain,
    normalize_time_sales_bars,
)

UTC = timezone.utc


def test_normalize_option_chain_preserves_greeks_and_iv():
    payload = {
        "options": {
            "option": [
                {
                    "option_type": "call",
                    "strike": 100,
                    "expiration_date": "2026-09-18",
                    "bid": 2.1,
                    "ask": 2.2,
                    "volume": 123,
                    "open_interest": 456,
                    "greeks": {
                        "mid_iv": 0.31,
                        "delta": 0.52,
                        "gamma": 0.04,
                        "vega": 0.10,
                        "theta": -0.08,
                    },
                }
            ]
        }
    }
    options = normalize_option_chain(payload)
    assert len(options) == 1
    option = options[0]
    assert option.option_type == "call"
    assert option.iv == 0.31
    assert option.open_interest == 456
    assert option.expiration.tzinfo is not None


def test_normalize_aggregate_timesales_leaves_aggressor_unknown():
    payload = {
        "series": {
            "data": [
                {
                    "time": "2026-09-08T09:30:00-04:00",
                    "open": 100,
                    "high": 101,
                    "low": 99.5,
                    "close": 100.5,
                    "volume": 10000,
                },
                {
                    "time": "2026-09-08T09:31:00-04:00",
                    "open": 100.5,
                    "high": 101.2,
                    "low": 100.3,
                    "close": 101.0,
                    "volume": 8000,
                },
            ]
        }
    }
    bars = normalize_time_sales_bars(payload)
    assert len(bars) == 2
    assert bars[0].ts.tzinfo is not None
    assert bars[0].aggressive_buy_volume is None
    assert bars[0].aggressive_sell_volume is None


def test_timesale_classifier_uses_quote_then_tick_rule_and_accumulates_cvd():
    classifier = TimesaleAggressorClassifier()
    accumulator = MinuteBarAccumulator("SPY")

    buy = classifier.classify(
        "SPY",
        {
            "type": "timesale",
            "symbol": "SPY",
            "bid": "100.00",
            "ask": "100.01",
            "last": "100.01",
            "size": "100",
            "date": "1788874200100",
            "cancel": False,
            "correction": False,
        },
    )
    assert buy is not None and buy.side == "buy"
    assert accumulator.push(buy) is None

    sell = classifier.classify(
        "SPY",
        {
            "type": "timesale",
            "symbol": "SPY",
            "bid": "99.99",
            "ask": "100.00",
            "last": "99.99",
            "size": "40",
            "date": "1788874200200",
            "cancel": False,
            "correction": False,
        },
    )
    assert sell is not None and sell.side == "sell"
    assert accumulator.push(sell) is None

    next_minute = classifier.classify(
        "SPY",
        {
            "type": "timesale",
            "symbol": "SPY",
            "bid": "100.02",
            "ask": "100.03",
            "last": "100.03",
            "size": "25",
            "date": "1788874260100",
            "cancel": False,
            "correction": False,
        },
    )
    completed = accumulator.push(next_minute)
    assert completed is not None
    assert completed.volume == 140
    assert completed.aggressive_buy_volume == 100
    assert completed.aggressive_sell_volume == 40


def test_cancelled_or_corrected_timesale_is_dropped():
    classifier = TimesaleAggressorClassifier()
    assert classifier.classify(
        "SPY",
        {"last": 100, "size": 10, "date": 1788874200100, "cancel": True},
    ) is None
