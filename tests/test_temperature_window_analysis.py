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


def test_agent_safe_range_clamps_alarm_and_duration_boundaries() -> None:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    analyzer = TemperatureWindowAnalyzer(max_window_days=2)

    resolution = analyzer.resolve_available_range(
        _history(alarm_at),
        start=(alarm_at - timedelta(days=3)).isoformat(),
        end=(alarm_at + timedelta(hours=1)).isoformat(),
        alarm_at=alarm_at,
    )

    assert resolution.requested_end == alarm_at + timedelta(hours=1)
    assert resolution.range_end == alarm_at
    assert resolution.range_start == alarm_at - timedelta(days=2)
    assert resolution.adjustments == [
        "End was clamped to the FDE alarm timestamp.",
        "Start was moved forward to enforce the 2-day limit.",
    ]


def test_agent_safe_range_snaps_to_nearest_available_readings() -> None:
    alarm_at = datetime(2026, 3, 17, 12, 0)
    analyzer = TemperatureWindowAnalyzer(max_window_days=2)

    resolution = analyzer.resolve_available_range(
        _history(alarm_at),
        start=(alarm_at - timedelta(hours=36)).isoformat(),
        end=(alarm_at - timedelta(hours=24)).isoformat(),
        alarm_at=alarm_at,
    )

    assert resolution.range_start == alarm_at - timedelta(hours=6)
    assert resolution.range_end == alarm_at - timedelta(hours=4)
    assert resolution.adjustments == [
        "Interval was moved to the nearest available three-reading window."
    ]
    summary = analyzer.summarize(
        _history(alarm_at),
        range_start=resolution.range_start,
        range_end=resolution.range_end,
    )
    assert summary.paired_readings == 3


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
