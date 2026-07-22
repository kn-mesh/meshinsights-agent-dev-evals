"""Spirax reviewer-evidence projection ported from Benchmark Studio."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.benchmarks.models import BenchmarkExample, BenchmarkVersion
from src.objects.pipeline_metadata import BenchmarkExamplePipelineMetadata
from src.retrievers.spirax_frozen_evidence_retriever import (
    SpiraxFrozenEvidenceRetriever,
)
from src.storage.azure_blob import EvidenceStore


EVIDENCE_SCHEMA_VERSION = "spirax-evidence-view/v1"
EVIDENCE_RECIPE_ID = "spirax-steam-trap-evidence@v2"


class SpiraxEvidenceAdapter:
    """Build the human review view from one exact published source snapshot."""

    def __init__(self, *, repository: Any, evidence_store: EvidenceStore) -> None:
        self._repository = repository
        self._evidence_store = evidence_store
        self._versions: dict[tuple[str, int], BenchmarkVersion] = {}

    def build_view(
        self, *, benchmark_key: str, version_number: int, example_id: str
    ) -> dict[str, Any]:
        key = (benchmark_key, version_number)
        benchmark = self._versions.get(key)
        if benchmark is None:
            benchmark = self._repository.load_published_version(
                benchmark_key=benchmark_key,
                version_number=version_number,
            )
            self._versions[key] = benchmark
        example = benchmark.get_example(example_id)
        metadata = BenchmarkExamplePipelineMetadata(
            unit=example.unit_id,
            example_id=example.example_id,
            decision_timestamp=example.decision_timestamp,
            benchmark_key=benchmark.benchmark_key,
            benchmark_version_id=benchmark.benchmark_version_id,
            benchmark_version_number=benchmark.version_number,
            source_snapshot_id=example.source_snapshot_id,
            source_snapshot_content_sha256=example.raw_snapshot_content_sha256,
            source_kind=example.raw_source_kind,
            raw_captured_at=example.raw_captured_at,
            raw_window_start=example.raw_window_start,
            raw_window_end=example.raw_window_end,
            raw_known_gaps=list(example.raw_known_gaps),
            raw_artifacts=[
                item.model_dump(mode="json") for item in example.raw_artifacts
            ],
            example_metadata=example.example_metadata,
        )
        payload = SpiraxFrozenEvidenceRetriever(
            evidence_store=self._evidence_store
        ).retrieve(metadata=metadata)
        return build_spirax_evidence_view(example=example, payload=payload)


def build_spirax_evidence_view(
    *, example: BenchmarkExample, payload: dict[str, Any]
) -> dict[str, Any]:
    """Return the Benchmark Studio-compatible reviewer-facing evidence envelope."""
    telemetry = [_normalize_telemetry(row) for row in payload["temperature_history"]]
    telemetry.sort(key=lambda row: row["timestamp"])
    selected_alarm = dict(payload["selected_alarm"])
    selected_id = str(selected_alarm.get("alarm_id") or "")
    markers = _alarm_marker_groups(payload.get("sensor_alarms", []), selected_id)
    window_start = _iso(payload["window_start"])
    window_end = _iso(payload["window_end"])
    decision_timestamp = _iso(payload["decision_timestamp"])
    known_gaps = [str(item) for item in payload.get("known_gaps", [])]
    return {
        "example": {
            "example_id": example.example_id,
            "unit_id": example.unit_id,
            "decision_timestamp": _iso(example.decision_timestamp),
            "metadata": example.example_metadata,
        },
        "window": {
            "start": window_start,
            "alarm": decision_timestamp,
            "end": window_end,
            "basis": "decision_timestamp",
            "lookback_days": payload["lookback_days"],
            "cutoff_policy": "decision_timestamp",
        },
        "evidence": {
            "selected_alarm": _json_safe(selected_alarm),
            "asset": {
                "sensor_id": payload.get("sensor_id"),
                "steam_trap_type": payload.get("steam_trap_type"),
                "tag": example.example_metadata.get("tag"),
            },
            "telemetry": telemetry,
            "chart_windows": {
                "short_window_days": 30,
                "long_window_days": payload["lookback_days"],
            },
            "alarm_markers": {
                "selected_detected_at": _optional_iso(
                    selected_alarm.get("source_detected_at")
                    or selected_alarm.get("detected_at")
                ),
                "selected_resolved_at": _optional_iso(
                    selected_alarm.get("resolved_at")
                ),
                **markers,
            },
            "coverage": {
                "telemetry_point_count": len(telemetry),
                "first_timestamp": telemetry[0]["timestamp"] if telemetry else None,
                "last_timestamp": telemetry[-1]["timestamp"] if telemetry else None,
                "source": payload.get("source_kind") or "source_snapshot",
            },
            "known_gaps": known_gaps,
        },
        "metadata": {
            "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            "evidence_recipe_id": EVIDENCE_RECIPE_ID,
            "source_snapshot_id": payload["source_snapshot_id"],
            "source_snapshot_content_sha256": payload["source_snapshot_content_sha256"],
            "source_kind": payload["source_kind"],
            "known_gaps": known_gaps,
        },
    }


def _normalize_telemetry(row: dict[str, Any]) -> dict[str, Any]:
    steam = _number(row.get("steam_temperature"))
    condensate = _number(row.get("condensate_temperature"))
    front_mic = _number(row.get("front_mic", row.get("frontMic")))
    return {
        "timestamp": _iso(row["timestamp"]),
        "steam_temperature": steam,
        "condensate_temperature": condensate,
        "temperature_delta": (
            steam - condensate if steam is not None and condensate is not None else None
        ),
        "front_mic": front_mic,
    }


def _alarm_marker_groups(
    alarms: list[dict[str, Any]], selected_id: str
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "unresolved_fde_detected_times": [],
        "resolved_fde_detected_times": [],
        "other_alarm_detected_times": [],
    }
    for alarm in alarms:
        if str(alarm.get("alarm_id") or "") == selected_id:
            continue
        detected_at = _optional_iso(alarm.get("detected_at"))
        if detected_at is None:
            continue
        if str(alarm.get("alarm_type") or "").upper() == "FDE":
            key = (
                "resolved_fde_detected_times"
                if alarm.get("resolved_at") is not None
                else "unresolved_fde_detected_times"
            )
        else:
            key = "other_alarm_detected_times"
        groups[key].append(detected_at)
    return groups


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _optional_iso(value: Any) -> str | None:
    return None if value is None else _iso(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
