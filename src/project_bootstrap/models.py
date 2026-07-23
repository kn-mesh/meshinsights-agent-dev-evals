"""Strict contracts for Agent Workbench project bootstrap."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ModelApi = Literal[
    "anthropic_messages",
    "google_generate_content",
    "openai_chat_completions",
    "openai_responses",
]
OwnershipKind = Literal[
    "reusable_library",
    "reusable_workbench",
    "reference_use_case",
    "root_infrastructure",
    "generated_local",
]


class StrictModel(BaseModel):
    """Reject unknown bootstrap fields and freeze validated values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectSpec(StrictModel):
    """Identity assigned to one use-case Agent Workbench repository."""

    key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    distribution_name: str = Field(pattern=r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
    use_case_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str = Field(min_length=1)


class BenchmarkStudioSpec(StrictModel):
    """Non-secret Azure identity of the published benchmark data plane."""

    project_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    access_mode: Literal["direct_read_only"]
    postgres_host: str = Field(pattern=r"^[a-z0-9.-]+\.postgres\.database\.azure\.com$")
    postgres_database: str = Field(min_length=1)
    storage_account_url: str = Field(
        pattern=r"^https://[a-z0-9]+\.blob\.core\.windows\.net$"
    )
    storage_container: str = Field(min_length=1)


class PublishedBenchmarkSpec(StrictModel):
    """One immutable published benchmark contract available to the project."""

    key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    published_contract_schema_version: int = Field(ge=1)
    label_fields: tuple[str, ...] = Field(min_length=1)
    evidence_recipe_id: str = Field(min_length=1)
    source_snapshot_contract: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_label_fields(self) -> PublishedBenchmarkSpec:
        """Require unique, non-empty configured evaluation-label fields."""
        normalized = tuple(value.strip() for value in self.label_fields)
        if any(not value for value in normalized):
            raise ValueError("Benchmark label fields cannot be empty.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Benchmark label fields must be unique.")
        object.__setattr__(self, "label_fields", normalized)
        return self


class BenchmarkSelection(StrictModel):
    """Exact benchmark selected as the new project's default."""

    key: str = Field(min_length=1)
    version: str = Field(min_length=1)


class BenchmarkCatalogSpec(StrictModel):
    """Published benchmark catalog and its default selection."""

    default: BenchmarkSelection
    published: tuple[PublishedBenchmarkSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> BenchmarkCatalogSpec:
        """Require unique versions and a resolvable default selection."""
        identities = tuple((item.key, item.version) for item in self.published)
        if len(identities) != len(set(identities)):
            raise ValueError("Published benchmark identities must be unique.")
        selected = (self.default.key, self.default.version)
        if selected not in identities:
            raise ValueError("Default benchmark must exist in the published catalog.")
        return self


class ModelPricingSpec(StrictModel):
    """Optional frozen non-secret rates copied into the project catalog."""

    version: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    input_per_million_tokens: float | None = Field(default=None, ge=0)
    output_per_million_tokens: float | None = Field(default=None, ge=0)
    cached_input_per_million_tokens: float | None = Field(default=None, ge=0)
    reasoning_per_million_tokens: float | None = Field(default=None, ge=0)
    effective_date: str | None = None
    source: str | None = None


class ModelSpec(StrictModel):
    """One project-supported model and its required provider API family."""

    id: str = Field(pattern=r"^[^:\s]+:[^\s]+$")
    api: ModelApi
    pricing: ModelPricingSpec | None = None


class ModelCatalogSpec(StrictModel):
    """Project-owned selectable model catalog and unattended default."""

    default_model: str = Field(pattern=r"^[^:\s]+:[^\s]+$")
    models: tuple[ModelSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_catalog(self) -> ModelCatalogSpec:
        """Require unique model IDs and a default contained in the catalog."""
        model_ids = tuple(model.id for model in self.models)
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("Model identifiers must be unique.")
        if self.default_model not in model_ids:
            raise ValueError("Default model must exist in the model catalog.")
        return self


class BootstrapSpec(StrictModel):
    """Reviewed, non-secret input to one project initialization."""

    schema_version: Literal[1]
    project: ProjectSpec
    benchmark_studio: BenchmarkStudioSpec
    benchmarks: BenchmarkCatalogSpec
    model_catalog: ModelCatalogSpec


class TemplateProvenance(StrictModel):
    """Exact standard-template source used to create a project."""

    source: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class ProjectPaths(StrictModel):
    """Durable locations used by Agent Workbench workflows."""

    use_case_context: str = "docs/use_case"
    pipeline_configs: str = "pipeline_configs"
    evaluation_configs: str = "evaluation_configs"
    agent_version_configs: str = "agent_version_configs"
    eval_results: str = "eval_results"
    promoted_agent_versions: str = "agent_versions"
    model_catalog: str = "models.yaml"


class ProjectContract(StrictModel):
    """Normalized generated identity and configuration for one project."""

    schema_version: Literal[1]
    created_at_utc: datetime
    template: TemplateProvenance
    project: ProjectSpec
    benchmark_studio: BenchmarkStudioSpec
    benchmarks: BenchmarkCatalogSpec
    model_catalog: ModelCatalogSpec
    paths: ProjectPaths


class OwnershipEntry(StrictModel):
    """One explicit repository path and its template ownership."""

    path: str
    owner: OwnershipKind
    description: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _relative_template_path(value)


class ReferenceResetSpec(StrictModel):
    """Exact reference content cleared when creating a new use-case repo."""

    clear_directories: tuple[str, ...] = ()
    remove_directories: tuple[str, ...] = ()
    remove_files: tuple[str, ...] = ()
    root_skills_with_project_defaults: tuple[str, ...] = ()
    leak_scan_paths: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()

    @field_validator(
        "clear_directories",
        "remove_directories",
        "remove_files",
        "root_skills_with_project_defaults",
        "leak_scan_paths",
    )
    @classmethod
    def validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(_relative_template_path(value) for value in values)
        if len(normalized) != len(set(normalized)):
            raise ValueError("Template reset paths must be unique.")
        return normalized

    @field_validator("forbidden_terms")
    @classmethod
    def validate_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip().lower() for value in values)
        if any(not value for value in normalized):
            raise ValueError("Forbidden reference terms cannot be empty.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Forbidden reference terms must be unique.")
        return normalized


class TemplateOwnershipManifest(StrictModel):
    """Versioned ownership and reference-reset contract for the template."""

    schema_version: Literal[1]
    ownership: tuple[OwnershipEntry, ...] = Field(min_length=1)
    reference_reset: ReferenceResetSpec

    @model_validator(mode="after")
    def validate_manifest(self) -> TemplateOwnershipManifest:
        paths = tuple(item.path for item in self.ownership)
        if len(paths) != len(set(paths)):
            raise ValueError("Template ownership paths must be unique.")
        overlap = set(self.reference_reset.clear_directories).intersection(
            self.reference_reset.remove_directories
        )
        if overlap:
            raise ValueError(
                "Template directories cannot be both cleared and removed: "
                + ", ".join(sorted(overlap))
            )
        return self


def _relative_template_path(value: str) -> str:
    """Return one normalized safe project-relative POSIX path."""
    from pathlib import PurePosixPath

    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized == "."
        or path.is_absolute()
        or ".." in path.parts
        or normalized != path.as_posix()
    ):
        raise ValueError(f"Template path must be normalized and relative: {value!r}")
    return normalized
