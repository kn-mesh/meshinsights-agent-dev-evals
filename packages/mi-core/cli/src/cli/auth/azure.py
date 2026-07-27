"""Shared Azure CLI helpers for ``mi auth`` providers.

Both :class:`AzureFoundryProvider` (Azure Anthropic) and
:class:`AzureOpenAIProvider` (Azure OpenAI) delegate to these utilities for
CLI detection, login verification, subscription and resource group selection,
and resource picking.

Results are cached on :class:`~cli.auth.context.AuthContext` so that when
multiple Azure providers run in the same ``mi auth`` session the user is
only prompted once for login, subscription, and resource group.

All public functions are **generators** that yield
:mod:`~cli.auth.prompts` request objects.  Callers use ``yield from``
to delegate.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Generator

from ..ui.prompts import spinner
from .context import AuthContext
from .prompts import (
    ConfirmPrompt,
    MessagePrompt,
    PromptRequest,
    SelectChoice,
    SelectPrompt,
    SubprocessPrompt,
)

logger = logging.getLogger(__name__)

_AZ_INSTALL_MARKER = Path.home() / ".meshinsights" / ".az-install-offered"
_AZ_INSTALL_URL = "https://aka.ms/installazurecli"

AZURE_ANTHROPIC_URL_PATTERN = "https://{resource}.services.ai.azure.com/anthropic/"
"""URL pattern for both ``ANTHROPIC_BASE_URL`` and ``ANTHROPIC_FOUNDRY_BASE_URL``."""


# ---------------------------------------------------------------------------
# Helpers (non-generator)
# ---------------------------------------------------------------------------


def _provider_tag(ctx: AuthContext) -> str:
    """Return ``" for <Provider>"`` if an active provider is set, else ``""``."""
    if ctx.active_provider:
        return f" for {ctx.active_provider}"
    return ""


def _styled_choices(
    items: list[dict[str, str]],
    name_key: str,
    detail_key: str,
) -> list[SelectChoice]:
    """Build :class:`SelectChoice` objects with grayed-out detail text."""
    choices: list[SelectChoice] = []
    for item in items:
        name = item[name_key]
        detail = item.get(detail_key, "")
        choices.append(SelectChoice(label=name, value=item, hint=detail))
    return choices


def az_json_command(
    ctx: AuthContext,
    args: list[str],
    *,
    message: str | None = None,
) -> Any:
    """Run an ``az`` command with ``--output json`` and return parsed JSON.

    Returns the parsed result, or ``None`` on failure.

    A transient spinner is displayed while the command runs so that the
    user sees feedback for potentially slow Azure CLI calls.
    """
    cmd = [ctx.az_path or "az", *args, "--output", "json"]
    logger.debug("Running: %s", " ".join(cmd))

    label = message or f"Running az {' '.join(args[:2])}..."
    result = spinner(
        label,
        work=lambda: subprocess.run(cmd, capture_output=True, text=True, check=False),
    )

    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result else ""
        logger.debug(
            "az command failed (exit %d): %s",
            result.returncode if result else -1,
            stderr,
        )
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug("Failed to parse az output: %s", result.stdout[:200])
        return None


# Type alias for azure helper generators.
_AzGen = Generator[PromptRequest, Any, Any]


# ---------------------------------------------------------------------------
# Azure CLI detection & login
# ---------------------------------------------------------------------------


def ensure_az_cli(ctx: AuthContext) -> _AzGen:
    """Check that the Azure CLI is available, offering install guidance if not.

    Yields prompt requests as needed.  Returns the path to ``az`` or
    ``None`` if it is unavailable.
    """
    if ctx.az_checked:
        return ctx.az_path

    ctx.az_checked = True
    az = shutil.which("az")
    if az is not None:
        ctx.az_path = az
        return az

    # First time: offer to install
    if not _AZ_INSTALL_MARKER.exists():
        _AZ_INSTALL_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _AZ_INSTALL_MARKER.touch()

        system = platform.system().lower()
        if system == "darwin":
            install_hint = "brew install azure-cli"
        elif system == "linux":
            install_hint = "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"
        else:
            install_hint = f"Visit {_AZ_INSTALL_URL}"

        yield MessagePrompt(
            "Azure CLI not found. It is required to auto-fetch Azure credentials.",
            style="warn",
        )
        yield MessagePrompt(f"Install with: {install_hint}", indent=True)
        yield MessagePrompt(f"Full instructions: {_AZ_INSTALL_URL}", indent=True)

        if system in ("darwin", "linux"):
            should_install: bool = yield ConfirmPrompt(
                "Attempt to install now?", default=False
            )
            if should_install:
                yield MessagePrompt("Installing Azure CLI...", style="info")
                rc: int = yield SubprocessPrompt(
                    ["sh", "-c", install_hint], label="Azure CLI install"
                )
                if rc == 0:
                    az = shutil.which("az")
                    if az is not None:
                        yield MessagePrompt(
                            "Azure CLI installed successfully.", style="info"
                        )
                        ctx.az_path = az
                        return az
                yield MessagePrompt("Azure CLI installation failed.", style="error")
    else:
        yield MessagePrompt(
            f"Azure CLI not found. Install from {_AZ_INSTALL_URL}",
            style="warn",
        )

    yield MessagePrompt(
        "Falling back to manual credential entry.", style="hint", indent=True
    )
    ctx.az_path = None
    return None


def ensure_az_login(ctx: AuthContext) -> _AzGen:
    """Verify the user is logged in to Azure, prompting ``az login`` if not.

    Returns ``True`` when the user is authenticated, ``False`` otherwise.
    """
    if ctx.az_logged_in is not None:
        return ctx.az_logged_in

    cmd = [ctx.az_path or "az", "account", "show"]
    result = spinner(
        "Checking Azure login status...",
        work=lambda: subprocess.run(cmd, capture_output=True, text=True, check=False),
    )

    if result is not None and result.returncode == 0:
        ctx.az_logged_in = True
        return True

    yield MessagePrompt("Not logged in to Azure.", style="warn", indent=True)
    should_login: bool = yield ConfirmPrompt("Run 'az login' now?", default=True)
    if not should_login:
        ctx.az_logged_in = False
        return False

    yield MessagePrompt("Opening browser for Azure login...", style="info", indent=True)
    login_rc: int = yield SubprocessPrompt(
        [ctx.az_path or "az", "login"], label="az login"
    )

    ctx.az_logged_in = login_rc == 0
    if not ctx.az_logged_in:
        yield MessagePrompt("Azure login failed.", style="error", indent=True)
    return ctx.az_logged_in


# ---------------------------------------------------------------------------
# Subscription & resource group selection
# ---------------------------------------------------------------------------


def ensure_subscription(ctx: AuthContext) -> _AzGen:
    """Prompt the user to select an Azure subscription if not already cached.

    Returns the subscription ID, or ``None`` on failure.
    """
    if ctx.az_subscription is not None:
        return ctx.az_subscription

    tag = _provider_tag(ctx)

    subs = az_json_command(
        ctx,
        [
            "account",
            "list",
            "--query",
            "[?state=='Enabled'].{id:id, name:name}",
        ],
        message="Fetching Azure subscriptions...",
    )

    if not subs:
        yield MessagePrompt("No Azure subscriptions found.", style="error", indent=True)
        return None

    if len(subs) == 1:
        ctx.az_subscription = subs[0]["id"]
        yield MessagePrompt(
            f"Using subscription: {subs[0]['name']}", style="info", indent=True
        )
        return ctx.az_subscription

    # Multiple subscriptions — let the user pick
    choices = _styled_choices(subs, name_key="name", detail_key="id")
    result = yield SelectPrompt(f"Select Azure subscription{tag}:", choices=choices)

    if result is None:
        return None

    ctx.az_subscription = result["id"]

    # Set it as the active subscription
    az_json_command(
        ctx,
        ["account", "set", "--subscription", result["id"]],
        message="Setting active subscription...",
    )
    yield MessagePrompt(
        f"Using subscription: {result['name']}", style="info", indent=True
    )
    return result["id"]


def ensure_resource_group(ctx: AuthContext) -> _AzGen:
    """Prompt the user to select an Azure resource group if not already cached.

    Returns the selected resource group name, or ``None`` if selection fails.
    """
    if ctx.az_resource_group is not None:
        return ctx.az_resource_group

    tag = _provider_tag(ctx)

    groups = az_json_command(
        ctx,
        ["group", "list", "--query", "[].name"],
        message="Fetching resource groups...",
    )
    if not groups:
        yield MessagePrompt(
            "No resource groups found in current subscription.",
            style="error",
            indent=True,
        )
        return None

    if len(groups) == 1:
        ctx.az_resource_group = groups[0]
        yield MessagePrompt(
            f"Using resource group: {groups[0]}", style="info", indent=True
        )
        return ctx.az_resource_group

    # Convert plain strings to SelectChoice objects
    str_choices = [SelectChoice(label=g) for g in groups]
    selected = yield SelectPrompt(f"Select resource group{tag}:", choices=str_choices)

    if selected is None:
        return None

    ctx.az_resource_group = selected
    yield MessagePrompt(f"Using resource group: {selected}", style="info", indent=True)
    return selected


# ---------------------------------------------------------------------------
# Resource selection
# ---------------------------------------------------------------------------


def select_azure_resource(
    ctx: AuthContext,
    resource_group: str,
    kind_filter: str,
    label: str,
) -> _AzGen:
    """List CognitiveServices resources and let the user pick one.

    If a previous Azure provider already selected a resource in this session,
    offers to reuse it.

    Returns ``{"name": ..., "endpoint": ...}`` or ``None`` on failure.
    """
    tag = _provider_tag(ctx)

    # Offer to reuse previous resource
    if ctx.az_last_resource is not None:
        prev_name = ctx.az_last_resource["name"]
        reuse: bool = yield ConfirmPrompt(
            f"Use same Azure resource as before ({prev_name}){tag}?",
            default=True,
        )
        if reuse:
            return ctx.az_last_resource

        # User declined — reset cached Azure state so they re-pick from scratch
        ctx.az_subscription = None
        ctx.az_resource_group = None
        ctx.az_last_resource = None

        # Re-prompt subscription and resource group
        sub = yield from ensure_subscription(ctx)
        if sub is None:
            return None
        rg = yield from ensure_resource_group(ctx)
        if rg is None:
            return None
        resource_group = rg

    resources = az_json_command(
        ctx,
        [
            "cognitiveservices",
            "account",
            "list",
            "-g",
            resource_group,
            "--query",
            f"[?kind=='{kind_filter}'].{{name:name, endpoint:properties.endpoint}}",
        ],
        message=f"Searching for {label} resources...",
    )

    if not resources:
        yield MessagePrompt(
            f"No {label} resources found in resource group '{resource_group}'.",
            style="warn",
        )
        return None

    if len(resources) == 1:
        selected = resources[0]
        yield MessagePrompt(f"Found resource: {selected['name']}", indent=True)
    else:
        # Normalise missing endpoints for alignment
        for r in resources:
            r.setdefault("endpoint", "")
        choices = _styled_choices(resources, name_key="name", detail_key="endpoint")
        selected = yield SelectPrompt(f"Select {label} resource{tag}:", choices=choices)

        if selected is None:
            return None

    # Cache for subsequent Azure providers
    ctx.az_last_resource = selected
    return selected


# ---------------------------------------------------------------------------
# Key fetching
# ---------------------------------------------------------------------------


def fetch_resource_key(
    ctx: AuthContext,
    resource_name: str,
    resource_group: str,
) -> _AzGen:
    """Fetch the primary API key for a CognitiveServices resource.

    Returns the key string, or ``None`` on failure.
    """
    keys = az_json_command(
        ctx,
        [
            "cognitiveservices",
            "account",
            "keys",
            "list",
            "-n",
            resource_name,
            "-g",
            resource_group,
        ],
        message=f"Fetching API key for {resource_name}...",
    )

    if not keys or "key1" not in keys:
        yield MessagePrompt("Failed to retrieve API key.", style="error", indent=True)
        return None

    yield MessagePrompt("API key retrieved.", style="info", indent=True)
    return keys["key1"]


# ---------------------------------------------------------------------------
# Foundry resource-name-vs-URI resolution
# ---------------------------------------------------------------------------


def resolve_foundry_resource_value(
    ctx: AuthContext,
    resource_name: str,
) -> _AzGen:
    """Decide whether to store the resource name or full URI for Foundry.

    Returns a single-entry dict: either ``{ANTHROPIC_FOUNDRY_RESOURCE: ...}``
    or ``{ANTHROPIC_FOUNDRY_BASE_URL: ...}``.
    """
    has_base_url_var = "ANTHROPIC_FOUNDRY_BASE_URL" in ctx.template_vars
    has_resource_var = "ANTHROPIC_FOUNDRY_RESOURCE" in ctx.template_vars

    if has_base_url_var and not has_resource_var:
        base_url = AZURE_ANTHROPIC_URL_PATTERN.format(resource=resource_name)
        return {"ANTHROPIC_FOUNDRY_BASE_URL": base_url}

    if has_resource_var and not has_base_url_var:
        return {"ANTHROPIC_FOUNDRY_RESOURCE": resource_name}

    # Both or neither in template — ask the user
    base_url = AZURE_ANTHROPIC_URL_PATTERN.format(resource=resource_name)
    choices = [
        SelectChoice(label="Full URI", value="uri", hint=f"({base_url})"),
        SelectChoice(label="Resource name", value="name", hint=f"({resource_name})"),
    ]
    selected = yield SelectPrompt(
        "Store resource as name or full URI?",
        choices=choices,
        max_height=0,
    )

    if selected == "uri":
        return {"ANTHROPIC_FOUNDRY_BASE_URL": base_url}
    # Default to name (including if user cancels)
    return {"ANTHROPIC_FOUNDRY_RESOURCE": resource_name}
