"""Progressively disclosed v2_0 agent for Pulse steam-trap alarm review."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd
from matplotlib import dates as mdates
from matplotlib import pyplot as plt

from mi.ai import (
    AIAgentMixin,
    AIProcessorConfig,
    AISkill,
    ImageContent,
    TextContent,
    UserMessage,
    ai_tool,
)
from mi.ai.tools import Tool
from mi.core.processors import BaseProcessor
from mi.core.versioning import (
    VersionAssetDeclaration,
    VersionAssetRole,
    VersionContractDeclaration,
)

from use_case.objects.process_object import PulseFailureAnalysisProcessObject
from use_case.processors.common.structured_outputs import PulseFailureAnalysisResult
from use_case.processors.v1_3.v1_3_alarm_classification_ai_workflow_processor import (
    V1_3AlarmClassificationAIWorkflowProcessor,
)


_SKILL_PATH = (
    Path(__file__).parent
    / "skills"
    / "complex-steam-trap-investigation"
    / "runtime-skill.md"
)
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class V2_0AlarmClassificationAgentConfig(AIProcessorConfig):
    """Configure the v2_0 progressively disclosed classification agent."""

    name: str | None = "v2_0_alarm_classification_agent"
    window_days_list: list[int] = [7, 30, 365]
    max_turns: int = 7
    timeout: float | None = 120
    tool_timeout: float | None = 30
    tool_calls_limit: int | None = 5
    finalize_on_tool_call_limit: bool = True
    transport_retries: int = 3
    tool_retries: int = 1
    output_retries: int | None = 0


class V2_0AlarmClassificationAgent(
    AIAgentMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Classify alarms directly, loading specialist evidence only when needed."""

    output_schema = PulseFailureAnalysisResult
    config: V2_0AlarmClassificationAgentConfig

    @classmethod
    def version_assets(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionAssetDeclaration]:
        """Declare the prompt, deferred skill, tools, and stable output schema."""
        _ = config
        return (
            VersionAssetDeclaration(
                role=VersionAssetRole.PROMPT,
                logical_name="v2_0_alarm_classification_system_prompt",
                symbol=f"{cls.__qualname__}._build_system_prompt",
            ),
            VersionAssetDeclaration(
                role=VersionAssetRole.PROMPT,
                logical_name="v1_3_baseline_decision_policy",
                path=("../v1_3/v1_3_alarm_classification_ai_workflow_processor.py"),
                symbol=(
                    "V1_3AlarmClassificationAIWorkflowProcessor._build_system_prompt"
                ),
                media_type="text/x-python",
            ),
            VersionAssetDeclaration(
                role=VersionAssetRole.SKILL,
                logical_name="complex_steam_trap_investigation",
                path=("skills/complex-steam-trap-investigation/runtime-skill.md"),
                media_type="text/markdown",
            ),
            VersionAssetDeclaration(
                role=VersionAssetRole.TOOL_DEFINITION,
                logical_name="v2_0_complex_investigation_tools",
                symbol=f"{cls.__qualname__}._build_complex_investigation_tools",
            ),
            VersionAssetDeclaration(
                role=VersionAssetRole.OUTPUT_SCHEMA,
                logical_name="pulse_failure_analysis_result",
                path="../common/structured_outputs.py",
                symbol="PulseFailureAnalysisResult",
                media_type="text/x-python",
            ),
        )

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        """Describe the eager evidence and deferred investigation surface."""
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.INPUT_SCHEMA,
                logical_name="v2_0_progressive_temperature_evidence",
                value={
                    "initial_chart_windows_days": list(
                        config.get("window_days_list", [7, 30, 365])
                    ),
                    "initial_chart_media": "image/png",
                    "deferred_skill": "complex-steam-trap-investigation",
                    "deferred_tools": [
                        "plot_raw_temperature_range",
                        "compare_temperature_ranges",
                    ],
                    "tool_decision_cutoff": "selected_alarm.detected_at",
                    "tool_plot_aggregation": "none",
                },
            ),
        )

    def __init__(
        self,
        config: V2_0AlarmClassificationAgentConfig | None = None,
    ) -> None:
        """Initialize the v2_0 agent with bounded turns and tool use."""
        resolved_config = config or V2_0AlarmClassificationAgentConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Extend the proven v1_3 policy with targeted runtime investigation."""
        v1_3_policy = V1_3AlarmClassificationAIWorkflowProcessor._build_system_prompt(
            self,  # pyright: ignore[reportArgumentType]
            data_object,
        )
        return (
            v1_3_policy
            + """

