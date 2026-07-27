"""Explicit project-owned deterministic grader registration."""

from __future__ import annotations

from evaluation import GraderRegistry, build_default_grader_registry
from evaluation.graders import GraderFactory


PROJECT_GRADERS: tuple[GraderFactory, ...] = ()


def build_project_grader_registry() -> GraderRegistry:
    """Combine core graders with explicitly imported project grader factories."""
    registry = build_default_grader_registry()
    for factory in PROJECT_GRADERS:
        registry.register(factory)
    return registry
