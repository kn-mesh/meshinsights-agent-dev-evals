"""Base provider classes for ``mi auth`` credential fetching.

Providers are generators that yield :mod:`~cli.auth.prompts` request
objects and receive user responses via ``send()``.  The wizard
orchestrator drives each generator using standalone UI components.
"""

from __future__ import annotations

import webbrowser
from abc import ABC, abstractmethod
from typing import Any, Generator

from ..context import AuthContext, CredentialField
from ..prompts import MessagePrompt, PromptRequest, TextPrompt

# Type alias for the generator signature used by all providers.
FetchGenerator = Generator[PromptRequest, Any, dict[str, str]]


class BaseProvider(ABC):
    """Abstract base for credential providers.

    Each concrete subclass defines the fields it manages and a ``fetch``
    generator that knows how to obtain values — whether by calling an
    external CLI, delegating to another tool, or prompting the user.
    """

    name: str
    """Human-readable provider name (e.g. ``"Azure Anthropic"``)."""

    slug: str
    """Machine identifier used in ``--provider`` flag and template matching."""

    description: str
    """Short description shown in the provider selection list."""

    fields: list[CredentialField]
    """Credential fields this provider manages."""

    console_url: str | None = None
    """URL to the provider's API-key management page.

    When set, :func:`prompt_for_credentials` opens this URL in the user's
    default browser before prompting for credentials.
    """

    @abstractmethod
    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        """Yield prompt requests and return collected credentials.

        Implementations yield :class:`~cli.auth.prompts.PromptRequest`
        objects and receive responses via ``send()``.  The final
        ``return`` value is a ``dict[str, str]`` mapping env-var names
        to their resolved values.
        """
        ...

    @property
    def env_vars(self) -> set[str]:
        """Return the set of all environment variable names managed by this provider."""
        return {f.env_var for f in self.fields}


class ManualProvider(BaseProvider):
    """Provider that collects credentials via interactive user prompts.

    Used directly for providers with no programmatic key-fetching mechanism
    (e.g. OpenRouter) and as a fallback when automated fetching fails
    (e.g. Azure CLI not installed).
    """

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        ctx.active_provider = self.name
        return (yield from prompt_for_credentials(self, ctx))


def prompt_for_credentials(
    provider: BaseProvider,
    ctx: AuthContext,
) -> FetchGenerator:
    """Interactively prompt the user for each credential field on *provider*.

    This is the manual-entry generator used by :class:`ManualProvider`
    and available as a fallback for any provider whose automated fetching
    fails.
    """
    results: dict[str, str] = {}
    ctx.active_provider = provider.name
    yield MessagePrompt(provider.description, indent=True)

    if provider.console_url:
        yield MessagePrompt(
            f"Opening {provider.console_url}", style="hint", indent=True
        )
        webbrowser.open(provider.console_url)

    for field in provider.fields:
        existing = ctx.existing_env.get(field.env_var)

        # Build hint text
        parts: list[str] = []
        if existing:
            parts.append(f"current: {_mask_value(existing)}")
        if not field.required:
            parts.append("optional")
        hint = f"({', '.join(parts)})" if parts else ""

        # When there is an existing value show a masked placeholder
        # so the raw secret never appears on screen.  If the user
        # presses Enter without typing, we keep the existing value.
        if existing:
            placeholder = _mask_value(existing)
        else:
            placeholder = field.default or "your_token"

        value: str = yield TextPrompt(
            field.description or field.env_var,
            default=placeholder,
            hint=hint,
            password=bool(existing),
        )

        # User accepted the masked placeholder → keep existing value.
        if existing and value == placeholder:
            value = existing

        if value and value != "your_token":
            results[field.env_var] = value

    return results


def _mask_value(value: str | None, visible: int = 5) -> str:
    """Mask all but the first *visible* characters of a value for display."""
    if not value:
        return ""
    if len(value) <= visible:
        return value
    return value[:visible] + "*" * (len(value) - visible)
