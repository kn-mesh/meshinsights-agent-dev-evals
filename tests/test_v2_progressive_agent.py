"""Contract tests for the progressive v2 case-brief investigation pipeline."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from evaluation import build_results_dir_for_pipeline
from mi.ai import ImageContent, TextContent, ToolContext
from mi.ai.backends.base import (
    AIUsage,
    AgentRequest,
    AgentResult,
    WorkflowRequest,
    WorkflowResult,
)
from mi.ai.mixins.agent import AgentDeps
from mi.core.pipeline_builder import PipelineBuilder
from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt

from src.hydrators.v2_process_to_action_hydrator import V2ProcessToActionHydrator
from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import (
    ClassificationResult,
    PulseFailureAnalysisResult,
    RootCauseResult,
)
from src.processors.v2.structured_outputs import (
    V2AlarmObservation,
    V2BaselineProfile,
    V2InvestigationCaseBrief,
    V2InvestigationHypothesis,
    V2ReferenceInterval,
)
from src.processors.v2.v2_capability_investigation_ai_agent_processor import (
    V2CapabilityInvestigationAIAgentProcessor,
    V2CapabilityInvestigationAIAgentProcessorConfig,
)
from src.processors.v2.v2_case_brief_ai_workflow_processor import (
    V2CaseBriefAIWorkflowProcessor,
    V2CaseBriefAIWorkflowProcessorConfig,
)


def _case_brief() -> V2InvestigationCaseBrief:
    return V2InvestigationCaseBrief(
        baseline=V2BaselineProfile(
            on_state="Historically about 140C steam, 105C condensate, +35C delta.",
            off_state="Both sensors usually settle near 25C.",
            recurring_patterns="Prior modulation steps stabilized with positive delta.",
            confidence="High",
        ),
        alarm_observation=V2AlarmObservation(
            operating_phase="Modulation",
            stabilized_regime="From March 15, both sensors stabilized near 110C.",
            departure_from_baseline="Delta narrowed from about 35C to 3C.",
            approximate_onset="2026-03-15T08:00:00",
        ),
        leading_hypothesis=V2InvestigationHypothesis(
            hypothesis="Closed failure",
            evidence="The lower regime has a materially reduced delta.",
        ),
        alternative_hypothesis=V2InvestigationHypothesis(
            hypothesis="Healthy operation",
            evidence="Both sensors moved together and then stabilized.",
        ),
        reference_intervals=[
            V2ReferenceInterval(
                label="Current alarm regime",
                start="2026-03-15T08:00:00",
                end="2026-03-17T12:00:00",
                relevance="Shows the level change and subsequent stabilization.",
            ),
            V2ReferenceInterval(
                label="On baseline",
                start="2026-03-08T00:00:00",
                end="2026-03-10T00:00:00",
                relevance="Provides a comparable elevated operating regime.",
            ),
        ],
        unresolved_question=(
            "Did the new regime retain a proportionate delta or continue degrading?"
        ),
        recommended_skill="modulation-vs-failure",
    )


def _process_object() -> PulseFailureAnalysisProcessObject:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    history = [
        {
            "timestamp": alarm_at - timedelta(minutes=30 * (480 - index)),
            "steam_temperature": 140.0 - index * 0.02,
            "condensate_temperature": 105.0 + index * 0.01,
        }
        for index in range(481)
    ]
    process_object = (
        PulseFailureAnalysisProcessObject()
        .set_alarm_context(
            {
                "unit": "trap-250003575",
                "sensor_id": 250003575,
                "example_id": "trap-250003575|2026-03-17T12:00:00",
                "benchmark_key": "steam-trap-regression",
                "benchmark_version_id": "version-id",
                "benchmark_version_number": 3,
                "source_snapshot_id": "snapshot-id",
                "decision_timestamp": alarm_at,
                "selected_alarm": {"detected_at": alarm_at},
            }
        )
        .set_steam_trap_type("Float")
        .set_temperature_history(history)
    )
    for window_days in (30, 365):
        process_object.set_temperature_chart(window_days, "aW1hZ2U=")
    return process_object


class CaseBriefBackend:
    """Capture the orientation request and return a fixed case brief."""

    def __init__(self) -> None:
        self.requests: list[WorkflowRequest[V2InvestigationCaseBrief]] = []

    def run_workflow(
        self, request: WorkflowRequest[V2InvestigationCaseBrief]
    ) -> WorkflowResult[V2InvestigationCaseBrief]:
        self.requests.append(request)
        return WorkflowResult(
            output=_case_brief(),
            usage=AIUsage(requests=1, input_tokens=900, output_tokens=220),
        )


class InvestigationBackend:
    """Capture the agent request and return a fixed final decision."""

    def __init__(self) -> None:
        self.requests: list[AgentRequest[PulseFailureAnalysisResult]] = []

    def run_agent(
        self,
        request: AgentRequest[PulseFailureAnalysisResult],
        *,
        deps: object | None = None,
    ) -> AgentResult[PulseFailureAnalysisResult]:
        assert isinstance(deps, AgentDeps)
        self.requests.append(request)
        alarm_at = deps.context.data_object.get_alarm_context()["selected_alarm"][
            "detected_at"
        ]
        request.capabilities[2].tools[0].function(
            deps.context,
            (alarm_at - timedelta(days=2)).isoformat(),
            alarm_at.isoformat(),
        )
        return AgentResult(
            output=PulseFailureAnalysisResult(
                classification=ClassificationResult(
                    value="Failure",
                    confidence="Low",
                    explanation="The new regime retained a materially collapsed delta.",
                ),
                root_cause=RootCauseResult(
                    value="Closed Failure",
                    confidence="Low",
                    explanation="Steam degraded toward the condensate baseline first.",
                ),
            ),
            usage=AIUsage(requests=3, input_tokens=1600, output_tokens=150),
        )


def test_case_brief_workflow_has_a_narrow_non_final_prompt() -> None:
    backend = CaseBriefBackend()
    workflow = V2CaseBriefAIWorkflowProcessor(
        V2CaseBriefAIWorkflowProcessorConfig(model="azure:gpt-5-mini")
    )
    workflow._backend_cache = backend
    process_object = _process_object()

    workflow.process(process_object)

    request = backend.requests[0]
    assert request.output_schema is V2InvestigationCaseBrief
    assert "Do not make the final" in request.system_prompt
    assert "<decision_framework>" not in request.system_prompt
    assert len(request.system_prompt) < 1_500
    assert (
        len(
            [
                block
                for block in request.user_message.content
                if isinstance(block, ImageContent)
            ]
        )
        == 2
    )
    assert process_object.get_investigation_case_brief() == _case_brief().model_dump()


def test_investigation_agent_progressively_discloses_four_skills() -> None:
    backend = InvestigationBackend()
    agent = V2CapabilityInvestigationAIAgentProcessor(
        V2CapabilityInvestigationAIAgentProcessorConfig(model="azure:gpt-5-mini")
    )
    agent._backend_cache = backend
    process_object = _process_object().set_investigation_case_brief(
        _case_brief().model_dump()
    )

    agent.process(process_object)

    request = backend.requests[0]
    assert request.tools == []
    assert request.toolsets == []
    assert request.max_turns == 8
    assert request.usage_limits.tool_calls_limit == 5
    assert [capability.id for capability in request.capabilities] == [
        "open-failure-investigation",
        "closed-vs-shutdown",
        "modulation-vs-failure",
        "history-and-sensor-integrity",
    ]
    assert all(capability.defer_loading for capability in request.capabilities)
    assert [tool.resolved_name() for tool in request.capabilities[0].tools] == [
        "inspect_open_failure_onset",
    ]
    assert [tool.resolved_name() for tool in request.capabilities[1].tools] == [
        "inspect_closed_failure_transition",
        "compare_closed_candidate_with_shutdown",
    ]
    assert [tool.resolved_name() for tool in request.capabilities[2].tools] == [
        "inspect_modulation_regime",
    ]
    assert [tool.resolved_name() for tool in request.capabilities[3].tools] == [
        "compare_current_with_history",
    ]
    assert not any(
        isinstance(block, ImageContent) for block in request.user_message.content
    )
    first_block = request.user_message.content[0]
    assert isinstance(first_block, TextContent)
    assert "modulation-vs-failure" in first_block.text
    assert process_object.get_ai_result() is not None
    assert process_object.get_investigation_evidence()[0]["kind"] == "window"


def test_deferred_skill_tool_returns_chart_and_basic_context() -> None:
    process_object = _process_object().set_investigation_case_brief(
        _case_brief().model_dump()
    )
    agent = V2CapabilityInvestigationAIAgentProcessor(
        V2CapabilityInvestigationAIAgentProcessorConfig(
            model="azure:gpt-5-mini", investigation_chart_dpi=40
        )
    )
    skills = {skill.name: skill for skill in agent._build_skills(process_object)}
    tool = skills["modulation-vs-failure"].tools[0]
    alarm_at = process_object.get_alarm_context()["selected_alarm"]["detected_at"]

    result = tool.function(
        ToolContext(data_object=process_object),
        (alarm_at - timedelta(days=2)).isoformat(),
        alarm_at.isoformat(),
    )

    assert isinstance(result, list)
    assert isinstance(result[0], TextContent)
    assert "Start medians (Steam / Condensate / Delta)" in result[0].text
    assert isinstance(result[1], ImageContent)
    assert result[1].base64_data.startswith("iVBOR")


def test_final_decision_is_rejected_without_focused_chart_evidence() -> None:
    process_object = _process_object().set_investigation_case_brief(
        _case_brief().model_dump()
    )
    agent = V2CapabilityInvestigationAIAgentProcessor(
        V2CapabilityInvestigationAIAgentProcessorConfig(model="azure:gpt-5-mini")
    )
    result = PulseFailureAnalysisResult(
        classification=ClassificationResult(
            value="Healthy",
            confidence="High",
            explanation="The current regime matches its historical baseline.",
        ),
        root_cause=RootCauseResult(
            value="N/A",
            confidence="High",
            explanation="N/A",
        ),
    )

    with pytest.raises(ValueError, match="focused investigation chart"):
        agent._attach_response(process_object, result)


def test_v2_hydrator_preserves_case_brief_in_final_payload() -> None:
    process_object = _process_object().set_investigation_case_brief(
        _case_brief().model_dump()
    )
    process_object.set_ai_result(
        PulseFailureAnalysisResult(
            classification=ClassificationResult(
                value="Failure",
                confidence="Low",
                explanation="The current regime is materially degraded.",
            ),
            root_cause=RootCauseResult(
                value="Unknown",
                confidence="Low",
                explanation="The first departing side remains ambiguous.",
            ),
        ).model_dump()
    )
    process_object.add_investigation_evidence(
        {
            "kind": "window",
            "label": "Candidate regime",
            "start": "2026-03-15T08:00:00",
            "end": "2026-03-17T12:00:00",
        }
    )
    receipt = PipelineReceipt(
        pipeline_id="test",
        process_receipt=StageReceipt("process", True, 0.0),
    )

    action_object = V2ProcessToActionHydrator().hydrate(process_object, receipt)

    result = action_object.get_pipeline_result()
    assert result["classification"]["value"] == "Failure"
    assert result["investigation_case_brief"] == _case_brief().model_dump()
    assert result["investigation_evidence"][0]["kind"] == "window"


def test_v2_pipeline_config_builds_registered_progressive_processors() -> None:
    source_path = Path("pipeline_configs/v2.ppln")
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

    assert pipeline.config.name == "pulse_alarm_failure_analysis_v2"
    assert pipeline.config.version == "2.0.0"
    assert config["process"]["hydrator"] == "V2ProcessToActionHydrator"
    assert [entry["processor"] for entry in config["process"]["processors"]] == [
        "V1_3TemperatureGraphsProcessor",
        "V2CaseBriefAIWorkflowProcessor",
        "V2CapabilityInvestigationAIAgentProcessor",
    ]


def test_v2_eval_results_use_the_canonical_pipeline_directory() -> None:
    assert build_results_dir_for_pipeline(
        base_results_dir=Path("eval_results"),
        yaml_path=Path("pipeline_configs/v2.ppln"),
    ) == Path("eval_results/v2")
