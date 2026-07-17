"""Hydrator components that convert data between pipeline stages.

Three hydrator types handle the transitions: retrieve -> process,
process -> action, and action -> final cleanup. Each implements
BaseHydrator with typed source and target generics.

See docs/components/hydrators.md for examples and best practices.
"""
# ruff: noqa: F401

from .base_hydrator import BaseHydrator, BaseHydratorConfig

__all__ = [
    # shared hydrator parent
    "BaseHydrator",
    "BaseHydratorConfig",
]
