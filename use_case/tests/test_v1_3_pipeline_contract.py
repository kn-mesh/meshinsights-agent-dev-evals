"""Reference-use-case contract tests for the Pulse v1_3 evidence handoff."""

from __future__ import annotations

from datetime import datetime, timedelta

from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt

from use_case.hydrators.finalize_action_hydrator import V1_3FinalizeActionHydrator
from use_case.hydrators.process_to_action_hydrator import V1_3ProcessToActionHydrator
from use_case.hydrators.retrieve_to_process_hydrator import V1_3RetrieveToProcessHydrator
from use_case.processors.common.structured_outputs import PulseFailureAnalysisResult
from use_case.processors.v1_3.v1_3_temperature_graphs_processor import (
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
    assert receipt.act_receipt.metadata["agent_context"]["unit"] == "trap-1"
    assert receipt.act_receipt.metadata["agent_context"]["decision_timestamp"] == (
        "2026-03-17T12:00:00"
    )
    assert receipt.act_receipt.metadata["agent_output"]["classification"]["value"] == (
        "Failure"
    )
    assert receipt.act_receipt.metadata["agent_output"]["root_cause"]["value"] == (
        "Closed Failure"
    )


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


def test_output_schema_rejects_inconsistent_root_cause() -> None:
    invalid_pairs = (("Healthy", "Open Failure"), ("Failure", "N/A"))

    for classification, root_cause in invalid_pairs:
        try:
            PulseFailureAnalysisResult.model_validate(
                {
                    "classification": {
                        "value": classification,
                        "confidence": "High",
                        "explanation": "Evidence explanation.",
                    },
                    "root_cause": {
                        "value": root_cause,
                        "confidence": "High",
                        "explanation": "Root-cause explanation.",
                    },
                }
            )
        except ValueError as error:
            assert "require" in str(error)
        else:
            raise AssertionError(
                f"Expected {classification}/{root_cause} to fail validation."
            )
