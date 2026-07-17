"""Shared validators for eval CLI inputs."""

from __future__ import annotations

from src.experimental_core.evals.cli.models import RuntimeProfileSpec


def normalize_ai_reasoning_effort(value: str | None) -> str | None:
    """Normalize an optional AI reasoning effort override to a canonical form."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized == "default":
        return None
    return normalized


def resolve_execution_profile(
    name: str, profiles: dict[str, RuntimeProfileSpec]
) -> RuntimeProfileSpec:
    """Resolve one named execution profile to its runtime settings."""
    try:
        return profiles[name]
    except KeyError as exc:
        supported = ", ".join(sorted(profiles)) or "<none>"
        raise ValueError(
            f"Unsupported execution profile: {name}. Supported: {supported}."
        ) from exc
