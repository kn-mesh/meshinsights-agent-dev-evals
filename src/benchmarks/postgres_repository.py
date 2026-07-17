"""Read published benchmarks directly from the labeling product's Azure PostgreSQL."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol, cast

import psycopg
from psycopg.rows import dict_row

from src.benchmarks.models import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
)

_SEARCH_PATH_OPTIONS = "-c search_path=app,public"
_CONNECT_TIMEOUT_SECONDS = 10

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
  sv.eval_label_fields,
  bve.example_id,
  bve.unit_id,
  bve.decision_timestamp,
  bve.approved_label_payload,
  bve.example_metadata,
  bve.source_snapshot_id,
  bve.raw_snapshot_content_sha256,
  bve.raw_source_kind,
  bve.raw_captured_at,
  bve.raw_window_start,
  bve.raw_window_end,
  bve.raw_known_gaps,
  bve.raw_artifacts
from selected_version sv
join benchmark_version_examples bve
  on bve.project_id = sv.project_id
 and bve.benchmark_version_id = sv.id
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
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Resolve required hosted configuration without any local fallback."""
        self._database_url = (database_url or os.getenv("DATABASE_URL", "")).strip()
        self.project_key = (project_key or os.getenv("APP_PROJECT_KEY", "")).strip()
        if not self._database_url and connection_factory is None:
            raise ValueError("DATABASE_URL is required for benchmark retrieval.")
        if not self.project_key:
            raise ValueError("APP_PROJECT_KEY or project_key is required.")
        self._connection_factory = connection_factory or self._connect

    def _connect(self) -> psycopg.Connection[Any]:
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
        return _build_benchmark_version([dict(row) for row in rows])

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


def _build_benchmark_version(rows: list[dict[str, Any]]) -> BenchmarkVersion:
    """Normalize PostgreSQL rows into the immutable benchmark domain model."""
    if not rows:
        raise ValueError("Cannot build a benchmark version without rows.")
    first = rows[0]
    eval_fields_raw = first.get("eval_label_fields")
    eval_fields = (
        [str(field) for field in eval_fields_raw]
        if isinstance(eval_fields_raw, list)
        else ["classification"]
    )
    examples: list[BenchmarkExample] = []
    for row in rows:
        label_payload = row.get("approved_label_payload")
        if not isinstance(label_payload, dict):
            raise ValueError("Published approved_label_payload must be an object.")
        approved_labels = {
            field: str(label_payload[field])
            for field in eval_fields
            if field in label_payload and label_payload[field] is not None
        }
        examples.append(
            BenchmarkExample.model_validate(
                {
                    "example_id": row["example_id"],
                    "unit_id": row["unit_id"],
                    "decision_timestamp": row["decision_timestamp"],
                    "approved_labels": approved_labels,
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
            "examples": examples,
        }
    )
