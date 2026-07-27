"""Versioned contracts for one immutable eval publication event."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Reject undeclared publication fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublishedArtifact(StrictModel):
    """Identity of one payload blob committed by a publication."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    media_type: Literal["application/json"]
    blob_name: str = Field(min_length=1)


class PublicationSeed(StrictModel):
    """Unique event seed bound to exact payload bytes."""

    schema_version: Literal[1]
    published_at_utc: str = Field(min_length=1)
    nonce: str = Field(min_length=1)
    project_key: str = Field(min_length=1)
    retained_eval_id: str = Field(pattern=r"^ret_[0-9a-f]{24}$")
    eval_run_id: str = Field(pattern=r"^eval_[0-9a-f]{24}$")
    benchmark: dict[str, Any]
    agent_version_id: str = Field(min_length=1)
    git_commit: str = Field(min_length=1)
    artifacts: dict[str, dict[str, int | str]]


class PublicationManifest(StrictModel):
    """Discovery and integrity root uploaded last as the commit marker."""

    contract: Literal["published-eval/v1"]
    schema_version: Literal[1]
    publication_id: str = Field(pattern=r"^pub_[0-9a-f]{24}$")
    published_at_utc: str = Field(min_length=1)
    project: dict[str, str]
    source: dict[str, str]
    benchmark: dict[str, Any]
    agent: dict[str, str]
    run_spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_example_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    counts: dict[str, Any]
    artifacts: dict[str, PublishedArtifact]
    publisher_contract_version: Literal[1]
    publication_seed: PublicationSeed
