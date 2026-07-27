"""Typed contracts for immutable agent versions."""

from __future__ import annotations

from typing import Any, Literal

from evaluation import canonical_sha256
from pydantic import BaseModel, ConfigDict, Field, model_validator


DirtyPolicy = Literal["reject", "capture"]


class PermittedOverrides(BaseModel):
    """Explicit model/runtime values an eval may change without a new version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    models: tuple[str, ...] = ()
    reasoning_efforts: tuple[str, ...] = ()


class ModelPolicy(BaseModel):
    """Default AI configuration and its bounded eval override surface."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_model: str = Field(min_length=1)
    default_reasoning_effort: str | None = None
    permitted_overrides: PermittedOverrides = Field(
        default_factory=PermittedOverrides
    )

    @model_validator(mode="after")
    def validate_defaults(self) -> "ModelPolicy":
        if (
            self.permitted_overrides.models
            and self.default_model not in self.permitted_overrides.models
        ):
            raise ValueError("Default model must be included in permitted models.")
        if (
            self.default_reasoning_effort is not None
            and self.permitted_overrides.reasoning_efforts
            and self.default_reasoning_effort
            not in self.permitted_overrides.reasoning_efforts
        ):
            raise ValueError(
                "Default reasoning effort must be included in permitted values."
            )
        return self


class PolicyAsset(BaseModel):
    """Project-owned behavior-bearing file not declared by a component."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: str = Field(min_length=1)
    logical_name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    media_type: str | None = None


class AgentVersionPolicy(BaseModel):
    """Small per-pipeline policy supplementing component declarations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    source_pipeline: str = Field(min_length=1)
    model_policy: ModelPolicy
    additional_assets: tuple[PolicyAsset, ...] = ()
    contracts: dict[str, Any] = Field(default_factory=dict)
    non_execution_exclusions: tuple[str, ...] = ()


class AgentVersionManifest(BaseModel):
    """Immutable envelope around canonical agent-version identity content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    agent_version_id: str
    manifest_sha256: str
    identity: dict[str, Any]

    @classmethod
    def build(cls, identity: dict[str, Any]) -> "AgentVersionManifest":
        digest = canonical_sha256({"schema_version": 1, "identity": identity})
        return cls(
            agent_version_id=f"av_{digest[:24]}",
            manifest_sha256=digest,
            identity=identity,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> "AgentVersionManifest":
        digest = canonical_sha256(
            {"schema_version": self.schema_version, "identity": self.identity}
        )
        if digest != self.manifest_sha256:
            raise ValueError("Agent-version manifest hash is invalid.")
        if self.agent_version_id != f"av_{digest[:24]}":
            raise ValueError("Agent-version ID does not match its manifest hash.")
        return self


class AgentVersionReference(BaseModel):
    """Compact immutable reference embedded in eval run/result contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_version_id: str
    manifest_sha256: str
    manifest_schema_version: int
    lifecycle_state_at_run: Literal["candidate", "promoted"]
    source_tree_state: Literal["clean", "dirty", "unavailable"]
    resolved_graph_sha256: str
    evidence_recipe_sha256: str
    model_policy_sha256: str

    @classmethod
    def from_manifest(
        cls,
        manifest: AgentVersionManifest,
        *,
        lifecycle_state: Literal["candidate", "promoted"] = "candidate",
    ) -> "AgentVersionReference":
        identity = manifest.identity
        return cls(
            agent_version_id=manifest.agent_version_id,
            manifest_sha256=manifest.manifest_sha256,
            manifest_schema_version=manifest.schema_version,
            lifecycle_state_at_run=lifecycle_state,
            source_tree_state=identity["source"]["tree_state"],
            resolved_graph_sha256=identity["source_pipeline"][
                "resolved_graph_sha256"
            ],
            evidence_recipe_sha256=identity["contracts"][
                "evidence_recipe_sha256"
            ],
            model_policy_sha256=identity["model_policy"]["policy_sha256"],
        )


class ResolvedAgentVersion(BaseModel):
    """Resolved manifest plus CAS bytes needed beyond its clean Git base."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: AgentVersionManifest
    blobs: dict[str, bytes] = Field(default_factory=dict)
    policy: AgentVersionPolicy
    pipeline_path: str

    @property
    def reference(self) -> AgentVersionReference:
        return AgentVersionReference.from_manifest(self.manifest)
