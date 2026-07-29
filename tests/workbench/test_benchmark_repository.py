"""Tests for published benchmark loading from Azure PostgreSQL rows."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from unittest.mock import Mock

import pytest

from workbench.benchmarks.postgres_repository import (
    AzurePostgresBenchmarkRepository,
    _PUBLISHED_BENCHMARK_SQL,
    _build_benchmark_version,
    _normalize_trusted_postgres_rows,
)


class _Rows:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Token:
    token = "entra-access-token"


class _Credential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def get_token(self, *scopes: str, **kwargs: Any) -> _Token:
        _ = kwargs
        self.scopes.extend(scopes)
        return _Token()


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
        "schema_key": "pump-failure-label",
        "version": "v1",
        "fields": [
            {"key": "classification", "values": ["Healthy", "Failure"]},
            {"key": "root_cause", "values": ["Closed Failure"]},
        ],
    }
    return {
        "project_key": "acme-pumps",
        "benchmark_key": "steam-trap-regression",
        "benchmark_name": "Pump Failure Regression",
        "benchmark_version_id": "version-id",
        "version_number": 2,
        "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "source_state_sha256": "d" * 64,
        "published_contract_schema_version": 2,
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
        "label_schema_key": "pump-failure-label",
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
        "verification_source": "operator_feedback",
        "verification_note": "Confirmed by customer.",
        "verification_recorded_at": datetime(
            2026, 3, 19, tzinfo=timezone.utc
        ),
        "source_verification_sha256": "e" * 64,
        "source_verification_schema_key": "pump_customer_verification",
        "source_verification_schema_version": "1",
        "source_verification_fields": {
            "failure_cause": "Trap failed closed",
            "action_to_resolve": "Replaced the trap",
        },
        "selected_review_event_id": "review-event-a",
        "reviewer_coverage": [
            {
                "review_event_id": "review-event-a",
                "label_revision": 2,
                "reviewer_user_id": "reviewer-user-a",
                "reviewer_display_name": "Alex Labeler",
                "reviewer_project_role": "domain_reviewer",
                "submitted_at": datetime(
                    2026, 3, 18, 8, tzinfo=timezone.utc
                ),
            },
            {
                "review_event_id": "review-event-b",
                "label_revision": 1,
                "reviewer_user_id": "reviewer-user-b",
                "reviewer_display_name": "Blair Reviewer",
                "reviewer_project_role": "domain_reviewer",
                "submitted_at": datetime(
                    2026, 3, 18, 7, tzinfo=timezone.utc
                ),
            }
        ],
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
        project_key="acme-pumps",
        connection_factory=lambda: connection,
    )

    benchmark = repository.load_published_version(
        benchmark_key="steam-trap-regression", version_number=2
    )

    assert connection.parameters == {
        "project_key": "acme-pumps",
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
    review_context = benchmark.examples[0].published_review_context
    assert review_context is not None
    reviewer = review_context.reviewer_coverage[0]
    assert reviewer.reviewer_display_name == "Alex Labeler"
    assert reviewer.label_revision == 2
    assert reviewer.is_selected_label_revision is True
    assert review_context.reviewer_coverage[1].is_selected_label_revision is False
    assert "explanation" not in reviewer.model_dump()
    assert "review_events" not in _PUBLISHED_BENCHMARK_SQL
    assert review_context.verification is not None
    assert review_context.verification.source == "operator_feedback"
    assert review_context.verification.source_fields == {
        "failure_cause": "Trap failed closed",
        "action_to_resolve": "Replaced the trap",
    }


def test_repository_uses_entra_token_for_hosted_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = _Credential()
    connection = Mock()
    connect = Mock(return_value=connection)
    monkeypatch.setattr("workbench.benchmarks.postgres_repository.psycopg.connect", connect)
    repository = AzurePostgresBenchmarkRepository(
        project_key="acme-pumps",
        host="benchmark.postgres.database.azure.com",
        database="label_benchmark",
        user="developer@example.com",
        credential=credential,
    )

    assert repository._connect() is connection

    assert credential.scopes == [
        "https://ossrdbms-aad.database.windows.net/.default"
    ]
    assert connect.call_args.kwargs["host"] == (
        "benchmark.postgres.database.azure.com"
    )
    assert connect.call_args.kwargs["dbname"] == "label_benchmark"
    assert connect.call_args.kwargs["user"] == "developer@example.com"
    assert connect.call_args.kwargs["password"] == "entra-access-token"
    assert connect.call_args.kwargs["sslmode"] == "require"


def test_repository_rejects_partial_or_non_azure_entra_configuration() -> None:
    with pytest.raises(ValueError, match="are all required"):
        AzurePostgresBenchmarkRepository(
            project_key="acme-pumps",
            host="benchmark.postgres.database.azure.com",
        )
    with pytest.raises(ValueError, match="Azure PostgreSQL hostname"):
        AzurePostgresBenchmarkRepository(
            project_key="acme-pumps",
            host="database.example.com",
            database="label_benchmark",
            user="developer@example.com",
        )


def test_repository_requests_latest_published_version_when_version_is_omitted() -> None:
    """Keep latest-version selection scoped to the explicit project and key."""
    connection = _Connection([_row()])
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="acme-pumps",
        connection_factory=lambda: connection,
    )

    benchmark = repository.load_published_version(
        benchmark_key="steam-trap-regression"
    )

    assert connection.parameters == {
        "project_key": "acme-pumps",
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
def test_strict_published_adapter_rejects_missing_publication_identity(
    missing_key: str, message: str
) -> None:
    rows = _normalize_trusted_postgres_rows([_row()])
    rows[0].pop(missing_key)

    with pytest.raises(ValueError, match=message):
        _build_benchmark_version(rows)


def test_strict_published_adapter_rejects_inconsistent_version_fields() -> None:
    rows = _normalize_trusted_postgres_rows([_row(), _row()])
    rows[1]["published_contract_schema_version"] = 3

    with pytest.raises(ValueError, match="inconsistent across examples"):
        _build_benchmark_version(rows)


def test_contract_v3_requires_and_preserves_reviewer_notes() -> None:
    row = _row()
    row["published_contract_schema_version"] = 3
    row["reviewer_coverage"] = [
        {**coverage, "note": f"Frozen explanation {index}."}
        for index, coverage in enumerate(row["reviewer_coverage"], start=1)
    ]

    benchmark = _build_benchmark_version(
        _normalize_trusted_postgres_rows([row])
    )

    assert benchmark.published_contract_schema_version == 3
    assert [
        reviewer.note
        for reviewer in benchmark.examples[0].published_review_context.reviewer_coverage
    ] == ["Frozen explanation 1.", "Frozen explanation 2."]

    row["reviewer_coverage"][0]["note"] = None
    with pytest.raises(ValueError, match="requires every reviewer coverage note"):
        _build_benchmark_version(_normalize_trusted_postgres_rows([row]))


def test_published_adapter_rejects_unknown_contract_version() -> None:
    row = _row()
    row["published_contract_schema_version"] = 4

    with pytest.raises(ValueError, match="expected 2 or 3"):
        _build_benchmark_version(_normalize_trusted_postgres_rows([row]))


def test_repository_loads_non_reference_units_and_artifact_kinds() -> None:
    """Keep the read-only repository boundary independent of use-case evidence."""
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
        "project_key": "acme-pumps",
        "benchmark_key": "steam-trap-regression",
        "benchmark_name": "Pump Failure Regression",
        "benchmark_version_id": "version-id",
        "version_number": 2,
        "published_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "source_state_sha256": "d" * 64,
        "example_count": 12,
    }
    connection = _Connection([catalog_row])
    repository = AzurePostgresBenchmarkRepository(
        database_url="postgresql://unused",
        project_key="acme-pumps",
        connection_factory=lambda: connection,
    )

    versions = repository.list_published_versions()

    assert connection.parameters == {"project_key": "acme-pumps"}
    assert len(versions) == 1
    assert versions[0].benchmark_key == "steam-trap-regression"
    assert versions[0].version_number == 2
    assert versions[0].example_count == 12
