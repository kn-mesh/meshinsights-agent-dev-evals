"""Tests for portable Pulse evidence snapshot retrieval."""

from __future__ import annotations

import json
from datetime import datetime

from src.objects.pipeline_metadata import PulseFailureAnalysisMetadata
from src.retrievers.pulse_data_retriever import (
    PulseAlarmTemperatureHistoryRetriever,
    PulseAlarmTemperatureHistoryRetrieverConfig,
)


def _encoded_datetime(value: datetime) -> dict[str, str]:
    """Encode a datetime using the retriever snapshot contract."""
    return {"__type__": "datetime", "value": value.isoformat()}


def test_strict_snapshot_mode_loads_evidence_without_mongo(tmp_path) -> None:
    """Run deterministic historical examples without database credentials."""
    decision_timestamp = datetime(2026, 3, 17, 12, 0)
    snapshot = tmp_path / "sensor_7" / "20260317T120000_lb365_pa0_keep0.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(
        json.dumps(
            {
                "sensor_id": 7,
                "unit": "trap-7",
                "decision_timestamp": _encoded_datetime(decision_timestamp),
                "steam_trap_type": "Float",
                "selected_alarm": {
                    "detected_at": _encoded_datetime(decision_timestamp)
                },
                "window_start": _encoded_datetime(datetime(2025, 3, 17, 12, 0)),
                "window_end": _encoded_datetime(decision_timestamp),
                "lookback_days": 365,
                "post_alarm_hours": 0,
                "temperature_history": [
                    {
                        "timestamp": _encoded_datetime(decision_timestamp),
                        "steam_temperature": 130.0,
                        "condensate_temperature": 105.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    retriever = PulseAlarmTemperatureHistoryRetriever(
        PulseAlarmTemperatureHistoryRetrieverConfig(
            snapshot_mode="strict",
            snapshot_dir=str(tmp_path),
            post_alarm_hours=0,
        )
    )

    payload = retriever.retrieve(
        metadata=PulseFailureAnalysisMetadata(
            unit="trap-7",
            sensor_id=7,
            decision_timestamp=decision_timestamp,
        )
    )

    assert payload["decision_timestamp"] == decision_timestamp
    assert payload["temperature_history"][0]["timestamp"] == decision_timestamp
