"""Behavior and pipeline contract tests for the Pulse v_2 agent."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from mi.ai import ImageContent, TextContent, ToolContext
from mi.ai.backends.base import AIUsage, AgentRequest, AgentResult
from mi.core.pipeline_builder import PipelineBuilder

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from src.processors.v_2.v2_alarm_investigation_ai_agent_processor import (
    V2AlarmInvestigationAIAgentProcessor,
    V2AlarmInvestigationAIAgentProcessorConfig,
)


class CapturingAgentBackend:
    """Capture one normalized agent request and return a fixed decision."""

    def __init__(self) -> None:
        self.requests: list[AgentRequest[PulseFailureAnalysisResult]] = []

    def run_agent(
        self,
        request: AgentRequest[PulseFailureAnalysisResult],
        *,
        deps: object | None = None,
    ) -> AgentResult[PulseFailureAnalysisResult]:
        _ = deps
        self.requests.append(request)
        return AgentResult(
            output=PulseFailureAnalysisResult(
                classification=ClassificationResult(
                    value="Healthy",
                    confidence="High",
                    explanation="The lower regime remained stable with positive delta.",
                ),
                root_cause=RootCauseResult(
                    value="N/A",
                    confidence="High",
                    explanation="N/A",
                ),
            ),
            usage=AIUsage(requests=2, input_tokens=1500, output_tokens=120),
        )


def _build_process_object() -> PulseFailureAnalysisProcessObject:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    history = [
        {
            "timestamp": alarm_at - timedelta(minutes=30 * (96 - index)),
            "steam_temperature": 130.0 - index * 0.05,
            "condensate_temperature": 105.0 - index * 0.03,
        }
        for index in range(97)
    ]
    process_object = (
        PulseFailureAnalysisProcessObject()
        .set_alarm_context(
            {
                "unit": "trap-250003575",
                "sensor_id": 250003575,
                "selected_alarm": {"detected_at": alarm_at},
            }
        )
        .set_steam_trap_type("Float")
        .set_temperature_history(history)
    )
    for window_days in (7, 30, 365):
        process_object.set_temperature_chart(window_days, "aW1hZ2U=")
    return process_object


def test_v_2_builds_a_bounded_agent_with_eager_tools() -> None:
    backend = CapturingAgentBackend()
    agent = V2AlarmInvestigationAIAgentProcessor(
        V2AlarmInvestigationAIAgentProcessorConfig(model="azure:gpt-5-mini")
    )
    agent._backend_cache = backend
    process_object = _build_process_object()

    agent.process(process_object)

    assert len(backend.requests) == 1
    request = backend.requests[0]
    assert request.max_turns == 5
    assert request.usage_limits.tool_calls_limit == 3
    assert request.output_schema is PulseFailureAnalysisResult
    assert request.capabilities == []
    assert [tool.resolved_name() for tool in request.tools] == [
        "measure_temperature_window",
        "render_temperature_zoom",
    ]
    assert process_object.get_ai_result() is not None
    assert process_object.get_artifact(f"{agent._get_artifact_key()}_response") is None
    assert process_object.get_artifact(f"{agent._get_artifact_key()}_usage") is not None


def test_v_2_tools_return_deterministic_measurements_and_png_zoom() -> None:
    process_object = _build_process_object()
    agent = V2AlarmInvestigationAIAgentProcessor(
        V2AlarmInvestigationAIAgentProcessorConfig(
            model="azure:gpt-5-mini", investigation_chart_dpi=40
        )
    )
    tools = {
        tool.resolved_name(): tool.function
        for tool in agent._build_tools(process_object)
    }
    context = ToolContext(data_object=process_object)
    alarm_at = process_object.get_alarm_context()["selected_alarm"]["detected_at"]
    start = (alarm_at - timedelta(days=1)).isoformat()
    end = alarm_at.isoformat()

    measurement_result = tools["measure_temperature_window"](context, start, end)
    zoom = tools["render_temperature_zoom"](context, start, end)

    assert isinstance(measurement_result, str)
    measurements = json.loads(measurement_result)
    assert measurements["paired_readings"] == 49
    assert measurements["start_delta_median_c"] > 0
    assert measurements["end_delta_median_c"] > 0
    assert "steam_trend_c_per_day" not in measurements
    assert isinstance(zoom, list)
    assert isinstance(zoom[0], TextContent)
    assert isinstance(zoom[1], ImageContent)
    zoom_image = zoom[1]
    assert isinstance(zoom_image, ImageContent)
    assert zoom_image.base64_data.startswith("iVBOR")


def test_v_2_pipeline_config_builds_registered_agent() -> None:
    source_path = Path("pipeline_configs/v_2.ppln")
    config = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    config["metadata"] = {
        "metadata": config.pop("metadata_class"),
        "unit": "trap-1",
        "example_id": "1|2026-03-17T12:00:00",
        "sensor_id": 1,
        "decision_timestamp": "2026-03-17T12:00:00",
        "benchmark_key": "steam-trap-regression",
        "benchmark_version_id": "version-id",
        "benchmark_version_number": 3,
        "source_snapshot_id": "snapshot-id",
        "source_snapshot_content_sha256": "a" * 64,
        "source_kind": "mongo",
        "raw_captured_at": "2026-03-18T00:00:00",
        "raw_window_start": "2025-03-17T00:00:00",
        "raw_window_end": "2026-03-17T12:00:00",
        "raw_known_gaps": [],
        "raw_artifacts": [],
        "example_metadata": {"sensor_id": "1"},
    }

    runtime_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ppln",
            dir="pipeline_configs",
            encoding="utf-8",
            delete=False,
        ) as runtime_file:
            yaml.safe_dump(config, runtime_file, sort_keys=False)
            runtime_path = Path(runtime_file.name)
        pipeline = PipelineBuilder.from_yaml(runtime_path).build()
    finally:
        if runtime_path is not None:
            runtime_path.unlink(missing_ok=True)

    assert pipeline.config.name == "pulse_alarm_failure_analysis_v_2"
    assert pipeline.config.version == "2.0.0"
