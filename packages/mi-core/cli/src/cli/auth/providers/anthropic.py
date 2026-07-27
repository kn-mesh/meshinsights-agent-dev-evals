"""Anthropic credential provider for ``mi auth``.

Offers the user a choice between:

1. **Direct API key** — prompt for ``ANTHROPIC_API_KEY`` (from console.anthropic.com).
2. **Azure-hosted** — auto-fetch an Azure AI Services key and build the
   ``ANTHROPIC_BASE_URL``, setting ``ANTHROPIC_API_KEY`` and
   ``ANTHROPIC_BASE_URL`` so the standard Anthropic SDK routes through Azure.
"""

from __future__ import annotations

from ..azure import (
    AZURE_ANTHROPIC_URL_PATTERN,
    ensure_az_cli,
    ensure_az_login,
    ensure_resource_group,
    ensure_subscription,
    fetch_resource_key,
    select_azure_resource,
)
from ..context import AuthContext, CredentialField
from ..prompts import MessagePrompt, SelectChoice, SelectPrompt
from .base import BaseProvider, FetchGenerator, prompt_for_credentials

# Fields for each mode — only the chosen mode's fields are used at runtime.
_DIRECT_FIELDS = [
    CredentialField("ANTHROPIC_API_KEY", "Anthropic API key"),
]

_AZURE_FIELDS = [
    CredentialField("ANTHROPIC_API_KEY", "Anthropic API key (Azure)"),
    CredentialField("ANTHROPIC_BASE_URL", "Anthropic base URL (Azure endpoint)"),
]


class AnthropicProvider(BaseProvider):
    name = "Anthropic"
    slug = "anthropic"
    description = "Anthropic Claude models (direct API or Azure-hosted)"
    fields = _DIRECT_FIELDS  # default for template matching

    @property
    def env_vars(self) -> set[str]:
        """Expose vars for both modes so template matching works."""
        return {f.env_var for f in _DIRECT_FIELDS + _AZURE_FIELDS}

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        ctx.active_provider = self.name

        # If env already has a base URL, default to Azure mode
        has_azure = bool(ctx.existing_env.get("ANTHROPIC_BASE_URL"))

        choices = [
            SelectChoice(
                label="Azure-hosted",
                value="azure",
                hint="(Anthropic via Azure AI Foundry)",
            ),
            SelectChoice(
                label="Direct API key",
                value="direct",
                hint="(console.anthropic.com)",
            ),
        ]

        # Pre-select based on existing credentials
        default = "azure" if has_azure else "direct"

        selected = yield SelectPrompt(
            "How do you want to authenticate with Anthropic?",
            choices=choices,
            default=default,
            max_height=0,  # Only 2 items, no scroll needed
        )

        if selected is None:
            return {}

        if selected == "azure":
            return (yield from self._fetch_azure(ctx))
        return (yield from self._fetch_direct(ctx))

    def _fetch_direct(self, ctx: AuthContext) -> FetchGenerator:
        """Prompt for a direct Anthropic API key."""
        self.fields = _DIRECT_FIELDS
        self.console_url = "https://console.anthropic.com/settings/keys"
        return (yield from prompt_for_credentials(self, ctx))

    def _fetch_azure(self, ctx: AuthContext) -> FetchGenerator:
        """Fetch credentials via Azure, setting ANTHROPIC_API_KEY + ANTHROPIC_BASE_URL."""
        self.fields = _AZURE_FIELDS

        az = yield from ensure_az_cli(ctx)
        if az is None:
            return (yield from prompt_for_credentials(self, ctx))

        logged_in = yield from ensure_az_login(ctx)
        if not logged_in:
            yield MessagePrompt(
                "Skipping Azure (not logged in).", style="warn", indent=True
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

        base_url = AZURE_ANTHROPIC_URL_PATTERN.format(resource=resource_name)

        return {
            "ANTHROPIC_API_KEY": api_key,
            "ANTHROPIC_BASE_URL": base_url,
        }
