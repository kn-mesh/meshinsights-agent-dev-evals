"""Deferred-skill investigation agent for the progressive Pulse v2 pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from mi.ai import (
    AIAgentMixin,
    AIProcessorConfig,
    AISkill,
    ImageContent,
    TextContent,
    ToolContext,
    UserMessage,
    ai_tool,
)
from mi.core.processors import BaseProcessor
from pydantic import Field

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import PulseFailureAnalysisResult
from src.processors.common.temperature_window_analysis import (
    TemperatureWindowAnalyzer,
    TemperatureWindowResolution,
    TemperatureWindowSummary,
)
from src.processors.v1_3.v1_3_temperature_graphs_processor import (
    V1_3TemperatureGraphsProcessor,
    V1_3TemperatureGraphsProcessorConfig,
)
from src.processors.v2.structured_outputs import V2InvestigationCaseBrief


class V2CapabilityInvestigationAIAgentProcessorConfig(AIProcessorConfig):
    """Configure the bounded specialist investigation."""

    name: str | None = "v2_capability_investigation_ai_agent_processor"
    max_investigation_days: int = Field(default=45, ge=1, le=365)
    investigation_chart_dpi: int = Field(default=120, ge=40, le=240)
    max_turns: int = 8
    tool_calls_limit: int | None = 4
    tool_timeout: float | None = 30
    timeout: float | None = 180
    transport_retries: int = 3
    tool_retries: int = 2
    output_retries: int | None = 1


class V2CapabilityInvestigationAIAgentProcessor(
    AIAgentMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Resolve a case-brief uncertainty using selectively loaded chart skills."""

    output_schema = PulseFailureAnalysisResult
    config: V2CapabilityInvestigationAIAgentProcessorConfig

    def __init__(
        self,
        config: V2CapabilityInvestigationAIAgentProcessorConfig | None = None,
    ) -> None:
        """Initialize the progressive investigation agent."""
        resolved_config = config or V2CapabilityInvestigationAIAgentProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build the small universal task shared by every investigation path."""
        _ = data_object
        return f"""
You make the final decision for a steam-trap alarm investigation. The supplied
case brief is a first-pass hypothesis, not ground truth. The FDE alarm is only a
review trigger, and each unit must be judged relative to its own historical
operating baseline.

Before deciding, load exactly one deferred investigation skill and call exactly
one of that skill's chart tools to resolve the case brief's main uncertainty.
Use the recommended skill unless another single skill is clearly better. Do not
load a second skill or request another chart: comparison tools already return
both charts in one call. Then make the final structured decision.

Every requested chart interval must be no longer than
{self.config.max_investigation_days} days and must end no later than the alarm.

Return Healthy or Failure. For Failure, return Open Failure, Closed Failure, or
Unknown. When failure remains plausible and cannot be ruled out, prefer Failure
with Low confidence over Healthy with Low confidence. Cite concrete dates,
temperatures, trajectories, delta behavior, and the historical comparison in the
structured explanations. Do not mention skills, tools, or chart numbers.
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Provide only the persisted orientation artifact and alarm identity."""
        raw_brief = data_object.get_investigation_case_brief()
        if raw_brief is None:
            raise ValueError("Required v2 investigation case brief is missing.")
        brief = V2InvestigationCaseBrief.model_validate(raw_brief)
        alarm_context = data_object.get_alarm_context()
        return UserMessage().add_text(
            f"""
Unit: {alarm_context.get("unit", alarm_context.get("sensor_id", "unknown"))}
Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
FDE alarm timestamp: {alarm_context["selected_alarm"]["detected_at"].isoformat()}

