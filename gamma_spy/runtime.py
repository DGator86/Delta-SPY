from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Iterable

from .capture import JsonlTapeWriter
from .contracts import (
    Bar,
    BehavioralState,
    CatalystObservation,
    MarketInternals,
    MarketSnapshot,
    OptionObservation,
    Positioning,
)
from .engine import GammaBehavioralEngine

UTC = timezone.utc


@dataclass
class SymbolRuntimeState:
    bars: deque[Bar]
    options: tuple[OptionObservation, ...] = ()
    internals: MarketInternals = field(default_factory=MarketInternals)
    positioning: Positioning = field(default_factory=Positioning)
    catalyst: CatalystObservation = field(default_factory=CatalystObservation)
    historical_iv: tuple[float, ...] = ()
    last_bar_at: datetime | None = None
    options_observed_at: datetime | None = None
    internals_observed_at: datetime | None = None
    positioning_observed_at: datetime | None = None
    catalyst_observed_at: datetime | None = None


class GammaRuntime:
    """Thread-safe rolling state used to freeze point-in-time Gamma snapshots.

    It is intentionally transport-agnostic: WebSocket collectors can push bars while separate
    refreshers supply options, internals, positioning and catalysts. Nothing inside this class trades.
    """

    def __init__(
        self,
        *,
        engine: GammaBehavioralEngine | None = None,
        max_bars: int = 780,
        tape: JsonlTapeWriter | None = None,
    ) -> None:
        if max_bars < 20:
            raise ValueError("max_bars must be >= 20")
        self.engine = engine or GammaBehavioralEngine()
        self.max_bars = max_bars
        self.tape = tape
        self._states: dict[str, SymbolRuntimeState] = {}
        self._lock = RLock()

    def _state(self, symbol: str) -> SymbolRuntimeState:
        symbol = symbol.upper()
        if symbol not in self._states:
            self._states[symbol] = SymbolRuntimeState(bars=deque(maxlen=self.max_bars))
        return self._states[symbol]

    def symbols(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._states))

    def push_bar(self, symbol: str, bar: Bar) -> None:
        with self._lock:
            state = self._state(symbol)
            if state.last_bar_at is not None and bar.ts < state.last_bar_at:
                raise ValueError(f"out-of-order bar for {symbol}: {bar.ts} < {state.last_bar_at}")
            if state.last_bar_at == bar.ts and state.bars:
                state.bars[-1] = bar
            else:
                state.bars.append(bar)
            state.last_bar_at = bar.ts

    def push_bars(self, symbol: str, bars: Iterable[Bar]) -> None:
        for bar in sorted(bars, key=lambda item: item.ts):
            self.push_bar(symbol, bar)

    def set_options(
        self,
        symbol: str,
        options: Iterable[OptionObservation],
        *,
        observed_at: datetime,
    ) -> None:
        with self._lock:
            state = self._state(symbol)
            state.options = tuple(options)
            state.options_observed_at = observed_at

    def set_internals(
        self,
        symbol: str,
        internals: MarketInternals,
        *,
        observed_at: datetime,
    ) -> None:
        with self._lock:
            state = self._state(symbol)
            state.internals = internals
            state.internals_observed_at = observed_at

    def set_positioning(
        self,
        symbol: str,
        positioning: Positioning,
        *,
        observed_at: datetime,
    ) -> None:
        with self._lock:
            state = self._state(symbol)
            state.positioning = positioning
            state.positioning_observed_at = observed_at

    def set_catalyst(
        self,
        symbol: str,
        catalyst: CatalystObservation,
        *,
        observed_at: datetime,
    ) -> None:
        with self._lock:
            state = self._state(symbol)
            state.catalyst = catalyst
            state.catalyst_observed_at = observed_at

    def set_historical_iv(self, symbol: str, values: Iterable[float]) -> None:
        with self._lock:
            self._state(symbol).historical_iv = tuple(float(value) for value in values)

    def input_ages_seconds(self, symbol: str, *, now: datetime | None = None) -> dict[str, float | None]:
        now = now or datetime.now(UTC)
        with self._lock:
            state = self._state(symbol)
            stamps = {
                "bars": state.last_bar_at,
                "options": state.options_observed_at,
                "internals": state.internals_observed_at,
                "positioning": state.positioning_observed_at,
                "catalyst": state.catalyst_observed_at,
            }
            return {
                key: max(0.0, (now - stamp).total_seconds()) if stamp is not None else None
                for key, stamp in stamps.items()
            }

    def freeze(self, symbol: str, *, observed_at: datetime | None = None) -> MarketSnapshot:
        symbol = symbol.upper()
        with self._lock:
            state = self._state(symbol)
            if len(state.bars) < 2:
                raise ValueError(f"not enough bars to freeze {symbol}")
            ts = observed_at or state.bars[-1].ts
            latency = max(0.0, (ts - state.bars[-1].ts).total_seconds() * 1000.0)
            return MarketSnapshot(
                symbol=symbol,
                ts=ts,
                bars=tuple(state.bars),
                bar_minutes=1,
                options=state.options,
                internals=state.internals,
                positioning=state.positioning,
                catalyst=state.catalyst,
                source="gamma_runtime_frozen",
                source_latency_ms=latency,
                historical_iv=state.historical_iv,
            )

    def evaluate(self, symbol: str, *, observed_at: datetime | None = None) -> BehavioralState:
        snapshot = self.freeze(symbol, observed_at=observed_at)
        if self.tape is not None:
            self.tape.append_snapshot(snapshot)
        state = self.engine.evaluate(snapshot)
        if self.tape is not None:
            self.tape.append_state(state)
        return state

    def evaluate_all(self, *, observed_at: datetime | None = None) -> list[BehavioralState]:
        results: list[BehavioralState] = []
        for symbol in self.symbols():
            try:
                results.append(self.evaluate(symbol, observed_at=observed_at))
            except ValueError:
                continue
        return results
