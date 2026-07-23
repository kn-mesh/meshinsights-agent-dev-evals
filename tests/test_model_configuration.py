"""Tests for the project-owned model and pricing configuration workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from model_catalog import load_model_catalog
from src import model_configuration


def _catalog(path: Path) -> None:
    path.write_text(
        "default_model: azure:existing\n"
        "models:\n"
        "  - id: azure:existing\n"
        "    api: openai_responses\n",
        encoding="utf-8",
    )


def test_upsert_cli_captures_versioned_rates_and_can_select_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "models.yaml"
    _catalog(path)

    assert (
        model_configuration.main(
            [
                "--catalog",
                str(path),
                "upsert",
                "azure:new",
                "--api",
                "openai_responses",
                "--currency",
                "USD",
                "--pricing-version",
                "2026-07-reviewed",
                "--effective-date",
                "2026-07-01",
                "--source",
                "reviewed vendor price sheet",
                "--input-price",
                "1.25",
                "--output-price",
                "5",
                "--cached-input-price",
                "0.25",
                "--reasoning-price",
                "5",
                "--make-default",
            ]
        )
        == 0
    )

    catalog = load_model_catalog(path)
    pricing = catalog.get("azure:new").pricing
    assert catalog.default_model == "azure:new"
    assert pricing is not None
    assert pricing.to_dict() == {
        "version": "2026-07-reviewed",
        "currency": "USD",
        "input_per_million_tokens": 1.25,
        "output_per_million_tokens": 5.0,
        "cached_input_per_million_tokens": 0.25,
        "reasoning_per_million_tokens": 5.0,
        "effective_date": "2026-07-01",
        "source": "reviewed vendor price sheet",
    }
    assert "input=1.25" in capsys.readouterr().out


def test_invalid_price_does_not_replace_catalog(tmp_path: Path) -> None:
    path = tmp_path / "models.yaml"
    _catalog(path)
    original = path.read_text(encoding="utf-8")

    with pytest.raises(SystemExit):
        model_configuration.main(
            [
                "--catalog",
                str(path),
                "upsert",
                "azure:new",
                "--api",
                "openai_responses",
                "--currency",
                "USD",
                "--pricing-version",
                "bad",
                "--input-price",
                "-1",
                "--output-price",
                "5",
            ]
        )

    assert path.read_text(encoding="utf-8") == original
