"""Shared utilities for AI configuration metadata and orchestration types."""

from __future__ import annotations

from typing import Any, Literal

# Type aliases for orchestrator configuration (matching mi.core.OrchestratorConfig)
RuntimeType = Literal["serial", "threaded", "process"]
ErrorActionType = Literal["stop", "continue"]


def build_ai_metadata_extras(
    *,
    ai_provider: str | None,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
) -> dict[str, Any]:
    """Build metadata extras dict from AI configuration.

    Converts optional AI CLI arguments into a dict suitable for passing
    to pipeline metadata.
    """

    extras: dict[str, Any] = {}
    if ai_provider:
        extras["ai_provider"] = ai_provider
    if ai_model:
        extras["ai_model"] = ai_model
    if ai_reasoning_effort:
        extras["ai_reasoning_effort"] = ai_reasoning_effort
    return extras
