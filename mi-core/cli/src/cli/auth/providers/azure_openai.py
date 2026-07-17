"""Azure OpenAI credential provider for ``mi auth``.

Auto-fetches ``AZURE_OPENAI_ENDPOINT`` and ``AZURE_OPENAI_API_KEY`` using the
Azure CLI.  Queries AIServices resources (Azure AI Foundry) — the same
resource type used by Azure Foundry — since Azure OpenAI is now served
through AI Foundry.

Falls back to manual entry when ``az`` is unavailable.
"""

from __future__ import annotations

from ..azure import (
    ensure_az_cli,
    ensure_az_login,
    ensure_resource_group,
    ensure_subscription,
    fetch_resource_key,
    select_azure_resource,
)
from ..context import AuthContext, CredentialField
from ..prompts import MessagePrompt
from .base import BaseProvider, FetchGenerator, prompt_for_credentials

_DEFAULT_API_VERSION = "2024-12-01-preview"


class AzureOpenAIProvider(BaseProvider):
    name = "Azure OpenAI"
    slug = "azure_openai"
    description = "Azure-hosted GPT models"
    fields = [
        CredentialField("AZURE_OPENAI_ENDPOINT", "Azure OpenAI endpoint URL"),
        CredentialField("AZURE_OPENAI_API_KEY", "Azure OpenAI API key"),
        CredentialField(
            "OPENAI_API_VERSION",
            "OpenAI API version",
            required=False,
            default=_DEFAULT_API_VERSION,
        ),
    ]

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        ctx.active_provider = self.name

        az = yield from ensure_az_cli(ctx)
        if az is None:
            return (yield from prompt_for_credentials(self, ctx))

        logged_in = yield from ensure_az_login(ctx)
        if not logged_in:
            yield MessagePrompt(
                "Skipping Azure OpenAI (not logged in).", style="warn", indent=True
            )
            return (yield from prompt_for_credentials(self, ctx))

        sub = yield from ensure_subscription(ctx)
        if sub is None:
            return (yield from prompt_for_credentials(self, ctx))

        rg = yield from ensure_resource_group(ctx)
        if rg is None:
            return (yield from prompt_for_credentials(self, ctx))

        # Azure OpenAI is served through AIServices (Azure AI Foundry)
        resource = yield from select_azure_resource(ctx, rg, "AIServices", "AI Foundry")
        if resource is None:
            return (yield from prompt_for_credentials(self, ctx))

        resource_name: str = resource["name"]
        endpoint: str = resource.get("endpoint", "")

        api_key = yield from fetch_resource_key(ctx, resource_name, rg)
        if api_key is None:
            return (yield from prompt_for_credentials(self, ctx))

        # Determine API version
        api_version = ctx.existing_env.get("OPENAI_API_VERSION", _DEFAULT_API_VERSION)

        result: dict[str, str] = {
            "AZURE_OPENAI_ENDPOINT": endpoint,
            "AZURE_OPENAI_API_KEY": api_key,
        }
        if api_version:
            result["OPENAI_API_VERSION"] = api_version

        return result
