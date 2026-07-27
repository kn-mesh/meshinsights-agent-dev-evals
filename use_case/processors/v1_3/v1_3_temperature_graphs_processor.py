"""Chart processor for the Spirax alarms v1_3 pipeline."""

from __future__ import annotations

from io import BytesIO
from typing import cast

import pandas as pd

from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from mi.core.processors import BaseProcessor

from use_case.objects.process_object import PulseFailureAnalysisProcessObject
from use_case.processors.common.temperature_graphs_three_intervals_processor import (
    TemperatureGraphsThreeIntervalsProcessor,
    TemperatureGraphsThreeIntervalsProcessorConfig,
)


class V1_3TemperatureGraphsProcessorConfig(
    TemperatureGraphsThreeIntervalsProcessorConfig
):
    """Configure segmented 365-day raw chart rendering for the v1_3 pipeline."""

    name: str | None = "v1_3_temperature_graphs_processor"
    segmented_window_days: int = 365
    segment_count: int = 4


class V1_3TemperatureGraphsProcessor(
    TemperatureGraphsThreeIntervalsProcessor,
    BaseProcessor[PulseFailureAnalysisProcessObject],
):
    """Render the 365-day chart as four contiguous raw-data segments."""

    def __init__(
        self, config: V1_3TemperatureGraphsProcessorConfig | None = None
    ) -> None:
        """Initialize the v1_3 chart processor with typed rendering settings."""
        resolved_config = config or V1_3TemperatureGraphsProcessorConfig()
        super().__init__(resolved_config)
        self.v1_config = resolved_config

    def _render_combined_chart(
        self,
        window_frame: pd.DataFrame,
        *,
        temperature_chart_title: str,
        delta_chart_title: str,
        window_days: int | None = None,
    ) -> bytes:
        """Render one chart, segmenting only the configured long window."""
        if window_days != self.v1_config.segmented_window_days:
            return super()._render_combined_chart(
                window_frame,
                temperature_chart_title=temperature_chart_title,
                delta_chart_title=delta_chart_title,
                window_days=window_days,
            )

        return self._render_segmented_combined_chart(
            window_frame,
            temperature_chart_title=temperature_chart_title,
            delta_chart_title=delta_chart_title,
        )

    def _render_segmented_combined_chart(
        self,
        window_frame: pd.DataFrame,
        *,
        temperature_chart_title: str,
        delta_chart_title: str,
    ) -> bytes:
        """Render one segmented 365-day chart that preserves raw datapoints."""
        delta_frame = self._build_delta_frame(window_frame)
        segment_ranges = self._build_segment_ranges(window_frame["timestamp"])
        figure, axes = plt.subplots(
            2,
            self.v1_config.segment_count,
            figsize=(19.5, 8.8),
            gridspec_kw={"height_ratios": [3, 2]},
            squeeze=False,
        )
        figure.subplots_adjust(
            left=0.06,
            right=0.985,
            top=0.88,
            bottom=0.22,
            wspace=0.18,
            hspace=0.62,
        )

        temperature_limits = self._compute_axis_limits(
            pd.concat(
                [
                    window_frame["steam_temperature"],
                    window_frame["condensate_temperature"],
                ],
                ignore_index=True,
            )
        )
        delta_limits = self._compute_axis_limits(
            pd.concat(
                [
                    delta_frame["delta"],
                    delta_frame["rolling_delta"],
                    pd.Series([0.0]),
                ],
                ignore_index=True,
            ),
            include_zero=True,
        )

        temperature_handles: list[Artist] | None = None
        temperature_labels: list[str] | None = None
        delta_handles: list[Artist] | None = None
        delta_labels: list[str] | None = None

        for index, (segment_start, segment_end) in enumerate(segment_ranges):
            is_last_segment = index == len(segment_ranges) - 1
            temperature_axis = axes[0, index]
            delta_axis = axes[1, index]

            temperature_segment = self._slice_frame_for_segment(
                window_frame,
                segment_start=segment_start,
                segment_end=segment_end,
                include_segment_end=is_last_segment,
            )
            delta_segment = self._slice_frame_for_segment(
                delta_frame,
                segment_start=segment_start,
                segment_end=segment_end,
                include_segment_end=is_last_segment,
            )

            self._plot_segment_temperature_chart(temperature_axis, temperature_segment)
            self._plot_segment_delta_chart(delta_axis, delta_segment)

            if temperature_handles is None:
                temperature_handles, temperature_labels = (
                    temperature_axis.get_legend_handles_labels()
                )
            if delta_handles is None:
                delta_handles, delta_labels = delta_axis.get_legend_handles_labels()

            temperature_axis.set_ylim(*temperature_limits)
            delta_axis.set_ylim(*delta_limits)
            temperature_axis.set_title(
                self._build_segment_title(
                    chart_title=temperature_chart_title,
                    segment_start=segment_start,
                    segment_end=segment_end,
                ),
                fontsize="small",
                pad=10,
            )
            delta_axis.set_title(
                self._build_segment_title(
                    chart_title=delta_chart_title,
                    segment_start=segment_start,
                    segment_end=segment_end,
                ),
                fontsize="small",
                pad=10,
            )

            self._format_segment_time_axis(
                temperature_axis,
                segment_start=segment_start,
                segment_end=segment_end,
                show_y_axis=True,
                show_x_labels=True,
            )
            self._format_segment_time_axis(
                delta_axis,
                segment_start=segment_start,
                segment_end=segment_end,
                show_y_axis=True,
                show_x_labels=True,
            )

        for index, axis in enumerate(axes[0]):
            axis.set_ylabel("Temperature, Celsius" if index == 0 else "")
            axis.set_xlabel("Timestamp, YY-MM-DD")
        for index, axis in enumerate(axes[1]):
            axis.set_ylabel("Steam - Condensate" if index == 0 else "")
            axis.set_xlabel("Timestamp, YY-MM-DD")

        if temperature_handles and temperature_labels:
            figure.legend(
                temperature_handles,
                temperature_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.995),
                ncol=2,
                frameon=True,
                edgecolor="#cccccc",
                fancybox=True,
                shadow=False,
            )
        if delta_handles and delta_labels:
            figure.legend(
                delta_handles,
                delta_labels,
                loc="lower center",
                bbox_to_anchor=(0.5, 0.10),
                ncol=3,
                frameon=True,
                edgecolor="#cccccc",
                fancybox=True,
                shadow=False,
                fontsize="small",
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

    def _build_delta_frame(self, window_frame: pd.DataFrame) -> pd.DataFrame:
        """Build the raw and rolling delta dataframe for one chart window."""
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
        delta_frame["rolling_delta"] = (
            delta_frame["delta"].rolling("4h", min_periods=1).mean()
        )
        return delta_frame.reset_index()

    def _build_segment_ranges(
        self, timestamps: pd.Series
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Split one chart time range into contiguous evenly sized segments."""
        boundaries = pd.date_range(
            start=timestamps.min(),
            end=timestamps.max(),
            periods=self.v1_config.segment_count + 1,
        )
        return [
            (boundaries[index], boundaries[index + 1])
            for index in range(self.v1_config.segment_count)
        ]

    def _slice_frame_for_segment(
        self,
        frame: pd.DataFrame,
        *,
        segment_start: pd.Timestamp,
        segment_end: pd.Timestamp,
        include_segment_end: bool,
    ) -> pd.DataFrame:
        """Return one contiguous time slice from the provided dataframe."""
        end_mask = (
            frame["timestamp"] <= segment_end
            if include_segment_end
            else frame["timestamp"] < segment_end
        )
        return frame.loc[(frame["timestamp"] >= segment_start) & end_mask].copy()

    def _plot_segment_temperature_chart(
        self, axis: Axes, window_frame: pd.DataFrame
    ) -> None:
        """Draw one raw temperature segment on the provided axis."""
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
        axis.grid(True, which="major", alpha=0.35)
        axis.tick_params(axis="y", which="major", length=6, width=1.2)

    def _plot_segment_delta_chart(self, axis: Axes, delta_frame: pd.DataFrame) -> None:
        """Draw one raw delta segment on the provided axis."""
        axis.fill_between(
            delta_frame["timestamp"],
            delta_frame["rolling_delta"].to_numpy(dtype=float),
            0,
            interpolate=True,
            color="#d8b4fe",
            alpha=0.45,
            label="4h rolling average area",
        )
        axis.plot(
            delta_frame["timestamp"],
            delta_frame["delta"],
            color="#a78bfa",
            alpha=0.4,
            linewidth=0.8,
            label="Raw delta",
        )
        axis.plot(
            delta_frame["timestamp"],
            delta_frame["rolling_delta"],
            color="#7e22ce",
            linewidth=1.4,
            label="4h rolling average",
        )
        axis.axhline(0.0, color="#94a3b8", linestyle="-", linewidth=1.5)
        axis.grid(True, which="major", alpha=0.35)
        axis.tick_params(axis="y", which="major", length=6, width=1.2)

    def _compute_axis_limits(
        self,
        values: pd.Series,
        *,
        include_zero: bool = False,
    ) -> tuple[float, float]:
        """Return padded y-axis bounds for one plotted row of values."""
        numeric_values = pd.to_numeric(values, errors="coerce").dropna()
        if numeric_values.empty:
            return (-1.0, 1.0)

        minimum = float(numeric_values.min())
        maximum = float(numeric_values.max())
        if include_zero:
            minimum = min(minimum, 0.0)
            maximum = max(maximum, 0.0)

        value_range = maximum - minimum
        padding = max(value_range * 0.08, 3.0 if value_range > 0 else 1.0)
        return (minimum - padding, maximum + padding)

    def _build_segment_label(
        self,
        segment_start: pd.Timestamp,
        segment_end: pd.Timestamp,
    ) -> str:
        """Build the label shown above one contiguous 365-day segment."""
        return f"{segment_start:%y-%m-%d} to {segment_end:%y-%m-%d}"

    def _build_segment_title(
        self,
        *,
        chart_title: str,
        segment_start: pd.Timestamp,
        segment_end: pd.Timestamp,
    ) -> str:
        """Build the title shown above one segmented subplot."""
        return (
            f"{self._build_segment_chart_title(chart_title=chart_title)}\n"
            f"{self._build_segment_label(segment_start, segment_end)}"
        )

    def _build_segment_chart_title(self, *, chart_title: str) -> str:
        """Build the chart title used for one segmented 3-month subplot."""
        if "Delta" in chart_title:
            return "3-Month Steam - Condensate Delta (4h avg)"
        return "3-Month Temperature Window"

    def _format_segment_time_axis(
        self,
        axis: Axes,
        *,
        segment_start: pd.Timestamp,
        segment_end: pd.Timestamp,
        show_y_axis: bool,
        show_x_labels: bool,
    ) -> None:
        """Format one segmented time axis with a compact date scale."""
        axis.set_xlim(
            cast(float, mdates.date2num(segment_start.to_pydatetime())),
            cast(float, mdates.date2num(segment_end.to_pydatetime())),
        )
        axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=5))
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d"))
        axis.tick_params(axis="x", which="both", bottom=True, labelbottom=show_x_labels)
        if show_x_labels:
            plt.setp(axis.get_xticklabels(), rotation=30, ha="right")
        if not show_y_axis:
            axis.tick_params(axis="y", labelleft=False)
