"""Load the project-owned AI model catalog from the repository root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


MODEL_CATALOG_PATH = Path(__file__).with_name("models.yaml")


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Validated model choices and the default used by unattended runs."""

    default_model: str
    models: tuple[str, ...]


def load_model_catalog(path: Path = MODEL_CATALOG_PATH) -> ModelCatalog:
    """Load and validate a project model catalog."""
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Model catalog must be a mapping: {path}")

    default_model = _model_identifier(payload.get("default_model"), "default_model")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError(f"Model catalog 'models' must be a non-empty list: {path}")

    models = tuple(
        _model_identifier(value, f"models[{index}]")
        for index, value in enumerate(raw_models)
    )
    if len(set(models)) != len(models):
        raise ValueError(f"Model catalog contains duplicate model identifiers: {path}")
    if default_model not in models:
        raise ValueError(
            f"Model catalog default '{default_model}' is not present in models: {path}"
        )
    return ModelCatalog(default_model=default_model, models=models)


def resolve_model(model: str | None, catalog: ModelCatalog | None = None) -> str:
    """Resolve a requested model or the project default and validate membership."""
    selected_catalog = catalog or load_model_catalog()
    selected = model.strip() if model is not None else selected_catalog.default_model
    if selected not in selected_catalog.models:
        choices = ", ".join(selected_catalog.models)
        raise ValueError(f"Unknown model '{selected}'. Choose one of: {choices}")
    return selected


def _model_identifier(value: object, field: str) -> str:
    """Validate the catalog's canonical provider:model identifier shape."""
    if not isinstance(value, str):
        raise ValueError(f"Model catalog '{field}' must be a string.")
    normalized = value.strip()
    provider, separator, model = normalized.partition(":")
    if not separator or not provider or not model:
        raise ValueError(
            f"Model catalog '{field}' must use provider:model format; got {value!r}."
        )
    return normalized