<v2_progressive_investigation>
The entire v1_3 decision framework above remains the default policy. Apply it
directly for straightforward cases; the specialist capability refines evidence
inspection and does not relax the framework's failure criteria.

A deferred capability named `complex-steam-trap-investigation` is available.
Load it only when the standard three-window review cannot resolve a material
question because the relevant transition is visually compressed, a connectivity
gap or restart hides the onset, a possible durable sensor reassignment needs a
targeted historical comparison, or Open-versus-Closed timing remains genuinely
indeterminate. Do not load it merely because a case contains a shutdown,
restart, lower regime, or low confidence, and do not load it for an obvious
stable healthy case or an obvious sustained directional failure.

Mandatory trigger: if you classify Failure and the first abnormal failed regime
appears during or immediately after a shutdown, restart, or connectivity
discontinuity, load the capability before assigning Open or Closed unless a
sustained one-sided departure is already plainly visible before that transition.
Warming from an Off-state is not a directional failure onset. If no sustained
one-sided failure evidence exists before the transition and the first abnormal
regime forms during restart, use Unknown even when condensate reaches its normal
On temperature before steam; unequal warmup order does not identify the failure
mechanism.

Range statistics measure magnitude but do not by themselves establish which
sensor moved first. Root-cause direction may be established from a consistent
trajectory across the supplied charts or targeted raw evidence; require a
defensible earliest sustained departure. A slow pre-transition convergence can
be directional when one sensor steadily departs its own baseline while the
other remains comparatively stable; later convergence, spikes, or a restart do
not erase that earlier evidence. If a post-restart abnormal regime appears
already formed or chaotic and neither directional onset is visible, use Unknown.
Do not turn mere uncertainty into Healthy: when the v1_3 framework finds a
sustained abnormal relationship but an alternative remains plausible, retain
Failure with Low confidence for human review.

