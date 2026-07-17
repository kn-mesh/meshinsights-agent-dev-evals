"""Provider registry for ``mi auth``.

All known credential providers are instantiated here and exposed via
:data:`PROVIDERS` (ordered list) and :data:`PROVIDER_BY_SLUG` (dict lookup).
"""
# ruff: noqa: F401

from __future__ import annotations

from .anthropic import AnthropicProvider
from .azure_foundry import AzureFoundryProvider
from .azure_openai import AzureOpenAIProvider
from .base import BaseProvider
from .google_gemini import GoogleGeminiProvider
from .logfire import LogfireProvider
from .openrouter import OpenRouterProvider

PROVIDERS: list[BaseProvider] = [
    AzureFoundryProvider(),
    AzureOpenAIProvider(),
    AnthropicProvider(),
    GoogleGeminiProvider(),
    OpenRouterProvider(),
    LogfireProvider(),
]
"""All known credential providers, in default display order."""

PROVIDER_BY_SLUG: dict[str, BaseProvider] = {p.slug: p for p in PROVIDERS}
"""Lookup table: provider slug -> provider instance."""


def match_providers_for_env_vars(env_vars: set[str]) -> list[BaseProvider]:
    """Return the providers whose fields overlap with *env_vars*.

    Used to determine which providers are "required" based on variables
    found in a ``.env.template`` file.
    """
    matched: list[BaseProvider] = []
    for provider in PROVIDERS:
        if provider.env_vars & env_vars:
            matched.append(provider)
    return matched
