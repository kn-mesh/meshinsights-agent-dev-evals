"""Reusable deterministic analysis for bounded temperature windows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class TemperatureWindowSummary(BaseModel):
    """Compact measurements for comparing the start and end of one interval."""

    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime
    paired_readings: int = Field(ge=3)
    start_steam_median_c: float
    end_steam_median_c: float
    start_condensate_median_c: float
    end_condensate_median_c: float
    start_delta_median_c: float
    end_delta_median_c: float
    delta_change_c: float
    median_normalized_delta: float
    same_direction_movement_fraction: float | None = Field(default=None, ge=0, le=1)
    nonpositive_delta_fraction: float = Field(ge=0, le=1)


class TemperatureWindowAnalyzer:
    """Validate, select, and summarize model-requested telemetry intervals."""

    def __init__(self, *, max_window_days: int) -> None:
        if max_window_days < 1:
            raise ValueError("max_window_days must be at least one day.")
        self.max_window_days = max_window_days

    def resolve_range(
        self,
        *,
        start: str,
        end: str,
        alarm_at: datetime,
    ) -> tuple[datetime, datetime]:
        """Parse an ISO-8601 interval and enforce the investigation boundary."""
        range_start = self._parse_datetime_like_alarm(start, alarm_at=alarm_at)
        range_end = self._parse_datetime_like_alarm(end, alarm_at=alarm_at)
        if range_start >= range_end:
            raise ValueError("Investigation start must be before end.")
        if range_end > alarm_at:
            raise ValueError(
                "Investigation end cannot be after the FDE alarm timestamp."
            )
        duration_days = (range_end - range_start).total_seconds() / 86_400
        if duration_days > self.max_window_days:
            raise ValueError(
                f"Investigation window cannot exceed {self.max_window_days} days."
            )
        return range_start, range_end

    def summarize(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> TemperatureWindowSummary:
        """Return robust edge medians and compact relationship measurements."""
        frame = self._select_window(
            temperature_history,
            range_start=range_start,
            range_end=range_end,
        )
        steam = frame["steam_temperature"].astype(float)
        condensate = frame["condensate_temperature"].astype(float)
        delta = steam - condensate
        normalized_delta = delta / steam.where(steam.abs() > 1e-9)
        edge_count = max(1, len(frame) // 5)

        start_steam = float(steam.iloc[:edge_count].median())
        end_steam = float(steam.iloc[-edge_count:].median())
        start_condensate = float(condensate.iloc[:edge_count].median())
        end_condensate = float(condensate.iloc[-edge_count:].median())
        start_delta = float(delta.iloc[:edge_count].median())
        end_delta = float(delta.iloc[-edge_count:].median())
        steam_movement = steam.diff().dropna()
        condensate_movement = condensate.diff().dropna()
        active_movement = (steam_movement.abs() > 1e-9) | (
            condensate_movement.abs() > 1e-9
        )
        same_direction_fraction = (
            float(
                (
                    steam_movement.loc[active_movement]
                    * condensate_movement.loc[active_movement]
                    > 0
                ).mean()
            )
            if active_movement.any()
            else None
        )

        return TemperatureWindowSummary(
            window_start=frame["timestamp"].iloc[0].to_pydatetime(),
            window_end=frame["timestamp"].iloc[-1].to_pydatetime(),
            paired_readings=len(frame),
            start_steam_median_c=round(start_steam, 3),
            end_steam_median_c=round(end_steam, 3),
            start_condensate_median_c=round(start_condensate, 3),
            end_condensate_median_c=round(end_condensate, 3),
            start_delta_median_c=round(start_delta, 3),
            end_delta_median_c=round(end_delta, 3),
            delta_change_c=round(end_delta - start_delta, 3),
            median_normalized_delta=round(float(normalized_delta.median()), 5),
            same_direction_movement_fraction=(
                round(same_direction_fraction, 4)
                if same_direction_fraction is not None
                else None
            ),
            nonpositive_delta_fraction=round(float((delta <= 0).mean()), 4),
        )

    def _select_window(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> pd.DataFrame:
        """Build one sorted interval containing usable paired readings."""
        frame = pd.DataFrame(temperature_history)
        if frame.empty:
            raise ValueError("Temperature history is empty.")
        required = {"timestamp", "steam_temperature", "condensate_temperature"}
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(
                "Temperature history is missing required columns: "
                + ", ".join(sorted(missing))
            )

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
