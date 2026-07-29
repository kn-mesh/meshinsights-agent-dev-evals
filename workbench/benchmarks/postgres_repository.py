"""Read published benchmarks directly from the labeling product's Azure PostgreSQL."""

from __future__ import annotations

import os
import hashlib
import json
from collections.abc import Callable
from typing import Any, Protocol, cast

import psycopg
from azure.identity import DefaultAzureCredential
from psycopg.rows import dict_row

from workbench.benchmarks.models import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
)

_SEARCH_PATH_OPTIONS = "-c search_path=app,public"
_CONNECT_TIMEOUT_SECONDS = 10
_AZURE_POSTGRES_TOKEN_SCOPE = (
    "https://ossrdbms-aad.database.windows.net/.default"
)

_PUBLISHED_BENCHMARK_CATALOG_SQL = """
select
  p.project_key,
  b.benchmark_key,
  b.name as benchmark_name,
  bv.id as benchmark_version_id,
  bv.version_number,
  bv.published_at,
  bv.source_state_sha256,
  count(bve.example_id)::integer as example_count
from projects p
join benchmarks b on b.project_id = p.id
join benchmark_versions bv on bv.benchmark_id = b.id
join benchmark_version_examples bve
  on bve.project_id = p.id
 and bve.benchmark_version_id = bv.id
where p.project_key = %(project_key)s
  and bv.published_at is not null
group by
  p.project_key,
  b.benchmark_key,
  b.name,
  bv.id,
  bv.version_number,
  bv.published_at,
  bv.source_state_sha256
order by lower(b.name), b.benchmark_key, bv.version_number desc
"""

_PUBLISHED_BENCHMARK_SQL = """
with selected_version as (
  select
    bv.id,
    bv.project_id,
    bv.version_number,
    bv.published_at,
    bv.source_state_sha256,
    bv.published_contract_schema_version,
    b.benchmark_key,
    b.name as benchmark_name,
    p.project_key,
    ucc.eval_label_fields
  from projects p
  join benchmarks b on b.project_id = p.id
  join benchmark_versions bv on bv.benchmark_id = b.id
  join use_case_configs ucc on ucc.project_id = p.id
  where p.project_key = %(project_key)s
    and b.benchmark_key = %(benchmark_key)s
    and bv.published_at is not null
    and (
      %(version_number)s::integer is null
      or bv.version_number = %(version_number)s
    )
  order by bv.version_number desc
  limit 1
)
select
  sv.project_key,
  sv.benchmark_key,
  sv.benchmark_name,
  sv.id as benchmark_version_id,
  sv.version_number,
  sv.published_at,
  sv.source_state_sha256,
  sv.published_contract_schema_version,
  sv.eval_label_fields,
  bve.example_id,
  bve.unit_id,
  bve.decision_timestamp,
  bve.approved_label_payload,
  bve.label_schema_version_id,
  lsv.schema_key as label_schema_key,
  lsv.version as label_schema_version,
  lsv.schema as label_schema,
  bve.example_metadata,
  bve.source_snapshot_id,
  bve.raw_snapshot_content_sha256,
  bve.raw_source_kind,
  bve.raw_captured_at,
  bve.raw_window_start,
  bve.raw_window_end,
  bve.raw_known_gaps,
  bve.raw_artifacts,
  bve.verification_source,
  bve.verification_note,
  bve.verification_recorded_at,
  bve.source_verification_sha256,
  bve.source_verification_schema_key,
  bve.source_verification_schema_version,
  bve.source_verification_fields,
  bve.selected_review_event_id,
  bve.reviewer_coverage
from selected_version sv
join benchmark_version_examples bve
  on bve.project_id = sv.project_id
 and bve.benchmark_version_id = sv.id
left join label_schema_versions lsv
  on lsv.project_id = bve.project_id
 and lsv.id = bve.label_schema_version_id
order by bve.example_id
"""


class BenchmarkRepository(Protocol):
    """Read-only published benchmark source used by eval orchestration."""

    def load_published_version(
        self,
        *,
        benchmark_key: str,
        version_number: int | None = None,
    ) -> BenchmarkVersion: ...

    def list_published_versions(self) -> tuple[PublishedBenchmarkVersionSummary, ...]:
        """List published versions available to the configured project."""
        ...


