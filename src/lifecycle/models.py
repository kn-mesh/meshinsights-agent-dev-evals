"""Typed JSON contracts for the derived local lifecycle catalog."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EntityKind = Literal["run", "version", "comparison"]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogFinding(_FrozenModel):
    code: str
    message: str
    path: str | None = None
    entity_kind: EntityKind | None = None
    entity_id: str | None = None


class CatalogReference(_FrozenModel):
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation: str


class RunCatalogEntry(_FrozenModel):
    run_id: str
    path: str
    created_at_utc: str | None = None
    result_status: Literal["materialized", "incomplete"]
    agent_version_id: str
    agent_lifecycle_state_at_run: str | None = None
    pipeline_path: str | None = None
    benchmark_key: str | None = None
    benchmark_version: int | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    planned_attempts: int = 0
    recorded_attempts: int = 0
    review_status: str
    diagnosis_count: int = 0
    file_count: int = 0
    bytes: int = 0


class VersionCatalogEntry(_FrozenModel):
    agent_version_id: str
    manifest_sha256: str
    lifecycle_state: Literal["candidate", "promoted"]
    manifest_path: str | None = None
    aliases: tuple[str, ...] = ()
    promotion_ids: tuple[str, ...] = ()
    source_run_ids: tuple[str, ...] = ()
    associated_run_ids: tuple[str, ...] = ()
    global_cas_objects: tuple[str, ...] = ()


class ComparisonCatalogEntry(_FrozenModel):
    comparison_id: str
    manifest_path: str
    result_path: str | None = None
    run_ids: tuple[str, ...]
    varying_dimensions: tuple[str, ...] = ()
    file_count: int = 0
    bytes: int = 0


class LifecycleCatalog(_FrozenModel):
    catalog_schema_version: int = 1
    project_root: str
    runs: tuple[RunCatalogEntry, ...]
    versions: tuple[VersionCatalogEntry, ...]
    comparisons: tuple[ComparisonCatalogEntry, ...]
    references: tuple[CatalogReference, ...]
    findings: tuple[CatalogFinding, ...]


class PlannedPath(_FrozenModel):
    path: str
    kind: Literal["file", "directory"]
    file_count: int
    bytes: int
    content_sha256: str
    reason: str


class DeletionPlan(_FrozenModel):
    deletion_plan_schema_version: int = 1
    target_kind: EntityKind
    target_id: str
    plan_sha256: str
    paths: tuple[PlannedPath, ...]
    warnings: tuple[str, ...]
    file_count: int
    bytes: int


class LifecycleOperation(_FrozenModel):
    lifecycle_operation_schema_version: int = 1
    operation_id: str
    state: Literal[
        "staging",
        "quarantined",
        "restoring",
        "restored",
        "purging",
        "purged",
    ]
    target_kind: EntityKind
    target_id: str
    plan_sha256: str
    paths: tuple[PlannedPath, ...]
    warnings: tuple[str, ...]
    created_at_utc: str
    updated_at_utc: str
