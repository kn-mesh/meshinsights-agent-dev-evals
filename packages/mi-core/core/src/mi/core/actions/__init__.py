"""Action components that execute side effects in the pipeline.

Actions run last in the pipeline lifecycle, reading decisions from
ActionDataObject to perform operations like saving to databases,
sending notifications, or publishing events.

See docs/components/actions.md for examples and best practices.
"""
# ruff: noqa: F401

from .base_action import BaseAction, BaseActionConfig

__all__ = [
    "BaseAction",
    "BaseActionConfig",
]
