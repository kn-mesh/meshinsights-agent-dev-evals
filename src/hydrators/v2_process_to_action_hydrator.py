"""Preserve the v2 case brief alongside the stable final decision."""

from __future__ import annotations

from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt

from src.objects.action_object import PulseFailureAnalysisActionObject
from src.objects.process_object import PulseFailureAnalysisProcessObject


class V2ProcessToActionHydrator(
    BaseHydrator[PulseFailureAnalysisProcessObject, PulseFailureAnalysisActionObject]
):
    """Add the inspectable first-pass brief to the v2 receipt payload."""

    def hydrate(
        self,
        source: PulseFailureAnalysisProcessObject,
        receipt: PipelineReceipt,
        *,
        metadata: Any = None,
    ) -> PulseFailureAnalysisActionObject:
        """Preserve the existing decision contract and append the case brief."""
        _ = receipt
        _ = metadata
        case_brief = source.get_investigation_case_brief()
        if case_brief is None:
            raise ValueError(
                "Process object is missing the investigation_case_brief artifact."
            )
        agent_result = source.get_ai_result()
        if agent_result is None:
            raise ValueError(
                "Process object is missing the ai_classification artifact."
            )
        context = source.get_alarm_context()
        investigation_evidence = source.get_investigation_evidence()
        if not investigation_evidence:
            raise ValueError("Process object is missing investigation evidence.")
        return PulseFailureAnalysisActionObject().set_pipeline_result(
            {
                "example_id": context["example_id"],
                "benchmark_key": context["benchmark_key"],
                "benchmark_version_id": context["benchmark_version_id"],
                "benchmark_version_number": context["benchmark_version_number"],
                "source_snapshot_id": context["source_snapshot_id"],
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
                "investigation_case_brief": case_brief,
                "investigation_evidence": investigation_evidence,
            }
        )
