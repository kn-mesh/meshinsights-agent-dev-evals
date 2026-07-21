"""First-pass orientation workflow for the progressive Pulse v2 pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mi.ai import AIProcessorConfig, AIWorkflowMixin, UserMessage
from mi.core.processors import BaseProcessor
from mi.core.versioning import VersionAssetDeclaration, VersionAssetRole

from src.objects.process_object import PulseFailureAnalysisProcessObject
from src.processors.v2.structured_outputs import V2InvestigationCaseBrief


class V2CaseBriefAIWorkflowProcessorConfig(AIProcessorConfig):
    """Configure the lightweight v2 orientation call."""

    name: str | None = "v2_case_brief_ai_workflow_processor"
    window_days_list: list[int] = [30, 365]
    timeout: float | None = 120
    transport_retries: int = 3
    output_retries: int | None = 1


class V2CaseBriefAIWorkflowProcessor(
    AIWorkflowMixin[PulseFailureAnalysisProcessObject, V2InvestigationCaseBrief],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Establish baseline, current regime, and uncertainty before diagnosis."""

    output_schema = V2InvestigationCaseBrief
    config: V2CaseBriefAIWorkflowProcessorConfig

    @classmethod
    def version_assets(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionAssetDeclaration]:
        """Declare the orientation prompt and structured handoff schema."""
        _ = config
        return (
            VersionAssetDeclaration(
                role=VersionAssetRole.PROMPT,
                logical_name="v2_case_brief_system_prompt",
                symbol=f"{cls.__qualname__}._build_system_prompt",
            ),
            VersionAssetDeclaration(
                role=VersionAssetRole.OUTPUT_SCHEMA,
                logical_name="v2_investigation_case_brief",
                path="structured_outputs.py",
                symbol="V2InvestigationCaseBrief",
                media_type="text/x-python",
            ),
        )

    def __init__(
        self, config: V2CaseBriefAIWorkflowProcessorConfig | None = None
    ) -> None:
        """Initialize the orientation workflow."""
        resolved_config = config or V2CaseBriefAIWorkflowProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build the intentionally narrow first-pass task."""
        _ = data_object
        return f"""
You are the orientation analyst for a steam-trap alarm investigation.
Two exterior pipe sensors measure steam/inlet and condensate/outlet temperature;
their difference is Steam minus Condensate. The FDE alarm is only a review trigger.

Use the supplied overview charts to establish this unit's own historical operating
baseline and describe the most meaningful regime around the alarm. Identify a
leading explanation, its strongest alternative, and the one uncertainty that a
focused investigation should resolve. Record the most useful current and
historical date intervals for follow-up charts. Do not make the final
Healthy/Failure or root-cause decision. Return only the structured case brief.
You receive {len(self.config.window_days_list)} overview charts.
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Attach only the historical and recent orientation views."""
        alarm_context = data_object.get_alarm_context()
        message = UserMessage().add_text(
            f"""
Unit: {alarm_context.get("unit", alarm_context.get("sensor_id", "unknown"))}
Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
FDE alarm timestamp: {alarm_context["selected_alarm"]["detected_at"].isoformat()}

Image 1 is the 365-day historical overview, segmented chronologically from left
to right. Image 2 is the continuous 30-day alarm-adjacent view. In both images,
red is Steam, blue is Condensate, and purple is Steam-minus-Condensate delta.
"""
        )
        for days in sorted(self.config.window_days_list, reverse=True):
            chart = data_object.get_temperature_chart(days)
            if chart is None:
                raise ValueError(
                    f"Required v2 orientation chart for {days} days is missing."
                )
            message.add_image(chart, media_type="image/png")
        return message

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: V2InvestigationCaseBrief,
    ) -> None:
        """Persist the inspectable handoff consumed by the specialist agent."""
        data_object.set_investigation_case_brief(response.model_dump())
