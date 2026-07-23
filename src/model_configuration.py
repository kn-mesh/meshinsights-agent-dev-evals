"""Project-owned model and frozen-pricing configuration workflow."""

from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path
from typing import Sequence, cast

import yaml

from model_catalog import (
    MODEL_APIS,
    MODEL_CATALOG_PATH,
    ModelApi,
    ModelCatalog,
    ModelDefinition,
    ModelPricing,
    load_model_catalog,
)


def format_model(model: ModelDefinition, *, default_model: str) -> str:
    """Return one operator-readable model and pricing summary."""
    marker = " (default)" if model.id == default_model else ""
    if model.pricing is None:
        pricing = "pricing not configured"
    else:
        rates = [
            f"input={_rate(model.pricing.input_per_million_tokens)}",
            f"output={_rate(model.pricing.output_per_million_tokens)}",
        ]
        if model.pricing.cached_input_per_million_tokens is not None:
            rates.append(
                f"cached-input={_rate(model.pricing.cached_input_per_million_tokens)}"
            )
        if model.pricing.reasoning_per_million_tokens is not None:
            rates.append(
                f"reasoning={_rate(model.pricing.reasoning_per_million_tokens)}"
            )
        pricing = (
            f"{model.pricing.currency}/1M tokens ({', '.join(rates)}; "
            f"version={model.pricing.version})"
        )
    return f"{model.id}{marker} | api={model.api} | {pricing}"


def upsert_model(
    path: Path,
    *,
    model_id: str,
    api: ModelApi,
    pricing: ModelPricing,
    make_default: bool,
) -> ModelCatalog:
    """Create or replace one selectable model and atomically persist the catalog."""
    catalog = load_model_catalog(path)
    definition = ModelDefinition(id=model_id.strip(), api=api, pricing=pricing)
    existing = [model for model in catalog.models if model.id != definition.id]
    updated = ModelCatalog(
        default_model=definition.id if make_default else catalog.default_model,
        models=tuple([*existing, definition]),
    )
    _write_catalog(path, updated)
    return load_model_catalog(path)


def set_default_model(path: Path, model_id: str) -> ModelCatalog:
    """Set the unattended default to an existing model."""
    catalog = load_model_catalog(path)
    catalog.get(model_id)
    updated = replace(catalog, default_model=model_id)
    _write_catalog(path, updated)
    return load_model_catalog(path)


def _write_catalog(path: Path, catalog: ModelCatalog) -> None:
    payload = {
        "default_model": catalog.default_model,
        "models": [
            {
                "id": model.id,
                "api": model.api,
                **(
                    {"pricing": model.pricing.to_dict()}
                    if model.pricing is not None
                    else {}
                ),
            }
            for model in catalog.models
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    try:
        load_model_catalog(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _rate(value: float | None) -> str:
    return "unpriced" if value is None else f"{value:g}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List or edit project-owned model and frozen pricing settings."
    )
    parser.add_argument("--catalog", type=Path, default=MODEL_CATALOG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List selectable models and configured prices.")
    default = subparsers.add_parser(
        "set-default", help="Choose the unattended project default."
    )
    default.add_argument("model_id")
    upsert = subparsers.add_parser(
        "upsert", help="Create or edit a model and its frozen pricing record."
    )
    upsert.add_argument("model_id")
    upsert.add_argument("--api", required=True, choices=sorted(MODEL_APIS))
    upsert.add_argument("--currency", required=True)
    upsert.add_argument("--pricing-version", required=True)
    upsert.add_argument("--effective-date")
    upsert.add_argument("--source")
    upsert.add_argument("--input-price", required=True, type=float)
    upsert.add_argument("--output-price", required=True, type=float)
    upsert.add_argument("--cached-input-price", type=float)
    upsert.add_argument("--reasoning-price", type=float)
    upsert.add_argument("--make-default", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the project model configuration command."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            catalog = load_model_catalog(args.catalog)
        elif args.command == "set-default":
            catalog = set_default_model(args.catalog, args.model_id)
        else:
            pricing = ModelPricing(
                version=args.pricing_version.strip(),
                currency=args.currency.strip(),
                input_per_million_tokens=args.input_price,
                output_per_million_tokens=args.output_price,
                cached_input_per_million_tokens=args.cached_input_price,
                reasoning_per_million_tokens=args.reasoning_price,
                effective_date=args.effective_date,
                source=args.source,
            )
            catalog = upsert_model(
                args.catalog,
                model_id=args.model_id,
                api=cast(ModelApi, args.api),
                pricing=pricing,
                make_default=args.make_default,
            )
    except ValueError as error:
        parser.error(str(error))
    for model in catalog.models:
        print(format_model(model, default_model=catalog.default_model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
