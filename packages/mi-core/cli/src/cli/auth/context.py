"""Shared dataclasses for the ``mi auth`` command."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CredentialField:
    """Describes a single environment variable required by a provider."""

    env_var: str
    """Environment variable name (e.g. ``ANTHROPIC_API_KEY``)."""

    description: str
    """Human-readable description shown during prompts."""

    required: bool = True
    """Whether this field is mandatory for the provider to function."""

    default: str | None = None
    """Default value to pre-fill when prompting the user."""


@dataclass
class AuthContext:
    """Mutable state shared across provider ``fetch()`` calls within a single
    ``mi auth`` session.

    Azure-specific fields are lazily populated by the first Azure provider
    that runs and reused by subsequent ones, avoiding redundant prompts.
    """

    project_root: Path
    """Resolved project root directory."""

    existing_env: dict[str, str] = field(default_factory=dict)
    """Key-value pairs already present in the ``.env`` file + ``os.environ``."""

    template_vars: set[str] = field(default_factory=set)
    """Variable names found in ``.env.template`` (used for smart defaults)."""

    # -- Active provider ---------------------------------------------------
    active_provider: str = ""
    """Human-readable name of the provider currently being configured.

    Set by each provider at the start of ``fetch()``.  Referenced by shared
    helpers (e.g. Azure selectors) so prompts clearly indicate which
    provider's credentials the user is selecting for.
    """

    # -- Azure shared state ------------------------------------------------
    az_path: str | None = None
    """Cached result of ``shutil.which("az")``.  ``None`` means not yet checked."""

    az_checked: bool = False
    """Whether Azure CLI availability has been checked."""

    az_logged_in: bool | None = None
    """Cached Azure login status.  ``None`` means not yet checked."""

    az_subscription: str | None = None
    """User-selected Azure subscription ID (reused across Azure providers)."""

    az_resource_group: str | None = None
    """User-selected Azure resource group (reused across Azure providers)."""

    az_last_resource: dict[str, Any] | None = None
    """Last Azure CognitiveServices resource selected by any provider.

    Stored as ``{"name": ..., "endpoint": ...}`` so subsequent Azure
    providers can offer to reuse the same resource.
    """
