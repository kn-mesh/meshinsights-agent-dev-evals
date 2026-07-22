"""Tests for published benchmark loading from Azure PostgreSQL rows."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import pytest

from src.benchmarks.postgres_repository import (
    AzurePostgresBenchmarkRepository,
    _build_benchmark_version,
    _normalize_trusted_postgres_rows,
)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.parameters: dict[str, object] | None = None

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *args: object) -> None:
        _ = args

    def execute(
        self, query: str, parameters: dict[str, object] | None = None
    ) -> "_Connection | _Rows":
        if query == "set transaction read only":
            return self
        self.parameters = parameters
        return _Rows(self.rows)


def _row() -> dict[str, Any]:
    label_schema = {
        "schema_key": "spirax-steam-trap-label",
        "version": "v1",
        "fields": [
            {"key": "classification", "values": ["Healthy", "Failure"]},
            {"key": "root_cause", "values": ["Closed Failure"]},
        ],
    }
    return {
        "project_key": "spirax-pulse",
        "benchmark_key": "steam-trap-regression",
        "benchmark_name": "Steam Trap Regression",
        "benchmark_version_id": "version-id",
        "version_number": 2,
        "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "source_state_sha256": "d" * 64,
        "eval_label_fields": ["classification", "root_cause"],
        "example_id": "7|2026-03-17T12:00:00",
        "unit_id": "7",
        "decision_timestamp": datetime(2026, 3, 17, 12, tzinfo=timezone.utc),
        "approved_label_payload": {
            "classification": "Failure",
            "root_cause": "Closed Failure",
            "non_eval_note": "ignored",
        },
        "label_schema_version_id": "schema-v1",
        "label_schema_key": "spirax-steam-trap-label",
        "label_schema_version": "v1",
        "label_schema": label_schema,
        "example_metadata": {"sensor_id": "7"},
        "source_snapshot_id": "snapshot-id",
        "raw_snapshot_content_sha256": "c" * 64,
        "raw_source_kind": "mongo",
        "raw_captured_at": datetime(2026, 3, 18, tzinfo=timezone.utc),
        "raw_window_start": datetime(2025, 3, 17, tzinfo=timezone.utc),
        "raw_window_end": datetime(2026, 3, 17, 12, tzinfo=timezone.utc),
        "raw_known_gaps": [],
        "raw_artifacts": [
            {
                "artifact_kind": "telemetry",
                "object_key": "snapshot/telemetry.parquet",
                "content_type": "application/parquet",
                "byte_size": 1,
                "content_sha256": "a" * 64,
            },
            {
                "artifact_kind": "alarms",
                "object_key": "snapshot/alarms.jsonl",
                "content_type": "application/x-ndjson",
                "byte_size": 1,
                "content_sha256": "b" * 64,
            },
        ],
    }


def test_repository_loads_full_labels_schema_and_frozen_manifest() -> None:
    connection = _Connection([_row()])
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="spirax-pulse",
        connection_factory=lambda: connection,
    )

    benchmark = repository.load_published_version(
        benchmark_key="steam-trap-regression", version_number=2
    )

    assert connection.parameters == {
        "project_key": "spirax-pulse",
        "benchmark_key": "steam-trap-regression",
        "version_number": 2,
    }
    assert benchmark.version_number == 2
    assert benchmark.examples[0].approved_label_payload == {
        "classification": "Failure",
        "root_cause": "Closed Failure",
        "non_eval_note": "ignored",
    }
    assert benchmark.examples[0].label_schema_version_id == "schema-v1"
    expected_hash = hashlib.sha256(
        json.dumps(
            _row()["label_schema"],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert benchmark.label_schemas[0].content_sha256 == expected_hash
    assert benchmark.examples[0].source_snapshot_id == "snapshot-id"
    assert benchmark.examples[0].unit_id == "7"


def test_repository_requests_latest_published_version_when_version_is_omitted() -> None:
    """Keep latest-version selection scoped to the explicit project and key."""
    connection = _Connection([_row()])
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="spirax-pulse",
        connection_factory=lambda: connection,
    )

    benchmark = repository.load_published_version(
        benchmark_key="steam-trap-regression"
    )

    assert connection.parameters == {
        "project_key": "spirax-pulse",
        "benchmark_key": "steam-trap-regression",
        "version_number": None,
    }
    assert benchmark.version_number == 2


@pytest.mark.parametrize(
    ("missing_key", "message"),
    [
        ("published_contract_schema_version", "contract schema version"),
        ("label_schema_content_sha256", "label-schema hash"),
    ],
)
def test_strict_v2_adapter_rejects_missing_publication_identity(
    missing_key: str, message: str
) -> None:
    rows = _normalize_trusted_postgres_rows([_row()])
    rows[0].pop(missing_key)

    with pytest.raises(ValueError, match=message):
        _build_benchmark_version(rows)


def test_strict_v2_adapter_rejects_inconsistent_version_fields() -> None:
    rows = _normalize_trusted_postgres_rows([_row(), _row()])
    rows[1]["published_contract_schema_version"] = 3

    with pytest.raises(ValueError, match="inconsistent across examples"):
        _build_benchmark_version(rows)


def test_repository_loads_non_spirax_units_and_artifact_kinds() -> None:
    """Keep the read-only repository boundary independent of Pulse evidence."""
    row = _row()
    schema = {
        "schema_key": "pump-decision-label",
        "version": "v1",
        "fields": [{"key": "classification", "values": ["normal", "fault"]}],
    }
    row.update(
        {
            "project_key": "acme-pumps",
            "benchmark_key": "pump-failures",
            "benchmark_name": "Pump Failures",
            "example_id": "pump-A|2026-03-17T12:00:00Z",
            "unit_id": "pump-A",
            "approved_label_payload": {"classification": "fault"},
            "label_schema_key": "pump-decision-label",
            "label_schema": schema,
            "eval_label_fields": ["classification"],
            "example_metadata": {"site": "north"},
            "raw_source_kind": "historian",
            "raw_artifacts": [
                {
                    "artifact_kind": "vibration-spectrum",
                    "object_key": "snapshot/vibration.arrow",
                    "content_type": "application/vnd.apache.arrow.file",
                    "byte_size": 42,
                    "content_sha256": "e" * 64,
                }
            ],
        }
    )
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="acme-pumps",
        connection_factory=lambda: _Connection([row]),
    )

    benchmark = repository.load_published_version(
        benchmark_key="pump-failures", version_number=2
    )

    example = benchmark.examples[0]
    assert example.unit_id == "pump-A"
    assert example.example_metadata == {"site": "north"}
    assert [artifact.artifact_kind for artifact in example.raw_artifacts] == [
        "vibration-spectrum"
    ]


def test_repository_lists_published_versions_for_configured_project() -> None:
    """Retrieve lightweight Azure catalog rows before loading example payloads."""
    catalog_row = {
        "project_key": "spirax-pulse",
        "benchmark_key": "steam-trap-regression",
        "benchmark_name": "Steam Trap Regression",
        "benchmark_version_id": "version-id",
        "version_number": 2,
        "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "source_state_sha256": "d" * 64,
        "example_count": 12,
    }
    connection = _Connection([catalog_row])
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="spirax-pulse",
        connection_factory=lambda: connection,
    )

    versions = repository.list_published_versions()

    assert connection.parameters == {"project_key": "spirax-pulse"}
    assert len(versions) == 1
    assert versions[0].benchmark_key == "steam-trap-regression"
    assert versions[0].version_number == 2
    assert versions[0].example_count == 12
