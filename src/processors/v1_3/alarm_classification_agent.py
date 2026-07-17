"""Capability- and skill-enabled Pulse v1_3 classification agent."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

from mi.ai import (
    AIAgentMixin,
    AICapability,
    AIProcessorConfig,
    AISkill,
    ContentBlock,
    ImageContent,
    TextContent,
    ToolSet,
    UserMessage,
    ai_tool,
)
from mi.core.processors import BaseProcessor

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.common.structured_outputs import PulseFailureAnalysisResult
from src.processors.v1_3.temperature_evidence_processor import (
    V1_3TemperatureEvidenceProcessor,
    V1_3TemperatureEvidenceProcessorConfig,
)

_SKILL_PATH = Path(__file__).parent / "skills" / "steam-trap-failure-diagnosis"


class V1_3AlarmClassificationAgentConfig(AIProcessorConfig):
    """Configure the adaptive v1_3 classification agent."""

    name: str | None = "v1_3_alarm_classification_agent"
    window_days_list: list[int] = [7, 30, 365]
    max_turns: int = 10
    timeout: float | None = 300
    tool_timeout: float | None = 45


class V1_3AlarmClassificationAgent(
    AIAgentMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Classify one Pulse alarm using charts and selectively loaded expertise."""

    output_schema = PulseFailureAnalysisResult
    config: V1_3AlarmClassificationAgentConfig

    def __init__(
        self, config: V1_3AlarmClassificationAgentConfig | None = None
    ) -> None:
        """Initialize the agent with unlimited token limits by default."""
        resolved = config or V1_3AlarmClassificationAgentConfig()
        super().__init__(resolved)
        self.config = resolved

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build the always-on task, safety, and output instructions."""
        trap_type = data_object.get_steam_trap_type() or "unknown"
        return f"""
You are a connected-system decision agent reviewing an unconfirmed steam-trap Failure Detection Engine alarm. The trap type is {trap_type}.

Decide whether the installation is Healthy or Failure at the alarm decision point. For failures, determine Open Failure, Closed Failure, or Unknown. Healthy requires root cause N/A.

Use only the supplied historical evidence and bounded evidence tools. Do not infer acoustic evidence, repair history, or post-decision outcomes. Start with the long-term baseline and compare the alarm-adjacent behavior to comparable operating states. Load the `steam-trap-failure-diagnosis` skill before finalizing the decision. Load `sensor-integrity-review` only if a durable sensor-label reversal or instrumentation change may materially affect the decision.

Return only the structured output. Explanations must cite concrete dates, temperature relationships, delta behavior, or recurring patterns rather than chart numbers.
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Attach v1_3 evidence from broadest to narrowest time window."""
        context = data_object.get_alarm_context()
        message = UserMessage().add_text(
            f"""Analyze Pulse unit {context["unit"]} (sensor {context["sensor_id"]}).
Decision timestamp: {context["decision_timestamp"].isoformat()}
FDE alarm timestamp: {context["selected_alarm"]["detected_at"].isoformat()}
Steam-trap type: {data_object.get_steam_trap_type() or "unknown"}

