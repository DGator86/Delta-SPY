from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

from core.timeframes import LOOKBACKS, TIMEFRAMES
from engines.alpha.contracts import (
    AlphaInput,
    AlphaLookbackRows,
    AlphaLookForwardRows,
    AlphaRows,
    AlphaState,
    ConfidenceChangeState,
    CrossSectionState,
    DataQuality,
    ForecastDistribution,
    ForecastDriftState,
    LinearProjectionComponent,
    LinearWalkForward1TState,
    PersistenceState,
    PriceBar,
    RegimeState,
    RegimeTransitionState,
    StateAccelerationState,
    StateVelocityState,
)

ALPHA_ROOT = Path(__file__).parents[2] / "engines" / "alpha"
FORBIDDEN_FIELD_TOKENS = {
    "action",
    "trade",
    "strategy",
    "position",
    "order",
    "broker",
    "quantity",
    "size",
    "entry",
    "exit",
    "strike",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "engines.beta",
    "engines.gamma",
    "delta",
    "broker",
    "execution",
    "strategy",
)
PUBLIC_CONTRACTS = (
    PriceBar,
    AlphaInput,
    ForecastDistribution,
    RegimeState,
    CrossSectionState,
    DataQuality,
    StateVelocityState,
    StateAccelerationState,
    PersistenceState,
    RegimeTransitionState,
    ForecastDriftState,
    ConfidenceChangeState,
    LinearProjectionComponent,
    LinearWalkForward1TState,
    AlphaRows,
    AlphaLookbackRows,
    AlphaLookForwardRows,
    AlphaState,
)


def _field_names(dataclass_type) -> set[str]:
    return {field.name.lower() for field in fields(dataclass_type)}


def test_canonical_current_lookback_and_forward_columns_are_fixed() -> None:
    assert TIMEFRAMES == (
        "1m",
        "5m",
        "15m",
        "30m",
        "1h",
        "4h",
        "1d",
        "3d",
        "5d",
    )
    assert LOOKBACKS == (
        "-1m",
        "-5m",
        "-15m",
        "-30m",
        "-1h",
        "-4h",
        "-1d",
        "-3d",
        "-5d",
    )


def test_alpha_public_contract_has_no_decision_or_execution_fields() -> None:
    names: set[str] = set()
    for contract in PUBLIC_CONTRACTS:
        names |= _field_names(contract)
    violations = sorted(
        name for name in names if any(token in name for token in FORBIDDEN_FIELD_TOKENS)
    )
    assert not violations, f"Alpha public contract contains decision/execution fields: {violations}"


def test_alpha_does_not_import_other_engines_or_trading_layers() -> None:
    violations: list[str] = []
    for path in ALPHA_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text())
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        forbidden = sorted(
            module
            for module in imports
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES)
        )
        if forbidden:
            violations.append(f"{path.name}: {', '.join(forbidden)}")
    assert not violations, "Alpha dependency boundary violated: " + "; ".join(violations)


def test_only_alpha_engine_exists_at_this_stage() -> None:
    engines_root = ALPHA_ROOT.parent
    implemented = sorted(
        path.name
        for path in engines_root.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    )
    assert implemented == ["alpha"]
