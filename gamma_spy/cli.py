from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import GammaBehavioralEngine
from .io import snapshot_from_dict


def _read_json(path: str | None) -> dict:
    if path:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return json.load(sys.stdin)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gamma-SPY behavioral state estimator")
    parser.add_argument("--input", help="JSON snapshot path; stdin when omitted")
    parser.add_argument("--output", help="Write result JSON to path; stdout when omitted")
    parser.add_argument("--risk-free-rate", type=float, default=0.04)
    args = parser.parse_args()

    payload = _read_json(args.input)
    snapshot = snapshot_from_dict(payload)
    engine = GammaBehavioralEngine(risk_free_rate=args.risk_free_rate, remember_state=False)
    state = engine.evaluate(snapshot)
    encoded = json.dumps(state.to_dict(), indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
