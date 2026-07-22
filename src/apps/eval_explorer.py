"""Launch the local Agent Workbench human eval-results explorer."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import threading
import webbrowser
from typing import Any

from agent_eval_ui import create_app
from evaluation import AttemptQuery, query_attempt_rows
import uvicorn

from src.benchmarks import AzurePostgresBenchmarkRepository
from src.evals.inspection import (
    find_run_directory,
    inspect_execution,
    inspection_summary,
    list_inspection_rows,
)
from src.evals.result_integrity import load_verified_result
from src.evals.run_specs import repository_root
from src.evidence import SpiraxEvidenceAdapter
from src.lifecycle.catalog import LocalLifecycleCatalog
from src.storage.azure_blob import AzureBlobEvidenceStore


_ATTEMPT_STATES = {
    "all",
    "correct",
    "incorrect",
    "invalid",
    "failed",
    "flaky",
    "unscored",
    "review-unavailable",
}


class ProjectExplorerBackend:
    """Compose generic explorer behavior with this project's managed contracts."""

    def __init__(
        self,
        project_root: Path,
        *,
        evidence_adapter: SpiraxEvidenceAdapter | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.eval_root = self.project_root / "eval_results"
        self._evidence_adapter = evidence_adapter

    def list_runs(self) -> dict[str, Any]:
        catalog = LocalLifecycleCatalog(self.project_root).build()
        return {
            "runs": [item.model_dump(mode="json") for item in catalog.runs],
            "findings": [item.model_dump(mode="json") for item in catalog.findings],
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        result = load_verified_result(run_dir / "result.json")
        inspection = inspection_summary(run_dir)
        review = dict(inspection.get("review", {}))
        review.pop("path", None)
        inspection["review"] = review
        return {
            "run_id": run_id,
            "path": str(run_dir.relative_to(self.project_root)),
            "summary": result.get("summary", {}),
            "run_config": result.get("run_config", {}),
            "selected_example_ids": result.get("selected_example_ids", []),
            "inspection": inspection,
        }

    def list_attempts(
        self,
        run_id: str,
        *,
        state: str,
        search: str,
        field: str | None,
        slice_key: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        if state not in _ATTEMPT_STATES:
            raise ValueError(f"Unsupported attempt state: {state}.")
        rows = list_inspection_rows(
            self._run_dir(run_id), filter_name="all", limit=10_000
        )["rows"]
        payload = query_attempt_rows(
            rows,
            AttemptQuery(
                state=state,  # type: ignore[arg-type]
                search=search,
                field=field,
                slice_key=slice_key,
                offset=offset,
                limit=limit,
            ),
        )
        return {"run_id": run_id, **payload}

    def get_attempt(self, run_id: str, execution_id: str) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        rows = list_inspection_rows(run_dir, filter_name="all", limit=10_000)["rows"]
        matching = [row for row in rows if row.get("execution_id") == execution_id]
        if len(matching) != 1:
            raise FileNotFoundError(
                f"Expected one attempt {execution_id}; found {len(matching)}."
            )
        review = None
        if matching[0].get("review_status") != "unavailable":
            review = inspect_execution(
                run_dir, execution_id=execution_id, resolve_text=True
            )
        return {"run_id": run_id, "row": matching[0], "review": review}

    def get_evidence(self, run_id: str, example_id: str) -> dict[str, Any]:
        result = load_verified_result(self._run_dir(run_id) / "result.json")
        config = result.get("run_config", {})
        benchmark_key = str(config.get("benchmark_key") or "")
        version = int(config.get("benchmark_version_number") or 0)
        if not benchmark_key or version < 1:
            raise ValueError("Run is missing exact benchmark identity.")
        adapter = self._evidence_adapter or _azure_evidence_adapter()
        return adapter.build_view(
            benchmark_key=benchmark_key,
            version_number=version,
            example_id=example_id,
        )

    def list_comparisons(self) -> dict[str, Any]:
        catalog = LocalLifecycleCatalog(self.project_root).build()
        return {
            "comparisons": [
                item.model_dump(mode="json") for item in catalog.comparisons
            ]
        }

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        catalog = LocalLifecycleCatalog(self.project_root).build()
        matches = [
            item for item in catalog.comparisons if item.comparison_id == comparison_id
        ]
        if len(matches) != 1 or matches[0].result_path is None:
            raise FileNotFoundError(f"Comparison result not found: {comparison_id}.")
        path = (self.project_root / matches[0].result_path).resolve()
        if not path.is_relative_to(self.project_root):
            raise ValueError("Comparison path escapes the project root.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("comparison_id") != comparison_id:
            raise ValueError("Comparison payload has the wrong identity.")
        return payload

    def _run_dir(self, run_id: str) -> Path:
        return find_run_directory(run_id, root=self.eval_root)


def _azure_evidence_adapter() -> SpiraxEvidenceAdapter:
    project_key = os.getenv("APP_PROJECT_KEY", "").strip()
    if not project_key:
        raise ValueError("APP_PROJECT_KEY is required to render evidence.")
    repository = AzurePostgresBenchmarkRepository(project_key=project_key)
    return SpiraxEvidenceAdapter(
        repository=repository,
        evidence_store=AzureBlobEvidenceStore(),
    )


def build_app(*, project_root: Path | None = None) -> Any:
    root = repository_root(project_root or Path.cwd())
    return create_app(
        backend=ProjectExplorerBackend(root), static_dir=root / "www" / "dist"
    )


app = build_app()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    if args.host != "127.0.0.1":
        parser.error("Remote binding is outside the local explorer MVP.")
    if not args.no_open:
        threading.Timer(
            0.8, lambda: webbrowser.open(f"http://{args.host}:{args.port}")
        ).start()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