class AzurePostgresBenchmarkRepository:
    """Load immutable published benchmark versions from Azure PostgreSQL."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        project_key: str | None = None,
        host: str | None = None,
        database: str | None = None,
        user: str | None = None,
        credential: Any | None = None,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Resolve required hosted configuration without any local fallback."""
        self._database_url = (database_url or os.getenv("DATABASE_URL", "")).strip()
        self._host = (host or os.getenv("AZURE_POSTGRES_HOST", "")).strip()
        self._database = (
            database or os.getenv("AZURE_POSTGRES_DATABASE", "")
        ).strip()
        self._user = (user or os.getenv("AZURE_POSTGRES_USER", "")).strip()
        self.project_key = (project_key or os.getenv("APP_PROJECT_KEY", "")).strip()
        entra_values = (self._host, self._database, self._user)
        if any(entra_values) and not all(entra_values):
            raise ValueError(
                "AZURE_POSTGRES_HOST, AZURE_POSTGRES_DATABASE, and "
                "AZURE_POSTGRES_USER are all required for Entra retrieval."
            )
        if self._host and not self._host.endswith(".postgres.database.azure.com"):
            raise ValueError(
                "AZURE_POSTGRES_HOST must be an Azure PostgreSQL hostname."
            )
        if not self._host and not self._database_url and connection_factory is None:
            raise ValueError(
                "Azure PostgreSQL Entra settings or DATABASE_URL are required "
                "for benchmark retrieval."
            )
        if not self.project_key:
            raise ValueError("APP_PROJECT_KEY or project_key is required.")
        self._credential = credential or (
            DefaultAzureCredential() if self._host else None
        )
        self._connection_factory = connection_factory or self._connect

    def _connect(self) -> psycopg.Connection[Any]:
        if self._host:
            assert self._credential is not None
            access_token = self._credential.get_token(
                _AZURE_POSTGRES_TOKEN_SCOPE
            ).token
            return psycopg.connect(
                host=self._host,
                dbname=self._database,
                user=self._user,
                password=access_token,
                sslmode="require",
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                row_factory=cast(Any, dict_row),
                options=_SEARCH_PATH_OPTIONS,
            )
        return psycopg.connect(
            self._database_url,
            connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            row_factory=cast(Any, dict_row),
            options=_SEARCH_PATH_OPTIONS,
        )

    def load_published_version(
        self,
        *,
        benchmark_key: str,
        version_number: int | None = None,
    ) -> BenchmarkVersion:
        """Load one explicit version, or the latest published version when omitted."""
        normalized_key = benchmark_key.strip()
        if not normalized_key:
            raise ValueError("benchmark_key must not be empty.")
        if version_number is not None and version_number < 1:
            raise ValueError("version_number must be at least 1.")
        with self._connection_factory() as connection:
            connection.execute("set transaction read only")
            rows = connection.execute(
                _PUBLISHED_BENCHMARK_SQL,
                {
                    "project_key": self.project_key,
                    "benchmark_key": normalized_key,
                    "version_number": version_number,
                },
            ).fetchall()
        if not rows:
            suffix = "latest" if version_number is None else f"v{version_number}"
            raise ValueError(
                f"Published benchmark {self.project_key}/{normalized_key} ({suffix}) "
                "was not found."
            )
        return _build_benchmark_version(
            _normalize_trusted_postgres_rows([dict(row) for row in rows])
        )

    def list_published_versions(
        self,
    ) -> tuple[PublishedBenchmarkVersionSummary, ...]:
        """Return the Azure-hosted benchmark catalog for terminal selection."""
        with self._connection_factory() as connection:
            connection.execute("set transaction read only")
            rows = connection.execute(
                _PUBLISHED_BENCHMARK_CATALOG_SQL,
                {"project_key": self.project_key},
            ).fetchall()
        return tuple(
            PublishedBenchmarkVersionSummary.model_validate(
                {
                    **dict(row),
                    "benchmark_version_id": str(row["benchmark_version_id"]),
                }
            )
            for row in rows
        )


