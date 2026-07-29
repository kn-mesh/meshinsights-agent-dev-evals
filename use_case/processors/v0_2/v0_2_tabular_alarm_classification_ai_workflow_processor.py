"""Text-first AI workflow for the alternate v0_2 Pulse agent lineage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from mi.ai import AIProcessorConfig, AIWorkflowMixin, UserMessage
from mi.core.processors import BaseProcessor
from mi.core.versioning import (
    VersionAssetDeclaration,
    VersionAssetRole,
    VersionContractDeclaration,
)

from use_case.objects.process_object import PulseFailureAnalysisProcessObject
from use_case.processors.common.structured_outputs import PulseFailureAnalysisResult


class V0_2TabularAlarmClassificationAIWorkflowProcessorConfig(AIProcessorConfig):
    """Configure the v0_2 text-and-table workflow."""

    name: str | None = "v0_2_tabular_alarm_classification_ai_workflow_processor"
    recent_aggregate_days: int = 30
    recent_aggregate_hours: int = 6
    alarm_detail_hours: int = 48
    timeout: float | None = 120
    transport_retries: int = 3
    output_retries: int | None = 0


class V0_2TabularAlarmClassificationAIWorkflowProcessor(
    AIWorkflowMixin[PulseFailureAnalysisProcessObject, PulseFailureAnalysisResult],
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Classify one alarm from deterministic numeric summaries and telemetry."""

    output_schema = PulseFailureAnalysisResult
    config: V0_2TabularAlarmClassificationAIWorkflowProcessorConfig

    @classmethod
    def version_assets(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionAssetDeclaration]:
        """Declare the embedded prompt and stable output contract."""
        _ = config
        return (
            VersionAssetDeclaration(
                role=VersionAssetRole.PROMPT,
                logical_name="v0_2_tabular_alarm_classification_system_prompt",
                symbol=f"{cls.__qualname__}._build_system_prompt",
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
        """Declare the alternative evidence projection used by this lineage."""
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.INPUT_SCHEMA,
                logical_name="v0_2_tabular_evidence_projection",
                value={
                    "decision_cutoff": "selected_alarm.detected_at",
                    "summary_periods_days_before_alarm": [
                        {"name": "historical", "start": 365, "end": 30},
                        {"name": "recent_baseline", "start": 30, "end": 7},
                        {"name": "lead_up", "start": 7, "end": 2},
                        {"name": "alarm_adjacent", "start": 2, "end": 0},
                    ],
                    "recent_aggregate_days": int(
                        config.get("recent_aggregate_days", 30)
                    ),
                    "recent_aggregate_hours": int(
                        config.get("recent_aggregate_hours", 6)
                    ),
                    "alarm_detail_hours": int(config.get("alarm_detail_hours", 48)),
                    "media": "csv_text",
                    "images": False,
                },
            ),
        )

    def __init__(
        self,
        config: V0_2TabularAlarmClassificationAIWorkflowProcessorConfig | None = None,
    ) -> None:
        """Initialize the v0_2 workflow with typed AI settings."""
        resolved_config = (
            config or V0_2TabularAlarmClassificationAIWorkflowProcessorConfig()
        )
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> str:
        """Build the compact numeric-evidence decision prompt."""
        _ = data_object
        return """
You review a rules-engine alarm for a steam trap. The rules engine is noisy, so
make an independent decision from the supplied numeric telemetry. Return the
required structured classification and root cause.

The two measurements are exterior pipe temperatures: steam/inlet and
condensate/outlet. Treat their absolute values as installation-specific. The
unit's own history is the reference.

Use this evidence order:
1. Establish the operating phase and the unit's historical relationship between
   steam, condensate, and steam-minus-condensate delta.
2. Compare the lead-up and alarm-adjacent periods with comparable historical
   operation. The alarm is only a review trigger; a sustained failure can start
   earlier and remain relevant at the alarm.
3. Prefer Healthy when both sides make a coherent process/load transition and
   settle with a stable positive relationship, or when the recent pattern fits a
   recurring historical pattern. A lower operating temperature alone is not a
   failure.
   Apply an unfinished-restart exception only when all three are visible: the
   relationship was normal immediately before shutdown, both sides then converged
   near ambient, and the cutoff occurs during a partial restart before both sides
   regain comparable on-state levels. Then prefer Healthy with Low confidence.
   Never apply this exception during uninterrupted elevated operation; sustained
   one-sided deterioration there remains Failure under the rules below.
4. Prefer Failure when a sustained, operating-state-adjusted relationship breaks:
   delta collapses or reverses, one side departs independently, or the new regime
   keeps degrading instead of stabilizing. Ignore isolated points.
   Judge "sustained" across the full recent trajectory, not only the final
   alarm-adjacent window. A late plateau does not restore health when one side
   has already moved persistently away from the unit's historical relationship
   and the relationship has not recovered. A positive remaining delta alone is
   not evidence of health.
   Analyze the onset before the endpoint. When steam first declines persistently
   while condensate remains near its operating baseline and the delta contracts,
   that supports Closed Failure; a later coupled cooldown does not erase the
   earlier one-sided departure.
5. For root cause, use direction of departure from each side's own baseline:
   condensate rising toward steam supports Open Failure; steam falling toward
   condensate supports Closed Failure. Use Unknown when failure is clear but the
   direction is not.

The period summary is coarse context, the 30-day series shows regime evolution,
and the 48-hour series has the most precise timing. Missing rows and long gaps
reduce confidence; summary statistics are evidence, not hard thresholds.

When the evidence remains genuinely ambiguous, choose Failure with Low
classification confidence because the result receives human review. Do not
force Open or Closed; use Unknown with Low confidence unless the direction is
clear. Healthy requires root cause N/A.

Explanations must cite concrete dates, temperatures, deltas, slopes, or patterns
from the supplied tables. Do not mention table names or hidden reasoning.
"""

    def _build_user_message(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> UserMessage:
        """Build the text-only evidence package for the model."""
        alarm_context = data_object.get_alarm_context()
        alarm_at = self._as_utc_timestamp(
            alarm_context["selected_alarm"]["detected_at"]
        )
        frame = self._build_temperature_frame(
            data_object.get_temperature_history(),
            alarm_at=alarm_at,
        )
        period_summary = self._build_period_summary(frame, alarm_at=alarm_at)
        recent_aggregate = self._build_recent_aggregate(frame, alarm_at=alarm_at)
        alarm_detail = self._build_alarm_detail(frame, alarm_at=alarm_at)

        return (
            UserMessage()
            .add_text(
                f"""
Alarm context:
- Steam trap type: {data_object.get_steam_trap_type() or "unknown"}
- FDE alarm timestamp: {alarm_at.isoformat()}
- Evidence is cut off at the alarm timestamp; there are no post-alarm rows.

Column guide:
- delta_c = steam_c - condensate_c.
- normalized_delta = delta_c / abs(steam_c), useful only for comparing operating
  levels within this unit.
- steam_slope_c_per_day, condensate_slope_c_per_day, and
  delta_slope_c_per_day summarize linear direction inside a period.
- coupled_correlation describes whether both temperatures moved together.
- gaps_over_2_5h counts likely connectivity gaps.
"""
            )
            .add_text("Period summary CSV (non-overlapping periods):")
            .add_dataframe(period_summary, string_format="csv")
            .add_text(
                f"Recent {self.config.recent_aggregate_days}-day CSV "
                f"({self.config.recent_aggregate_hours}-hour median bins):"
            )
            .add_dataframe(recent_aggregate, string_format="csv")
            .add_text(
                f"Alarm-adjacent CSV (raw points from the final "
                f"{self.config.alarm_detail_hours} hours):"
            )
            .add_dataframe(alarm_detail, string_format="csv")
        )

    def _build_temperature_frame(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        alarm_at: pd.Timestamp,
    ) -> pd.DataFrame:
        """Normalize history and enforce the decision-time cutoff."""
        frame = pd.DataFrame(temperature_history)
        required = {"timestamp", "steam_temperature", "condensate_temperature"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                "Temperature history is missing required columns: "
                + ", ".join(sorted(missing))
            )
        if frame.empty:
            raise ValueError("Temperature history is empty.")

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
            .reset_index(drop=True)
        )
        if frame[["steam_temperature", "condensate_temperature"]].dropna(
            how="all"
        ).empty:
            raise ValueError("Temperature history has no usable pre-alarm values.")

        frame["delta_c"] = (
            frame["steam_temperature"] - frame["condensate_temperature"]
        )
        denominator = frame["steam_temperature"].abs().clip(lower=1.0)
        frame["normalized_delta"] = frame["delta_c"] / denominator
        return frame

    def _build_period_summary(
        self, frame: pd.DataFrame, *, alarm_at: pd.Timestamp
    ) -> pd.DataFrame:
        """Summarize four non-overlapping decision-relative periods."""
        periods = (
            ("historical", 365, 30),
            ("recent_baseline", 30, 7),
            ("lead_up", 7, 2),
            ("alarm_adjacent", 2, 0),
        )
        rows = [
            self._summarize_period(
                frame,
                name=name,
                start=alarm_at - pd.Timedelta(days=start_days),
                end=alarm_at - pd.Timedelta(days=end_days),
                include_end=end_days == 0,
            )
            for name, start_days, end_days in periods
        ]
        return pd.DataFrame(rows)

    def _summarize_period(
        self,
        frame: pd.DataFrame,
        *,
        name: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        include_end: bool,
    ) -> dict[str, Any]:
        """Build one bounded numeric summary row."""
        end_mask = frame["timestamp"] <= end if include_end else frame["timestamp"] < end
        period = frame.loc[(frame["timestamp"] >= start) & end_mask].copy()
        paired = period.dropna(subset=["steam_temperature", "condensate_temperature"])
        if paired.empty:
            return {
                "period": name,
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "paired_points": 0,
                "gaps_over_2_5h": 0,
            }

        gaps = int(
            (paired["timestamp"].diff() > pd.Timedelta(hours=2.5)).sum()
        )
        return {
            "period": name,
            "start_utc": paired["timestamp"].iloc[0].isoformat(),
            "end_utc": paired["timestamp"].iloc[-1].isoformat(),
            "paired_points": int(len(paired)),
            "gaps_over_2_5h": gaps,
            "steam_median_c": self._rounded(paired["steam_temperature"].median()),
            "condensate_median_c": self._rounded(
                paired["condensate_temperature"].median()
            ),
            "delta_median_c": self._rounded(paired["delta_c"].median()),
            "delta_p10_c": self._rounded(paired["delta_c"].quantile(0.10)),
            "delta_p90_c": self._rounded(paired["delta_c"].quantile(0.90)),
            "delta_lte_zero_pct": self._rounded(
                100.0 * (paired["delta_c"] <= 0).mean()
            ),
            "normalized_delta_median": self._rounded(
                paired["normalized_delta"].median()
            ),
            "steam_slope_c_per_day": self._slope_per_day(
                paired, "steam_temperature"
            ),
            "condensate_slope_c_per_day": self._slope_per_day(
                paired, "condensate_temperature"
            ),
            "delta_slope_c_per_day": self._slope_per_day(paired, "delta_c"),
            "coupled_correlation": self._correlation(
                paired["steam_temperature"], paired["condensate_temperature"]
            ),
        }

    def _build_recent_aggregate(
        self, frame: pd.DataFrame, *, alarm_at: pd.Timestamp
    ) -> pd.DataFrame:
        """Return median bins for recent regime and trajectory review."""
        start = alarm_at - pd.Timedelta(days=self.config.recent_aggregate_days)
        recent = frame.loc[frame["timestamp"] >= start].copy()
        aggregate = (
            recent.set_index("timestamp")
            .loc[
                :,
                [
                    "steam_temperature",
                    "condensate_temperature",
                    "delta_c",
                    "normalized_delta",
                ],
            ]
            .resample(f"{self.config.recent_aggregate_hours}h")
            .median()
            .dropna(how="all")
            .reset_index()
            .rename(
                columns={
                    "timestamp": "bin_start_utc",
                    "steam_temperature": "steam_median_c",
                    "condensate_temperature": "condensate_median_c",
                    "delta_c": "delta_median_c",
                    "normalized_delta": "normalized_delta_median",
                }
            )
        )
        return self._format_table(aggregate)

    def _build_alarm_detail(
        self, frame: pd.DataFrame, *, alarm_at: pd.Timestamp
    ) -> pd.DataFrame:
        """Return raw alarm-adjacent points for precise transition timing."""
        start = alarm_at - pd.Timedelta(hours=self.config.alarm_detail_hours)
        detail = frame.loc[
            frame["timestamp"] >= start,
            [
                "timestamp",
                "steam_temperature",
                "condensate_temperature",
                "delta_c",
                "normalized_delta",
            ],
        ].rename(
            columns={
                "timestamp": "timestamp_utc",
                "steam_temperature": "steam_c",
                "condensate_temperature": "condensate_c",
            }
        )
        return self._format_table(detail.reset_index(drop=True))

    def _slope_per_day(self, frame: pd.DataFrame, column: str) -> float | None:
        """Calculate a simple least-squares slope against elapsed days."""
        valid = frame.dropna(subset=[column])
        if len(valid) < 2:
            return None
        elapsed_days = (
            valid["timestamp"] - valid["timestamp"].iloc[0]
        ).dt.total_seconds() / 86_400
        variance = elapsed_days.var()
        if pd.isna(variance) or variance == 0:
            return None
        return self._rounded(valid[column].cov(elapsed_days) / variance)

    def _format_table(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Round numeric columns and render timestamps consistently."""
        formatted = frame.copy()
        for column in formatted.columns:
            if pd.api.types.is_datetime64_any_dtype(formatted[column]):
                formatted[column] = formatted[column].map(
                    lambda value: value.isoformat() if not pd.isna(value) else ""
                )
            elif pd.api.types.is_numeric_dtype(formatted[column]):
                formatted[column] = formatted[column].round(3)
        return formatted

    def _as_utc_timestamp(self, value: Any) -> pd.Timestamp:
        """Normalize one alarm timestamp to UTC."""
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize("UTC")
        return timestamp.tz_convert("UTC")

    def _rounded(self, value: Any) -> float | None:
        """Return a compact finite scalar for CSV serialization."""
        if value is None or pd.isna(value):
            return None
        return round(float(value), 3)

    def _correlation(
        self, left: pd.Series[Any], right: pd.Series[Any]
    ) -> float | None:
        """Return correlation only when both signals vary."""
        paired = pd.concat([left, right], axis=1).dropna()
        if len(paired) < 2 or paired.iloc[:, 0].nunique() < 2:
            return None
        if paired.iloc[:, 1].nunique() < 2:
            return None
        return self._rounded(paired.iloc[:, 0].corr(paired.iloc[:, 1]))

    def _attach_response(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        response: PulseFailureAnalysisResult,
    ) -> None:
        """Store the structured decision under the stable pipeline key."""
        data_object.set_ai_result(response.model_dump())
        super()._attach_response(data_object, response)
