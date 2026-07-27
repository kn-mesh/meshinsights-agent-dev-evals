"""Decode Spirax evidence from immutable Azure benchmark artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import io
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from mi.core.pipeline import PipelineMetadata
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
from mi.core.versioning import VersionAssetRole, VersionContractDeclaration

from src.benchmarks import BenchmarkExamplePipelineMetadata, SourceArtifact
from src.storage.azure_blob import AzureBlobEvidenceStore, EvidenceStore


class SpiraxFrozenEvidenceRetrieverConfig(BaseRetrieverConfig):
    """Configure the Spirax frozen-artifact decoder."""

    name: str = "azure_blob"
    scope: str = "pulse_alarm_temperature_history"


class SpiraxFrozenEvidenceRetriever(BaseRetriever):
    """Load, verify, and decode the Spirax telemetry/alarm evidence contract."""

    config: SpiraxFrozenEvidenceRetrieverConfig

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        """Declare immutable Azure evidence inputs without embedding evidence."""
        _ = config
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.EVIDENCE_RECIPE,
                logical_name="azure_published_benchmark_evidence",
                value={
                    "source": "azure_blob",
                    "required_metadata": [
                        "example_id",
                        "benchmark_key",
                        "benchmark_version_id",
                        "benchmark_version_number",
                        "source_snapshot_id",
                        "source_snapshot_content_sha256",
                        "decision_timestamp",
                        "raw_artifacts",
                    ],
                    "artifact_integrity": ["byte_size", "content_sha256"],
                    "write_access": False,
                },
            ),
        )

    def __init__(
        self,
        config: SpiraxFrozenEvidenceRetrieverConfig | None = None,
        *,
        evidence_store: EvidenceStore | None = None,
    ) -> None:
        """Initialize the retriever with an optional injected store for tests."""
        resolved = config or SpiraxFrozenEvidenceRetrieverConfig()
        super().__init__(resolved)
        self.config = resolved
        self._evidence_store = evidence_store

    def retrieve(self, *, metadata: PipelineMetadata | None = None) -> dict[str, Any]:
        """Return a normalized, hindsight-safe evidence package from Azure Blob."""
        typed_metadata = self._validate_metadata(metadata)
        artifacts = tuple(
            SourceArtifact.model_validate(artifact)
            for artifact in typed_metadata.raw_artifacts
        )
        by_kind = {artifact.artifact_kind: artifact for artifact in artifacts}
        missing = {"telemetry", "alarms"} - by_kind.keys()
        if missing:
            raise ValueError(
                "Benchmark manifest is missing raw artifacts: "
                + ", ".join(sorted(missing))
            )
        store = self._evidence_store or AzureBlobEvidenceStore()
        telemetry = self._load_telemetry(store.read_verified(by_kind["telemetry"]))
        selected_alarm, sensor_alarms = self._load_alarms(
            store.read_verified(by_kind["alarms"])
        )
        if not selected_alarm:
            raise ValueError("Benchmark evidence does not contain a selected alarm.")

        decision_timestamp = _naive_utc(typed_metadata.decision_timestamp)
        window_start = _optional_naive_utc(typed_metadata.raw_window_start)
        window_end = _optional_naive_utc(typed_metadata.raw_window_end)
        if window_start is None or window_end is None:
            raise ValueError("Published benchmark evidence requires a frozen window.")
        if window_start > window_end:
            raise ValueError("Benchmark evidence window start is after its end.")
        if window_end > decision_timestamp:
            raise ValueError(
                "Benchmark evidence window extends beyond the decision timestamp."
            )
        for row in telemetry:
            timestamp = row.get("timestamp")
            if not isinstance(timestamp, datetime):
                raise ValueError("Benchmark telemetry timestamp must be a datetime.")
            if timestamp > decision_timestamp:
                raise ValueError(
                    "Benchmark telemetry extends beyond the decision timestamp."
                )

        selected_alarm = _normalize_alarm(selected_alarm)
        normalized_sensor_alarms = [_normalize_alarm(row) for row in sensor_alarms]
        selected_alarm = _project_selected_alarm_at_decision(
            selected_alarm,
            window_start=window_start,
            window_end=window_end,
            decision_timestamp=decision_timestamp,
        )
        for index, alarm in enumerate(normalized_sensor_alarms):
            resolved_at = alarm.get("resolved_at")
            if isinstance(resolved_at, datetime) and resolved_at > decision_timestamp:
                # Historical alarms remain valid evidence at the cutoff, but their
                # eventual post-cutoff resolution state must not reach the agent.
                alarm["resolved_at"] = None
            _validate_alarm_window(
                alarm,
                label=f"historical alarm at index {index}",
                window_start=window_start,
                window_end=window_end,
                decision_timestamp=decision_timestamp,
            )
        lookback_days = max((window_end - window_start).days, 1)
        return {
            "example_id": typed_metadata.example_id,
            "benchmark_key": typed_metadata.benchmark_key,
            "benchmark_version_id": typed_metadata.benchmark_version_id,
            "benchmark_version_number": typed_metadata.benchmark_version_number,
            "source_snapshot_id": typed_metadata.source_snapshot_id,
            "source_snapshot_content_sha256": (
                typed_metadata.source_snapshot_content_sha256
            ),
            "source_kind": typed_metadata.source_kind,
            "known_gaps": list(typed_metadata.raw_known_gaps),
            "sensor_id": _sensor_id(typed_metadata),
            "unit": typed_metadata.unit,
            "decision_timestamp": decision_timestamp,
            "steam_trap_type": typed_metadata.example_metadata.get("steam_trap_type"),
            "selected_alarm": selected_alarm,
            "sensor_alarms": normalized_sensor_alarms,
            "window_start": window_start,
            "window_end": window_end,
            "lookback_days": lookback_days,
            "post_alarm_hours": 0,
            "temperature_history": telemetry,
        }

    def _validate_metadata(
        self, metadata: PipelineMetadata | None
    ) -> BenchmarkExamplePipelineMetadata:
        """Require benchmark publication metadata rather than live query inputs."""
        if not isinstance(metadata, BenchmarkExamplePipelineMetadata):
            raise ValueError(
                "Pipeline metadata must be BenchmarkExamplePipelineMetadata."
            )
        return metadata

    def _load_telemetry(self, content: bytes) -> list[dict[str, Any]]:
        """Decode the labeling product's immutable telemetry Parquet artifact."""
        frame = pd.read_parquet(io.BytesIO(content))
        required = {"timestamp", "steam_temperature", "condensate_temperature"}
        if frame.empty or not required.issubset(frame.columns):
            raise ValueError(
                "Benchmark telemetry is missing timestamp or temperature columns."
            )
        raw_rows = frame.astype(object).to_dict(orient="records")
        rows: list[dict[str, Any]] = [
            {
                str(key): None if _is_missing(value) else value
                for key, value in row.items()
            }
            for row in raw_rows
        ]
        for row in rows:
            row["timestamp"] = _parse_datetime(row["timestamp"])
        return rows

    def _load_alarms(
        self, content: bytes
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Decode selected and historical alarms from the immutable NDJSON artifact."""
        selected: dict[str, Any] = {}
        sensor_alarms: list[dict[str, Any]] = []
        for line in content.decode("utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict) or not isinstance(
                record.get("alarm"), dict
            ):
                raise ValueError("Benchmark alarm artifact contains an invalid record.")
            if record.get("kind") == "selected_alarm":
                selected = record["alarm"]
            elif record.get("kind") == "sensor_alarm":
                sensor_alarms.append(record["alarm"])
        return selected, sensor_alarms


def _normalize_alarm(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize both canonical and raw-source alarm field names."""
    alarm_data = value.get("alarmData")
    alarm_data = alarm_data if isinstance(alarm_data, dict) else {}
    detected_at = value.get("detected_at", value.get("detectedAt"))
    return {
        "alarm_id": str(value.get("alarm_id", value.get("_id", ""))),
        "sensor_id": value.get("sensor_id", value.get("sensorIdDec")),
        "detected_at": _parse_datetime(detected_at),
        "resolved_at": _optional_parse_datetime(
            value.get("resolved_at", value.get("resolvedOn"))
        ),
        "alert_type": value.get("alert_type", value.get("alertType")),
        "analyst_status": value.get("analyst_status", value.get("analystStatus")),
        "alarm_type": value.get(
            "alarm_type", alarm_data.get("type", value.get("type"))
        ),
        "alarm_code": value.get("alarm_code", alarm_data.get("code")),
        "alarm_description": value.get(
            "alarm_description", alarm_data.get("description")
        ),
    }


def _validate_alarm_window(
    alarm: Mapping[str, Any],
    *,
    label: str,
    window_start: datetime,
    window_end: datetime,
    decision_timestamp: datetime,
) -> None:
    """Reject alarm timestamps that can reveal evidence outside the frozen window."""
    for field in ("detected_at", "resolved_at"):
        timestamp = alarm.get(field)
        if timestamp is None and field == "resolved_at":
            continue
        if not isinstance(timestamp, datetime):
            raise ValueError(f"Benchmark {label} is missing {field}.")
        if timestamp > decision_timestamp:
            raise ValueError(
                f"Benchmark {label} {field} extends beyond the decision timestamp."
            )
        if timestamp < window_start or timestamp > window_end:
            raise ValueError(
                f"Benchmark {label} {field} is outside the frozen evidence window."
            )


def _project_selected_alarm_at_decision(
    alarm: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
    decision_timestamp: datetime,
) -> dict[str, Any]:
    """Project a selected alarm onto its published, hindsight-safe decision state."""
    source_detected_at = alarm.get("detected_at")
    if not isinstance(source_detected_at, datetime):
        raise ValueError("Benchmark selected alarm is missing detected_at.")
    if source_detected_at < window_start:
        raise ValueError(
            "Benchmark selected alarm detected_at is outside the frozen evidence "
            "window."
        )
    if source_detected_at > decision_timestamp:
        same_published_second = (
            source_detected_at.replace(microsecond=0)
            == decision_timestamp.replace(microsecond=0)
        )
        if not same_published_second:
            raise ValueError(
                "Benchmark selected alarm detected_at extends beyond the decision "
                "timestamp."
            )
    elif source_detected_at > window_end:
        raise ValueError(
            "Benchmark selected alarm detected_at is outside the frozen evidence "
            "window."
        )

    resolved_at = alarm.get("resolved_at")
    if resolved_at is not None:
        if not isinstance(resolved_at, datetime):
            raise ValueError("Benchmark selected alarm is missing resolved_at.")
        if resolved_at > decision_timestamp:
            # The immutable artifact may contain eventual resolution state. It is
            # deliberately censored from the decision-time pipeline payload.
            alarm["resolved_at"] = None
        elif resolved_at < window_start or resolved_at > window_end:
            raise ValueError(
                "Benchmark selected alarm resolved_at is outside the frozen evidence "
                "window."
            )

    alarm["source_detected_at"] = source_detected_at
    alarm["detected_at"] = decision_timestamp
    return alarm


def _sensor_id(metadata: BenchmarkExamplePipelineMetadata) -> int:
    """Resolve the Pulse sensor identity inside the use-case adapter boundary."""
    raw = metadata.example_metadata.get("sensor_id", metadata.unit)
    try:
        return int(str(raw).strip())
    except ValueError as error:
        raise ValueError(
            f"Benchmark example {metadata.example_id} has a non-numeric sensor_id."
        ) from error


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _naive_utc(value)
    if value is None:
        raise ValueError("Expected a timestamp value.")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _naive_utc(parsed)


def _optional_parse_datetime(value: Any) -> datetime | None:
    return None if value is None else _parse_datetime(value)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _optional_naive_utc(value: datetime | None) -> datetime | None:
    return None if value is None else _naive_utc(value)


def _is_missing(value: Any) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
