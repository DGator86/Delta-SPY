from __future__ import annotations

from core.linear_bridge import LINEAR_PAIRS, linear_bridge
from core.timeframes import Timeframe

from .contracts import (
    AlphaLookbackRows,
    AlphaLookForwardRows,
    AlphaRows,
    LinearWalkForward1TState,
)


def build_linear_ab_1t(
    current: AlphaRows,
    lookback: AlphaLookbackRows,
) -> dict[Timeframe, LinearWalkForward1TState]:
    """Walk the observed prior->current SPY spot line forward exactly one native T."""

    output: dict[Timeframe, LinearWalkForward1TState] = {}
    for lookback_label, timeframe in LINEAR_PAIRS:
        point_a = lookback.spot[lookback_label]
        point_b = current.spot[timeframe]
        bridge = linear_bridge(lookback_label, point_a, point_b)
        output[timeframe] = LinearWalkForward1TState(
            lookback=lookback_label,
            timeframe=timeframe,
            point_a=point_a,
            point_b=point_b,
            observed_delta=point_b - point_a,
            slope_per_minute=bridge.slope_per_minute,
            projected_spot=bridge.forward_one_t_value,
        )
    return output


def build_look_forward_rows(
    current: AlphaRows,
    lookback: AlphaLookbackRows,
) -> AlphaLookForwardRows:
    """Build Alpha's look-forward processing matrix.

    The first processor row is the deliberately naive A->B one-T linear continuation.
    Additional forward processors can be added as independent rows later.
    """

    return AlphaLookForwardRows(linear_ab_1t=build_linear_ab_1t(current, lookback))
