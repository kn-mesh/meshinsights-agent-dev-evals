"""Shared compute processor for three-window combined temperature analysis charts."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any

import matplotlib
import pandas as pd

matplotlib.use("Agg")

from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.axes import Axes

from mi.core.processors import BaseProcessor, BaseProcessorConfig

from src.objects.process_object import PulseFailureAnalysisProcessObject


class TemperatureGraphsThreeIntervalsProcessorConfig(BaseProcessorConfig):
    """Configure the shared three-window combined temperature chart processor."""

    name: str | None = "temperature_graphs_three_intervals_processor"
    window_days_list: list[int] = [7, 30, 365]
    image_format: str = "png"
    dpi: int = 160


class TemperatureGraphsThreeIntervalsProcessor(
    BaseProcessor[PulseFailureAnalysisProcessObject]
):
    """Render combined raw-plus-delta charts for default windows and agent zooms."""

    config: TemperatureGraphsThreeIntervalsProcessorConfig

    def __init__(
        self, config: TemperatureGraphsThreeIntervalsProcessorConfig | None = None
    ) -> None:
        """Initialize the shared chart processor with typed rendering settings."""
        resolved_config = config or TemperatureGraphsThreeIntervalsProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def process(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        *,
        metadata: Any = None,
    ) -> None:
        """Render one combined raw-plus-delta chart for each configured window."""
        _ = metadata

        temperature_frame = self._build_temperature_frame(
            data_object.get_temperature_history()
        )
        alarm_detected_at = data_object.get_alarm_context()["selected_alarm"][
            "detected_at"
        ]

        for window_days in self.config.window_days_list:
            window_frame = self._build_analysis_window(
                temperature_frame,
                alarm_detected_at=alarm_detected_at,
                window_days=window_days,
            )
            chart_bytes = self._render_combined_chart(
                window_frame,
                temperature_chart_title=self._build_window_temperature_chart_title(
                    window_days
                ),
                delta_chart_title=self._build_window_delta_chart_title(window_days),
                window_days=window_days,
            )
            data_object.set_temperature_chart(
                window_days, base64.b64encode(chart_bytes).decode("ascii")
            )

    def render_custom_combined_chart(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        range_start: datetime,
        range_end: datetime,
        alarm_detected_at: datetime,
    ) -> bytes:
        """Render one combined raw-plus-delta chart over a caller-provided range."""
        if range_start > range_end:
            raise ValueError("Custom temperature chart start must be before the end.")
        if range_end > alarm_detected_at:
            raise ValueError(
                "Custom temperature chart end cannot be after the FDE alarm timestamp."
            )

        temperature_frame = self._build_temperature_frame(temperature_history)
        window_frame = self._build_custom_analysis_window(
            temperature_frame,
            range_start=range_start,
            range_end=range_end,
            alarm_detected_at=alarm_detected_at,
        )
        return self._render_combined_chart(
            window_frame,
            temperature_chart_title=self._build_custom_temperature_chart_title(
                range_start=range_start,
                range_end=range_end,
                include_post_alarm_point=range_end == alarm_detected_at,
            ),
            delta_chart_title="Steam - Condensate Delta (4h avg)",
        )

    def _build_temperature_frame(
        self, temperature_history: list[dict[str, Any]]
    ) -> pd.DataFrame:
        """Convert retrieved temperature history into a sorted dataframe."""
        frame = pd.DataFrame(temperature_history)
        if frame.empty:
            raise ValueError("Temperature history is empty.")

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        return frame

    def _build_analysis_window(
        self,
        temperature_frame: pd.DataFrame,
        *,
        alarm_detected_at: datetime,
        window_days: int,
    ) -> pd.DataFrame:
        """Return one default pre-alarm window plus the first post-alarm point."""
        window_start = alarm_detected_at - timedelta(days=window_days)
        requested_frame = temperature_frame.loc[
            (temperature_frame["timestamp"] >= window_start)
            & (temperature_frame["timestamp"] <= alarm_detected_at),
            ["timestamp", "steam_temperature", "condensate_temperature"],
        ].copy()
        window_frame = self._append_first_post_alarm_frame(
            requested_frame,
            temperature_frame=temperature_frame,
            alarm_detected_at=alarm_detected_at,
            include_post_alarm_point=True,
        )
        self._validate_temperature_window(
            window_frame,
            window_label=f"{window_days}-day pre-alarm window",
        )
        return self._insert_gap_break_rows(window_frame)

    def _build_custom_analysis_window(
        self,
        temperature_frame: pd.DataFrame,
        *,
        range_start: datetime,
        range_end: datetime,
        alarm_detected_at: datetime,
    ) -> pd.DataFrame:
        """Return one caller-selected analysis window for agent-generated charts."""
        requested_frame = temperature_frame.loc[
            (temperature_frame["timestamp"] >= range_start)
            & (temperature_frame["timestamp"] <= range_end),
            ["timestamp", "steam_temperature", "condensate_temperature"],
        ].copy()
        window_frame = self._append_first_post_alarm_frame(
            requested_frame,
            temperature_frame=temperature_frame,
            alarm_detected_at=alarm_detected_at,
            include_post_alarm_point=range_end == alarm_detected_at,
        )
        self._validate_temperature_window(
            window_frame,
            window_label="requested analysis window",
        )
        return self._insert_gap_break_rows(window_frame)

    def _append_first_post_alarm_frame(
        self,
        requested_frame: pd.DataFrame,
        *,
        temperature_frame: pd.DataFrame,
        alarm_detected_at: datetime,
        include_post_alarm_point: bool,
    ) -> pd.DataFrame:
        """Append the first post-alarm row when the caller requests it."""
        frames_to_concat = [requested_frame]
        if include_post_alarm_point:
            first_post_alarm_frame = temperature_frame.loc[
                temperature_frame["timestamp"] > alarm_detected_at,
                ["timestamp", "steam_temperature", "condensate_temperature"],
            ].head(1)
            if not first_post_alarm_frame.empty:
                frames_to_concat.append(first_post_alarm_frame)
        return pd.concat(frames_to_concat, ignore_index=True)

    def _validate_temperature_window(
        self,
        window_frame: pd.DataFrame,
        *,
        window_label: str,
    ) -> None:
        """Validate that one analysis window contains usable temperature data."""
        if window_frame.empty:
            raise ValueError(f"No temperature rows were found in the {window_label}.")

        if (
            window_frame[["steam_temperature", "condensate_temperature"]]
            .dropna(how="all")
            .empty
        ):
            raise ValueError(f"The {window_label} has no usable temperature values.")

    def _insert_gap_break_rows(self, window_frame: pd.DataFrame) -> pd.DataFrame:
        """Insert NaN rows before long offline gaps so lines are not bridged."""
        time_diffs = window_frame["timestamp"].diff()
        gap_threshold = pd.Timedelta(hours=2.5)
        gaps_mask = time_diffs > gap_threshold

        if not gaps_mask.any():
            return window_frame

        nan_rows: list[dict[str, Any]] = []
        for idx in window_frame[gaps_mask].index:
            previous_timestamp = pd.Timestamp(window_frame.loc[idx - 1, "timestamp"])
            nan_rows.append(
                {
                    "timestamp": previous_timestamp + pd.Timedelta(seconds=1),
                    "steam_temperature": float("nan"),
                    "condensate_temperature": float("nan"),
                }
            )

        nan_frame = pd.DataFrame(nan_rows)
        return (
            pd.concat([window_frame, nan_frame], ignore_index=True)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def _render_combined_chart(
        self,
        window_frame: pd.DataFrame,
        *,
        temperature_chart_title: str,
        delta_chart_title: str,
        window_days: int | None = None,
    ) -> bytes:
        """Render one combined raw temperature and delta chart as PNG bytes."""
        figure, axes = plt.subplots(
            2,
            1,
            figsize=(11, 8.4),
            gridspec_kw={"height_ratios": [3, 2], "hspace": 0.55},
        )
        temperature_axis, delta_axis = axes
        self._plot_temperature_chart(
            temperature_axis,
            window_frame,
            chart_title=temperature_chart_title,
        )
        self._plot_delta_chart(
            delta_axis,
            window_frame,
            chart_title=delta_chart_title,
        )
        self._format_shared_time_axis(
            temperature_axis,
            delta_axis,
            window_frame["timestamp"],
            window_days=window_days,
        )

        buffer = BytesIO()
        figure.savefig(
            buffer,
            format=self.config.image_format,
            dpi=self.config.dpi,
            bbox_inches="tight",
        )
        plt.close(figure)
        return buffer.getvalue()

    def _plot_temperature_chart(
        self,
        axis: Axes,
        window_frame: pd.DataFrame,
        *,
        chart_title: str,
    ) -> None:
        """Draw the raw steam and condensate temperatures on the provided axis."""
        axis.plot(
            window_frame["timestamp"],
            window_frame["steam_temperature"],
            color="#C44E52",
            linewidth=1.0,
            label="Steam temperature",
        )
        axis.plot(
            window_frame["timestamp"],
            window_frame["condensate_temperature"],
            color="#4C72B0",
            linewidth=1.0,
            label="Condensate temperature",
        )

        axis.set_title(chart_title, loc="left")
        axis.set_xlabel("Timestamp, YY-MM-DD HH:MM")
        axis.set_ylabel("Temperature, Celsius")
        axis.grid(True, which="major", alpha=0.4)
        axis.minorticks_on()
        axis.grid(True, which="minor", alpha=0.15)
        axis.tick_params(axis="y", which="major", length=6, width=1.2)
        axis.legend(
            loc="lower right",
            bbox_to_anchor=(1.0, 1.005),
            ncol=2,
            frameon=False,
        )

    def _plot_delta_chart(
        self,
        axis: Axes,
        window_frame: pd.DataFrame,
        *,
        chart_title: str,
    ) -> None:
        """Draw the raw and rolling-average delta on the provided axis."""
        raw_delta = (
            window_frame["steam_temperature"] - window_frame["condensate_temperature"]
        )
        if raw_delta.dropna().empty:
            raise ValueError(
                "The requested analysis window has no usable delta values."
            )

        delta_frame = pd.DataFrame(
            {
                "timestamp": window_frame["timestamp"],
                "delta": raw_delta,
            }
        ).set_index("timestamp")
        rolling_delta = delta_frame["delta"].rolling("4h", min_periods=1).mean()
        rolling_delta_values = rolling_delta.to_numpy(dtype=float)

        axis.fill_between(
            rolling_delta.index,
            rolling_delta_values,
            0,
            interpolate=True,
            color="#d8b4fe",
            alpha=0.45,
            label="4h rolling average area",
        )
        axis.plot(
            delta_frame.index,
            delta_frame["delta"],
            color="#a78bfa",
            alpha=0.4,
            linewidth=0.8,
            label="Raw delta",
        )
        axis.plot(
            rolling_delta.index,
            rolling_delta_values,
            color="#7e22ce",
            linewidth=1.4,
            label="4h rolling average",
        )
        axis.axhline(0.0, color="#94a3b8", linestyle="-", linewidth=1.5)

        axis.set_title(chart_title, loc="left")
        axis.set_xlabel("Timestamp, YY-MM-DD HH:MM")
        axis.set_ylabel("Steam - Condensate")
        axis.grid(True, which="major", alpha=0.4)
        axis.minorticks_on()
        axis.grid(True, which="minor", alpha=0.15)
        axis.tick_params(axis="y", which="major", length=6, width=1.2)
        axis.legend(
            loc="lower right",
            bbox_to_anchor=(1.0, 1.005),
            ncol=3,
            frameon=False,
            fontsize="small",
        )

    def _format_shared_time_axis(
        self,
        temperature_axis: Axes,
        delta_axis: Axes,
        timestamps: pd.Series,
        *,
        window_days: int | None = None,
    ) -> None:
        """Apply a shared time range and date formatting to both chart panels."""
        x_range = timestamps.max() - timestamps.min()
        if x_range > timedelta(0):
            x_pad = x_range * 0.005
        else:
            x_pad = timedelta(minutes=30)
        x_min = timestamps.min() - x_pad
        x_max = timestamps.max() + x_pad

        for axis in (temperature_axis, delta_axis):
            axis.set_xlim(x_min, x_max)

        if window_days is not None:
            for axis in (temperature_axis, delta_axis):
                if window_days >= 365:
                    axis.xaxis.set_major_locator(mdates.MonthLocator())
                axis.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d"))
                axis.tick_params(axis="x", which="both", bottom=True, labelbottom=True)
                plt.setp(axis.get_xticklabels(), rotation=30, ha="right")
            return

        delta_days = max(
            (timestamps.max() - timestamps.min()).total_seconds() / 86400, 1
        )
        if delta_days <= 10:
            formatter = mdates.DateFormatter("%Y-%m-%d\n%H:%M")
        else:
            formatter = mdates.DateFormatter("%Y-%m-%d")
        delta_axis.xaxis.set_major_formatter(formatter)
        temperature_axis.tick_params(axis="x", labelbottom=False)
        plt.setp(delta_axis.get_xticklabels(), rotation=30, ha="right")

    def _build_window_temperature_chart_title(self, window_days: int) -> str:
        """Build the title used for one default pre-alarm temperature chart."""
        return f"{window_days}-Day Temperature Window"

    def _build_window_delta_chart_title(self, window_days: int) -> str:
        """Build the title used for one default pre-alarm delta chart."""
        return f"{window_days}-Day Steam - Condensate Delta (4h avg)"

    def _build_custom_temperature_chart_title(
        self,
        *,
        range_start: datetime,
        range_end: datetime,
        include_post_alarm_point: bool,
    ) -> str:
        """Build the title used for one caller-selected combined chart."""
        post_alarm_suffix = (
            " (+ first point after alarm)" if include_post_alarm_point else ""
        )
        return (
            "Combined Temperature Analysis "
            f"{self._format_chart_timestamp(range_start)} to "
            f"{self._format_chart_timestamp(range_end)}"
            f"{post_alarm_suffix}"
        )

    def _format_chart_timestamp(self, value: datetime) -> str:
        """Format one chart boundary timestamp for display."""
        return value.strftime("%Y-%m-%d %H:%M")
