"""Deterministic temperature-evidence charts for the Pulse v1_3 agent."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, cast

import matplotlib
import pandas as pd
from pydantic import Field

matplotlib.use("Agg")

from matplotlib import dates as mdates
from matplotlib import pyplot as plt
from matplotlib.axes import Axes

from mi.core.processors import BaseProcessor, BaseProcessorConfig

from src.objects.process_object import PulseFailureAnalysisProcessObject


class V1_3TemperatureEvidenceProcessorConfig(BaseProcessorConfig):
    """Configure the v1_3 evidence windows and deterministic image rendering."""

    name: str | None = "v1_3_temperature_evidence_processor"
    window_days_list: list[int] = Field(default_factory=lambda: [7, 30, 365])
    segmented_window_days: int = Field(default=365, ge=1)
    segment_count: int = Field(default=4, ge=1)
    image_format: str = "png"
    dpi: int = Field(default=140, ge=1)


class V1_3TemperatureEvidenceProcessor(
    BaseProcessor[PulseFailureAnalysisProcessObject]
):
    """Render 7/30-day charts and a segmented yearly chart without hindsight."""

    config: V1_3TemperatureEvidenceProcessorConfig

    def __init__(
        self, config: V1_3TemperatureEvidenceProcessorConfig | None = None
    ) -> None:
        """Initialize deterministic chart rendering."""
        resolved = config or V1_3TemperatureEvidenceProcessorConfig()
        super().__init__(resolved)
        self.config = resolved

    def process(
        self,
        data_object: PulseFailureAnalysisProcessObject,
        *,
        metadata: Any = None,
    ) -> None:
        """Render configured evidence windows into process artifacts."""
        _ = metadata
        frame = self._temperature_frame(data_object.get_temperature_history())
        alarm_at = self._alarm_timestamp(data_object)
        for window_days in self.config.window_days_list:
            window = self._window(
                frame, alarm_at - timedelta(days=window_days), alarm_at
            )
            image = self._render(window, window_days=window_days)
            data_object.set_temperature_chart(
                window_days, base64.b64encode(image).decode("ascii")
            )

    def render_custom_chart(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        range_start: datetime,
        range_end: datetime,
        alarm_detected_at: datetime,
    ) -> bytes:
        """Render one agent-selected range ending no later than the alarm."""
        if range_start > range_end:
            raise ValueError("Custom chart start must be on or before its end.")
        if range_end > alarm_detected_at:
            raise ValueError("Custom chart end cannot be after the alarm timestamp.")
        frame = self._temperature_frame(temperature_history)
        return self._render(
            self._window(frame, range_start, range_end, include_post_alarm=False),
            window_days=None,
        )

    def summarize_range(
        self,
        temperature_history: list[dict[str, Any]],
        *,
        range_start: datetime,
        range_end: datetime,
    ) -> dict[str, Any]:
        """Compute bounded descriptive evidence for an agent-selected range."""
        frame = self._temperature_frame(temperature_history)
        window = self._window(frame, range_start, range_end, include_post_alarm=False)
        delta = window["steam_temperature"] - window["condensate_temperature"]
        return {
            "range_start": pd.Timestamp(window["timestamp"].min()).isoformat(),
            "range_end": pd.Timestamp(window["timestamp"].max()).isoformat(),
            "point_count": int(
                window[["steam_temperature", "condensate_temperature"]]
                .dropna(how="all")
                .shape[0]
            ),
            "steam_min": self._rounded(window["steam_temperature"].min()),
            "steam_median": self._rounded(window["steam_temperature"].median()),
            "steam_max": self._rounded(window["steam_temperature"].max()),
            "condensate_min": self._rounded(window["condensate_temperature"].min()),
            "condensate_median": self._rounded(
                window["condensate_temperature"].median()
            ),
            "condensate_max": self._rounded(window["condensate_temperature"].max()),
            "delta_median": self._rounded(delta.median()),
            "delta_last": self._rounded(delta.dropna().iloc[-1]),
            "negative_delta_fraction": round(
                sum(bool(value) for value in (delta.dropna() < 0).tolist())
                / len(delta.dropna()),
                3,
            ),
        }

    def _temperature_frame(self, history: list[dict[str, Any]]) -> pd.DataFrame:
        """Normalize retrieved telemetry into a sorted numeric dataframe."""
        frame = pd.DataFrame(history)
        required = {"timestamp", "steam_temperature", "condensate_temperature"}
        if frame.empty or not required.issubset(frame.columns):
            raise ValueError(
                "Temperature history is missing required evidence columns."
            )
        frame = frame.loc[:, sorted(required)].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
        frame["steam_temperature"] = pd.to_numeric(
            frame["steam_temperature"], errors="coerce"
        )
        frame["condensate_temperature"] = pd.to_numeric(
            frame["condensate_temperature"], errors="coerce"
        )
        return frame.sort_values("timestamp").reset_index(drop=True)

    def _alarm_timestamp(
        self, data_object: PulseFailureAnalysisProcessObject
    ) -> datetime:
        """Return the alarm timestamp from the evidence contract."""
        value = data_object.get_alarm_context()["selected_alarm"]["detected_at"]
        if not isinstance(value, datetime):
            raise ValueError("Selected alarm detected_at must be a datetime.")
        return value

    def _window(
        self,
        frame: pd.DataFrame,
        range_start: datetime,
        range_end: datetime,
        *,
        include_post_alarm: bool = True,
    ) -> pd.DataFrame:
        """Select a bounded evidence range and optionally one continuity point."""
        selected = frame.loc[
            (frame["timestamp"] >= range_start) & (frame["timestamp"] <= range_end)
        ].copy()
        if include_post_alarm:
            post_alarm = frame.loc[frame["timestamp"] > range_end].head(1)
            selected = pd.concat([selected, post_alarm], ignore_index=True)
        if (
            selected.empty
            or selected[["steam_temperature", "condensate_temperature"]]
            .dropna(how="all")
            .empty
        ):
            raise ValueError(
                "The requested evidence window has no usable temperatures."
            )
        return self._insert_gap_rows(selected)

    def _insert_gap_rows(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Break plotted lines across telemetry gaps longer than 2.5 hours."""
        gap_indexes = frame.index[frame["timestamp"].diff() > pd.Timedelta(hours=2.5)]
        if gap_indexes.empty:
            return frame
        gaps = [
            {
                "timestamp": cast(datetime, frame.loc[index - 1, "timestamp"])
                + timedelta(seconds=1),
                "steam_temperature": float("nan"),
                "condensate_temperature": float("nan"),
            }
            for index in gap_indexes
        ]
        return pd.concat([frame, pd.DataFrame(gaps)], ignore_index=True).sort_values(
            "timestamp"
        )

    def _render(self, frame: pd.DataFrame, *, window_days: int | None) -> bytes:
        """Render raw temperatures and rolling delta into a PNG."""
        segment_count = (
            self.config.segment_count
            if window_days == self.config.segmented_window_days
            else 1
        )
        figure, axes = plt.subplots(
            2,
            segment_count,
            figsize=(19.5 if segment_count > 1 else 11, 8.4),
            gridspec_kw={"height_ratios": [3, 2]},
            squeeze=False,
        )
        boundaries = pd.date_range(
            frame["timestamp"].min(),
            frame["timestamp"].max(),
            periods=segment_count + 1,
        )
        temperature_limits = self._limits(
            pd.concat([frame["steam_temperature"], frame["condensate_temperature"]])
        )
        delta_values = frame["steam_temperature"] - frame["condensate_temperature"]
        delta_limits = self._limits(pd.concat([delta_values, pd.Series([0.0])]))

        for index in range(segment_count):
            start, end = boundaries[index], boundaries[index + 1]
            end_operator = (
                frame["timestamp"] <= end
                if index == segment_count - 1
                else frame["timestamp"] < end
            )
            segment = frame.loc[(frame["timestamp"] >= start) & end_operator]
            self._plot_temperatures(axes[0, index], segment)
            self._plot_delta(axes[1, index], segment)
            axes[0, index].set_ylim(*temperature_limits)
            axes[1, index].set_ylim(*delta_limits)
            for axis in (axes[0, index], axes[1, index]):
                axis.set_xlim(start, end)
                axis.xaxis.set_major_locator(
                    mdates.AutoDateLocator(minticks=3, maxticks=6)
                )
                axis.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d"))
                plt.setp(axis.get_xticklabels(), rotation=30, ha="right")
            label = f"{start:%Y-%m-%d} to {end:%Y-%m-%d}"
            axes[0, index].set_title(f"Temperature evidence\n{label}")
            axes[1, index].set_title(f"Steam - condensate delta (4h average)\n{label}")

        axes[0, 0].set_ylabel("Temperature, Celsius")
        axes[1, 0].set_ylabel("Steam - condensate")
        for axis in axes.flat:
            axis.grid(True, alpha=0.3)
        axes[0, 0].legend(loc="best", fontsize="small")
        axes[1, 0].legend(loc="best", fontsize="small")
        figure.tight_layout()
        buffer = BytesIO()
        figure.savefig(buffer, format=self.config.image_format, dpi=self.config.dpi)
        plt.close(figure)
        return buffer.getvalue()

    def _plot_temperatures(self, axis: Axes, frame: pd.DataFrame) -> None:
        """Plot raw inlet and outlet temperatures."""
        axis.plot(
            frame["timestamp"],
            frame["steam_temperature"],
            color="#C44E52",
            linewidth=1,
            label="Steam/inlet",
        )
        axis.plot(
            frame["timestamp"],
            frame["condensate_temperature"],
            color="#4C72B0",
            linewidth=1,
            label="Condensate/outlet",
        )

    def _plot_delta(self, axis: Axes, frame: pd.DataFrame) -> None:
        """Plot raw and four-hour rolling temperature deltas."""
        delta = pd.DataFrame(
            {
                "timestamp": frame["timestamp"],
                "delta": frame["steam_temperature"] - frame["condensate_temperature"],
            }
        ).set_index("timestamp")
        rolling = delta["delta"].rolling("4h", min_periods=1).mean()
        axis.plot(
            delta.index,
            delta["delta"],
            color="#a78bfa",
            alpha=0.35,
            linewidth=0.8,
            label="Raw delta",
        )
        axis.plot(
            rolling.index, rolling, color="#7e22ce", linewidth=1.4, label="4h average"
        )
        axis.axhline(0, color="#64748b", linewidth=1)

    def _limits(self, values: pd.Series) -> tuple[float, float]:
        """Compute padded finite y-axis bounds."""
        numeric = pd.to_numeric(values, errors="coerce").dropna()
        if numeric.empty:
            return (-1.0, 1.0)
        minimum, maximum = float(numeric.min()), float(numeric.max())
        padding = max((maximum - minimum) * 0.08, 1.0)
        return minimum - padding, maximum + padding

    def _rounded(self, value: Any) -> float | None:
        """Return a JSON-friendly rounded numeric value."""
        return None if pd.isna(value) else round(float(value), 2)
