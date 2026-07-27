"""Hydrate the agent decision into the action-stage object."""

from __future__ import annotations

from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt

from use_case.objects.action_object import PulseFailureAnalysisActionObject
from use_case.objects.process_object import PulseFailureAnalysisProcessObject


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
                "identity": {
                    "example_id": context["example_id"],
                    "benchmark_key": context["benchmark_key"],
                    "benchmark_version_id": context["benchmark_version_id"],
                    "benchmark_version_number": context["benchmark_version_number"],
                    "source_snapshot_id": context["source_snapshot_id"],
                },
                "agent_context": {
                    "unit": context["unit"],
                    "sensor_id": context["sensor_id"],
                    "decision_timestamp": context["decision_timestamp"].isoformat(),
                    "selected_alarm_detected_at": context["selected_alarm"][
                        "detected_at"
                    ].isoformat(),
                    "steam_trap_type": source.get_steam_trap_type(),
                    "temperature_point_count": len(source.get_temperature_history()),
                },
                "agent_output": agent_result,
                "execution_telemetry": {
                    "usage": source.get_ai_usage(),
                    "retry_telemetry": source.get_ai_retry_telemetry(),
                },
            }
        )
