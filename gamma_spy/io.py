from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import (
    Bar,
    CatalystObservation,
    MarketInternals,
    MarketSnapshot,
    OptionObservation,
    Positioning,
)


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def snapshot_from_dict(payload: dict[str, Any]) -> MarketSnapshot:
    bars = tuple(
        Bar(
            ts=_dt(row["ts"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
            aggressive_buy_volume=(float(row["aggressive_buy_volume"]) if row.get("aggressive_buy_volume") is not None else None),
            aggressive_sell_volume=(float(row["aggressive_sell_volume"]) if row.get("aggressive_sell_volume") is not None else None),
        )
        for row in payload.get("bars", [])
    )
    options = tuple(
        OptionObservation(
            strike=float(row["strike"]),
            expiration=_dt(row["expiration"]),
            option_type=str(row["option_type"]).lower(),  # type: ignore[arg-type]
            bid=float(row["bid"]) if row.get("bid") is not None else None,
            ask=float(row["ask"]) if row.get("ask") is not None else None,
            volume=float(row.get("volume", 0.0)),
            open_interest=float(row.get("open_interest", 0.0)),
            iv=float(row["iv"]) if row.get("iv") is not None else None,
            delta=float(row["delta"]) if row.get("delta") is not None else None,
            gamma=float(row["gamma"]) if row.get("gamma") is not None else None,
            vega=float(row["vega"]) if row.get("vega") is not None else None,
            theta=float(row["theta"]) if row.get("theta") is not None else None,
        )
        for row in payload.get("options", [])
    )
    internals = MarketInternals(**payload.get("internals", {}))
    positioning = Positioning(**payload.get("positioning", {}))
    catalyst = CatalystObservation(**payload.get("catalyst", {}))
    return MarketSnapshot(
        symbol=str(payload["symbol"]),
        ts=_dt(payload["ts"]),
        bars=bars,
        bar_minutes=int(payload.get("bar_minutes", 1)),
        options=options,
        internals=internals,
        positioning=positioning,
        catalyst=catalyst,
        source=str(payload.get("source", "normalized")),
        source_latency_ms=(float(payload["source_latency_ms"]) if payload.get("source_latency_ms") is not None else None),
        historical_iv=tuple(float(x) for x in payload.get("historical_iv", [])),
    )
