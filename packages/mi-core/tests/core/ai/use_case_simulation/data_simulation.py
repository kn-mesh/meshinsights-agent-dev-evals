from __future__ import annotations

from datetime import datetime, timedelta
import math
import random

import pandas as pd


class TemperatureDataSimulator:
    """Generate deterministic hourly Fahrenheit temperature data for one month."""

    def __init__(self, seed: int = 42) -> None:
        """Initialize simulation settings and seeded random generator."""
        self._seed = seed
        self._rng = random.Random(seed)
        self._hours_per_day = 24

    def simulate_temperature_data(self) -> pd.DataFrame:
        """Return one month of hourly temperature readings sorted oldest to newest."""
        start_timestamp = self._get_month_start_timestamp()
        timestamps = self._build_hourly_timestamps(start_timestamp)
        degrees_f = self._build_temperature_values(timestamps)

        return (
            pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "degrees_f": degrees_f,
                }
            )
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def _get_month_start_timestamp(self) -> datetime:
        """Return the midnight timestamp for the first day of the current month."""
        now = datetime.now()
        return datetime(year=now.year, month=now.month, day=1)

    def _build_hourly_timestamps(self, start_timestamp: datetime) -> list[datetime]:
        """Build a month-long hourly timestamp sequence starting from month start."""
        if start_timestamp.month == 12:
            next_month_start = datetime(year=start_timestamp.year + 1, month=1, day=1)
        else:
            next_month_start = datetime(
                year=start_timestamp.year,
                month=start_timestamp.month + 1,
                day=1,
            )

        total_hours = int((next_month_start - start_timestamp).total_seconds() // 3600)
        return [start_timestamp + timedelta(hours=hour) for hour in range(total_hours)]

    def _build_temperature_values(self, timestamps: list[datetime]) -> list[float]:
        """Compute deterministic sine-wave temperatures with small seeded variability."""
        base_temp_f = 65
        daily_amplitude_f = 20

        temperatures: list[float] = []
        for timestamp in timestamps:
            daily_cycle = math.sin(
                (2 * math.pi * (timestamp.hour - 6)) / self._hours_per_day
            )
            seeded_noise = self._rng.gauss(mu=0.0, sigma=0.8)
            temperature_f = (
                base_temp_f + (daily_amplitude_f * daily_cycle) + seeded_noise
            )
            temperatures.append(round(temperature_f, 2))
        return temperatures


def simulate_temperature_data() -> pd.DataFrame:
    """Generate deterministic hourly Fahrenheit temperature data for one month."""
    simulator = TemperatureDataSimulator(seed=42)
    return simulator.simulate_temperature_data()


class RelativeHumidityDataSimulator:
    """Generate deterministic hourly relative-humidity data for one month."""

    def __init__(self, seed: int = 43) -> None:
        """Initialize simulation settings and seeded random generator."""
        self._seed = seed
        self._rng = random.Random(seed)
        self._hours_per_day = 24

    def simulate_relative_humidity_data(self) -> pd.DataFrame:
        """Return one month of hourly humidity readings sorted oldest to newest."""
        start_timestamp = self._get_month_start_timestamp()
        timestamps = self._build_hourly_timestamps(start_timestamp)
        humidity_percent = self._build_relative_humidity_values(timestamps)

        return (
            pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "relative_humidity_percent": humidity_percent,
                }
            )
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def _get_month_start_timestamp(self) -> datetime:
        """Return the midnight timestamp for the first day of the current month."""
        now = datetime.now()
        return datetime(year=now.year, month=now.month, day=1)

    def _build_hourly_timestamps(self, start_timestamp: datetime) -> list[datetime]:
        """Build a month-long hourly timestamp sequence starting from month start."""
        if start_timestamp.month == 12:
            next_month_start = datetime(year=start_timestamp.year + 1, month=1, day=1)
        else:
            next_month_start = datetime(
                year=start_timestamp.year,
                month=start_timestamp.month + 1,
                day=1,
            )

        total_hours = int((next_month_start - start_timestamp).total_seconds() // 3600)
        return [start_timestamp + timedelta(hours=hour) for hour in range(total_hours)]

    def _build_relative_humidity_values(
        self, timestamps: list[datetime]
    ) -> list[float]:
        """Compute deterministic step-change humidity values with small seeded variability."""
        day_step_levels = [42.0, 54.0, 48.0, 62.0, 56.0, 70.0, 64.0, 78.0]
        first_day = timestamps[0].date()

        humidity_values: list[float] = []
        for timestamp in timestamps:
            day_index = (timestamp.date() - first_day).days
            step_level = day_step_levels[day_index % len(day_step_levels)]
            seeded_noise = self._rng.gauss(mu=0.0, sigma=0.12)
            humidity_percent = step_level + seeded_noise
            humidity_values.append(round(max(0.0, min(100.0, humidity_percent)), 2))
        return humidity_values


def simulate_relative_humidity_data() -> pd.DataFrame:
    """Generate deterministic hourly relative-humidity data for one month."""
    simulator = RelativeHumidityDataSimulator(seed=43)
    return simulator.simulate_relative_humidity_data()


def select_last_n_days(
    dataframe: pd.DataFrame,
    *,
    timestamp_column: str = "timestamp",
    days: int = 1,
) -> pd.DataFrame:
    """Return rows within the trailing ``days`` window ending at max timestamp."""
    if days <= 0:
        raise ValueError("data_simulation: days must be greater than zero")
    if dataframe.empty:
        raise ValueError("data_simulation: dataframe cannot be empty")
    if timestamp_column not in dataframe.columns:
        raise ValueError(
            f"data_simulation: missing timestamp column '{timestamp_column}'"
        )

    timestamp_series = pd.to_datetime(dataframe[timestamp_column], errors="coerce")
    if timestamp_series.isna().any():
        raise ValueError(
            f"data_simulation: column '{timestamp_column}' contains invalid timestamps"
        )

    latest_timestamp = timestamp_series.max()
    start_timestamp = latest_timestamp - pd.Timedelta(days=days)
    within_window = timestamp_series >= start_timestamp
    filtered_data = dataframe.loc[within_window].copy()
    filtered_data.loc[:, timestamp_column] = timestamp_series.loc[within_window]

    if filtered_data.empty:
        raise ValueError("data_simulation: no rows found in requested time window")

    return filtered_data.sort_values(timestamp_column).reset_index(drop=True)


# uv run tests/core/ai/data_simulation.py
if __name__ == "__main__":
    temperature_df = simulate_temperature_data()
    humidity_df = simulate_relative_humidity_data()
    print(temperature_df)
    print(humidity_df)