def _build_benchmark_version(
    rows: list[dict[str, Any]],
) -> BenchmarkVersion:
    """Strictly normalize supported published-contract rows from any read adapter."""
    if not rows:
        raise ValueError("Cannot build a benchmark version without rows.")
    first = rows[0]
    raw_contract_version = first.get("published_contract_schema_version")
    if raw_contract_version is None:
        raise ValueError(
            "Published benchmark response is missing its contract schema version."
        )
    contract_schema_version = int(raw_contract_version)
    if contract_schema_version not in {2, 3}:
        raise ValueError(
            f"Unsupported published benchmark contract version "
            f"{contract_schema_version}; expected 2 or 3."
        )
    version_fields = (
        "project_key",
        "benchmark_key",
        "benchmark_name",
        "benchmark_version_id",
        "version_number",
        "published_at",
        "source_state_sha256",
        "published_contract_schema_version",
        "eval_label_fields",
    )
    for row in rows[1:]:
        for key in version_fields:
            if row.get(key) != first.get(key):
                raise ValueError(
                    f"Published benchmark field {key!r} is inconsistent across examples."
                )
    eval_fields_raw = first.get("eval_label_fields")
    eval_field_hints = (
        [str(field) for field in eval_fields_raw]
        if isinstance(eval_fields_raw, list)
        else []
    )
    examples: list[BenchmarkExample] = []
    label_schemas: dict[str, dict[str, Any]] = {}
    for row in rows:
        label_payload = row.get("approved_label_payload")
        if not isinstance(label_payload, dict):
            raise ValueError("Published approved_label_payload must be an object.")
        schema = row.get("label_schema")
        if not isinstance(schema, dict):
            raise ValueError("Published label schema must be an object.")
        schema_id = str(row.get("label_schema_version_id") or "").strip()
        if not schema_id:
            raise ValueError("Published example is missing label schema identity.")
        derived_schema_sha256 = hashlib.sha256(
            json.dumps(
                schema,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        published_schema_sha256 = row.get("label_schema_content_sha256")
        if published_schema_sha256 is None:
            raise ValueError(
                "Published benchmark contract is missing a label-schema hash."
            )
        schema_sha256 = str(published_schema_sha256).strip()
        if schema_sha256 != derived_schema_sha256:
            raise ValueError(
                f"Published label schema hash does not match for {schema_id}."
            )
        existing_schema = label_schemas.get(schema_id)
        if existing_schema is not None and existing_schema != {
            "schema_version_id": schema_id,
            "schema_key": row["label_schema_key"],
            "version": row["label_schema_version"],
            "schema": schema,
            "content_sha256": schema_sha256,
        }:
            raise ValueError(
                f"Published label schema {schema_id} is inconsistent across examples."
            )
        label_schemas[schema_id] = {
            "schema_version_id": schema_id,
            "schema_key": row["label_schema_key"],
            "version": row["label_schema_version"],
            "schema": schema,
            "content_sha256": schema_sha256,
        }
        examples.append(
            BenchmarkExample.model_validate(
                {
                    "example_id": row["example_id"],
                    "unit_id": row["unit_id"],
                    "decision_timestamp": row["decision_timestamp"],
                    "approved_label_payload": label_payload,
                    "label_schema_version_id": schema_id,
                    "example_metadata": row.get("example_metadata") or {},
                    "source_snapshot_id": row["source_snapshot_id"],
                    "raw_snapshot_content_sha256": row[
                        "raw_snapshot_content_sha256"
                    ],
                    "raw_source_kind": row["raw_source_kind"],
                    "raw_captured_at": row["raw_captured_at"],
                    "raw_window_start": row.get("raw_window_start"),
                    "raw_window_end": row.get("raw_window_end"),
                    "raw_known_gaps": row.get("raw_known_gaps") or [],
                    "raw_artifacts": row.get("raw_artifacts") or [],
                    "published_review_context": _published_review_context(row),
                }
            )
        )
    return BenchmarkVersion.model_validate(
        {
            "project_key": first["project_key"],
            "benchmark_key": first["benchmark_key"],
            "benchmark_name": first["benchmark_name"],
            "benchmark_version_id": str(first["benchmark_version_id"]),
            "version_number": first["version_number"],
            "published_at": first["published_at"],
            "source_state_sha256": first.get("source_state_sha256"),
            "published_contract_schema_version": contract_schema_version,
            "eval_label_field_hints": eval_field_hints,
            "label_schemas": list(label_schemas.values()),
            "examples": examples,
        }
    )


def _published_review_context(row: dict[str, Any]) -> dict[str, Any]:
    coverage = row.get("reviewer_coverage")
    if coverage is None:
        coverage = []
    if not isinstance(coverage, list):
        raise ValueError("Published reviewer coverage must be an array.")
    if int(row.get("published_contract_schema_version") or 0) >= 3 and any(
        not isinstance(item, dict) or not str(item.get("note") or "").strip()
        for item in coverage
    ):
        raise ValueError(
            "Published contract v3 requires every reviewer coverage note."
        )
    selected_review_event_id = str(row.get("selected_review_event_id") or "")
    reviewer_coverage = [
        {
            **item,
            "is_selected_label_revision": (
                str(item.get("review_event_id") or "") == selected_review_event_id
            ),
        }
        for item in coverage
        if isinstance(item, dict)
    ]
    if len(reviewer_coverage) != len(coverage):
        raise ValueError("Published reviewer coverage entries must be objects.")
    source = row.get("verification_source")
    verification = None
    if source is not None:
        verification = {
            "source": source,
            "note": row.get("verification_note"),
            "recorded_at": row.get("verification_recorded_at"),
            "source_content_sha256": row.get("source_verification_sha256"),
            "context_schema_key": row.get("source_verification_schema_key"),
            "context_schema_version": row.get(
                "source_verification_schema_version"
            ),
            "source_fields": row.get("source_verification_fields"),
        }
    return {"reviewer_coverage": reviewer_coverage, "verification": verification}


def _normalize_trusted_postgres_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Adapt trusted database rows to the strict published response contract."""
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        schema = row.get("label_schema")
        if not isinstance(schema, dict):
            raise ValueError("Published label schema must be an object.")
        if row.get("published_contract_schema_version") is None:
            raise ValueError(
                "Published benchmark row is missing its contract schema version."
            )
        row["label_schema_content_sha256"] = hashlib.sha256(
            json.dumps(
                schema,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        normalized.append(row)
    return normalized
