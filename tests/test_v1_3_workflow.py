"""Behavior tests for the prototype-equivalent Pulse v1_3 workflow."""

from __future__ import annotations

from datetime import datetime, timedelta

from mi.ai.backends.base import AIUsage, WorkflowRequest, WorkflowResult
from mi.ai.message import ImageContent, TextContent

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from src.processors.v1_3.v1_3_alarm_classification_ai_workflow_processor import (
    V1_3AlarmClassificationAIWorkflowProcessor,
    V1_3AlarmClassificationAIWorkflowProcessorConfig,
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
                    explanation="The positive delta remains stable through the alarm.",
                ),
                root_cause=RootCauseResult(
                    value="N/A",
                    confidence="High",
                    explanation="N/A",
                ),
            ),
            usage=AIUsage(requests=1, input_tokens=1200, output_tokens=90),
        )


def _build_process_object() -> PulseFailureAnalysisProcessObject:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    history = [
        {
            "timestamp": alarm_at - timedelta(days=day),
            "steam_temperature": 130.0 - day * 0.01,
            "condensate_temperature": 105.0 - day * 0.01,
        }
        for day in range(365, -1, -1)
    ]
    process_object = (
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
    for window_days in (7, 30, 365):
        process_object.set_temperature_chart(window_days, "aW1hZ2U=")
    return process_object


def test_v1_3_executes_one_structured_multimodal_workflow_request() -> None:
    backend = CapturingBackend()
    workflow = V1_3AlarmClassificationAIWorkflowProcessor(
        V1_3AlarmClassificationAIWorkflowProcessorConfig(model="azure:gpt-5-mini")
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
    assert "<decision_framework>" in request.system_prompt
    assert "<critical_rules>" in request.system_prompt
    assert isinstance(request.user_message.content[0], TextContent)
    assert [
        block.media_type
        for block in request.user_message.content
        if isinstance(block, ImageContent)
    ] == ["image/png", "image/png", "image/png"]
    assert process_object.get_ai_result() == {
        "classification": {
            "value": "Healthy",
            "confidence": "High",
            "explanation": "The positive delta remains stable through the alarm.",
        },
        "root_cause": {
            "value": "N/A",
            "confidence": "High",
            "explanation": "N/A",
        },
    }
