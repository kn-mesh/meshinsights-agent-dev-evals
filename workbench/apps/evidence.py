"""Reusable evidence-adapter contracts for explorer composition."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from workbench.benchmarks.models import BenchmarkExample


class ProjectEvidenceAdapter(Protocol):
    """Build one verified project-owned evidence view."""

    def build_view(
        self,
        *,
        benchmark_key: str,
        benchmark_version_id: str,
        version_number: int,
        example: BenchmarkExample,
    ) -> dict[str, Any]: ...


class ProjectEvidenceAdapterFactory(Protocol):
    """Create an adapter for current or retained storage identity."""

    def __call__(
        self,
        project_root: Path,
        *,
        account_url: str | None = None,
        container: str | None = None,
    ) -> ProjectEvidenceAdapter: ...


class UnconfiguredProjectEvidenceAdapter:
    """Fail precisely until a generated project ports its evidence view."""

    def build_view(
        self,
        *,
        benchmark_key: str,
        benchmark_version_id: str,
        version_number: int,
        example: BenchmarkExample,
    ) -> dict[str, Any]:
        _ = (benchmark_key, benchmark_version_id, version_number, example)
        raise RuntimeError(
            "Use case not configured: port the project evidence adapter before "
            "opening evidence."
        )


def create_unconfigured_project_evidence_adapter(
    project_root: Path,
    *,
    account_url: str | None = None,
    container: str | None = None,
) -> ProjectEvidenceAdapter:
    """Create the neutral adapter used before a project evidence port."""
    _ = (project_root, account_url, container)
    return UnconfiguredProjectEvidenceAdapter()
