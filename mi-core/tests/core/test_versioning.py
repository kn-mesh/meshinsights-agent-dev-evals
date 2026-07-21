"""Tests for reusable component version declarations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from mi.core.versioning import (
    VersionAssetDeclaration,
    VersionAssetRole,
    VersionContractDeclaration,
    declared_version_assets,
    declared_version_contracts,
)


class _Provider:
    @classmethod
    def version_assets(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionAssetDeclaration]:
        return (
            VersionAssetDeclaration(
                role=VersionAssetRole.PROMPT,
                logical_name=str(config["name"]),
                symbol="_Provider.prompt",
            ),
        )

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.ACTION_POLICY,
                logical_name="noop",
                value={"external_side_effect": False},
            ),
        )


def test_structural_provider_declarations_are_validated() -> None:
    assets = declared_version_assets(_Provider, {"name": "system-prompt"})
    contracts = declared_version_contracts(_Provider, {})

    assert assets[0].logical_name == "system-prompt"
    assert contracts[0].value == {"external_side_effect": False}


def test_asset_declaration_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="relative"):
        VersionAssetDeclaration(
            role=VersionAssetRole.SKILL,
            logical_name="unsafe",
            path="/tmp/SKILL.md",
        )
