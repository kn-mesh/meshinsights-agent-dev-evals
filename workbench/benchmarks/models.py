"""Immutable published-benchmark models shared by pipelines and evals."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceArtifact(BaseModel):
    """Describe one content-addressed raw source artifact in Azure Blob Storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_kind: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    byte_size: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PublishedLabelSchema(BaseModel):
    """Immutable label schema referenced by published benchmark examples."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version_id: str = Field(min_length=1)
    schema_key: str = Field(min_length=1)
    version: str = Field(min_length=1)
    schema_document: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        encoded = json.dumps(
            self.schema_document,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != self.content_sha256:
            raise ValueError("Published label schema content hash does not match.")
        return self


class PublishedReviewerCoverage(BaseModel):
    """One reviewer revision frozen into published benchmark coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    review_event_id: str = Field(min_length=1)
    label_revision: int = Field(ge=1)
    reviewer_user_id: str
    reviewer_display_name: str
    reviewer_project_role: str
    submitted_at: datetime
    is_selected_label_revision: bool


class PublishedVerification(BaseModel):
    """Immutable customer or onsite verification for the published labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["direct_observation", "operator_feedback"]
    note: str | None = None
    recorded_at: datetime | None = None
    source_content_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    context_schema_key: str | None = None
    context_schema_version: str | None = None
    source_fields: dict[str, Any] | None = None


class PublishedReviewContext(BaseModel):
    """Frozen reviewer coverage and verification retained with an eval run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_coverage: tuple[PublishedReviewerCoverage, ...] = ()
    verification: PublishedVerification | None = None


class BenchmarkExample(BaseModel):
    """One frozen example in a published benchmark version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    decision_timestamp: datetime
    approved_label_payload: dict[str, Any]
    label_schema_version_id: str = Field(min_length=1)
    example_metadata: dict[str, Any] = Field(default_factory=dict)
    source_snapshot_id: str = Field(min_length=1)
    raw_snapshot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_source_kind: str = Field(min_length=1)
    raw_captured_at: datetime
    raw_window_start: datetime | None = None
    raw_window_end: datetime | None = None
    raw_known_gaps: tuple[Any, ...] = ()
    raw_artifacts: tuple[SourceArtifact, ...]
    published_review_context: PublishedReviewContext

    @field_validator("approved_label_payload")
    @classmethod
    def validate_approved_label_payload(
        cls, value: dict[str, Any]
    ) -> dict[str, Any]:
        """Preserve the complete published payload without value coercion."""
        if not value or not all(isinstance(key, str) and key.strip() for key in value):
            raise ValueError("A benchmark example requires named approved labels.")
        return value

    @model_validator(mode="after")
    def validate_raw_artifacts(self) -> Self:
        """Require an unambiguous, non-empty frozen artifact manifest."""
        artifact_kinds = [artifact.artifact_kind for artifact in self.raw_artifacts]
        if not artifact_kinds:
            raise ValueError("Benchmark example contains no raw artifacts.")
        if len(artifact_kinds) != len(set(artifact_kinds)):
            raise ValueError("Benchmark example contains duplicate raw artifact kinds.")
        if (
            self.raw_window_start is not None
            and self.raw_window_end is not None
            and self.raw_window_start > self.raw_window_end
        ):
            raise ValueError("Benchmark evidence window start is after its end.")
        if (
            self.raw_window_end is not None
            and self.raw_window_end > self.decision_timestamp
        ):
            raise ValueError(
                "Benchmark evidence window extends beyond the decision timestamp."
            )
        return self


class BenchmarkVersion(BaseModel):
    """A published, immutable Benchmark Studio version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_key: str = Field(min_length=1)
    benchmark_key: str = Field(min_length=1)
    benchmark_name: str = Field(min_length=1)
    benchmark_version_id: str = Field(min_length=1)
    version_number: int = Field(ge=1)
    published_at: datetime
    source_state_sha256: str | None = None
    published_contract_schema_version: int = Field(ge=2)
    eval_label_field_hints: tuple[str, ...]
    label_schemas: tuple[PublishedLabelSchema, ...]
    examples: tuple[BenchmarkExample, ...]

    @model_validator(mode="after")
    def validate_examples(self) -> Self:
        """Require unique examples in every published benchmark version."""
        if not self.examples:
            raise ValueError("Published benchmark version contains no examples.")
        ids = [example.example_id for example in self.examples]
        if len(ids) != len(set(ids)):
            raise ValueError("Published benchmark version contains duplicate example IDs.")
        schemas = {schema.schema_version_id for schema in self.label_schemas}
        if len(schemas) != len(self.label_schemas):
            raise ValueError("Published benchmark contains duplicate label schemas.")
        missing = {
            example.label_schema_version_id for example in self.examples
        } - schemas
        if missing:
            raise ValueError(
                "Published benchmark examples reference missing label schemas: "
                + ", ".join(sorted(missing))
            )
        return self

    def get_example(self, example_id: str) -> BenchmarkExample:
        """Return one exact benchmark example or fail with an actionable error."""
        normalized = example_id.strip()
        for example in self.examples:
            if example.example_id == normalized:
                return example
        raise ValueError(
            f"Example '{example_id}' was not found in benchmark "
            f"{self.benchmark_key} v{self.version_number}."
        )


class PublishedBenchmarkVersionSummary(BaseModel):
    """Lightweight catalog entry used to choose an Azure benchmark version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_key: str = Field(min_length=1)
    benchmark_key: str = Field(min_length=1)
    benchmark_name: str = Field(min_length=1)
    benchmark_version_id: str = Field(min_length=1)
    version_number: int = Field(ge=1)
    published_at: datetime
    source_state_sha256: str | None = None
    example_count: int = Field(ge=1)