At most five successful function-tool calls are available, including capability
loading. Once no function tools remain, immediately return the best structured
decision supported by the evidence already collected.
</v2_progressive_investigation>
"""
        )

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Build the standard three-window multimodal evidence package."""
        alarm_context = data_object.get_alarm_context()
        charts: dict[int, str] = {}
        for days in self.config.window_days_list:
            chart = data_object.get_temperature_chart(days)
            if chart is None:
                raise ValueError(
                    f"Required v2_0 combined pre-alarm chart for {days}-day window is missing."
                )
            charts[days] = chart

        sorted_windows = sorted(self.config.window_days_list, reverse=True)
        descriptions = "\n".join(
            self._build_image_description(index=index, days=days)
            for index, days in enumerate(sorted_windows, 1)
        )
        message = UserMessage().add_text(
            f"""
<alarm_context>
Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
FDE alarm cutoff: {alarm_context["selected_alarm"]["detected_at"].isoformat()}
</alarm_context>

<images>
{descriptions}
</images>

The far-right pre-alarm point is the decision cutoff. Begin with the annual
baseline, then use 30 days for regime evolution and 7 days for precise recent
timing. Compare each raw panel with its delta panel.
"""
        )
        for days in sorted_windows:
            message.add_image(charts[days], media_type="image/png")
        return message

    def _build_skills(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> Sequence[AISkill]:
        """Expose the complex investigation as a deferred Agent Skill."""
        return [
            AISkill.from_path(
                _SKILL_PATH,
                tools=self._build_complex_investigation_tools(data_object),
            )
        ]

    def _build_complex_investigation_tools(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> list[Tool]:
        """Build raw plotting and numeric comparison tools for this example."""
        frame, alarm_at = self._build_tool_frame(data_object)

        @ai_tool(name="plot_raw_temperature_range", timeout=30)
        def plot_raw_temperature_range(
            start_date: str,
            end_date: str,
        ) -> list[TextContent | ImageContent]:
            """Plot unaggregated steam and condensate readings for an inclusive date range at or before the alarm cutoff. Use ISO dates or timestamps."""
            try:
                selected = self._select_tool_range(
                    frame,
                    start_date=start_date,
                    end_date=end_date,
                )
            except ValueError as exc:
                return [
                    TextContent(
                        text=(
                            f"Unable to plot the requested range: {exc} "
                            "Choose a range within the available cutoff-bounded evidence."
                        )
                    )
                ]
            image = self._render_raw_range(selected)
            return [
                TextContent(
                    text=(
                        f"Raw unaggregated range: {selected['timestamp'].iloc[0].isoformat()} "
                        f"through {selected['timestamp'].iloc[-1].isoformat()}, "
                        f"{len(selected)} rows; evidence cutoff "
                        f"{alarm_at.isoformat()}."
                    )
                ),
                ImageContent.from_bytes(image, media_type="image/png"),
            ]

        @ai_tool(name="compare_temperature_ranges")
        def compare_temperature_ranges(
            reference_start_date: str,
            reference_end_date: str,
            focus_start_date: str,
            focus_end_date: str,
        ) -> str:
            """Compare exact raw telemetry statistics for a historical reference range and a focus range at or before the alarm cutoff."""
            try:
                reference = self._select_tool_range(
                    frame,
                    start_date=reference_start_date,
                    end_date=reference_end_date,
                )
                focus = self._select_tool_range(
                    frame,
                    start_date=focus_start_date,
                    end_date=focus_end_date,
                )
            except ValueError as exc:
                return json.dumps(
                    {
                        "error": str(exc),
                        "available_start_utc": frame["timestamp"].iloc[0].isoformat(),
                        "available_end_utc": frame["timestamp"].iloc[-1].isoformat(),
                        "instruction": (
                            "Choose two valid ranges within the available "
                            "cutoff-bounded evidence."
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            payload = {
                "evidence_cutoff_utc": alarm_at.isoformat(),
                "reference": self._summarize_tool_range(reference),
                "focus": self._summarize_tool_range(focus),
                "interpretation_guardrail": (
                    "These are descriptive measurements, not classification thresholds. "
                    "Compare operating phases before interpreting differences. "
                    "A difference between reference and focus medians does not establish "
                    "which sensor moved first; root-cause direction requires a visible "
                    "continuous one-sided onset in raw telemetry."
                ),
            }
            return json.dumps(payload, indent=2, sort_keys=True)

        return [plot_raw_temperature_range, compare_temperature_ranges]

    def _build_tool_frame(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> tuple[pd.DataFrame, pd.Timestamp]:
        """Normalize raw history and enforce the alarm-time evidence cutoff."""
        frame = pd.DataFrame(data_object.get_temperature_history())
        required = {"timestamp", "steam_temperature", "condensate_temperature"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                "Temperature history is missing required columns: "
                + ", ".join(sorted(missing))
            )
        alarm_at = self._as_utc_timestamp(
            data_object.get_alarm_context()["selected_alarm"]["detected_at"]
        )
        frame = frame.loc[:, sorted(required)].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["steam_temperature"] = pd.to_numeric(
            frame["steam_temperature"], errors="coerce"
        )
        frame["condensate_temperature"] = pd.to_numeric(
            frame["condensate_temperature"], errors="coerce"
        )
        frame = (
            frame.loc[frame["timestamp"] <= alarm_at]
            .sort_values("timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .dropna(
                subset=["steam_temperature", "condensate_temperature"],
                how="all",
            )
            .reset_index(drop=True)
        )
        if frame.empty:
            raise ValueError("Temperature history has no usable pre-alarm values.")
        frame["delta_c"] = frame["steam_temperature"] - frame["condensate_temperature"]
        return frame, alarm_at

    def _select_tool_range(
        self,
        frame: pd.DataFrame,
        *,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Select a validated inclusive range, normalizing reversed bounds."""
        start = self._parse_tool_timestamp(start_date, field_name="start_date")
        end = self._parse_tool_timestamp(end_date, field_name="end_date")
        start_is_date = bool(_DATE_ONLY.fullmatch(start_date.strip()))
        end_is_date = bool(_DATE_ONLY.fullmatch(end_date.strip()))
        if end < start:
            start, end = end, start
            start_is_date, end_is_date = end_is_date, start_is_date
        if end_is_date:
            end_exclusive = end + pd.Timedelta(days=1)
            mask = (frame["timestamp"] >= start) & (frame["timestamp"] < end_exclusive)
        else:
            mask = (frame["timestamp"] >= start) & (frame["timestamp"] <= end)
        selected = frame.loc[mask].copy()
        if len(selected) < 2:
            available_start = frame["timestamp"].iloc[0].isoformat()
            available_end = frame["timestamp"].iloc[-1].isoformat()
            raise ValueError(
                "The requested range needs at least two usable readings. "
                f"Available evidence spans {available_start} through {available_end}."
            )
        return selected

    def _render_raw_range(self, frame: pd.DataFrame) -> bytes:
        """Render unaggregated steam-versus-condensate observations."""
        plotted = self._insert_gap_break_rows(frame)
        figure, axis = plt.subplots(figsize=(12.5, 5.5))
        axis.plot(
            plotted["timestamp"],
            plotted["steam_temperature"],
            color="#d62728",
            linewidth=1.25,
            label="Steam / inlet",
        )
        axis.plot(
            plotted["timestamp"],
            plotted["condensate_temperature"],
            color="#1f77b4",
            linewidth=1.25,
            label="Condensate / outlet",
        )
        axis.set_title(
            "Raw steam vs condensate temperatures\n"
            f"{frame['timestamp'].iloc[0].isoformat()} to "
            f"{frame['timestamp'].iloc[-1].isoformat()}"
        )
        axis.set_ylabel("Temperature, Celsius")
        axis.set_xlabel("Timestamp")
        axis.grid(alpha=0.22)
        axis.legend(loc="best")
        locator = mdates.AutoDateLocator(minticks=4, maxticks=10)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        figure.tight_layout()
        buffer = BytesIO()
        figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        plt.close(figure)
        return buffer.getvalue()

    def _insert_gap_break_rows(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Break plotted lines when telemetry is absent for over 2.5 hours."""
        plotted = frame.loc[
            :,
            ["timestamp", "steam_temperature", "condensate_temperature"],
        ].copy()
        gap_indexes = plotted.index[
            plotted["timestamp"].diff() > pd.Timedelta(hours=2.5)
        ]
        if gap_indexes.empty:
            return plotted
        break_rows: list[dict[str, Any]] = []
        for index in gap_indexes:
            timestamp_value: Any = plotted.loc[index - 1, "timestamp"]
            break_rows.append(
                {
                    "timestamp": pd.Timestamp(timestamp_value)
                    + pd.Timedelta(seconds=1),
                    "steam_temperature": float("nan"),
                    "condensate_temperature": float("nan"),
                }
            )
        return (
            pd.concat([plotted, pd.DataFrame(break_rows)], ignore_index=True)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def _summarize_tool_range(self, frame: pd.DataFrame) -> dict[str, Any]:
        """Return robust range statistics plus first/last-quintile movement."""
        paired = frame.dropna(
            subset=["steam_temperature", "condensate_temperature"]
        ).copy()
        quintile_size = max(1, len(paired) // 5)
        first = paired.head(quintile_size)
        last = paired.tail(quintile_size)

        def rounded(value: Any) -> float | None:
            return None if pd.isna(value) else round(float(value), 3)

        return {
            "start_utc": paired["timestamp"].iloc[0].isoformat(),
            "end_utc": paired["timestamp"].iloc[-1].isoformat(),
            "paired_points": int(len(paired)),
            "gaps_over_2_5h": int(
                (paired["timestamp"].diff() > pd.Timedelta(hours=2.5)).sum()
            ),
            "steam_median_c": rounded(paired["steam_temperature"].median()),
            "condensate_median_c": rounded(paired["condensate_temperature"].median()),
            "delta_median_c": rounded(paired["delta_c"].median()),
            "delta_p10_c": rounded(paired["delta_c"].quantile(0.10)),
            "delta_p90_c": rounded(paired["delta_c"].quantile(0.90)),
            "delta_lte_zero_pct": rounded(100.0 * (paired["delta_c"] <= 0).mean()),
            "steam_first_to_last_quintile_change_c": rounded(
                last["steam_temperature"].median() - first["steam_temperature"].median()
            ),
            "condensate_first_to_last_quintile_change_c": rounded(
                last["condensate_temperature"].median()
                - first["condensate_temperature"].median()
            ),
            "delta_first_to_last_quintile_change_c": rounded(
                last["delta_c"].median() - first["delta_c"].median()
            ),
            "steam_condensate_correlation": rounded(
                paired["steam_temperature"].corr(paired["condensate_temperature"])
            ),
        }

    def _parse_tool_timestamp(self, value: str, *, field_name: str) -> pd.Timestamp:
        """Parse one tool timestamp and normalize it to UTC."""
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an ISO date or timestamp.") from exc
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _as_utc_timestamp(self, value: Any) -> pd.Timestamp:
        """Normalize a decision timestamp to UTC."""
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _build_image_description(self, *, index: int, days: int) -> str:
        """Describe one standard chart without repeating the full runbook."""
        if days == 365:
            return (
                f"Image {index}: {days}-day baseline split into four chronological "
                "segments. Each segment has raw temperatures above and raw plus "
                "4-hour rolling delta below; read left to right."
            )
        return (
            f"Image {index}: continuous {days}-day view with raw steam and "
            "condensate above and raw plus 4-hour rolling delta below."
        )

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Store the structured decision under the stable pipeline artifact."""
        data_object.set_ai_result(response.model_dump())
        super()._attach_response(data_object, response)
