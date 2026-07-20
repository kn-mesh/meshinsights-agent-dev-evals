"""Tool-using investigation agent for the Pulse v_2 pipeline."""

from __future__ import annotations

from mi.ai import (
    AIAgentMixin,
    AIProcessorConfig,
    ImageContent,
    TextContent,
    Tool,
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
)
from src.processors.v1_3.v1_3_temperature_graphs_processor import (
    V1_3TemperatureGraphsProcessor,
    V1_3TemperatureGraphsProcessorConfig,
)


class V2AlarmInvestigationAIAgentProcessorConfig(AIProcessorConfig):
    """Configure the bounded v_2 investigation agent."""

    name: str | None = "v2_alarm_investigation_ai_agent_processor"
    window_days_list: list[int] = [7, 30, 365]
    max_investigation_days: int = Field(default=45, ge=1, le=365)
    investigation_chart_dpi: int = Field(default=120, ge=40, le=240)
    max_turns: int = 5
    tool_calls_limit: int | None = 3
    tool_timeout: float | None = 30
    timeout: float | None = 180
    transport_retries: int = 1
    tool_retries: int = 1
    output_retries: int | None = 1


class V2AlarmInvestigationAIAgentProcessor(
    AIAgentMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Investigate ambiguous alarm patterns with selective evidence tools."""

    output_schema = PulseFailureAnalysisResult
    config: V2AlarmInvestigationAIAgentProcessorConfig

    def __init__(
        self,
        config: V2AlarmInvestigationAIAgentProcessorConfig | None = None,
    ) -> None:
        """Initialize the v_2 agent with typed execution and tool budgets."""
        resolved_config = config or V2AlarmInvestigationAIAgentProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build stable task rules and the adaptive investigation policy."""
        _ = data_object
        return f"""
<task>
A rules-based Failure Detection Engine (FDE) flagged a possible steam-trap failure.
The FDE has a greater than 50 percent false-positive rate. Determine whether the
trap was Healthy or in Failure around the alarm, then classify a failure as Open
Failure, Closed Failure, or Unknown.
</task>

<evidence_policy>
Start with the supplied 365-day, 30-day, and 7-day charts. Establish this unit's
normal On, Off, startup, shutdown, and modulation behavior before judging the
alarm-adjacent period. Do not call investigation tools when the supplied evidence
already supports a clear decision.

When healthy control modulation remains difficult to distinguish from a closed
failure, call measure_temperature_window before relying on visual impressions.
Call render_temperature_zoom only when a more precise view of that interval would
discriminate between the competing explanations.
Tool windows must be no longer than {self.config.max_investigation_days} days and
must not extend beyond the FDE alarm timestamp.
</evidence_policy>

<decision_rules>
- Treat the alarm as a review trigger, not as proof of failure or the exact start
  of failure. Judge the broader stabilized regime around it.
- Compare like operating states. Delta naturally shrinks at lower absolute
  temperatures, so consider both raw and normalized delta.
- Healthy modulation generally shows a step to a new regime followed by a stable
  horizontal average, thermal coupling, and a persistently positive proportional
  delta.
- A new regime that continues driving downward, repeatedly inverts, or has a
  sustained delta collapse relative to comparable historical On-states supports
  Failure even when the two sensors appear coupled.
- A simultaneous drop by both sensors is normally a shutdown or load change. A
  multi-hour separation in their response can support a closed failure.
- A historical precedent is healthy evidence only if it is similar in depth and
  duration and clearly recovers to the unit's normal baseline.
- Suspect a sensor flip only when the reversal is long-standing, not merely after
  a shutdown or during one alarm-adjacent interval.
- For root cause, identify the earliest sustained departure: condensate rising
  toward steam supports Open Failure; steam degrading toward condensate supports
  Closed Failure. Use Unknown when direction is not defensible.
- When failure remains plausible and cannot be ruled out, prefer Failure with Low
  confidence over Healthy with Low confidence. Use confidence High only when the
  operating phase, baseline, and main alternative explanation are clear.
</decision_rules>

<output_rules>
Return the required structured result. Explanations must cite concrete dates,
temperatures, delta behavior, trajectories, and the historical baseline used.
Do not mention chart numbers or tool names. Healthy requires root cause N/A;
Failure requires Open Failure, Closed Failure, or Unknown.
</output_rules>
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Attach the standard overview charts and alarm-specific context."""
        alarm_context = data_object.get_alarm_context()
        sorted_windows = sorted(self.config.window_days_list, reverse=True)
        charts: dict[int, str] = {}
        for days in sorted_windows:
            chart = data_object.get_temperature_chart(days)
            if chart is None:
                raise ValueError(
                    f"Required v_2 combined pre-alarm chart for {days}-day window is missing."
                )
            charts[days] = chart

        descriptions = "\n".join(
            self._build_image_description(index=index, days=days)
            for index, days in enumerate(sorted_windows, 1)
        )
        alarm_at = alarm_context["selected_alarm"]["detected_at"]
        message = UserMessage().add_text(
            f"""
<alarm_context>
Unit: {alarm_context.get("unit", alarm_context.get("sensor_id", "unknown"))}
Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
FDE alarm detected at: {alarm_at.isoformat()}
</alarm_context>

<overview_images>
{descriptions}
</overview_images>

The frozen overview windows end at the FDE alarm timestamp. Connectivity gaps
longer than 2.5 hours are shown as breaks rather than connected lines. Read the
365-day segments from left to right, then use the 30-day and 7-day views for
alarm-adjacent timing.
"""
        )
        for days in sorted_windows:
            message.add_image(charts[days], media_type="image/png")
        return message

    def _build_tools(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[Tool]:
        """Expose two eager, bounded investigation tools."""
        _ = data_object
        analyzer = TemperatureWindowAnalyzer(
            max_window_days=self.config.max_investigation_days
        )

        @ai_tool(name="measure_temperature_window")
        def measure_temperature_window(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> str:
            """Measure edge medians, directional coupling, and delta in an ISO-8601 interval."""
            alarm_at = ctx.data_object.get_alarm_context()["selected_alarm"][
                "detected_at"
            ]
            range_start, range_end = analyzer.resolve_range(
                start=start,
                end=end,
                alarm_at=alarm_at,
            )
            summary = analyzer.summarize(
                ctx.data_object.get_temperature_history(),
                range_start=range_start,
                range_end=range_end,
            )
            return summary.model_dump_json()

        @ai_tool(name="render_temperature_zoom")
        def render_temperature_zoom(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> list[TextContent | ImageContent]:
            """Render raw temperatures and rolling delta for a bounded ISO-8601 interval."""
            alarm_at = ctx.data_object.get_alarm_context()["selected_alarm"][
                "detected_at"
            ]
            range_start, range_end = analyzer.resolve_range(
                start=start,
                end=end,
                alarm_at=alarm_at,
            )
            chart_processor = V1_3TemperatureGraphsProcessor(
                V1_3TemperatureGraphsProcessorConfig(
                    dpi=self.config.investigation_chart_dpi
                )
            )
            chart_bytes = chart_processor.render_custom_combined_chart(
                ctx.data_object.get_temperature_history(),
                range_start=range_start,
                range_end=range_end,
                alarm_detected_at=alarm_at,
            )
            return [
                TextContent(
                    text=(
                        f"Zoom interval {range_start.isoformat()} through "
                        f"{range_end.isoformat()}."
                    )
                ),
                ImageContent.from_bytes(chart_bytes, media_type="image/png"),
            ]

        return [measure_temperature_window, render_temperature_zoom]

    def _build_image_description(self, *, index: int, days: int) -> str:
        """Describe one overview image without embedding unit-specific facts."""
        if days == 365:
            return (
                f"Image {index}: {days}-day combined analysis. The top row contains "
                "four chronological raw-temperature segments; the bottom row contains "
                "the matching Steam-minus-Condensate delta segments. All segments "
                "share their row's y-axis."
            )
        return (
            f"Image {index}: {days}-day combined analysis. Top panel is raw "
            "temperature (Red=Steam, Blue=Condensate); bottom panel is delta "
            "(Purple=4h rolling average, faint purple=raw delta)."
        )

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Preserve the stable decision artifact consumed by existing hydrators."""
        data_object.set_ai_result(response.model_dump())
