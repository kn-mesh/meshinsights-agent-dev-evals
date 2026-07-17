"""Behavior tests for the Pulse v1_3 agent composition."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from mi.ai.backends.base import AIUsage, AgentRequest, AgentResult

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from src.processors.v1_3.alarm_classification_agent import (
    V1_3AlarmClassificationAgent,
    V1_3AlarmClassificationAgentConfig,
)


class CapturingBackend:
    """Capture the normalized agent request and return a deterministic decision."""

    request: AgentRequest[PulseFailureAnalysisResult] | None = None

    def run_agent(
        self,
        request: AgentRequest[PulseFailureAnalysisResult],
        *,
        deps: object | None = None,
    ) -> AgentResult[PulseFailureAnalysisResult]:
        """Return one valid healthy decision."""
        _ = deps
        self.request = request
        return AgentResult(
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
            usage=AIUsage(requests=3, input_tokens=1200, output_tokens=90),
        )


def _build_process_object() -> PulseFailureAnalysisProcessObject:
    """Build representative process input with a year of sparse evidence."""
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


def test_agent_propagates_toolset_capability_skill_and_unlimited_tokens() -> None:
    """Compose all extension types while preserving unlimited token defaults."""
    backend = CapturingBackend()
    agent = V1_3AlarmClassificationAgent(
        V1_3AlarmClassificationAgentConfig(model="azure:gpt-5-mini")
    )
    agent._backend_cache = backend
    process_object = _build_process_object()

    agent.process(process_object)

    assert backend.request is not None
    assert [toolset.id for toolset in backend.request.toolsets] == [
        "temperature-evidence-inspection"
    ]
    assert [capability.id for capability in backend.request.capabilities] == [
        "sensor-integrity-review",
        "steam-trap-failure-diagnosis",
    ]
    assert all(capability.defer_loading for capability in backend.request.capabilities)
    assert backend.request.usage_limits.input_tokens_limit is None
    assert backend.request.usage_limits.output_tokens_limit is None
    assert backend.request.usage_limits.total_tokens_limit is None
    assert backend.request.transport_retries == 3
    assert backend.request.tool_retries == 3
    assert backend.request.output_retries is None
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


def test_evidence_toolset_exposes_bounded_summary_and_zoom_tools() -> None:
    """Expose deterministic inspection tools with stable names."""
    backend = CapturingBackend()
    agent = V1_3AlarmClassificationAgent(
        V1_3AlarmClassificationAgentConfig(model="azure:gpt-5-mini")
    )
    agent._backend_cache = backend

    agent.process(_build_process_object())

    assert backend.request is not None
    tools = backend.request.toolsets[0].tools
    assert [tool.resolved_name() for tool in tools] == [
        "summarize_temperature_range",
        "render_temperature_zoom",
    ]
    summary = tools[0].function("2026-03-10", "2026-03-17")
    assert isinstance(summary, str)
    assert '"delta_median": 25.0' in summary

    assert isinstance(
        tools[1].function("2026-03-10", "2026-03-17", "recent_alarm_review"),
        list,
    )
    assert isinstance(
        tools[1].function("2025-03-17", "2025-03-24", "historical_comparison"),
        list,
    )
    with pytest.raises(ValueError, match="At most two targeted temperature zooms"):
        tools[1].function("2026-03-01", "2026-03-05", "historical_comparison")
