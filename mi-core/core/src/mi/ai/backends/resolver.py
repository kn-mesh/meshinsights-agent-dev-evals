"""Backend resolver for mi.ai.

Uses a catalog of ``BackendSpec`` entries to resolve user-facing backend
names to concrete implementations.  Backend modules are imported lazily
so that ``import mi.ai`` does not pull in optional dependencies like
pydantic-ai at module load time.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mi.ai.backends.base import AIBackend


@dataclass(frozen=True, slots=True)
class BackendSpec:
    """Describes how to locate and instantiate a backend.

    Attributes:
        name:    Canonical backend identifier (should match the class's
                 ``BACKEND_NAME``).
        aliases: All accepted user-facing names that resolve to this
                 backend (including *name* itself).
        module:  Dotted module path imported lazily at resolution time.
        attr:    Name of the ``AIBackend`` subclass inside *module*.
    """

    name: str
    aliases: tuple[str, ...]
    module: str
    attr: str


# NOTE: Built-in catalog

_BACKEND_CATALOG: list[BackendSpec] = [
    BackendSpec(
        name="pydantic_ai",
        aliases=("auto", "pydantic", "pydantic_ai"),
        module="mi.ai.backends.pydantic_ai_backend",
        attr="PydanticAIBackend",
    ),
]


# NOTE: Public registration API


def register_backend(spec: BackendSpec) -> None:
    """Register a custom backend spec.

    Raises ``ValueError`` on alias collisions with existing entries.
    """
    existing_aliases = _build_alias_index()
    for alias in spec.aliases:
        if alias in existing_aliases:
            owner = existing_aliases[alias]
            raise ValueError(
                f"Backend alias '{alias}' is already claimed by backend '{owner.name}'"
            )
    _BACKEND_CATALOG.append(spec)


# NOTE: Resolution


def _normalize(name: str | None) -> str:
    return (name or "auto").strip().lower().replace("-", "_")


def _build_alias_index() -> dict[str, BackendSpec]:
    """Build a flat alias -> spec mapping, detecting collisions."""
    index: dict[str, BackendSpec] = {}
    for spec in _BACKEND_CATALOG:
        for alias in spec.aliases:
            if alias in index:
                raise ValueError(
                    f"Backend alias '{alias}' is claimed by both "
                    f"'{index[alias].name}' and '{spec.name}'"
                )
            index[alias] = spec
    return index


def resolve_backend(name: str | None) -> AIBackend:
    """Resolve a backend name to an implementation instance.

    Backends are imported lazily so that ``import mi.ai`` does not
    require heavy optional dependencies at module load time.
    """
    key = _normalize(name)
    index = _build_alias_index()
    spec = index.get(key)
    if spec is None:
        available = sorted(index.keys())
        raise ValueError(
            f"Unknown AI backend '{name}'. Available: {', '.join(available)}"
        )

    mod = import_module(spec.module)
    cls = getattr(mod, spec.attr, None)
    if cls is None:
        raise ImportError(
            f"Backend class '{spec.attr}' not found in module '{spec.module}'"
        )

    # Sanity-check: the class should declare the same name the spec expects.
    declared = getattr(cls, "BACKEND_NAME", None)
    if declared is not None and declared != spec.name:
        raise ValueError(
            f"Backend class '{spec.attr}' declares BACKEND_NAME='{declared}' "
            f"but catalog spec expects '{spec.name}'"
        )

    return cls()
