"""Reference-use-case tests for frozen Azure Blob evidence retrieval."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
import pandas as pd
import pytest

from workbench.benchmarks import BenchmarkExamplePipelineMetadata, SourceArtifact
from use_case.retrievers.spirax_frozen_evidence_retriever import (
    SpiraxFrozenEvidenceRetriever,
)
from workbench.storage.azure_blob import AzureBlobEvidenceStore


def _artifact(kind: str, key: str, content_type: str, content: bytes) -> SourceArtifact:
    return SourceArtifact(
        artifact_kind=kind,
        object_key=key,
        content_type=content_type,
        byte_size=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


def _evidence(
    *,
    telemetry_timestamp: str = "2026-03-17T11:30:00+00:00",
    alarm_records: list[dict[str, object]] | None = None,
) -> tuple[bytes, bytes, tuple[SourceArtifact, ...]]:
    telemetry_buffer = io.BytesIO()
    pd.DataFrame(
        [
            {
                "telemetry_id": "row-1",
                "timestamp": telemetry_timestamp,
                "steam_temperature": 130.0,
                "condensate_temperature": 105.0,
                "front_mic": 0,
            }
        ]
    ).to_parquet(telemetry_buffer, index=False)
    telemetry = telemetry_buffer.getvalue()
    records = alarm_records or [
        {
            "kind": "selected_alarm",
            "alarm": {
                "alarm_id": "alarm-1",
                "sensor_id": 7,
                "detected_at": "2026-03-17T12:00:00+00:00",
                "alarm_type": "FDE",
            },
        }
    ]
    alarms = "".join(json.dumps(record) + "\n" for record in records).encode()
    artifacts = (
        _artifact(
            "telemetry", "snapshot/telemetry.parquet", "application/parquet", telemetry
        ),
        _artifact("alarms", "snapshot/alarms.jsonl", "application/x-ndjson", alarms),
    )
    return telemetry, alarms, artifacts


class _MemoryEvidenceStore:
    def __init__(self, content: dict[str, bytes]) -> None:
        self.content = content

    def read_verified(self, artifact: SourceArtifact) -> bytes:
        return self.content[artifact.artifact_kind]


def _metadata(
    artifacts: tuple[SourceArtifact, ...],
) -> BenchmarkExamplePipelineMetadata:
    return BenchmarkExamplePipelineMetadata(
        unit="7",
        example_id="7|2026-03-17T12:00:00",
        decision_timestamp=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        benchmark_key="steam-trap-regression",
        benchmark_version_id="version-id",
        benchmark_version_number=3,
        source_snapshot_id="snapshot-id",
        source_snapshot_content_sha256="a" * 64,
        source_kind="mongo",
        raw_captured_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        raw_window_start=datetime(2025, 3, 17, 12, 0, tzinfo=timezone.utc),
        raw_window_end=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        raw_known_gaps=[],
        raw_artifacts=[artifact.model_dump(mode="json") for artifact in artifacts],
        example_metadata={"steam_trap_type": "Float"},
    )


def test_retriever_decodes_frozen_parquet_and_alarm_artifacts() -> None:
    """Build the portable pipeline payload without MongoDB or local snapshots."""
    telemetry, alarms, artifacts = _evidence()
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    payload = retriever.retrieve(metadata=_metadata(artifacts))

    assert payload["example_id"] == "7|2026-03-17T12:00:00"
    assert payload["source_snapshot_id"] == "snapshot-id"
    assert payload["decision_timestamp"] == datetime(2026, 3, 17, 12, 0)
    assert payload["selected_alarm"]["detected_at"] == datetime(2026, 3, 17, 12, 0)
    assert payload["selected_alarm"]["source_detected_at"] == datetime(
        2026, 3, 17, 12, 0
    )
    assert payload["temperature_history"][0]["steam_temperature"] == 130.0


def test_retriever_projects_selected_alarm_with_source_subsecond_precision() -> None:
    """Reconcile publication precision and censor eventual resolution state."""
    telemetry, alarms, artifacts = _evidence(
        alarm_records=[
            {
                "kind": "selected_alarm",
                "alarm": {
                    "alarm_id": "alarm-1",
                    "detected_at": "2026-03-17T12:00:00.374000+00:00",
                    "resolved_at": "2026-03-18T12:00:00.453000+00:00",
                },
            }
        ]
    )
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    payload = retriever.retrieve(metadata=_metadata(artifacts))

    assert payload["selected_alarm"]["source_detected_at"] == datetime(
        2026, 3, 17, 12, 0, 0, 374000
    )
    assert payload["selected_alarm"]["detected_at"] == datetime(
        2026, 3, 17, 12, 0
    )
    assert payload["selected_alarm"]["resolved_at"] is None


class _Download:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def readall(self) -> bytes:
        return self._content


class _Container:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def download_blob(self, key: str) -> _Download:
        _ = key
        return _Download(self._content)


def test_blob_store_rejects_content_that_differs_from_frozen_hash() -> None:
    """Fail closed when Blob content no longer matches benchmark publication."""
    expected = b"expected"
    artifact = _artifact(
        "alarms", "snapshot/alarms.jsonl", "application/json", expected
    )
    store = AzureBlobEvidenceStore(container_client=_Container(b"tampered"))

    with pytest.raises(ValueError, match="byte-size mismatch|checksum mismatch"):
        store.read_verified(artifact)


def test_blob_store_rejects_same_size_content_with_wrong_checksum() -> None:
    """Enforce content identity even when a replacement has the same byte size."""
    expected = b"expected"
    artifact = _artifact(
        "alarms", "snapshot/alarms.jsonl", "application/json", expected
    )
    store = AzureBlobEvidenceStore(container_client=_Container(b"tampered"))

    with pytest.raises(ValueError, match="checksum mismatch"):
        store.read_verified(artifact)


def test_retriever_rejects_telemetry_after_benchmark_decision_timestamp() -> None:
    """Enforce the published example's decision point as the hard evidence cutoff."""
    telemetry, alarms, artifacts = _evidence(
        telemetry_timestamp="2026-03-17T12:00:01+00:00"
    )
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    with pytest.raises(ValueError, match="extends beyond the decision timestamp"):
        retriever.retrieve(metadata=_metadata(artifacts))