The following charts contain raw steam/inlet and condensate/outlet temperatures plus their four-hour rolling delta. The 365-day chart is segmented into four contiguous periods to preserve raw evidence. Review 365 days first, then 30 days, then 7 days. Each default chart can include at most the first telemetry point after the alarm for line continuity; do not treat that point as an outcome.
"""
        )
        for window_days in sorted(self.config.window_days_list, reverse=True):
            chart = data_object.get_temperature_chart(window_days)
            if chart is None:
                raise ValueError(
                    f"Required {window_days}-day evidence chart is missing."
                )
            message.add_text(f"{window_days}-day evidence chart:").add_image(
                chart, media_type="image/png"
            )
        return message

    def _build_toolsets(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[ToolSet]:
        """Build the eager evidence-inspection toolset."""
        renderer = V1_3TemperatureEvidenceProcessor(
            V1_3TemperatureEvidenceProcessorConfig()
        )
        alarm_at = self._normalized_datetime(
            data_object.get_alarm_context()["selected_alarm"]["detected_at"]
        )
        zoom_call_count = 0

        @ai_tool(
            name="summarize_temperature_range",
            description="Return deterministic min, median, max, and delta statistics for a bounded YYYY-MM-DD range ending no later than the alarm.",
        )
        def summarize_temperature_range(start_date: str, end_date: str) -> str:
            """Summarize a bounded telemetry interval."""
            range_start, range_end = self._parse_tool_range(
                start_date, end_date, alarm_at
            )
            summary = renderer.summarize_range(
                data_object.get_temperature_history(),
                range_start=range_start,
                range_end=range_end,
            )
            return json.dumps(summary, sort_keys=True)

        @ai_tool(
            name="render_temperature_zoom",
            description="Render at most two targeted raw-temperature and delta zooms for a YYYY-MM-DD range selected from the provided evidence.",
        )
        def render_temperature_zoom(
            start_date: str,
            end_date: str,
            purpose: Literal["recent_alarm_review", "historical_comparison"],
        ) -> list[ContentBlock]:
            """Render one bounded evidence zoom as text and image content."""
            nonlocal zoom_call_count
            if zoom_call_count >= 2:
                raise ValueError("At most two targeted temperature zooms are allowed.")
            range_start, range_end = self._parse_tool_range(
                start_date, end_date, alarm_at
            )
            image = renderer.render_custom_chart(
                data_object.get_temperature_history(),
                range_start=range_start,
                range_end=range_end,
                alarm_detected_at=alarm_at,
            )
            zoom_call_count += 1
            return [
                TextContent(
                    text=f"{purpose} evidence from {range_start.isoformat()} through {range_end.isoformat()}."
                ),
                ImageContent.from_bytes(image),
            ]

        return [
            ToolSet.builder()
            .add(summarize_temperature_range)
            .add(render_temperature_zoom)
            .with_id("temperature-evidence-inspection")
            .with_instructions(
                "Use numeric summaries to verify chart interpretations. Render no more than two non-overlapping, hypothesis-driven zooms."
            )
            .build()
        ]

    def _build_capabilities(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[AICapability]:
        """Build a deferred specialist capability for suspected label problems."""

        @ai_tool(
            name="summarize_sensor_relationship",
            description="Compare early and recent sensor relationships to test for a durable label reversal or an evolving failure pattern.",
        )
        def summarize_sensor_relationship() -> str:
            """Return early-versus-recent delta evidence without classifying it."""
            frame = pd.DataFrame(data_object.get_temperature_history())
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
            frame["delta"] = pd.to_numeric(
                frame["steam_temperature"], errors="coerce"
            ) - pd.to_numeric(frame["condensate_temperature"], errors="coerce")
            frame = frame.dropna(subset=["delta"]).sort_values("timestamp")
            if frame.empty:
                raise ValueError(
                    "Temperature history has no usable sensor relationship."
                )
            split = max(len(frame) // 4, 1)
            early_negative = frame.head(split)["delta"] < 0
            recent_negative = frame.tail(split)["delta"] < 0
            return json.dumps(
                {
                    "evidence_start": frame.iloc[0]["timestamp"].isoformat(),
                    "evidence_end": frame.iloc[-1]["timestamp"].isoformat(),
                    "early_delta_median": round(
                        float(frame.head(split)["delta"].median()), 2
                    ),
                    "early_negative_fraction": round(
                        sum(bool(value) for value in early_negative.tolist())
                        / len(early_negative),
                        3,
                    ),
                    "recent_delta_median": round(
                        float(frame.tail(split)["delta"].median()), 2
                    ),
                    "recent_negative_fraction": round(
                        sum(bool(value) for value in recent_negative.tolist())
                        / len(recent_negative),
                        3,
                    ),
                },
                sort_keys=True,
            )

        return [
            AICapability(
                id="sensor-integrity-review",
                description="Use only when suspected flipped labels, sensor movement, or an instrumentation discontinuity could change the health decision.",
                instructions=(
                    "Treat labels as flipped only for a long-standing reversal from the beginning of evidence or after a clear instrumentation discontinuity. "
                    "A relationship that evolves from normal to reversed supports failure instead."
                ),
                tools=[summarize_sensor_relationship],
                defer_loading=True,
            )
        ]

    def _build_skills(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[AISkill]:
        """Load the deferred domain diagnostic runbook."""
        _ = data_object
        return [AISkill.from_path(_SKILL_PATH)]

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Attach the stable agent artifact required by hydrators and evals."""
        data_object.set_ai_result(response.model_dump(mode="json"))

    def _parse_tool_range(
        self, start_value: str, end_value: str, alarm_at: datetime
    ) -> tuple[datetime, datetime]:
        """Validate and normalize one tool-selected inclusive date range."""
        try:
            start = date.fromisoformat(start_value.strip())
            end = date.fromisoformat(end_value.strip())
        except (AttributeError, ValueError) as error:
            raise ValueError("Tool dates must use YYYY-MM-DD format.") from error
        alarm_date = alarm_at.date()
        end = min(end, alarm_date)
        if start > end:
            raise ValueError("start_date must be on or before end_date.")
        range_start = datetime.combine(start, time.min)
        range_end = alarm_at if end == alarm_date else datetime.combine(end, time.max)
        return range_start, range_end

    def _normalized_datetime(self, value: datetime) -> datetime:
        """Normalize an aware datetime into naive UTC for local telemetry comparisons."""
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
