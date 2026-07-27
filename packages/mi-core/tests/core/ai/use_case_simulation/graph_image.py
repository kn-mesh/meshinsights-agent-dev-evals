"""Matplotlib chart renderers for simulated temperature and humidity data."""

from __future__ import annotations

from io import BytesIO
from threading import Lock

import matplotlib
import pandas as pd
from mi.ai import ImageContent

matplotlib.use("Agg")
from matplotlib import pyplot as plt

_RENDER_LOCK = Lock()


def generate_temperature_graph_image_for_llm(temperature_data: pd.DataFrame) -> str:
    """Render simulated temperature data and return base64 PNG for LLM APIs."""
    image_bytes = generate_temperature_graph_image_bytes(
        temperature_data=temperature_data
    )
    return ImageContent.from_bytes(image_bytes, media_type="image/png").base64_data


def generate_humidity_graph_image_for_llm(humidity_data: pd.DataFrame) -> str:
    """Render last-7-day humidity data and return base64 PNG for LLM APIs."""
    image_bytes = generate_humidity_graph_image_bytes(humidity_data=humidity_data)
    return ImageContent.from_bytes(image_bytes, media_type="image/png").base64_data


def generate_graph_image_for_llm(data: pd.DataFrame) -> str:
    """Return a backward-compatible temperature graph image payload."""
    return generate_temperature_graph_image_for_llm(temperature_data=data)


def generate_temperature_graph_image_bytes(temperature_data: pd.DataFrame) -> bytes:
    """Render simulated temperature data as a PNG image and return raw bytes."""
    _validate_temperature_graph_input(temperature_data=temperature_data)

    with _RENDER_LOCK:
        figure, axis = plt.subplots(figsize=(12.0, 5.0), dpi=120)

        try:
            axis.plot(
                temperature_data["timestamp"],
                temperature_data["degrees_f"],
                color="#d97706",
                linewidth=1.5,
                label="Temperature (F)",
            )
            axis.set_title("Temperature Sensors at Location 123")
            axis.set_xlabel("Timestamp")
            axis.set_ylabel("Degrees Fahrenheit")
            axis.grid(alpha=0.3)
            axis.legend(loc="upper left")
            figure.autofmt_xdate()
            figure.tight_layout()

            buffer = BytesIO()
            figure.savefig(buffer, format="png")
            return buffer.getvalue()
        finally:
            plt.close(figure)


def generate_humidity_graph_image_bytes(humidity_data: pd.DataFrame) -> bytes:
    """Render last-7-day humidity data as a PNG image and return raw bytes."""
    _validate_humidity_graph_input(humidity_data=humidity_data)
    recent_humidity_data = _select_last_n_days(humidity_data=humidity_data, days=7)

    with _RENDER_LOCK:
        figure, axis = plt.subplots(figsize=(12.0, 5.0), dpi=120)

        try:
            axis.plot(
                recent_humidity_data["timestamp"],
                recent_humidity_data["relative_humidity_percent"],
                color="#0284c7",
                linewidth=1.5,
                label="Relative Humidity (%)",
            )
            axis.set_title("Relative Humidity Sensors at Location 123 (Last 7 Days)")
            axis.set_xlabel("Timestamp")
            axis.set_ylabel("Relative Humidity (%)")
            axis.grid(alpha=0.3)
            axis.legend(loc="upper left")
            figure.autofmt_xdate()
            figure.tight_layout()

            buffer = BytesIO()
            figure.savefig(buffer, format="png")
            return buffer.getvalue()
        finally:
            plt.close(figure)


def _validate_temperature_graph_input(temperature_data: pd.DataFrame) -> None:
    """Validate temperature data contains required graph columns and at least one row."""
    if temperature_data.empty:
        raise ValueError("graph_image: Cannot render graph from empty temperature data")

    required_columns = {"timestamp", "degrees_f"}
    missing_columns = [
        column for column in required_columns if column not in temperature_data.columns
    ]
    if missing_columns:
        missing_display = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"graph_image: Missing required temperature columns: {missing_display}"
        )


def _validate_humidity_graph_input(humidity_data: pd.DataFrame) -> None:
    """Validate humidity data contains required graph columns and at least one row."""
    if humidity_data.empty:
        raise ValueError("graph_image: Cannot render graph from empty humidity data")

    required_columns = {"timestamp", "relative_humidity_percent"}
    missing_columns = [
        column for column in required_columns if column not in humidity_data.columns
    ]
    if missing_columns:
        missing_display = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"graph_image: Missing required humidity columns: {missing_display}"
        )


def _select_last_n_days(humidity_data: pd.DataFrame, days: int) -> pd.DataFrame:
    """Return humidity rows that fall within the last N days of the dataset."""
    if days <= 0:
        raise ValueError("graph_image: days must be greater than zero")

    timestamp_series = pd.to_datetime(humidity_data["timestamp"], errors="coerce")
    if timestamp_series.isna().any():
        raise ValueError(
            "graph_image: Humidity timestamp column contains invalid values"
        )

    latest_timestamp = timestamp_series.max()
    start_timestamp = latest_timestamp - pd.Timedelta(days=days)
    within_window = timestamp_series >= start_timestamp
    filtered_data = humidity_data.loc[within_window].copy()
    filtered_data.loc[:, "timestamp"] = timestamp_series.loc[within_window]

    if filtered_data.empty:
        raise ValueError("graph_image: No humidity rows found in requested time window")

    return filtered_data.sort_values("timestamp").reset_index(drop=True)


# uv run tests/core/ai/graph_image.py
if __name__ == "__main__":
    from data_simulation import (
        simulate_relative_humidity_data,
        simulate_temperature_data,
    )

    temperature_df = simulate_temperature_data()
    humidity_df = simulate_relative_humidity_data()

    temperature_image_bytes = generate_temperature_graph_image_bytes(temperature_df)
    humidity_image_bytes = generate_humidity_graph_image_bytes(humidity_df)

    with open("tests/core/ai/temperature_graph.png", "wb") as file_obj:
        file_obj.write(temperature_image_bytes)
    with open("tests/core/ai/humidity_graph_last_7_days.png", "wb") as file_obj:
        file_obj.write(humidity_image_bytes)
