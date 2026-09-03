from __future__ import annotations

from core.timeframes import require_timeframe_columns

from .contracts import AlphaInput, AlphaState
from .engine_v04 import AlphaEngine as AlphaEngineV04
from .look_forward import build_look_forward_rows

ENGINE_VERSION = "alpha-0.5.0"


class AlphaEngine(AlphaEngineV04):
    """Alpha v0.5: current, lookback, and forward-processing matrices."""

    version = ENGINE_VERSION

    def process(self, input_state: AlphaInput) -> AlphaState:
        base = super().process(input_state)
        look_forward = build_look_forward_rows(base.current, base.lookback)
        require_timeframe_columns(
            look_forward.linear_ab_1t,
            label="AlphaState.look_forward.linear_ab_1t",
        )

        metadata = dict(base.metadata)
        metadata.update(
            {
                "look_forward_processors": "linear_ab_1t",
                "linear_ab_1t_semantics": (
                    "A=prior_native_spot_at_t_minus_T;B=current_native_spot_at_t;"
                    "projection_at_t_plus_T=2B-A"
                ),
            }
        )
        return AlphaState(
            engine=base.engine,
            engine_version=self.version,
            as_of=base.as_of,
            current=base.current,
            lookback=base.lookback,
            look_forward=look_forward,
            current_columns=base.current_columns,
            lookback_columns=base.lookback_columns,
            look_forward_columns=base.current_columns,
            metadata=metadata,
        )
