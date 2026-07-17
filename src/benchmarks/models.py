"""Immutable published-benchmark models shared by pipelines and evals."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceArtifact(BaseModel):
    """Describe one content-addressed raw source artifact in Azure Blob Storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_kind: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    byte_size: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BenchmarkExample(BaseModel):
    """One frozen example in a published benchmark version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    example_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    decision_timestamp: datetime
    approved_labels: dict[str, str]
    example_metadata: dict[str, Any] = Field(default_factory=dict)
    source_snapshot_id: str = Field(min_length=1)
    raw_snapshot_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_source_kind: str = Field(min_length=1)
    raw_captured_at: datetime
    raw_window_start: datetime | None = None
    raw_window_end: datetime | None = None
    raw_known_gaps: tuple[Any, ...] = ()
    raw_artifacts: tuple[SourceArtifact, ...]

    @field_validator("approved_labels")
    @classmethod
    def validate_approved_labels(cls, value: dict[str, str]) -> dict[str, str]:
        """Require at least one non-empty evaluation label."""
        normalized = {
            str(key).strip(): str(item).strip()
            for key, item in value.items()
            if str(key).strip() and str(item).strip()
        }
        if not normalized:
            raise ValueError("A benchmark example requires approved evaluation labels.")
        return normalized

    @model_validator(mode="after")
    def validate_raw_artifacts(self) -> Self:
        """Require the two raw Spirax artifacts frozen by benchmark publication."""
        artifact_kinds = [artifact.artifact_kind for artifact in self.raw_artifacts]
        if len(artifact_kinds) != len(set(artifact_kinds)):
            raise ValueError("Benchmark example contains duplicate raw artifact kinds.")
        kinds = set(artifact_kinds)
        missing = {"telemetry", "alarms"} - kinds
        if missing:
            raise ValueError(
                "Benchmark example is missing raw artifacts: "
                + ", ".join(sorted(missing))
            )
        return self

    @property
    def sensor_id(self) -> int:
        """Resolve the numeric Pulse sensor identity from frozen example metadata."""
        raw = self.example_metadata.get("sensor_id", self.unit_id)
        try:
            return int(str(raw).strip())
        except ValueError as error:
            raise ValueError(
                f"Benchmark example {self.example_id} has a non-numeric sensor_id."
            ) from error


class BenchmarkVersion(BaseModel):
    """A published, immutable benchmark version loaded from Azure PostgreSQL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_key: str = Field(min_length=1)
    benchmark_key: str = Field(min_length=1)
    benchmark_name: str = Field(min_length=1)
    benchmark_version_id: str = Field(min_length=1)
    version_number: int = Field(ge=1)
    published_at: datetime
    source_state_sha256: str | None = None
    examples: tuple[BenchmarkExample, ...]

    @model_validator(mode="after")
    def validate_examples(self) -> Self:
        """Require unique examples in every published benchmark version."""
        if not self.examples:
            raise ValueError("Published benchmark version contains no examples.")
        ids = [example.example_id for example in self.examples]
        if len(ids) != len(set(ids)):
            raise ValueError("Published benchmark version contains duplicate example IDs.")
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
