from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .contracts import BehavioralState, MarketSnapshot

TAPE_SCHEMA_VERSION = "gamma-tape-v1"


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return _encode(asdict(value))
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_encode(item) for item in value]
    return value


def canonical_json(payload: Any) -> str:
    return json.dumps(_encode(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class JsonlTapeWriter:
    """Append-only local tape for point-in-time Gamma inputs and outputs.

    Each record stores a SHA-256 of the canonical payload. The writer fsyncs after every append by
    default so a process crash is less likely to leave apparently-valid uncaptured model history.
    """

    def __init__(self, path: str | Path, *, fsync: bool = True) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fsync = fsync

    def append(
        self,
        record_type: str,
        payload: Any,
        *,
        observed_at: datetime,
        source: str,
    ) -> str:
        encoded = _encode(payload)
        digest = fingerprint(encoded)
        envelope = {
            "schema_version": TAPE_SCHEMA_VERSION,
            "record_type": record_type,
            "observed_at": observed_at.isoformat(),
            "source": source,
            "payload_sha256": digest,
            "payload": encoded,
        }
        line = canonical_json(envelope) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            if self.fsync:
                os.fsync(handle.fileno())
        return digest

    def append_snapshot(self, snapshot: MarketSnapshot) -> str:
        return self.append(
            "market_snapshot",
            snapshot,
            observed_at=snapshot.ts,
            source=snapshot.source,
        )

    def append_state(self, state: BehavioralState) -> str:
        return self.append(
            "behavioral_state",
            state.to_dict(),
            observed_at=state.ts,
            source=state.engine_version,
        )


def read_tape(path: str | Path, *, verify: bool = True) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            record = json.loads(text)
            if not isinstance(record, dict):
                raise ValueError(f"invalid tape record on line {line_number}")
            if verify:
                expected = record.get("payload_sha256")
                actual = fingerprint(record.get("payload"))
                if expected != actual:
                    raise ValueError(
                        f"tape payload hash mismatch on line {line_number}: {expected} != {actual}"
                    )
            records.append(record)
    return records


def iter_tape(
    path: str | Path,
    *,
    record_type: str | None = None,
    verify: bool = True,
) -> Iterable[dict[str, Any]]:
    for record in read_tape(path, verify=verify):
        if record_type is None or record.get("record_type") == record_type:
            yield record
