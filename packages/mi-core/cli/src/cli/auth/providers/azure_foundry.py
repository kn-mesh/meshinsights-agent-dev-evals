"""Azure Anthropic credential provider for ``mi auth``.

Auto-fetches ``ANTHROPIC_FOUNDRY_API_KEY`` and the resource identifier
(name or full URI, depending on template configuration) using the Azure CLI.
Falls back to manual entry when ``az`` is unavailable.
"""

from __future__ import annotations

from ..azure import (
    ensure_az_cli,
    ensure_az_login,
    ensure_resource_group,
    ensure_subscription,
    fetch_resource_key,
    resolve_foundry_resource_value,
    select_azure_resource,
)
from ..context import AuthContext, CredentialField
from ..prompts import MessagePrompt
from .base import BaseProvider, FetchGenerator, prompt_for_credentials


class AzureFoundryProvider(BaseProvider):
    name = "Azure Anthropic"
    slug = "azure_foundry"
    description = "Claude models via Azure AI Foundry (ANTHROPIC_FOUNDRY_* vars)"
    fields = [
        CredentialField("ANTHROPIC_FOUNDRY_API_KEY", "Azure Anthropic API key"),
        CredentialField("ANTHROPIC_FOUNDRY_RESOURCE", "Azure Anthropic resource name"),
    ]

    @property
    def env_vars(self) -> set[str]:
        """Match both RESOURCE and BASE_URL variants for template detection."""
        base = {f.env_var for f in self.fields}
        base.add("ANTHROPIC_FOUNDRY_BASE_URL")
        return base

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        ctx.active_provider = self.name

        az = yield from ensure_az_cli(ctx)
        if az is None:
            return (yield from prompt_for_credentials(self, ctx))

        logged_in = yield from ensure_az_login(ctx)
        if not logged_in:
            yield MessagePrompt(
                "Skipping Azure Anthropic (not logged in).", style="warn", indent=True
            )
            return (yield from prompt_for_credentials(self, ctx))

        sub = yield from ensure_subscription(ctx)
        if sub is None:
            return (yield from prompt_for_credentials(self, ctx))

        rg = yield from ensure_resource_group(ctx)
        if rg is None:
            return (yield from prompt_for_credentials(self, ctx))

        resource = yield from select_azure_resource(ctx, rg, "AIServices", "AI Foundry")
        if resource is None:
            return (yield from prompt_for_credentials(self, ctx))

        resource_name: str = resource["name"]

        api_key = yield from fetch_resource_key(ctx, resource_name, rg)
        if api_key is None:
            return (yield from prompt_for_credentials(self, ctx))

        result = {"ANTHROPIC_FOUNDRY_API_KEY": api_key}
        resource_value = yield from resolve_foundry_resource_value(ctx, resource_name)
        result.update(resource_value)
        return result
