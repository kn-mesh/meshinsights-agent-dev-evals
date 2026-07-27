"""Shared provider selection and env prerequisite helpers for AI smoke tests."""

from __future__ import annotations

import os
from typing import TypeVar, cast

import pytest

TModel = TypeVar("TModel", bound=str)


def selected_models_from_pytest_option(
    pytestconfig: pytest.Config,
    supported_model_options: tuple[TModel, ...],
) -> tuple[TModel, ...]:
    """Return provider selection from pytest CLI option with validation."""
    selected_provider = str(
        pytestconfig.getoption("pydantic_ai_provider", default="all")
    ).strip()
    if selected_provider == "all":
        return tuple(cast(TModel, model_name) for model_name in supported_model_options)
    if selected_provider in supported_model_options:
        return (cast(TModel, selected_provider),)

    valid_options = ", ".join(["all", *supported_model_options])
    raise pytest.UsageError(
        f"Invalid --pydantic-ai-provider value '{selected_provider}'. Valid options: {valid_options}"
    )


def build_provider_test_id(model_name: str) -> str:
    """Return compact pytest test id for a provider model name."""
    return model_name.split(":", maxsplit=1)[1]


def _is_azure_claude(model_name: str) -> bool:
    """Return True if ``model_name`` is an ``azure:claude-*`` model."""
    return model_name.startswith("azure:claude")


def missing_prerequisites_for_provider(model_name: str) -> str | None:
    """Return missing env prerequisite for a provider smoke test, if any.

    Each provider / model combination has its own credential requirements:

    * ``azure:claude-*`` — Foundry credentials
      (``ANTHROPIC_FOUNDRY_API_KEY`` + ``ANTHROPIC_FOUNDRY_RESOURCE`` or
      ``ANTHROPIC_FOUNDRY_BASE_URL``).
    * ``azure:*`` (non-Claude) — Azure OpenAI credentials
      (``AZURE_OPENAI_ENDPOINT`` + ``AZURE_OPENAI_API_KEY``).
    * ``anthropic:*`` — direct Anthropic API key (``ANTHROPIC_API_KEY``).
    * ``google:*`` — direct Google Gemini API key
      (``GOOGLE_API_KEY`` or ``GEMINI_API_KEY``).
    * ``openrouter:*`` — OpenRouter API key (``OPENROUTER_API_KEY``).
    """
    if not os.getenv("LOGFIRE_READ_TOKEN", "").strip():
        return "LOGFIRE_READ_TOKEN"

    if _is_azure_claude(model_name):
        if not os.getenv("ANTHROPIC_FOUNDRY_API_KEY", "").strip():
            return "ANTHROPIC_FOUNDRY_API_KEY"
        has_base_url = bool(os.getenv("ANTHROPIC_FOUNDRY_BASE_URL", "").strip())
        has_resource = bool(os.getenv("ANTHROPIC_FOUNDRY_RESOURCE", "").strip())
        if not (has_base_url or has_resource):
            return "ANTHROPIC_FOUNDRY_BASE_URL or ANTHROPIC_FOUNDRY_RESOURCE"
        return None

    if model_name.startswith("azure:"):
        if not os.getenv("AZURE_OPENAI_ENDPOINT", "").strip():
            return "AZURE_OPENAI_ENDPOINT"
        if not os.getenv("AZURE_OPENAI_API_KEY", "").strip():
            return "AZURE_OPENAI_API_KEY"
        return None

    if model_name.startswith("openrouter:"):
        if not os.getenv("OPENROUTER_API_KEY", "").strip():
            return "OPENROUTER_API_KEY"
        return None

    if model_name.startswith("google:"):
        has_google_api_key = bool(os.getenv("GOOGLE_API_KEY", "").strip())
        has_gemini_api_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
        if not (has_google_api_key or has_gemini_api_key):
            return "GOOGLE_API_KEY or GEMINI_API_KEY"
        return None

    if model_name.startswith("anthropic:"):
        if not os.getenv("ANTHROPIC_API_KEY", "").strip():
            return "ANTHROPIC_API_KEY"
        return None

    return None


def is_provider_connection_error(error: Exception) -> bool:
    """Return whether *error* looks like an external provider connectivity issue."""
    message = str(error).lower()
    return any(
        needle in message
        for needle in (
            "connection error",
            "connect error",
            "nodename nor servname provided",
            "temporary failure in name resolution",
        )
    )
