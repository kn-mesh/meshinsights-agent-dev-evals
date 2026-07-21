"""Side-effect-free declarations for versioning pipeline components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VersionAssetRole(StrEnum):
    """Supported behavior-bearing asset roles."""

    PROMPT = "prompt"
    SKILL = "skill"
    TOOL_DEFINITION = "tool_definition"
    AGENT_ASSET = "agent_asset"
    INPUT_SCHEMA = "input_schema"
    OUTPUT_SCHEMA = "output_schema"
    ACTION_POLICY = "action_policy"
    EVIDENCE_RECIPE = "evidence_recipe"
    TRANSFORM = "transform"
    MODEL_POLICY = "model_policy"
    RUNTIME_CONTRACT = "runtime_contract"


class VersionAssetDeclaration(BaseModel):
    """One file or embedded symbol that contributes to agent behavior."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: VersionAssetRole
    logical_name: str = Field(min_length=1)
    path: str | None = None
    symbol: str | None = None
    media_type: str | None = None
    required_for_reconstruction: bool = True

    @model_validator(mode="after")
    def validate_locator(self) -> "VersionAssetDeclaration":
        """Require a file, an embedded symbol, or both."""
        if self.path is None and self.symbol is None:
            raise ValueError("Version assets require a path or symbol.")
        if self.path is not None:
            candidate = Path(self.path)
            if candidate.is_absolute():
                raise ValueError("Version asset paths must be relative paths.")
        return self


class VersionContractDeclaration(BaseModel):
    """One inspectable component contract contributing to the manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: VersionAssetRole
    logical_name: str = Field(min_length=1)
    value: dict[str, Any]


@runtime_checkable
class VersionAssetProvider(Protocol):
    """Structural protocol implemented by version-aware component classes."""

    @classmethod
    def version_assets(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionAssetDeclaration]:
        """Declare external files and embedded behavior-bearing symbols."""
        ...

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        """Declare normalized behavioral assumptions for inspection."""
        ...


def declared_version_assets(
    component: type[Any], config: Mapping[str, Any]
) -> tuple[VersionAssetDeclaration, ...]:
    """Read and validate optional structural declarations from a component."""
    provider = getattr(component, "version_assets", None)
    if not callable(provider):
        return ()
    return tuple(VersionAssetDeclaration.model_validate(item) for item in provider(config))


def declared_version_contracts(
    component: type[Any], config: Mapping[str, Any]
) -> tuple[VersionContractDeclaration, ...]:
    """Read and validate optional contract declarations from a component."""
    provider = getattr(component, "version_contracts", None)
    if not callable(provider):
        return ()
    return tuple(
        VersionContractDeclaration.model_validate(item) for item in provider(config)
    )


__all__ = [
    "VersionAssetDeclaration",
    "VersionAssetProvider",
    "VersionAssetRole",
    "VersionContractDeclaration",
    "declared_version_assets",
    "declared_version_contracts",
]
