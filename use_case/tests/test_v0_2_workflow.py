"""Behavior tests for the alternate Pulse v0_2 workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mi.ai.backends.base import AIUsage, WorkflowRequest, WorkflowResult
from mi.ai.message import ImageContent, TextContent

from use_case.objects.process_object import PulseFailureAnalysisProcessObject
from use_case.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from use_case.processors.v0_2.v0_2_tabular_alarm_classification_ai_workflow_processor import (
    V0_2TabularAlarmClassificationAIWorkflowProcessor,
    V0_2TabularAlarmClassificationAIWorkflowProcessorConfig,
)


class CapturingBackend:
    """Capture the one-shot workflow request and return a fixed decision."""

    requests: list[WorkflowRequest[PulseFailureAnalysisResult]]

    def __init__(self) -> None:
        self.requests = []

    def run_workflow(
        self, request: WorkflowRequest[PulseFailureAnalysisResult]
    ) -> WorkflowResult[PulseFailureAnalysisResult]:
        self.requests.append(request)
        return WorkflowResult(
            output=PulseFailureAnalysisResult(
                classification=ClassificationResult(
                    value="Healthy",
                    confidence="High",
                    explanation="The recent positive delta remains stable.",
                ),
                root_cause=RootCauseResult(
                    value="N/A",
                    confidence="High",
                    explanation="N/A",
                ),
            ),
            usage=AIUsage(requests=1, input_tokens=800, output_tokens=80),
        )


def _build_process_object() -> PulseFailureAnalysisProcessObject:
    alarm_at = datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)
    history = [
        {
            "timestamp": alarm_at - timedelta(hours=hour),
            "steam_temperature": 130.0 - min(hour, 96) * 0.01,
            "condensate_temperature": 105.0,
        }
        for hour in range(24 * 365, -3, -1)
    ]
    return (
        PulseFailureAnalysisProcessObject()
        .set_alarm_context(
            {
                "unit": "trap-250003575",
                "sensor_id": 250003575,
                "decision_timestamp": alarm_at,
                "selected_alarm": {"detected_at": alarm_at},
            }
        )
        .set_steam_trap_type("Float")
        .set_temperature_history(history)
    )


def test_v0_2_executes_one_text_only_structured_workflow_request() -> None:
    backend = CapturingBackend()
    workflow = V0_2TabularAlarmClassificationAIWorkflowProcessor(
        V0_2TabularAlarmClassificationAIWorkflowProcessorConfig(
            model="azure:gpt-5.6-luna"
        )
    )
    workflow._backend_cache = backend
    process_object = _build_process_object()

    workflow.process(process_object)

    assert len(backend.requests) == 1
    request = backend.requests[0]
    assert request.output_schema is PulseFailureAnalysisResult
    assert request.timeout == 120
    assert request.transport_retries == 3
    assert request.output_retries == 0
    assert "numeric telemetry" in request.system_prompt
    normalized_prompt = " ".join(request.system_prompt.split())
    assert "A positive remaining delta alone is not evidence of health" in (
        normalized_prompt
    )
    assert "Analyze the onset before the endpoint" in normalized_prompt
    assert "Apply an unfinished-restart exception only when all three" in (
        normalized_prompt
    )
    assert "Never apply this exception during uninterrupted elevated operation" in (
        normalized_prompt
    )
    assert all(isinstance(block, TextContent) for block in request.user_message.content)
    assert not any(
        isinstance(block, ImageContent) for block in request.user_message.content
    )
    rendered = "\n".join(
        block.text
        for block in request.user_message.content
        if isinstance(block, TextContent)
    )
    assert "historical" in rendered
    assert "recent_baseline" in rendered
    assert "steam_slope_c_per_day" in rendered
    assert "2026-03-17T14:00:00+00:00" not in rendered
    assert process_object.get_ai_result() == {
        "classification": {
            "value": "Healthy",
            "confidence": "High",
            "explanation": "The recent positive delta remains stable.",
        },
        "root_cause": {
            "value": "N/A",
            "confidence": "High",
            "explanation": "N/A",
        },
    }


def test_v0_2_periods_are_non_overlapping_and_cut_off_at_alarm() -> None:
    workflow = V0_2TabularAlarmClassificationAIWorkflowProcessor(
        V0_2TabularAlarmClassificationAIWorkflowProcessorConfig(
            model="azure:gpt-5.6-luna"
        )
    )
    process_object = _build_process_object()
    alarm_at = workflow._as_utc_timestamp(
        process_object.get_alarm_context()["selected_alarm"]["detected_at"]
    )

    frame = workflow._build_temperature_frame(
        process_object.get_temperature_history(),
        alarm_at=alarm_at,
    )
    summary = workflow._build_period_summary(frame, alarm_at=alarm_at)

    assert list(summary["period"]) == [
        "historical",
        "recent_baseline",
        "lead_up",
        "alarm_adjacent",
    ]
    assert int(summary["paired_points"].sum()) == len(frame)
    assert frame["timestamp"].max() == alarm_at
