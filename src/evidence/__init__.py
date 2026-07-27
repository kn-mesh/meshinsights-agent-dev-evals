"""Project-owned evidence normalization and explorer presentation contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from src.benchmarks.models import BenchmarkExample
from src.evidence.spirax import SpiraxEvidenceAdapter, build_spirax_evidence_view
from src.storage.azure_blob import AzureBlobEvidenceStore


class ProjectEvidenceAdapter(Protocol):
    """Use-case extension point consumed by the reusable explorer backend."""

    def build_view(
        self,
        *,
        benchmark_key: str,
        benchmark_version_id: str,
        version_number: int,
        example: BenchmarkExample,
    ) -> dict[str, Any]: ...


def create_project_evidence_adapter(
    project_root: Path,
    *,
    account_url: str | None = None,
    container: str | None = None,
) -> ProjectEvidenceAdapter:
    """Build the current use case's adapter from non-secret project identity."""
    if account_url is None or container is None:
        project_path = project_root / "workbench.project.json"
        try:
            project = json.loads(project_path.read_text(encoding="utf-8"))
            benchmark_studio = project["benchmark_studio"]
            account_url = str(benchmark_studio["storage_account_url"]).strip()
            container = str(benchmark_studio["storage_container"]).strip()
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError(
                "workbench.project.json must declare Benchmark Studio Blob account "
                "and container identities for evidence retrieval."
            ) from error
    account_url = account_url.strip()
    container = container.strip()
    if not account_url or not container:
        raise ValueError(
            "Benchmark Studio Blob account and container identities must not be empty."
        )
    return SpiraxEvidenceAdapter(
        evidence_store=AzureBlobEvidenceStore(
            account_url=account_url,
            container=container,
        )
    )


__all__ = [
    "ProjectEvidenceAdapter",
    "SpiraxEvidenceAdapter",
    "build_spirax_evidence_view",
    "create_project_evidence_adapter",
]
