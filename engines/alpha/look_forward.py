from __future__ import annotations

from dataclasses import fields, is_dataclass

from core.linear_bridge import LINEAR_PAIRS, linear_bridge
from core.timeframes import Timeframe

from .contracts import (
    AlphaLookbackRows,
    AlphaLookForwardRows,
    AlphaRows,
    LinearProjectionComponent,
    LinearWalkForward1TState,
)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _flatten_pair(
    point_a: object,
    point_b: object,
    *,
    prefix: str,
) -> tuple[dict[str, tuple[float | None, float | None]], list[str]]:
    numeric: dict[str, tuple[float | None, float | None]] = {}
    non_projectable: list[str] = []

    if is_dataclass(point_a) and is_dataclass(point_b):
        for field_info in fields(point_b):
            name = field_info.name
            child_prefix = f"{prefix}.{name}" if prefix else name
            child_a = getattr(point_a, name, None)
            child_b = getattr(point_b, name, None)
            child_numeric, child_non_projectable = _flatten_pair(
                child_a,
                child_b,
                prefix=child_prefix,
            )
            numeric.update(child_numeric)
            non_projectable.extend(child_non_projectable)
        return numeric, non_projectable

    if _is_number(point_a) or _is_number(point_b):
        numeric[prefix] = (
            float(point_a) if _is_number(point_a) else None,
            float(point_b) if _is_number(point_b) else None,
        )
        return numeric, non_projectable

    if point_a is None and point_b is None:
        return numeric, non_projectable

    non_projectable.append(prefix)
    return numeric, non_projectable


def _temporal_components(
    current: AlphaRows,
    lookback: AlphaLookbackRows,
    *,
    timeframe: Timeframe,
    lookback_label: str,
) -> tuple[dict[str, tuple[float | None, float | None]], tuple[str, ...]]:
    numeric: dict[str, tuple[float | None, float | None]] = {}
    non_projectable: list[str] = []

    for row_field in fields(current):
        row_name = row_field.name
        current_mapping = getattr(current, row_name)
        lookback_mapping = getattr(lookback, row_name)
        point_b = current_mapping[timeframe]
        point_a = lookback_mapping[lookback_label]
        row_numeric, row_non_projectable = _flatten_pair(
            point_a,
            point_b,
            prefix=row_name,
        )
        numeric.update(row_numeric)
        non_projectable.extend(row_non_projectable)

    return numeric, tuple(sorted(set(non_projectable)))


def build_linear_ab_1t(
    current: AlphaRows,
    lookback: AlphaLookbackRows,
) -> dict[Timeframe, LinearWalkForward1TState]:
    """Walk every numeric Alpha temporal component forward exactly one native T."""

    output: dict[Timeframe, LinearWalkForward1TState] = {}
    for lookback_label, timeframe in LINEAR_PAIRS:
        paired_values, non_projectable = _temporal_components(
            current,
            lookback,
            timeframe=timeframe,
            lookback_label=lookback_label,
        )
        components: dict[str, LinearProjectionComponent] = {}
        for path, (point_a, point_b) in paired_values.items():
            if point_a is None or point_b is None:
                components[path] = LinearProjectionComponent(
                    path=path,
                    point_a=point_a,
                    point_b=point_b,
                    observed_delta=None,
                    slope_per_minute=None,
                    projected_value=None,
                )
                continue

            bridge = linear_bridge(lookback_label, point_a, point_b)
            components[path] = LinearProjectionComponent(
                path=path,
                point_a=point_a,
                point_b=point_b,
                observed_delta=point_b - point_a,
                slope_per_minute=bridge.slope_per_minute,
                projected_value=bridge.forward_one_t_value,
            )

        output[timeframe] = LinearWalkForward1TState(
            lookback=lookback_label,
            timeframe=timeframe,
            components=components,
            non_projectable_paths=non_projectable,
        )
    return output


def build_look_forward_rows(
    current: AlphaRows,
    lookback: AlphaLookbackRows,
) -> AlphaLookForwardRows:
    """Build Alpha's look-forward processing matrix."""

    return AlphaLookForwardRows(linear_ab_1t=build_linear_ab_1t(current, lookback))
