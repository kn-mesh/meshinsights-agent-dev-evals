"""Tests for benchmark-frozen Azure Blob evidence retrieval."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timezone
import pandas as pd
import pytest

from src.benchmarks.models import SourceArtifact
from src.objects.pipeline_metadata import BenchmarkExamplePipelineMetadata
from src.retrievers.azure_blob_evidence_retriever import (
    AzureBlobBenchmarkEvidenceRetriever,
)
from src.storage.azure_blob import AzureBlobEvidenceStore


def _artifact(kind: str, key: str, content_type: str, content: bytes) -> SourceArtifact:
    return SourceArtifact(
        artifact_kind=kind,
        object_key=key,
        content_type=content_type,
        byte_size=len(content),
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


def _evidence(
    *, telemetry_timestamp: str = "2026-03-17T11:30:00+00:00"
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
    alarms = (
        json.dumps(
            {
                "kind": "selected_alarm",
                "alarm": {
                    "alarm_id": "alarm-1",
                    "sensor_id": 7,
                    "detected_at": "2026-03-17T12:00:00+00:00",
                    "alarm_type": "FDE",
                },
            }
        )
        + "\n"
    ).encode()
    artifacts = (
        _artifact("telemetry", "snapshot/telemetry.parquet", "application/parquet", telemetry),
        _artifact("alarms", "snapshot/alarms.jsonl", "application/x-ndjson", alarms),
    )
    return telemetry, alarms, artifacts


class _MemoryEvidenceStore:
    def __init__(self, content: dict[str, bytes]) -> None:
        self.content = content

    def read_verified(self, artifact: SourceArtifact) -> bytes:
        return self.content[artifact.artifact_kind]


def _metadata(artifacts: tuple[SourceArtifact, ...]) -> BenchmarkExamplePipelineMetadata:
    return BenchmarkExamplePipelineMetadata(
        unit="7",
        example_id="7|2026-03-17T12:00:00",
        sensor_id=7,
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
    retriever = AzureBlobBenchmarkEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore(
            {"telemetry": telemetry, "alarms": alarms}
        )
    )

    payload = retriever.retrieve(metadata=_metadata(artifacts))

    assert payload["example_id"] == "7|2026-03-17T12:00:00"
    assert payload["source_snapshot_id"] == "snapshot-id"
    assert payload["decision_timestamp"] == datetime(2026, 3, 17, 12, 0)
    assert payload["selected_alarm"]["detected_at"] == datetime(
        2026, 3, 17, 12, 0
    )
    assert payload["selected_alarm"]["source_detected_at"] == datetime(
        2026, 3, 17, 12, 0
    )
    assert payload["temperature_history"][0]["steam_temperature"] == 130.0


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
    artifact = _artifact("alarms", "snapshot/alarms.jsonl", "application/json", expected)
    store = AzureBlobEvidenceStore(container_client=_Container(b"tampered"))

    with pytest.raises(ValueError, match="byte-size mismatch|checksum mismatch"):
        store.read_verified(artifact)


def test_blob_store_rejects_same_size_content_with_wrong_checksum() -> None:
    """Enforce content identity even when a replacement has the same byte size."""
    expected = b"expected"
    artifact = _artifact("alarms", "snapshot/alarms.jsonl", "application/json", expected)
    store = AzureBlobEvidenceStore(container_client=_Container(b"tampered"))

    with pytest.raises(ValueError, match="checksum mismatch"):
        store.read_verified(artifact)


def test_retriever_rejects_telemetry_after_benchmark_decision_timestamp() -> None:
    """Enforce the published example's decision point as the hard evidence cutoff."""
    telemetry, alarms, artifacts = _evidence(
        telemetry_timestamp="2026-03-17T12:00:01+00:00"
    )
    retriever = AzureBlobBenchmarkEvidenceRetriever(
        evidence_store=_MemoryEvidenceStore(
            {"telemetry": telemetry, "alarms": alarms}
        )
    )

    with pytest.raises(ValueError, match="extends beyond the decision timestamp"):
        retriever.retrieve(metadata=_metadata(artifacts))
