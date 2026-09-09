from datetime import datetime, timedelta, timezone

import pytest

from gamma_spy import Bar, GammaBehavioralEngine
from gamma_spy.capture import JsonlTapeWriter, read_tape
from gamma_spy.runtime import GammaRuntime

UTC = timezone.utc


def _bars() -> list[Bar]:
    start = datetime(2026, 9, 8, 13, 30, tzinfo=UTC)
    result = []
    price = 100.0
    for i in range(25):
        close = price + 0.05
        result.append(
            Bar(
                ts=start + timedelta(minutes=i),
                open=price,
                high=close + 0.02,
                low=price - 0.02,
                close=close,
                volume=10_000 + i * 100,
                aggressive_buy_volume=7_000 + i * 70,
                aggressive_sell_volume=3_000 + i * 30,
            )
        )
        price = close
    return result


def test_runtime_freezes_evaluates_and_writes_verified_tape(tmp_path):
    tape_path = tmp_path / "gamma.jsonl"
    runtime = GammaRuntime(
        engine=GammaBehavioralEngine(remember_state=True),
        tape=JsonlTapeWriter(tape_path, fsync=False),
    )
    runtime.push_bars("SPY", _bars())
    state = runtime.evaluate("SPY")
    records = read_tape(tape_path, verify=True)
    assert state.symbol == "SPY"
    assert [record["record_type"] for record in records] == [
        "market_snapshot",
        "behavioral_state",
    ]
    assert state.execution_authority is False


def test_tape_detects_payload_tampering(tmp_path):
    tape_path = tmp_path / "gamma.jsonl"
    writer = JsonlTapeWriter(tape_path, fsync=False)
    writer.append("example", {"x": 1}, observed_at=_bars()[0].ts, source="test")
    text = tape_path.read_text(encoding="utf-8").replace('"x":1', '"x":2')
    tape_path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_tape(tape_path, verify=True)
