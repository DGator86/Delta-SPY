from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .contracts import Bar, OptionObservation

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")


class TradierMarketDataError(RuntimeError):
    pass


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1e12:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=UTC)
    if not isinstance(value, str):
        raise ValueError(f"unsupported timestamp value: {value!r}")
    text = value.strip()
    numeric_text = text.lstrip("+-").replace(".", "", 1)
    if numeric_text.isdigit():
        numeric = float(text)
        if numeric > 1e12:
            numeric /= 1000.0
        return datetime.fromtimestamp(numeric, tz=UTC)
    text = text.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=EASTERN).astimezone(UTC)


def _expiration_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=EASTERN)
    if isinstance(value, date):
        d = value
    else:
        d = date.fromisoformat(str(value)[:10])
    return datetime(d.year, d.month, d.day, 16, 0, tzinfo=EASTERN).astimezone(UTC)


class TradierMarketDataClient:
    """Read-only Tradier market-data adapter.

    This class deliberately exposes no account, order, position or execution endpoint.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.tradier.com/v1",
        timeout: float = 12.0,
    ) -> None:
        if not token:
            raise ValueError("Tradier token is required")
        self._token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = ""
        if params:
            query = "?" + urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.base_url}{path}{query}"
        data = None
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }
        if form is not None:
            data = urlencode({k: v for k, v in form.items() if v is not None}).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif method.upper() == "POST":
            data = b""
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(request, timeout=self.timeout) as response:  # nosec B310 - fixed HTTPS API base by default
                raw = response.read().decode("utf-8")
        except Exception as exc:  # urllib raises several transport/status subclasses
            raise TradierMarketDataError(f"Tradier market-data request failed: {path}: {exc}") from exc
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise TradierMarketDataError(f"Tradier returned invalid JSON for {path}") from exc
        if not isinstance(payload, dict):
            raise TradierMarketDataError(f"Unexpected Tradier payload for {path}: expected object")
        return payload

    def quotes(self, symbols: Iterable[str], *, greeks: bool = False, use_post: bool = False) -> dict[str, Any]:
        symbol_csv = ",".join(s.upper() for s in symbols if s)
        if not symbol_csv:
            raise ValueError("at least one symbol is required")
        if use_post:
            return self._request_json(
                "POST",
                "/markets/quotes",
                form={"symbols": symbol_csv, "greeks": str(greeks).lower()},
            )
        return self._request_json(
            "GET",
            "/markets/quotes",
            params={"symbols": symbol_csv, "greeks": str(greeks).lower()},
        )

    def option_expirations(self, symbol: str, *, include_all_roots: bool = False) -> list[str]:
        payload = self._request_json(
            "GET",
            "/markets/options/expirations",
            params={
                "symbol": symbol.upper(),
                "includeAllRoots": str(include_all_roots).lower(),
                "strikes": "false",
            },
        )
        expirations = payload.get("expirations") or {}
        raw = expirations.get("date") if isinstance(expirations, dict) else expirations
        return [str(item) for item in _as_list(raw)]

    def option_chain(self, symbol: str, expiration: str, *, greeks: bool = True) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/markets/options/chains",
            params={
                "symbol": symbol.upper(),
                "expiration": expiration,
                "greeks": str(greeks).lower(),
            },
        )

    def time_sales(
        self,
        symbol: str,
        *,
        interval: str = "1min",
        start: str | None = None,
        end: str | None = None,
        session_filter: str = "open",
    ) -> dict[str, Any]:
        return self._request_json(
            "GET",
            "/markets/timesales",
            params={
                "symbol": symbol.upper(),
                "interval": interval,
                "start": start,
                "end": end,
                "session_filter": session_filter,
            },
        )

    def create_stream_session(self) -> str:
        payload = self._request_json("POST", "/markets/events/session")
        stream = payload.get("stream") or {}
        sessionid = stream.get("sessionid") if isinstance(stream, dict) else None
        if not sessionid:
            raise TradierMarketDataError("Tradier market stream session response had no sessionid")
        return str(sessionid)


def normalize_option_chain(payload: dict[str, Any]) -> tuple[OptionObservation, ...]:
    options = payload.get("options") or {}
    rows = options.get("option") if isinstance(options, dict) else options
    result: list[OptionObservation] = []
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        kind = str(row.get("option_type") or row.get("type") or "").lower()
        if kind not in {"call", "put"}:
            continue
        greeks = row.get("greeks") or {}
        if not isinstance(greeks, dict):
            greeks = {}
        expiration = row.get("expiration_date") or row.get("expiration")
        strike = row.get("strike")
        if expiration is None or strike is None:
            continue
        iv = (
            greeks.get("mid_iv")
            if greeks.get("mid_iv") is not None
            else greeks.get("smv_vol")
        )
        if iv is None:
            iv = row.get("iv")
        result.append(
            OptionObservation(
                strike=float(strike),
                expiration=_expiration_datetime(expiration),
                option_type=kind,  # type: ignore[arg-type]
                bid=float(row["bid"]) if row.get("bid") is not None else None,
                ask=float(row["ask"]) if row.get("ask") is not None else None,
                volume=float(row.get("volume") or 0.0),
                open_interest=float(row.get("open_interest") or 0.0),
                iv=float(iv) if iv is not None else None,
                delta=float(greeks["delta"]) if greeks.get("delta") is not None else None,
                gamma=float(greeks["gamma"]) if greeks.get("gamma") is not None else None,
                vega=float(greeks["vega"]) if greeks.get("vega") is not None else None,
                theta=float(greeks["theta"]) if greeks.get("theta") is not None else None,
            )
        )
    return tuple(result)


def normalize_time_sales_bars(payload: dict[str, Any]) -> tuple[Bar, ...]:
    """Normalize aggregate 1m/5m/15m Time & Sales rows to Bars.

    Aggregate REST rows do not expose exchange-native aggressor side, so buy/sell volume remains None.
    """
    series = payload.get("series") or {}
    rows = series.get("data") if isinstance(series, dict) else series
    result: list[Bar] = []
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        ts_value = row.get("timestamp") or row.get("time") or row.get("date")
        required = (row.get("open"), row.get("high"), row.get("low"), row.get("close"))
        if ts_value is None or any(value is None for value in required):
            continue
        result.append(
            Bar(
                ts=_parse_ts(ts_value),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0.0),
            )
        )
    result.sort(key=lambda bar: bar.ts)
    return tuple(result)


@dataclass(frozen=True)
class ClassifiedTrade:
    ts: datetime
    price: float
    size: float
    side: str  # buy / sell / neutral
    bid: float | None
    ask: float | None


class TimesaleAggressorClassifier:
    """Quote/tick-rule aggressor-side proxy for Tradier streaming timesales.

    Tradier timesale fields contain bid/ask/last/size but do not assert exchange-native initiator side.
    This classifier therefore labels its result as a proxy.
    """

    def __init__(self) -> None:
        self._last_price: dict[str, float] = {}

    def classify(self, symbol: str, event: dict[str, Any]) -> ClassifiedTrade | None:
        if event.get("cancel") or event.get("correction"):
            return None
        last = event.get("last")
        size = event.get("size")
        ts_value = event.get("date") or event.get("timestamp") or event.get("time")
        if last is None or size is None or ts_value is None:
            return None
        price = float(last)
        quantity = max(0.0, float(size))
        bid = float(event["bid"]) if event.get("bid") is not None else None
        ask = float(event["ask"]) if event.get("ask") is not None else None
        epsilon = max(1e-8, price * 1e-8)
        side = "neutral"
        if ask is not None and price >= ask - epsilon:
            side = "buy"
        elif bid is not None and price <= bid + epsilon:
            side = "sell"
        else:
            prior = self._last_price.get(symbol.upper())
            if prior is not None:
                if price > prior:
                    side = "buy"
                elif price < prior:
                    side = "sell"
        self._last_price[symbol.upper()] = price
        return ClassifiedTrade(
            ts=_parse_ts(ts_value),
            price=price,
            size=quantity,
            side=side,
            bid=bid,
            ask=ask,
        )


class MinuteBarAccumulator:
    """Build one-minute OHLCV/CVD-ready bars from classified streaming timesales."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.upper()
        self._minute: datetime | None = None
        self._open: float | None = None
        self._high: float | None = None
        self._low: float | None = None
        self._close: float | None = None
        self._volume = 0.0
        self._buy = 0.0
        self._sell = 0.0

    @staticmethod
    def _floor_minute(ts: datetime) -> datetime:
        return ts.astimezone(UTC).replace(second=0, microsecond=0)

    def _emit(self) -> Bar | None:
        if self._minute is None or self._open is None or self._close is None:
            return None
        return Bar(
            ts=self._minute,
            open=self._open,
            high=float(self._high),
            low=float(self._low),
            close=self._close,
            volume=self._volume,
            aggressive_buy_volume=self._buy,
            aggressive_sell_volume=self._sell,
        )

    def push(self, trade: ClassifiedTrade) -> Bar | None:
        minute = self._floor_minute(trade.ts)
        completed = None
        if self._minute is not None and minute != self._minute:
            completed = self._emit()
            self._open = self._high = self._low = self._close = None
            self._volume = self._buy = self._sell = 0.0
        self._minute = minute
        if self._open is None:
            self._open = self._high = self._low = self._close = trade.price
        else:
            self._high = max(float(self._high), trade.price)
            self._low = min(float(self._low), trade.price)
            self._close = trade.price
        self._volume += trade.size
        if trade.side == "buy":
            self._buy += trade.size
        elif trade.side == "sell":
            self._sell += trade.size
        return completed

    def flush(self) -> Bar | None:
        return self._emit()
