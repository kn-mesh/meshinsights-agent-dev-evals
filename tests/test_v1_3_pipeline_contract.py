"""Contract tests for the Pulse v1_3 evidence and receipt handoff."""

from __future__ import annotations

from datetime import datetime, timedelta

from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt

from src.hydrators.finalize_action_hydrator import V1_3FinalizeActionHydrator
from src.hydrators.process_to_action_hydrator import V1_3ProcessToActionHydrator
from src.hydrators.retrieve_to_process_hydrator import V1_3RetrieveToProcessHydrator
from src.processors.common.structured_outputs import PulseFailureAnalysisResult
from src.processors.v1_3.v1_3_temperature_graphs_processor import (
    V1_3TemperatureGraphsProcessor,
    V1_3TemperatureGraphsProcessorConfig,
)


def _retrieval_payload() -> dict[str, object]:
    """Build one portable example at a fixed decision timestamp."""
    alarm_at = datetime(2026, 3, 17, 12, 0)
    history = [
        {
            "timestamp": alarm_at - timedelta(hours=6 - index),
            "steam_temperature": 130.0,
            "condensate_temperature": 105.0,
        }
        for index in range(7)
    ]
    return {
        "example_id": "trap-1|2026-03-17T12:00:00",
        "benchmark_key": "steam-trap-regression",
        "benchmark_version_id": "version-id",
        "benchmark_version_number": 3,
        "source_snapshot_id": "snapshot-id",
        "source_snapshot_content_sha256": "a" * 64,
        "unit": "trap-1",
        "sensor_id": 1,
        "decision_timestamp": alarm_at,
        "steam_trap_type": "Float",
        "selected_alarm": {"detected_at": alarm_at},
        "window_start": alarm_at - timedelta(days=365),
        "window_end": alarm_at + timedelta(hours=2),
        "lookback_days": 365,
        "post_alarm_hours": 2,
        "temperature_history": history,
    }


def test_workflow_decision_flows_to_durable_act_receipt_metadata() -> None:
    """Preserve the stable artifact-to-action-to-receipt contract."""
    retriever_object = RetrieverDataObject()
    retriever_object.azure_blob["pulse_alarm_temperature_history"] = (
        _retrieval_payload()
    )
    receipt = PipelineReceipt(
        pipeline_id="test",
        retrieve_receipt=StageReceipt("retrieve", True, 0.0),
        act_receipt=StageReceipt("act", True, 0.0),
    )
    process_object = V1_3RetrieveToProcessHydrator().hydrate(retriever_object, receipt)
    process_object.set_ai_result(
        {
            "classification": {
                "value": "Failure",
                "confidence": "High",
                "explanation": "The inlet temperature degraded first.",
            },
            "root_cause": {
                "value": "Closed Failure",
                "confidence": "High",
                "explanation": "The delta collapsed as inlet temperature fell.",
            },
        }
    )

    action_object = V1_3ProcessToActionHydrator().hydrate(process_object, receipt)
    V1_3FinalizeActionHydrator().hydrate(action_object, receipt)

    assert receipt.act_receipt is not None
    assert receipt.act_receipt.metadata["example_id"] == "trap-1|2026-03-17T12:00:00"
    assert receipt.act_receipt.metadata["source_snapshot_id"] == "snapshot-id"
    assert receipt.act_receipt.metadata["unit"] == "trap-1"
    assert receipt.act_receipt.metadata["decision_timestamp"] == ("2026-03-17T12:00:00")
    assert receipt.act_receipt.metadata["classification"]["value"] == "Failure"
    assert receipt.act_receipt.metadata["root_cause"]["value"] == "Closed Failure"


def test_temperature_processor_renders_png_evidence() -> None:
    """Render deterministic chart evidence from normalized telemetry."""
    retriever_object = RetrieverDataObject()
    retriever_object.azure_blob["pulse_alarm_temperature_history"] = (
        _retrieval_payload()
    )
    receipt = PipelineReceipt(
        pipeline_id="test", retrieve_receipt=StageReceipt("retrieve", True, 0.0)
    )
    process_object = V1_3RetrieveToProcessHydrator().hydrate(retriever_object, receipt)
    processor = V1_3TemperatureGraphsProcessor(
        V1_3TemperatureGraphsProcessorConfig(window_days_list=[7], dpi=40)
    )

    processor.process(process_object)

    chart = process_object.get_temperature_chart(7)
    assert chart is not None
    assert chart.startswith("iVBOR")


def test_output_schema_matches_the_prototype_contract() -> None:
    result = PulseFailureAnalysisResult.model_validate(
        {
            "classification": {
                "value": "Healthy",
                "confidence": "High",
                "explanation": "Stable delta.",
            },
            "root_cause": {
                "value": "N/A",
                "confidence": "High",
                "explanation": "N/A",
            },
        }
    )

    assert set(result.model_dump()) == {"classification", "root_cause"}
