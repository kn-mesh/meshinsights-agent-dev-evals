"""Tests for reusable bounded temperature-window analysis."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.processors.common.temperature_window_analysis import (
    TemperatureWindowAnalyzer,
)


def _history(alarm_at: datetime) -> list[dict[str, object]]:
    return [
        {
            "timestamp": alarm_at - timedelta(hours=6 - index),
            "steam_temperature": 120.0 + index,
            "condensate_temperature": 100.0 + index * 0.5,
        }
        for index in range(7)
    ]


def test_summary_uses_typed_compact_measurements() -> None:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    analyzer = TemperatureWindowAnalyzer(max_window_days=2)
    range_start, range_end = analyzer.resolve_range(
        start=(alarm_at - timedelta(hours=6)).isoformat(),
        end=alarm_at.isoformat(),
        alarm_at=alarm_at,
    )

    summary = analyzer.summarize(
        _history(alarm_at),
        range_start=range_start,
        range_end=range_end,
    )

    assert summary.paired_readings == 7
    assert summary.end_steam_median_c > summary.start_steam_median_c
    assert summary.end_delta_median_c > summary.start_delta_median_c
    assert summary.median_normalized_delta > 0
    assert summary.same_direction_movement_fraction == 1.0
    assert summary.nonpositive_delta_fraction == 0


def test_range_rejects_post_alarm_and_oversized_windows() -> None:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    analyzer = TemperatureWindowAnalyzer(max_window_days=2)

    with pytest.raises(ValueError, match="after the FDE alarm"):
        analyzer.resolve_range(
            start=(alarm_at - timedelta(hours=1)).isoformat(),
            end=(alarm_at + timedelta(minutes=30)).isoformat(),
            alarm_at=alarm_at,
        )

    with pytest.raises(ValueError, match="cannot exceed 2 days"):
        analyzer.resolve_range(
            start=(alarm_at - timedelta(days=3)).isoformat(),
            end=alarm_at.isoformat(),
            alarm_at=alarm_at,
        )


def test_summary_rejects_incomplete_telemetry_contract() -> None:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    analyzer = TemperatureWindowAnalyzer(max_window_days=2)

    with pytest.raises(ValueError, match="condensate_temperature"):
        analyzer.summarize(
            [
                {
                    "timestamp": alarm_at - timedelta(hours=index),
                    "steam_temperature": 120.0,
                }
                for index in range(3)
            ],
            range_start=alarm_at - timedelta(hours=3),
            range_end=alarm_at,
        )
