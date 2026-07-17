"""Hydrate the agent decision into the action-stage object."""

from __future__ import annotations

from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt

from src.objects.action_object import PulseFailureAnalysisActionObject
from src.objects.process_object import PulseFailureAnalysisProcessObject


class V1_3ProcessToActionHydrator(
    BaseHydrator[PulseFailureAnalysisProcessObject, PulseFailureAnalysisActionObject]
):
    """Create a compact, portable action decision from process artifacts."""

    def hydrate(
        self,
        source: PulseFailureAnalysisProcessObject,
        receipt: PipelineReceipt,
        *,
        metadata: Any = None,
    ) -> PulseFailureAnalysisActionObject:
        """Move the stable agent artifact into the action contract."""
        _ = receipt
        _ = metadata
        agent_result = source.get_ai_result()
        if agent_result is None:
            raise ValueError(
                "Process object is missing the ai_classification artifact."
            )
        context = source.get_alarm_context()
        return PulseFailureAnalysisActionObject().set_pipeline_result(
            {
                "unit": context["unit"],
                "sensor_id": context["sensor_id"],
                "decision_timestamp": context["decision_timestamp"].isoformat(),
                "selected_alarm_detected_at": context["selected_alarm"][
                    "detected_at"
                ].isoformat(),
                "steam_trap_type": source.get_steam_trap_type(),
                "temperature_point_count": len(source.get_temperature_history()),
                "classification": agent_result["classification"],
                "root_cause": agent_result["root_cause"],
            }
        )
