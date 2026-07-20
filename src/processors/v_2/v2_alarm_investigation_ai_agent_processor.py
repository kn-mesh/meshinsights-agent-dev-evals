"""Tool-using investigation agent for the Pulse v_2 pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd
from mi.ai import (
    AIAgentMixin,
    AICapability,
    AIProcessorConfig,
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
    max_turns: int = 6
    tool_calls_limit: int | None = 4
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
failure, load the control-modulation-review capability. Use its measurement tool
before relying on visual impressions, and request a zoom only when a more precise
view of a specific interval would discriminate between the competing explanations.
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

    def _build_capabilities(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[AICapability]:
        """Expose a deferred specialist investigation with bounded tools."""
        _ = data_object

        @ai_tool(name="measure_temperature_window")
        def measure_temperature_window(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> str:
            """Measure trends, coupling, and raw and normalized delta in an ISO-8601 interval."""
            range_start, range_end = self._validate_tool_range(
                ctx.data_object,
                start=start,
                end=end,
            )
            frame = self._build_tool_window(
                ctx.data_object,
                range_start=range_start,
                range_end=range_end,
            )
            return json.dumps(
                self._measure_window(frame),
                sort_keys=True,
                separators=(",", ":"),
            )

        @ai_tool(name="render_temperature_zoom")
        def render_temperature_zoom(
            ctx: ToolContext[PulseFailureAnalysisProcessObject],
            start: str,
            end: str,
        ) -> list[TextContent | ImageContent]:
            """Render raw temperatures and rolling delta for a bounded ISO-8601 interval."""
            range_start, range_end = self._validate_tool_range(
                ctx.data_object,
                start=start,
                end=end,
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
                alarm_detected_at=ctx.data_object.get_alarm_context()["selected_alarm"][
                    "detected_at"
                ],
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

        return [
            AICapability(
                id="control-modulation-review",
                description=(
                    "Use when a temperature step or downward regime could be "
                    "either healthy control modulation or a closed failure."
                ),
                instructions=(
                    "Form the healthy-modulation and closed-failure hypotheses. "
                    "Measure the disputed interval first. Compare beginning and "
                    "ending levels, raw and normalized delta, direction of each "
                    "sensor, coupling, and stability. Render a zoom only if the "
                    "numerical result leaves an important visual ambiguity. "
                    "Relate the findings back to a comparable baseline in the "
                    "overview before finalizing."
                ),
                tools=[measure_temperature_window, render_temperature_zoom],
                defer_loading=True,
            )
        ]

    def _validate_tool_range(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        *,
        start: str,
        end: str,
    ) -> tuple[datetime, datetime]:
        """Parse and bound one model-requested investigation interval."""
        alarm_at = data_object.get_alarm_context()["selected_alarm"]["detected_at"]
        range_start = self._parse_datetime_like_alarm(start, alarm_at=alarm_at)
        range_end = self._parse_datetime_like_alarm(end, alarm_at=alarm_at)
        if range_start >= range_end:
            raise ValueError("Investigation start must be before end.")
        if range_end > alarm_at:
            raise ValueError(
                "Investigation end cannot be after the FDE alarm timestamp."
            )
        duration_days = (range_end - range_start).total_seconds() / 86_400
        if duration_days > self.config.max_investigation_days:
            raise ValueError(
                "Investigation window cannot exceed "
                f"{self.config.max_investigation_days} days."
            )
        return range_start, range_end

    def _parse_datetime_like_alarm(self, value: str, *, alarm_at: datetime) -> datetime:
        """Parse ISO-8601 input and align its timezone shape with the alarm."""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp: {value}") from exc

        if alarm_at.tzinfo is None:
            return parsed.replace(tzinfo=None)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=alarm_at.tzinfo)
        return parsed.astimezone(alarm_at.tzinfo)

    def _build_tool_window(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> pd.DataFrame:
        """Build a validated numeric telemetry window for deterministic tools."""
        frame = pd.DataFrame(data_object.get_temperature_history())
        if frame.empty:
            raise ValueError("Temperature history is empty.")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
        frame = frame.loc[
            (frame["timestamp"] >= range_start) & (frame["timestamp"] <= range_end),
            ["timestamp", "steam_temperature", "condensate_temperature"],
        ].copy()
        frame = frame.dropna(subset=["steam_temperature", "condensate_temperature"])
        if len(frame) < 3:
            raise ValueError(
                "Investigation window must contain at least three paired readings."
            )
        return frame.sort_values("timestamp").reset_index(drop=True)

    def _measure_window(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Calculate compact measurements that distinguish trend from modulation."""
        steam = frame["steam_temperature"].astype(float)
        condensate = frame["condensate_temperature"].astype(float)
        delta = steam - condensate
        normalized_delta = delta / steam.where(steam.abs() > 1e-9)
        edge_count = max(1, len(frame) // 5)

        first_steam = float(steam.iloc[:edge_count].median())
        last_steam = float(steam.iloc[-edge_count:].median())
        first_condensate = float(condensate.iloc[:edge_count].median())
        last_condensate = float(condensate.iloc[-edge_count:].median())
        first_delta = float(delta.iloc[:edge_count].median())
        last_delta = float(delta.iloc[-edge_count:].median())
        duration_days = max(
            (frame["timestamp"].iloc[-1] - frame["timestamp"].iloc[0]).total_seconds()
            / 86_400,
            1 / 48,
        )
        correlation = steam.corr(condensate)

        return {
            "window_start": frame["timestamp"].iloc[0].isoformat(),
            "window_end": frame["timestamp"].iloc[-1].isoformat(),
            "paired_readings": len(frame),
            "median_steam_c": round(float(steam.median()), 3),
            "median_condensate_c": round(float(condensate.median()), 3),
            "median_delta_c": round(float(delta.median()), 3),
            "median_normalized_delta": round(float(normalized_delta.median()), 5),
            "steam_change_c": round(last_steam - first_steam, 3),
            "condensate_change_c": round(last_condensate - first_condensate, 3),
            "delta_change_c": round(last_delta - first_delta, 3),
            "steam_trend_c_per_day": round(
                (last_steam - first_steam) / duration_days, 3
            ),
            "condensate_trend_c_per_day": round(
                (last_condensate - first_condensate) / duration_days, 3
            ),
            "delta_trend_c_per_day": round(
                (last_delta - first_delta) / duration_days, 3
            ),
            "delta_stddev_c": round(float(delta.std(ddof=0)), 3),
            "sensor_correlation": (
                round(float(correlation), 4) if pd.notna(correlation) else None
            ),
            "nonpositive_delta_fraction": round(float((delta <= 0).mean()), 4),
        }

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
        super()._attach_response(data_object, response)
