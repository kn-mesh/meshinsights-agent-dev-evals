"""Tests for the project-owned root model catalog."""

from pathlib import Path

import pytest

from model_catalog import (
    load_model_catalog,
    resolve_model,
    resolve_model_definition,
)


def test_root_catalog_defines_current_default_and_choices() -> None:
    catalog = load_model_catalog()

    assert catalog.default_model == "azure:gpt-5.6-luna"
    assert catalog.default_model in catalog.model_ids
    assert catalog.get("azure:gpt-5.6-luna").api == "openai_responses"
    assert catalog.get("anthropic:claude-sonnet-4-6").api == "anthropic_messages"
    assert catalog.get("google:gemini-3.5-flash").api == "google_generate_content"
    assert (
        catalog.get("openrouter:google/gemini-3.5-flash").api
        == "openai_chat_completions"
    )
    assert resolve_model(None, catalog) == "azure:gpt-5.6-luna"
    assert resolve_model_definition(None, catalog).api == "openai_responses"


def test_catalog_rejects_a_default_outside_its_model_list(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "default_model: azure:new-model\n"
        "models:\n"
        "  - id: azure:other-model\n"
        "    api: openai_responses\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="is not present in models"):
        load_model_catalog(path)


def test_model_selection_rejects_values_outside_catalog() -> None:
    catalog = load_model_catalog()

    with pytest.raises(ValueError, match="Unknown model"):
        resolve_model("azure:not-in-this-project", catalog)


def test_catalog_requires_api_metadata_for_every_model(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "default_model: azure:new-model\nmodels:\n  - id: azure:new-model\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"models\[0\]\.api"):
        load_model_catalog(path)


def test_catalog_loads_versioned_optional_pricing(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    path.write_text(
        "default_model: azure:new-model\n"
        "models:\n"
        "  - id: azure:new-model\n"
        "    api: openai_responses\n"
        "    pricing:\n"
        "      version: 2026-07\n"
        "      currency: USD\n"
        "      input_per_million_tokens: 1.25\n"
        "      output_per_million_tokens: 5.0\n",
        encoding="utf-8",
    )

    pricing = load_model_catalog(path).models[0].pricing

    assert pricing is not None
    assert pricing.version == "2026-07"
    assert pricing.input_per_million_tokens == 1.25
