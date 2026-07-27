"""Model selection and reasoning configuration primitives for mi.ai."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from typing import Literal, TypeAlias


# NOTE: Provider/Model system

KnownProviderName: TypeAlias = Literal[
    "anthropic",
    "azure",
    "google",
    # "openai",
    "openrouter",
]

# Applications own their fast-moving model catalogs, so model names remain
# unrestricted and mi-core does not need a release for every model addition.
ModelName: TypeAlias = str


_KNOWN_PROVIDERS: frozenset[str] = frozenset(KnownProviderName.__args__)  # type: ignore[attr-defined]
_REGISTERED_PROVIDERS: set[str] = set()


def register_provider(name: str) -> None:
    """Register an application-defined provider name."""
    _REGISTERED_PROVIDERS.add(name.strip().lower())


def is_known_provider(provider: str) -> bool:
    """Return whether *provider* is built-in or application-registered."""
    normalized = provider.strip().lower()
    return normalized in _KNOWN_PROVIDERS or normalized in _REGISTERED_PROVIDERS


@dataclass(frozen=True, slots=True)
class ModelRef:
    """Canonical provider/model reference parsed from ``provider:model``."""

    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ModelRef:
        """Parse and normalize a model identifier.

        Expected format: ``provider:model``.
        """
        raw = value.strip()
        if not raw:
            raise ValueError("Model cannot be empty. Expected format: provider:model")

        provider, sep, model = raw.partition(":")
        if sep == "" or not provider or not model:
            raise ValueError(
                f"Invalid model '{value}'. Expected format: provider:model"
            )

        normalized_provider = provider.strip().lower()
        normalized_model = model.strip()

        if not is_known_provider(normalized_provider):
            raise ValueError(
                f"Unknown provider '{provider}'. "
                "Use a known provider or register one via register_provider()."
            )

        if not normalized_model:
            raise ValueError(f"Invalid model '{value}'. Model name cannot be empty")

        return cls(provider=normalized_provider, model=normalized_model)

    def canonical(self) -> str:
        """Return canonical ``provider:model`` form."""
        return f"{self.provider}:{self.model}"


# NOTE: Reasoning effort


class ReasoningEffort(str, Enum):
    """Supported unified thinking levels passed through to pydantic-ai."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(frozen=True, slots=True)
class ReasoningSpec:
    """Unified reasoning configuration for a model or model pattern.

    ``efforts`` maps the local ``ReasoningEffort`` enum to the unified value
    sent to pydantic-ai's ``thinking`` request parameter. ``False`` disables
    thinking for that effort. Enum values are forwarded as their underlying
    pydantic-compatible strings.
    """

    efforts: dict[ReasoningEffort, bool | ReasoningEffort] = field(default_factory=dict)


_DEFAULT_REASONING_EFFORTS: dict[ReasoningEffort, ReasoningEffort] = {
    effort: effort for effort in ReasoningEffort
}


_REASONING_SPECS: dict[str, ReasoningSpec] = {
    "anthropic:*": ReasoningSpec(
        efforts=dict(_DEFAULT_REASONING_EFFORTS),
    ),
    "azure:claude-*": ReasoningSpec(
        efforts=dict(_DEFAULT_REASONING_EFFORTS),
    ),
    "azure:*": ReasoningSpec(
        efforts=dict(_DEFAULT_REASONING_EFFORTS),
    ),
    "openrouter:*gemini*": ReasoningSpec(
        efforts=dict(_DEFAULT_REASONING_EFFORTS),
    ),
    "google:gemini*": ReasoningSpec(
        efforts=dict(_DEFAULT_REASONING_EFFORTS),
    ),
}

_FALLBACK_SPEC = ReasoningSpec()


def register_reasoning_spec(pattern: str, spec: ReasoningSpec) -> None:
    """Register or override a reasoning spec for a model pattern.

    *pattern* is an fnmatch glob matched against ``provider:model``.
    Exact model names (no wildcards) take priority over glob patterns.
    """
    _REASONING_SPECS[pattern] = spec


def match_reasoning_spec(model: ModelRef) -> ReasoningSpec:
    """Find the best matching reasoning spec for a model.

    Resolution: exact match first, then fnmatch patterns in insertion
    order, then fallback (empty reasoning spec).
    """
    canonical = model.canonical()

    # Exact match (key contains no wildcards)
    if canonical in _REASONING_SPECS:
        return _REASONING_SPECS[canonical]

    # Pattern match in insertion order
    for pattern, spec in _REASONING_SPECS.items():
        if fnmatch(canonical, pattern):
            return spec

    return _FALLBACK_SPEC
