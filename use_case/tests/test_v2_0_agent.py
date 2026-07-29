"""Reference-use-case tests for the progressively disclosed v2_0 agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import cast

from mi.ai.backends.base import AIUsage, AgentRequest, AgentResult
from mi.ai.message import ImageContent, TextContent

from use_case.objects.process_object import PulseFailureAnalysisProcessObject
from use_case.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from use_case.processors.v1_3.v1_3_temperature_graphs_processor import (
    V1_3TemperatureGraphsProcessor,
    V1_3TemperatureGraphsProcessorConfig,
)
from use_case.processors.v2_0.v2_0_alarm_classification_agent import (
    V2_0AlarmClassificationAgent,
    V2_0AlarmClassificationAgentConfig,
)
from workbench.agent_versions import resolve_agent_version
from workbench.pipelines.pipeline_run_from_yaml import _load_pipeline_config


ROOT = Path(__file__).resolve().parents[2]


class CapturingBackend:
    """Capture the agent request and return a fixed structured decision."""

    request: AgentRequest[PulseFailureAnalysisResult] | None = None

    def run_agent(
        self,
        request: AgentRequest[PulseFailureAnalysisResult],
        *,
        deps: object | None = None,
    ) -> AgentResult[PulseFailureAnalysisResult]:
        """Store the request without invoking the real model."""
        _ = deps
        self.request = request
        return AgentResult(
            output=PulseFailureAnalysisResult(
                classification=ClassificationResult(
                    value="Healthy",
                    confidence="High",
                    explanation="The stable positive relationship matches the baseline.",
                ),
                root_cause=RootCauseResult(
                    value="N/A",
                    confidence="High",
                    explanation="N/A",
                ),
            ),
            usage=AIUsage(requests=1, input_tokens=900, output_tokens=80),
        )


def _build_process_object() -> PulseFailureAnalysisProcessObject:
    alarm_at = datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)
    history = [
        {
            "timestamp": alarm_at - timedelta(minutes=30 * offset),
            "steam_temperature": 130.0 - 0.02 * offset,
            "condensate_temperature": 103.0 - 0.01 * offset,
        }
        for offset in range(480, -3, -1)
    ]
    process_object = (
        PulseFailureAnalysisProcessObject()
        .set_alarm_context(
            {
                "unit": "trap-7",
                "sensor_id": 7,
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


def test_v2_0_sends_standard_evidence_with_one_deferred_skill() -> None:
    """Keep specialist instructions and tools deferred on the initial turn."""
    backend = CapturingBackend()
    agent = V2_0AlarmClassificationAgent(
        V2_0AlarmClassificationAgentConfig(model="azure:gpt-5-mini")
    )
    agent._backend_cache = backend
    process_object = _build_process_object()

    agent.process(process_object)

    assert backend.request is not None
    request = backend.request
    assert request.output_schema is PulseFailureAnalysisResult
    assert request.max_turns == 7
    assert request.usage_limits.tool_calls_limit == 5
    assert request.finalize_on_tool_call_limit is True
    assert request.tools == []
    assert len(request.capabilities) == 1
    capability = request.capabilities[0]
    assert capability.id == "complex-steam-trap-investigation"
    assert capability.defer_loading is True
    assert [tool.resolved_name() for tool in capability.tools] == [
        "plot_raw_temperature_range",
        "compare_temperature_ranges",
    ]
    assert "<decision_framework>" in request.system_prompt
    assert "<v2_progressive_investigation>" in request.system_prompt
    assert [
        block.media_type
        for block in request.user_message.content
        if isinstance(block, ImageContent)
    ] == ["image/png", "image/png", "image/png"]
    assert process_object.get_ai_result() is not None


def test_complex_skill_tools_plot_raw_data_and_compare_ranges() -> None:
    """Return a real PNG plus deterministic cutoff-bounded range statistics."""
    agent = V2_0AlarmClassificationAgent(
        V2_0AlarmClassificationAgentConfig(model="azure:gpt-5-mini")
    )
    process_object = _build_process_object()
    skill = agent._build_skills(process_object)[0]
    plot_tool, compare_tool = skill.tools

    raw_plot_result = plot_tool.function("2026-03-16", "2026-03-17")
    assert isinstance(raw_plot_result, list)
    plot_result = cast(list[TextContent | ImageContent], raw_plot_result)
    assert isinstance(plot_result[0], TextContent)
    assert isinstance(plot_result[1], ImageContent)
    image = cast(ImageContent, plot_result[1])
    text = cast(TextContent, plot_result[0])
    assert image.base64_data.startswith("iVBOR")
    assert "evidence cutoff 2026-03-17T12:00:00+00:00" in text.text

    raw_comparison = compare_tool.function(
        "2026-03-08",
        "2026-03-09",
        "2026-03-16",
        "2026-03-17",
    )
    assert isinstance(raw_comparison, str)
    comparison = json.loads(raw_comparison)
    assert comparison["reference"]["paired_points"] > 2
    assert comparison["focus"]["paired_points"] > 2
    assert comparison["focus"]["end_utc"] == "2026-03-17T12:00:00+00:00"
    assert "classification thresholds" in comparison["interpretation_guardrail"]

    reversed_result = plot_tool.function("2026-03-17", "2026-03-16")
    assert isinstance(reversed_result, list)
    assert any(isinstance(block, ImageContent) for block in reversed_result)

    invalid_result = compare_tool.function(
        "not-a-date",
        "2026-03-09",
        "2026-03-16",
        "2026-03-17",
    )
    assert isinstance(invalid_result, str)
    assert "error" in json.loads(invalid_result)


def test_v2_0_initial_charts_stop_at_the_decision_timestamp() -> None:
    """Prevent the initial evidence package from leaking a post-alarm reading."""
    process_object = _build_process_object()
    alarm_at = process_object.get_alarm_context()["selected_alarm"]["detected_at"]
    processor = V1_3TemperatureGraphsProcessor(
        V1_3TemperatureGraphsProcessorConfig(include_post_alarm_point=False)
    )
    temperature_frame = processor._build_temperature_frame(
        process_object.get_temperature_history()
    )

    window = processor._build_analysis_window(
        temperature_frame,
        alarm_detected_at=alarm_at,
        window_days=7,
    )

    assert window["timestamp"].max() == alarm_at


def test_v2_0_pipeline_and_version_manifest_include_the_skill() -> None:
    """Keep the pipeline runnable and the deferred behavior reconstructable."""
    source = _load_pipeline_config(Path("use_case/pipeline_configs/v2_0.ppln"))
    assert [item["processor"] for item in source["process"]["processors"]] == [
        "V1_3TemperatureGraphsProcessor",
        "V2_0AlarmClassificationAgent",
    ]
    assert (
        source["process"]["processors"][0]["include_post_alarm_point"] is False
    )
    assert source["process"]["processors"][1]["tool_calls_limit"] == 5
    assert (
        source["process"]["processors"][1]["finalize_on_tool_call_limit"] is True
    )

    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v2_0.ppln",
        dirty_policy="capture",
    )
    assets = {
        asset["path"]: {role["role"] for role in asset["roles"]}
        for asset in resolved.manifest.identity["assets"]
    }
    skill_path = (
        "use_case/processors/v2_0/skills/"
        "complex-steam-trap-investigation/runtime-skill.md"
    )
    assert "skill" in assets[skill_path]
