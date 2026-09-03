from __future__ import annotations

from dataclasses import replace

from core.timeframes import (
    require_lookback_columns,
    require_timeframe_columns,
)

from .contracts import AlphaInput, AlphaState
from .dynamics import build_current_dynamics, build_lookback_dynamics
from .engine import AlphaEngine as AlphaEngineV03

ENGINE_VERSION = "alpha-0.4.0"


class AlphaEngine(AlphaEngineV03):
    """Alpha v0.4: statistical state plus causal temporal dynamics rows."""

    version = ENGINE_VERSION

    def process(self, input_state: AlphaInput) -> AlphaState:
        base = super().process(input_state)

        (
            current_velocity,
            current_acceleration,
            current_persistence,
            current_transition,
            current_forecast_drift,
            current_confidence_change,
        ) = build_current_dynamics(input_state)
        (
            lookback_velocity,
            lookback_acceleration,
            lookback_persistence,
            lookback_transition,
            lookback_forecast_drift,
            lookback_confidence_change,
        ) = build_lookback_dynamics(input_state)

        for label, mapping in (
            ("AlphaState.current.state_velocity", current_velocity),
            ("AlphaState.current.state_acceleration", current_acceleration),
            ("AlphaState.current.persistence", current_persistence),
            ("AlphaState.current.regime_transition", current_transition),
            ("AlphaState.current.forecast_drift", current_forecast_drift),
            ("AlphaState.current.confidence_change", current_confidence_change),
        ):
            require_timeframe_columns(mapping, label=label)

        for label, mapping in (
            ("AlphaState.lookback.state_velocity", lookback_velocity),
            ("AlphaState.lookback.state_acceleration", lookback_acceleration),
            ("AlphaState.lookback.persistence", lookback_persistence),
            ("AlphaState.lookback.regime_transition", lookback_transition),
            ("AlphaState.lookback.forecast_drift", lookback_forecast_drift),
            ("AlphaState.lookback.confidence_change", lookback_confidence_change),
        ):
            require_lookback_columns(mapping, label=label)

        current = replace(
            base.current,
            state_velocity=current_velocity,
            state_acceleration=current_acceleration,
            persistence=current_persistence,
            regime_transition=current_transition,
            forecast_drift=current_forecast_drift,
            confidence_change=current_confidence_change,
        )
        lookback = replace(
            base.lookback,
            state_velocity=lookback_velocity,
            state_acceleration=lookback_acceleration,
            persistence=lookback_persistence,
            regime_transition=lookback_transition,
            forecast_drift=lookback_forecast_drift,
            confidence_change=lookback_confidence_change,
        )
        metadata = dict(base.metadata)
        metadata.update(
            {
                "temporal_dynamics": (
                    "state_velocity|state_acceleration|persistence|regime_transition|"
                    "forecast_drift|confidence_change"
                ),
                "dynamics_semantics": "causal_native_bar_first_and_second_differences",
            }
        )
        return AlphaState(
            engine=base.engine,
            engine_version=self.version,
            as_of=base.as_of,
            current=current,
            lookback=lookback,
            current_columns=base.current_columns,
            lookback_columns=base.lookback_columns,
            metadata=metadata,
        )
