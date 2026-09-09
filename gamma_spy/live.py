from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from .contracts import Bar
from .tradier import MinuteBarAccumulator, TimesaleAggressorClassifier, TradierMarketDataClient

BarHandler = Callable[[str, Bar], Awaitable[None] | None]
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class TradierLiveCollector:
    """Single-session, market-data-only Tradier WebSocket collector.

    Tradier permits one market-data streaming session at a time. This object therefore owns one
    shared connection and supports dynamically replacing its symbol subscription. It never opens
    account streams and has no broker/order functionality.
    """

    def __init__(
        self,
        client: TradierMarketDataClient,
        symbols: Iterable[str],
        *,
        websocket_url: str = "wss://ws.tradier.com/v1/markets/events",
        on_bar: BarHandler | None = None,
        on_event: EventHandler | None = None,
        reconnect_delay_seconds: float = 1.5,
    ) -> None:
        self.client = client
        self.websocket_url = websocket_url
        self.on_bar = on_bar
        self.on_event = on_event
        self.reconnect_delay_seconds = max(0.25, reconnect_delay_seconds)
        self._symbols = sorted({symbol.upper() for symbol in symbols if symbol})
        self._classifier = TimesaleAggressorClassifier()
        self._accumulators: dict[str, MinuteBarAccumulator] = {
            symbol: MinuteBarAccumulator(symbol) for symbol in self._symbols
        }
        self._ws: Any = None
        self._stop = asyncio.Event()
        self._subscription_lock = asyncio.Lock()

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._symbols)

    def stop(self) -> None:
        self._stop.set()

    async def _call(self, handler: Callable[..., Awaitable[None] | None] | None, *args: Any) -> None:
        if handler is None:
            return
        result = handler(*args)
        if asyncio.iscoroutine(result):
            await result

    def _subscription_payload(self, sessionid: str) -> str:
        return json.dumps(
            {
                "symbols": self._symbols,
                "filter": ["timesale"],
                "sessionid": sessionid,
                "linebreak": True,
                "validOnly": True,
                "advancedDetails": True,
            }
        )

    async def replace_symbols(self, symbols: Iterable[str]) -> None:
        """Replace the active symbol set without intentionally opening a second stream."""
        new_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
        async with self._subscription_lock:
            self._symbols = new_symbols
            for symbol in new_symbols:
                self._accumulators.setdefault(symbol, MinuteBarAccumulator(symbol))
            if self._ws is not None:
                # Existing WebSocket sessions accept updated subscription payloads with the same
                # session id, but the id is connection-scoped. We cache it on connect.
                sessionid = getattr(self, "_sessionid", None)
                if sessionid:
                    await self._ws.send(self._subscription_payload(sessionid))

    async def _consume_payload(self, payload: dict[str, Any]) -> None:
        await self._call(self.on_event, payload)
        if str(payload.get("type", "")).lower() != "timesale":
            return
        symbol = str(payload.get("symbol") or "").upper()
        if not symbol:
            return
        trade = self._classifier.classify(symbol, payload)
        if trade is None:
            return
        accumulator = self._accumulators.setdefault(symbol, MinuteBarAccumulator(symbol))
        completed = accumulator.push(trade)
        if completed is not None:
            await self._call(self.on_bar, symbol, completed)

    async def _connect_once(self) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Live WebSocket collection requires the optional 'live' dependency: "
                "pip install -e '.[live]'"
            ) from exc

        sessionid = await asyncio.to_thread(self.client.create_stream_session)
        self._sessionid = sessionid
        async with websockets.connect(
            self.websocket_url,
            ssl=True,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_queue=20_000,
        ) as websocket:
            self._ws = websocket
            await websocket.send(self._subscription_payload(sessionid))
            async for message in websocket:
                if self._stop.is_set():
                    break
                text = message.decode("utf-8") if isinstance(message, bytes) else str(message)
                for line in text.splitlines() or [text]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict):
                        await self._consume_payload(payload)
        self._ws = None

    async def run(self) -> None:
        """Run until `stop()` is called, reconnecting market-data sessions after disconnects."""
        self._stop.clear()
        while not self._stop.is_set():
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._stop.is_set():
                    break
                await asyncio.sleep(self.reconnect_delay_seconds)

    async def flush(self) -> None:
        for symbol, accumulator in self._accumulators.items():
            bar = accumulator.flush()
            if bar is not None:
                await self._call(self.on_bar, symbol, bar)
