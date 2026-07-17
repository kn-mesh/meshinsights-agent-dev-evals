"""Tests for the project-owned root model catalog."""

from pathlib import Path

import pytest

from model_catalog import load_model_catalog, resolve_model


def test_root_catalog_defines_current_default_and_choices() -> None:
    catalog = load_model_catalog()

    assert catalog.default_model == "azure:gpt-5.4-mini"
    assert catalog.default_model in catalog.models
    assert "azure:gpt-5.4" in catalog.models
    assert resolve_model(None, catalog) == "azure:gpt-5.4-mini"


def test_catalog_rejects_a_default_outside_its_model_list(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "default_model: azure:new-model\nmodels:\n  - azure:other-model\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is not present in models"):
        load_model_catalog(path)


def test_model_selection_rejects_values_outside_catalog() -> None:
    catalog = load_model_catalog()

    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model("azure:not-in-this-project", catalog)
