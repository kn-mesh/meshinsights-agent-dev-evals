"""Strict contracts for Agent Workbench project bootstrap."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ModelApi = Literal[
    "anthropic_messages",
    "google_generate_content",
    "openai_chat_completions",
    "openai_responses",
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


class ModelSpec(StrictModel):
    """One project-supported model and its required provider API family."""

    id: str = Field(pattern=r"^[^:\s]+:[^\s]+$")
    api: ModelApi


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
