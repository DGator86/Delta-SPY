from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .contracts import CatalystObservation, MarketInternals, MarketSnapshot, Positioning
from .tradier import TradierMarketDataClient, normalize_option_chain, normalize_time_sales_bars


@dataclass(frozen=True)
class CoveragePolicy:
    """Control expensive/deep inputs without changing Gamma semantics.

    Whole-universe bars can be collected broadly while deep options-chain analysis is restricted to
    symbols selected upstream (for example SPY plus the highest-weight or highest-activity names).
    """

    options_symbols: frozenset[str] = frozenset({"SPY"})
    bar_interval: str = "1min"
    session_filter: str = "open"

    def wants_options(self, symbol: str) -> bool:
        return symbol.upper() in self.options_symbols


class TradierSnapshotBuilder:
    """Build frozen Gamma MarketSnapshot objects from read-only Tradier market data.

    Market internals, positioning, catalysts and historical-IV context remain explicit caller inputs
    because they may come from other point-in-time providers. Missing data stays missing rather than
    being fabricated or silently forward-filled.
    """

    def __init__(
        self,
        client: TradierMarketDataClient,
        *,
        coverage: CoveragePolicy | None = None,
    ) -> None:
        self.client = client
        self.coverage = coverage or CoveragePolicy()

    def build(
        self,
        symbol: str,
        *,
        start: str | None = None,
        end: str | None = None,
        expiration: str | None = None,
        internals: MarketInternals | None = None,
        positioning: Positioning | None = None,
        catalyst: CatalystObservation | None = None,
        historical_iv: Iterable[float] = (),
        source_latency_ms: float | None = None,
    ) -> MarketSnapshot:
        symbol = symbol.upper()
        time_sales = self.client.time_sales(
            symbol,
            interval=self.coverage.bar_interval,
            start=start,
            end=end,
            session_filter=self.coverage.session_filter,
        )
        bars = normalize_time_sales_bars(time_sales)
        if len(bars) < 2:
            raise ValueError(f"Tradier returned insufficient bar history for {symbol}")

        options = ()
        if self.coverage.wants_options(symbol):
            chosen = expiration
            if chosen is None:
                expirations = self.client.option_expirations(symbol)
                if expirations:
                    chosen = expirations[0]
            if chosen is not None:
                options = normalize_option_chain(self.client.option_chain(symbol, chosen, greeks=True))

        return MarketSnapshot(
            symbol=symbol,
            ts=bars[-1].ts,
            bars=bars,
            bar_minutes={"1min": 1, "5min": 5, "15min": 15}.get(self.coverage.bar_interval, 1),
            options=options,
            internals=internals or MarketInternals(),
            positioning=positioning or Positioning(),
            catalyst=catalyst or CatalystObservation(),
            source="tradier_market_data",
            source_latency_ms=source_latency_ms,
            historical_iv=tuple(float(value) for value in historical_iv),
        )

    def build_many(
        self,
        symbols: Iterable[str],
        **shared_kwargs,
    ) -> list[MarketSnapshot]:
        """Build several snapshots sequentially.

        This is intentionally deterministic and simple. Production orchestration may parallelize
        requests subject to provider limits, but that concurrency belongs outside the model layer.
        """
        return [self.build(symbol, **shared_kwargs) for symbol in symbols]