@pytest.mark.parametrize("kind", ["selected_alarm", "sensor_alarm"])
def test_retriever_rejects_alarm_detected_after_decision_timestamp(
    kind: str,
) -> None:
    """Do not expose selected or historical alarms created after the cutoff."""
    records: list[dict[str, object]] = [
        {
            "kind": "selected_alarm",
            "alarm": {
                "alarm_id": "alarm-1",
                "detected_at": "2026-03-17T12:00:00+00:00",
            },
        }
    ]
    if kind == "selected_alarm":
        records[0]["alarm"] = {
            "alarm_id": "alarm-1",
            "detected_at": "2026-03-17T12:00:01+00:00",
        }
    else:
        records.append(
            {
                "kind": "sensor_alarm",
                "alarm": {
                    "alarm_id": "alarm-2",
                    "detected_at": "2026-03-17T12:00:01+00:00",
                },
            }
        )
    telemetry, alarms, artifacts = _evidence(alarm_records=records)
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    with pytest.raises(ValueError, match="alarm.*beyond the decision timestamp"):
        retriever.retrieve(metadata=_metadata(artifacts))


def test_retriever_censors_historical_alarm_resolution_after_cutoff() -> None:
    """A pre-cutoff alarm remains visible without its post-cutoff resolution."""
    telemetry, alarms, artifacts = _evidence(
        alarm_records=[
            {
                "kind": "selected_alarm",
                "alarm": {
                    "alarm_id": "alarm-1",
                    "detected_at": "2026-03-17T12:00:00+00:00",
                },
            },
            {
                "kind": "sensor_alarm",
                "alarm": {
                    "alarm_id": "alarm-2",
                    "detected_at": "2026-03-16T12:00:00+00:00",
                    "resolved_at": "2026-03-17T12:00:01+00:00",
                },
            },
        ]
    )
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    payload = retriever.retrieve(metadata=_metadata(artifacts))

    assert payload["sensor_alarms"][0]["detected_at"] == datetime(
        2026, 3, 16, 12, 0
    )
    assert payload["sensor_alarms"][0]["resolved_at"] is None


def test_retriever_rejects_historical_alarm_before_frozen_window() -> None:
    """Do not return alarm evidence outside the published lookback window."""
    telemetry, alarms, artifacts = _evidence(
        alarm_records=[
            {
                "kind": "selected_alarm",
                "alarm": {
                    "alarm_id": "alarm-1",
                    "detected_at": "2026-03-17T12:00:00+00:00",
                },
            },
            {
                "kind": "sensor_alarm",
                "alarm": {
                    "alarm_id": "alarm-2",
                    "detected_at": "2025-03-17T11:59:59+00:00",
                },
            },
        ]
    )
    retriever = SpiraxFrozenEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore({"telemetry": telemetry, "alarms": alarms})
    )

    with pytest.raises(ValueError, match="outside the frozen evidence window"):
        retriever.retrieve(metadata=_metadata(artifacts))
