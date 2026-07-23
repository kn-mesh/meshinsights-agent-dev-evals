"""Load the project-owned AI model catalog from the repository root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, Literal, TypeAlias

import yaml


MODEL_CATALOG_PATH = Path(__file__).with_name("models.yaml")
ModelApi: TypeAlias = Literal[
    "anthropic_messages",
    "google_generate_content",
    "openai_chat_completions",
    "openai_responses",
]
MODEL_APIS: frozenset[str] = frozenset(
    {
        "anthropic_messages",
        "google_generate_content",
        "openai_chat_completions",
        "openai_responses",
    }
)


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """One project-selectable model and the API family it requires."""

    id: str
    api: ModelApi
    pricing: "ModelPricing | None" = None


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Versioned project-owned rates used only for labeled cost estimates."""

    version: str
    currency: str
    input_per_million_tokens: float | None = None
    output_per_million_tokens: float | None = None
    cached_input_per_million_tokens: float | None = None
    reasoning_per_million_tokens: float | None = None
    effective_date: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "currency": self.currency,
            "input_per_million_tokens": self.input_per_million_tokens,
            "output_per_million_tokens": self.output_per_million_tokens,
            "cached_input_per_million_tokens": (self.cached_input_per_million_tokens),
            "reasoning_per_million_tokens": self.reasoning_per_million_tokens,
            "effective_date": self.effective_date,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Validated model choices and the default used by unattended runs."""

    default_model: str
    models: tuple[ModelDefinition, ...]

    @property
    def model_ids(self) -> tuple[str, ...]:
        """Return model identifiers in their configured display order."""
        return tuple(model.id for model in self.models)

    def get(self, model_id: str) -> ModelDefinition:
        """Return metadata for one model identifier."""
        for model in self.models:
            if model.id == model_id:
                return model
        choices = ", ".join(self.model_ids)
        raise ValueError(f"Unknown model '{model_id}'. Choose one of: {choices}")


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
        _model_definition(value, index) for index, value in enumerate(raw_models)
    )
    model_ids = tuple(model.id for model in models)
    if len(set(model_ids)) != len(model_ids):
        raise ValueError(f"Model catalog contains duplicate model identifiers: {path}")
    if default_model not in model_ids:
        raise ValueError(
            f"Model catalog default '{default_model}' is not present in models: {path}"
        )
    return ModelCatalog(default_model=default_model, models=models)


def resolve_model(model: str | None, catalog: ModelCatalog | None = None) -> str:
    """Resolve a requested model or the project default and validate membership."""
    return resolve_model_definition(model, catalog).id


def resolve_model_definition(
    model: str | None, catalog: ModelCatalog | None = None
) -> ModelDefinition:
    """Resolve a requested model and return its project-owned runtime metadata."""
    selected_catalog = catalog or load_model_catalog()
    selected = model.strip() if model is not None else selected_catalog.default_model
    return selected_catalog.get(selected)


def _model_definition(value: object, index: int) -> ModelDefinition:
    """Validate one structured model catalog entry."""
    field = f"models[{index}]"
    if not isinstance(value, dict):
        raise ValueError(f"Model catalog '{field}' must be a mapping with id and api.")
    model_id = _model_identifier(value.get("id"), f"{field}.id")
    raw_api = value.get("api")
    if not isinstance(raw_api, str) or raw_api not in MODEL_APIS:
        choices = ", ".join(sorted(MODEL_APIS))
        raise ValueError(
            f"Model catalog '{field}.api' must be one of: {choices}; got {raw_api!r}."
        )
    return ModelDefinition(
        id=model_id,
        api=cast(ModelApi, raw_api),
        pricing=_pricing_definition(value.get("pricing"), field=field),
    )


def _pricing_definition(value: object, *, field: str) -> ModelPricing | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"Model catalog '{field}.pricing' must be a mapping.")
    version = value.get("version")
    currency = value.get("currency")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"Model catalog '{field}.pricing.version' is required.")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError(f"Model catalog '{field}.pricing.currency' is required.")
    rate_names = (
        "input_per_million_tokens",
        "output_per_million_tokens",
        "cached_input_per_million_tokens",
        "reasoning_per_million_tokens",
    )
    rates: dict[str, float | None] = {}
    for name in rate_names:
        raw_rate = value.get(name)
        if raw_rate is None:
            rates[name] = None
        elif (
            isinstance(raw_rate, (int, float))
            and not isinstance(raw_rate, bool)
            and raw_rate >= 0
        ):
            rates[name] = float(raw_rate)
        else:
            raise ValueError(
                f"Model catalog '{field}.pricing.{name}' must be non-negative."
            )
    return ModelPricing(
        version=version.strip(),
        currency=currency.strip(),
        effective_date=(
            str(value["effective_date"]) if value.get("effective_date") else None
        ),
        source=str(value["source"]) if value.get("source") else None,
        **rates,
    )


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
