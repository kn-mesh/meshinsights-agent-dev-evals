"""Preflight project, pipeline, and published benchmark compatibility."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.benchmarks.models import BenchmarkExample, BenchmarkVersion
from src.project_bootstrap.models import ProjectContract, PublishedBenchmarkSpec


PROJECT_CONTRACT_FILE = "workbench.project.json"


class PipelineBenchmarkContract(BaseModel):
    """Use-case pipeline requirements checked before pipeline construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    published_contract_schema_version: int = Field(ge=2)
    evidence_recipe_id: str = Field(min_length=1)
    source_snapshot_contract: str = Field(min_length=1)
    required_artifact_kinds: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_artifact_kinds(self) -> Self:
        normalized = tuple(kind.strip() for kind in self.required_artifact_kinds)
        if any(not kind for kind in normalized):
            raise ValueError("Required artifact kinds cannot be empty.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Required artifact kinds must be unique.")
        object.__setattr__(self, "required_artifact_kinds", normalized)
        return self


def load_project_contract(start_path: str | Path) -> ProjectContract:
    """Load the nearest generated project contract, failing closed if absent."""
    start = Path(start_path).resolve()
    directory = start if start.is_dir() else start.parent
    for candidate_root in (directory, *directory.parents):
        candidate = candidate_root / PROJECT_CONTRACT_FILE
        if candidate.is_file():
            return ProjectContract.model_validate_json(
                candidate.read_text(encoding="utf-8")
            )
    raise ValueError(
        f"Cannot find {PROJECT_CONTRACT_FILE} from {start}; initialize or "
        "configure this Agent Workbench project before execution."
    )


def load_pipeline_benchmark_contract(
    pipeline_config: Mapping[str, Any],
) -> PipelineBenchmarkContract:
    """Validate the source-controlled compatibility declaration in pipeline YAML."""
    payload = pipeline_config.get("benchmark_contract")
    if not isinstance(payload, Mapping):
        raise ValueError("Pipeline YAML must define a benchmark_contract mapping.")
    return PipelineBenchmarkContract.model_validate(dict(payload))


def preflight_pipeline_benchmark_contract(
    *,
    pipeline_config: Mapping[str, Any],
    benchmark: BenchmarkVersion,
    examples: Iterable[BenchmarkExample],
    start_path: str | Path,
    project_contract: ProjectContract | None = None,
) -> PipelineBenchmarkContract:
    """Reject incompatible local declarations and frozen publication data."""
    pipeline = load_pipeline_benchmark_contract(pipeline_config)
    project = project_contract or load_project_contract(start_path)
    if benchmark.project_key != project.benchmark_studio.project_key:
        raise ValueError(
            "Published benchmark project does not match workbench.project.json: "
            f"{benchmark.project_key!r} != {project.benchmark_studio.project_key!r}."
        )
    configured = find_configured_published_benchmark(project, benchmark)
    schema_versions = {
        benchmark.published_contract_schema_version,
        configured.published_contract_schema_version,
        pipeline.published_contract_schema_version,
    }
    if len(schema_versions) != 1:
        raise ValueError(
            "Published benchmark contract schema versions do not match between "
            "Azure, workbench.project.json, and pipeline YAML."
        )
    if pipeline.evidence_recipe_id != configured.evidence_recipe_id:
        raise ValueError(
            "Pipeline evidence_recipe_id does not match workbench.project.json."
        )
    if pipeline.source_snapshot_contract != configured.source_snapshot_contract:
        raise ValueError(
            "Pipeline source_snapshot_contract does not match "
            "workbench.project.json."
        )
    _validate_label_fields(configured, benchmark)
    required = set(pipeline.required_artifact_kinds)
    selected = tuple(examples)
    if not selected:
        raise ValueError("Compatibility preflight requires at least one example.")
    for example in selected:
        available = {artifact.artifact_kind for artifact in example.raw_artifacts}
        missing = required - available
        if missing:
            raise ValueError(
                f"Benchmark example {example.example_id} is missing pipeline "
                "artifact kinds: " + ", ".join(sorted(missing))
            )
    return pipeline


def find_configured_published_benchmark(
    project: ProjectContract, benchmark: BenchmarkVersion
) -> PublishedBenchmarkSpec:
    """Return the project-owned contract for one exact published benchmark."""
    identity = (benchmark.benchmark_key, str(benchmark.version_number))
    for configured in project.benchmarks.published:
        if (configured.key, configured.version) == identity:
            return configured
    raise ValueError(
        "Published benchmark is not configured in workbench.project.json: "
        f"{benchmark.benchmark_key} v{benchmark.version_number}."
    )


def _validate_label_fields(
    configured: PublishedBenchmarkSpec, benchmark: BenchmarkVersion
) -> None:
    for schema in benchmark.label_schemas:
        fields = schema.schema_document.get("fields")
        if not isinstance(fields, list):
            raise ValueError(
                f"Published label schema {schema.schema_key!r} has no fields list."
            )
        available = {
            str(field.get("key"))
            for field in fields
            if isinstance(field, Mapping) and field.get("key")
        }
        missing = set(configured.label_fields) - available
        if missing:
            raise ValueError(
                f"Published label schema {schema.schema_key!r} is missing configured "
                "evaluation fields: " + ", ".join(sorted(missing))
            )