First-pass case brief:
{brief.model_dump_json(indent=2)}
"""
        )

    def _build_skills(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> Sequence[AISkill]:
        """Attach focused chart tools to deferred Agent Skills."""
        _ = data_object

        @ai_tool(name="inspect_open_failure_onset")
        def inspect_open_failure_onset(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> list[TextContent | ImageContent]:
            """Chart the suspected condensate-side departure and resulting regime."""
            return self._render_window_evidence(
                ctx,
                start=start,
                end=end,
                label="Suspected open-failure onset and stabilized regime",
            )

        @ai_tool(name="compare_closed_candidate_with_shutdown")
        def compare_closed_candidate_with_shutdown(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            candidate_start: str,
            candidate_end: str,
            shutdown_start: str,
            shutdown_end: str,
        ) -> list[TextContent | ImageContent]:
            """Return paired charts for a candidate event and historical shutdown."""
            return self._render_comparison_evidence(
                ctx,
                first_start=candidate_start,
                first_end=candidate_end,
                first_label="Candidate alarm-adjacent transition",
                second_start=shutdown_start,
                second_end=shutdown_end,
                second_label="Historical shutdown comparison",
            )

        @ai_tool(name="inspect_closed_failure_transition")
        def inspect_closed_failure_transition(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> list[TextContent | ImageContent]:
            """Chart steam-side timing when no comparable shutdown is identified."""
            return self._render_window_evidence(
                ctx,
                start=start,
                end=end,
                label="Candidate closed-failure or shutdown transition",
            )

        @ai_tool(name="inspect_modulation_regime")
        def inspect_modulation_regime(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> list[TextContent | ImageContent]:
            """Chart a level change and enough of the new regime to assess stability."""
            return self._render_window_evidence(
                ctx,
                start=start,
                end=end,
                label="Candidate modulation transition and resulting regime",
            )

        @ai_tool(name="compare_current_with_history")
        def compare_current_with_history(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            current_start: str,
            current_end: str,
            historical_start: str,
            historical_end: str,
        ) -> list[TextContent | ImageContent]:
            """Return paired charts for a current pattern and historical precedent."""
            return self._render_comparison_evidence(
                ctx,
                first_start=current_start,
                first_end=current_end,
                first_label="Current alarm-adjacent pattern",
                second_start=historical_start,
                second_end=historical_end,
                second_label="Historical precedent or sensor regime",
            )

        skill_root = Path(__file__).with_name("skills")
        return [
            AISkill.from_path(
                skill_root / "open-failure-investigation",
                tools=[inspect_open_failure_onset],
            ),
            AISkill.from_path(
                skill_root / "closed-vs-shutdown",
                tools=[
                    inspect_closed_failure_transition,
                    compare_closed_candidate_with_shutdown,
                ],
            ),
            AISkill.from_path(
                skill_root / "modulation-vs-failure",
                tools=[inspect_modulation_regime],
            ),
            AISkill.from_path(
                skill_root / "history-and-sensor-integrity",
                tools=[compare_current_with_history],
            ),
        ]

    def _render_window_evidence(
        self,
        ctx: ToolContext[PulseFailureAnalysisProcessObject],
        *,
        start: str,
        end: str,
        label: str,
    ) -> list[TextContent | ImageContent]:
        """Return one bounded chart with compact measurements."""
        existing_evidence = ctx.data_object.get_investigation_evidence()
        if existing_evidence:
            return [
                TextContent(
                    text=(
                        "The one-call investigation evidence budget is already used. "
                        "Use the existing chart evidence and return the final decision."
                    )
                )
            ]
        resolution, summary, chart = self._analyze_and_render(
            ctx,
            start=start,
            end=end,
        )
        ctx.data_object.add_investigation_evidence(
            {
                "kind": "window",
                "label": label,
                "requested_start": resolution.requested_start.isoformat(),
                "requested_end": resolution.requested_end.isoformat(),
                "start": resolution.range_start.isoformat(),
                "end": resolution.range_end.isoformat(),
                "adjustments": resolution.adjustments,
            }
        )
        return [
            TextContent(
                text=self._format_summary(
                    label=label,
                    summary=summary,
                    resolution=resolution,
                )
            ),
            ImageContent.from_bytes(chart, media_type="image/png"),
        ]

    def _render_comparison_evidence(
        self,
        ctx: ToolContext[PulseFailureAnalysisProcessObject],
        *,
        first_start: str,
        first_end: str,
        first_label: str,
        second_start: str,
        second_end: str,
        second_label: str,
    ) -> list[TextContent | ImageContent]:
        """Return two independently scaled charts with comparable measurements."""
        existing_evidence = ctx.data_object.get_investigation_evidence()
        if existing_evidence:
            return [
                TextContent(
                    text=(
                        "The one-call investigation evidence budget is already used. "
                        "Use the existing chart evidence and return the final decision."
                    )
                )
            ]
        first_resolution, first_summary, first_chart = self._analyze_and_render(
            ctx, start=first_start, end=first_end
        )
        second_resolution, second_summary, second_chart = self._analyze_and_render(
            ctx, start=second_start, end=second_end
        )
        ctx.data_object.add_investigation_evidence(
            {
                "kind": "comparison",
                "intervals": [
                    {
                        "label": first_label,
                        "requested_start": first_resolution.requested_start.isoformat(),
                        "requested_end": first_resolution.requested_end.isoformat(),
                        "start": first_resolution.range_start.isoformat(),
                        "end": first_resolution.range_end.isoformat(),
                        "adjustments": first_resolution.adjustments,
                    },
                    {
                        "label": second_label,
                        "requested_start": second_resolution.requested_start.isoformat(),
                        "requested_end": second_resolution.requested_end.isoformat(),
                        "start": second_resolution.range_start.isoformat(),
                        "end": second_resolution.range_end.isoformat(),
                        "adjustments": second_resolution.adjustments,
                    },
                ],
            }
        )
        return [
            TextContent(
                text=self._format_summary(
                    label=first_label,
                    summary=first_summary,
                    resolution=first_resolution,
                )
            ),
            ImageContent.from_bytes(first_chart, media_type="image/png"),
            TextContent(
                text=self._format_summary(
                    label=second_label,
                    summary=second_summary,
                    resolution=second_resolution,
                )
            ),
            ImageContent.from_bytes(second_chart, media_type="image/png"),
        ]

    def _analyze_and_render(
        self,
        ctx: ToolContext[PulseFailureAnalysisProcessObject],
        *,
        start: str,
        end: str,
    ) -> tuple[TemperatureWindowResolution, TemperatureWindowSummary, bytes]:
        """Resolve, summarize, and chart one model-requested interval."""
        alarm_at = ctx.data_object.get_alarm_context()["selected_alarm"]["detected_at"]
        analyzer = TemperatureWindowAnalyzer(
            max_window_days=self.config.max_investigation_days
        )
        history = ctx.data_object.get_temperature_history()
        resolution = analyzer.resolve_available_range(
            history,
            start=start,
            end=end,
            alarm_at=alarm_at,
        )
        summary = analyzer.summarize(
            history,
            range_start=resolution.range_start,
            range_end=resolution.range_end,
        )
        chart_processor = V1_3TemperatureGraphsProcessor(
            V1_3TemperatureGraphsProcessorConfig(
                dpi=self.config.investigation_chart_dpi
            )
        )
        chart = chart_processor.render_custom_combined_chart(
            history,
            range_start=resolution.range_start,
            range_end=resolution.range_end,
            alarm_detected_at=alarm_at,
        )
        return resolution, summary, chart

    def _format_summary(
        self,
        *,
        label: str,
        summary: TemperatureWindowSummary,
        resolution: TemperatureWindowResolution,
    ) -> str:
        """Format only the basic measurements needed to orient chart reading."""
        adjustment_text = (
            "None" if not resolution.adjustments else " ".join(resolution.adjustments)
        )
        return (
            f"{label}\n"
            f"Requested interval: {resolution.requested_start.isoformat()} through "
            f"{resolution.requested_end.isoformat()}\n"
            f"Rendered interval: {resolution.range_start.isoformat()} through "
            f"{resolution.range_end.isoformat()}\n"
            f"Automatic interval adjustments: {adjustment_text}\n"
            f"Available paired readings: {summary.paired_readings}\n"
            f"Start medians (Steam / Condensate / Delta): "
            f"{summary.start_steam_median_c:.1f}C / "
            f"{summary.start_condensate_median_c:.1f}C / "
            f"{summary.start_delta_median_c:.1f}C\n"
            f"End medians (Steam / Condensate / Delta): "
            f"{summary.end_steam_median_c:.1f}C / "
            f"{summary.end_condensate_median_c:.1f}C / "
            f"{summary.end_delta_median_c:.1f}C\n"
            f"Median normalized delta: {summary.median_normalized_delta:.3f}\n"
            f"Same-direction movement fraction: "
            f"{summary.same_direction_movement_fraction}\n"
            f"Nonpositive delta fraction: {summary.nonpositive_delta_fraction:.3f}\n"
            "Treat these measurements as chart context, not standalone rules."
        )

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Preserve the stable receipt and evaluation artifact contract."""
        if not data_object.get_investigation_evidence():
            raise ValueError(
                "A focused investigation chart is required before the final decision."
            )
        data_object.set_ai_result(response.model_dump())
