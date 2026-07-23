"""Load project model choices and reusable model-pricing snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast, Literal, TypeAlias

import yaml


MODEL_CATALOG_PATH = Path(__file__).with_name("models.yaml")
MODEL_PRICING_PATH = Path(__file__).with_name("model_pricing.yaml")
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
    """One project-selectable model, its API family, and resolved pricing."""

    id: str
    api: ModelApi
    pricing_key: str | None = None
    pricing: "ModelPricing | None" = None


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Versioned reusable rates used only for labeled cost estimates."""

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


def load_model_catalog(
    path: Path = MODEL_CATALOG_PATH,
    pricing_path: Path | None = None,
) -> ModelCatalog:
    """Load model choices and resolve reusable pricing references."""
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Model catalog must be a mapping: {path}")

    default_model = _model_identifier(payload.get("default_model"), "default_model")
    raw_models = payload.get("models")
    if not isinstance(raw_models, list) or not raw_models:
        raise ValueError(f"Model catalog 'models' must be a non-empty list: {path}")

    selected_pricing_path = pricing_path or path.with_name(MODEL_PRICING_PATH.name)
    pricing = (
        load_model_pricing(selected_pricing_path)
        if selected_pricing_path.exists()
        else {}
    )
    models = tuple(
        _model_definition(value, index, pricing=pricing)
        for index, value in enumerate(raw_models)
    )
    model_ids = tuple(model.id for model in models)
    if len(set(model_ids)) != len(model_ids):
        raise ValueError(f"Model catalog contains duplicate model identifiers: {path}")
    if default_model not in model_ids:
        raise ValueError(
            f"Model catalog default '{default_model}' is not present in models: {path}"
        )
    return ModelCatalog(default_model=default_model, models=models)


def load_model_pricing(path: Path = MODEL_PRICING_PATH) -> dict[str, ModelPricing]:
    """Load the reusable, versioned pricing records keyed by billing identity."""
    payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Model pricing catalog must be a mapping: {path}")
    if payload.get("schema_version") != 1:
        raise ValueError(f"Model pricing catalog schema_version must be 1: {path}")
    raw_rates = payload.get("rates")
    if not isinstance(raw_rates, dict) or not raw_rates:
        raise ValueError(f"Model pricing catalog 'rates' must be a mapping: {path}")

    rates: dict[str, ModelPricing] = {}
    for raw_key, value in raw_rates.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise ValueError(f"Model pricing catalog contains an invalid rate key: {path}")
        key = raw_key.strip()
        if key in rates:
            raise ValueError(f"Model pricing catalog contains duplicate key '{key}': {path}")
        resolved = _pricing_definition(value, field=f"rates.{key}", catalog="pricing")
        if resolved is None:
            raise ValueError(f"Model pricing catalog rate '{key}' cannot be null.")
        rates[key] = resolved
    return rates


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


def _model_definition(
    value: object,
    index: int,
    *,
    pricing: dict[str, ModelPricing],
) -> ModelDefinition:
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
    raw_pricing_key = value.get("pricing_key")
    if raw_pricing_key is not None and (
        not isinstance(raw_pricing_key, str) or not raw_pricing_key.strip()
    ):
        raise ValueError(f"Model catalog '{field}.pricing_key' must be a string.")
    pricing_key = raw_pricing_key.strip() if isinstance(raw_pricing_key, str) else None
    inline_pricing = _pricing_definition(value.get("pricing"), field=field)
    if pricing_key is not None and inline_pricing is not None:
        raise ValueError(
            f"Model catalog '{field}' cannot define both pricing_key and pricing."
        )
    if pricing_key is not None and pricing_key not in pricing:
        raise ValueError(
            f"Model catalog '{field}.pricing_key' references unknown reusable "
            f"pricing '{pricing_key}'."
        )
    return ModelDefinition(
        id=model_id,
        api=cast(ModelApi, raw_api),
        pricing_key=pricing_key,
        pricing=pricing.get(pricing_key) if pricing_key is not None else inline_pricing,
    )


def _pricing_definition(
    value: object,
    *,
    field: str,
    catalog: str = "model",
) -> ModelPricing | None:
    label = "Model pricing catalog" if catalog == "pricing" else "Model catalog"
    if value is None:
        return None
    if not isinstance(value, dict):
        suffix = "" if catalog == "pricing" else ".pricing"
        raise ValueError(f"{label} '{field}{suffix}' must be a mapping.")
    version = value.get("version")
    currency = value.get("currency")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{label} '{field}.version' is required.")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError(f"{label} '{field}.currency' is required.")
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
                f"{label} '{field}.{name}' must be non-negative."
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
