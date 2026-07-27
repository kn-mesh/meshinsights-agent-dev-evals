"""Mesh Insights - A flexible, type-safe framework for building multi-stage data pipelines.

Subpackages:
    - mi.core: Pipeline framework, components, and execution engine
    - mi.utilities: Shared infrastructure (caching, thread-safe execution)
    - mi.ai: AI workflow and agent processors (requires optional dependencies)

See docs/getting-started.md for a quick-start tutorial.
"""
# ruff: noqa: F401

from mi import core, utilities

__all__ = ["core", "utilities"]
