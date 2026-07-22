"""Launch the local Agent Workbench human eval-results explorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import threading
import webbrowser
from typing import Any

from agent_eval_ui import create_app
from evaluation import AttemptQuery, query_attempt_rows
from mi.core import bootstrap_environment
import uvicorn

from src.benchmarks.models import BenchmarkExample
from src.evals.inspection import (
    all_inspection_rows,
    find_run_directory,
    inspect_execution,
    inspection_summary,
)
from src.evals.result_integrity import load_verified_result
from src.evals.run_specs import repository_root
from src.evals.run_store import LocalRunStore
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
            "run": result.get("run", {}),
            "example_ids": [
                row["example_id"]
                for row in LocalRunStore(run_dir, run_id=run_id).evaluation_rows()
            ],
            "inspection": inspection,
        }

    def get_performance(self, run_id: str) -> dict[str, Any]:
        """Return optional disposable performance with attempt correlation."""
        run_dir = self._run_dir(run_id)
        path = run_dir / "performance" / "summary.json"
        if not path.is_file():
            return {
                "run_id": run_id,
                "availability": "unavailable",
                "reason": "Performance summary is absent or was deleted.",
            }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Performance summary must be a JSON object.")
            if payload.get("schema_version") != 1 or payload.get("run_id") != run_id:
                raise ValueError("Performance summary identity is invalid.")
            raw_model_calls = payload.get("model_calls", {})
            if not isinstance(raw_model_calls, dict):
                raise ValueError("Performance model_calls must be a JSON object.")
            model_calls = dict(raw_model_calls)
            slowest = model_calls.get("slowest", [])
            if not isinstance(slowest, list):
                raise ValueError("Performance model_calls.slowest must be a JSON array.")
            correlations = self._execution_correlations(run_dir, run_id=run_id)
            model_calls["slowest"] = [
                {
                    **item,
                    **correlations.get(str(item.get("execution_id")), {}),
                }
                for item in slowest
                if isinstance(item, dict)
                and str(item.get("execution_id")) in correlations
            ]
            return {
                "availability": "available",
                **payload,
                "model_calls": model_calls,
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            return {
                "run_id": run_id,
                "availability": "unavailable",
                "reason": f"Performance summary is invalid: {error}",
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
        rows = all_inspection_rows(self._run_dir(run_id))
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
        rows = all_inspection_rows(run_dir)
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
        performance = self._attempt_performance(run_dir, execution_id=execution_id)
        return {
            "run_id": run_id,
            "row": matching[0],
            "review": review,
            "performance": performance,
        }

    def get_evidence(self, run_id: str, example_id: str) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        store = LocalRunStore(run_dir, run_id=run_id)
        manifest = store.read_manifest()
        contract = manifest.get("eval_contract")
        if not isinstance(contract, dict) or contract.get("schema_version") != 1:
            raise ValueError("Run manifest is missing its schema-v1 eval contract.")
        config = contract.get("run")
        if not isinstance(config, dict):
            raise ValueError("Run manifest is missing retained run identity.")
        benchmark_key = str(config.get("benchmark_key") or "")
        benchmark_version_id = str(config.get("benchmark_version_id") or "")
        version = int(config.get("benchmark_version_number") or 0)
        if not benchmark_key or not benchmark_version_id or version < 1:
            raise ValueError("Run is missing exact benchmark identity.")

        raw_examples = contract.get("examples")
        if not isinstance(raw_examples, list):
            raise ValueError("Run manifest is missing retained examples.")
        matches = [
            item
            for item in raw_examples
            if isinstance(item, dict) and item.get("example_id") == example_id
        ]
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected one retained example {example_id}; found {len(matches)}."
            )
        try:
            example = _retained_benchmark_example(matches[0])
        except (TypeError, ValueError) as error:
            raise ValueError(
                "This run predates retained frozen-evidence manifests and cannot "
                "render evidence without weakening integrity. Re-run the evaluation "
                "with the current schema-v1 writer."
            ) from error

        if self._evidence_adapter is None:
            self._evidence_adapter = _azure_evidence_adapter(self.project_root)
        return self._evidence_adapter.build_view(
            benchmark_key=benchmark_key,
            benchmark_version_id=benchmark_version_id,
            version_number=version,
            example=example,
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

    @staticmethod
    def _execution_correlations(
        run_dir: Path, *, run_id: str
    ) -> dict[str, dict[str, Any]]:
        store = LocalRunStore(run_dir, run_id=run_id)
        manifest = store.read_manifest()
        examples = {
            str(item.get("example_id")): item
            for item in manifest.get("eval_contract", {}).get("examples", [])
            if isinstance(item, dict)
        }
        return {
            str(records[-1]["execution_id"]): {
                "example_id": records[-1].get("example_id"),
                "unit_id": examples.get(
                    str(records[-1].get("example_id")), {}
                ).get("unit_id"),
            }
            for records in store.records_by_work_item().values()
            if records
        }

    @staticmethod
    def _attempt_performance(run_dir: Path, *, execution_id: str) -> dict[str, Any]:
        store = LocalRunStore(run_dir, run_id=run_dir.name)
        if not store.performance_dir.is_dir():
            return {
                "availability": "unavailable",
                "reason": "Performance observations are absent or were deleted.",
            }
        try:
            durable = [
                records[-1]
                for records in store.records_by_work_item().values()
                if records and records[-1].get("execution_id") == execution_id
            ]
            if len(durable) != 1:
                return {
                    "availability": "unavailable",
                    "reason": f"Performance is not current for {execution_id}.",
                }
            generation = (
                str(durable[0]["work_item_id"]), int(durable[0]["generation"])
            )
            matching = [
                item
                for item in store.read_performance_records(generations={generation})
                if item.get("execution_id") == execution_id
            ]
            if len(matching) != 1:
                return {
                    "availability": "unavailable",
                    "reason": (
                        f"Expected one performance record for {execution_id}; "
                        f"found {len(matching)}."
                    ),
                }
            return {"availability": "available", **matching[0]}
        except (OSError, ValueError, RuntimeError) as error:
            return {
                "availability": "unavailable",
                "reason": f"Performance observations are invalid: {error}",
            }


def _azure_evidence_adapter(project_root: Path) -> SpiraxEvidenceAdapter:
    """Use project-owned non-secret Blob identity with local Azure credentials."""
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


def _retained_benchmark_example(payload: dict[str, Any]) -> BenchmarkExample:
    """Validate one complete frozen example retained by the run manifest."""
    return BenchmarkExample.model_validate(
        {
            "example_id": payload.get("example_id"),
            "unit_id": payload.get("unit_id"),
            "decision_timestamp": payload.get("decision_timestamp"),
            "approved_label_payload": payload.get("benchmark_labels"),
            "label_schema_version_id": payload.get("label_schema_version_id"),
            "example_metadata": payload.get("metadata", {}),
            "source_snapshot_id": payload.get("source_snapshot_id"),
            "raw_snapshot_content_sha256": payload.get(
                "raw_snapshot_content_sha256"
            ),
            "raw_source_kind": payload.get("raw_source_kind"),
            "raw_captured_at": payload.get("raw_captured_at"),
            "raw_window_start": payload.get("raw_window_start"),
            "raw_window_end": payload.get("raw_window_end"),
            "raw_known_gaps": payload.get("raw_known_gaps", []),
            "raw_artifacts": payload.get("raw_artifacts"),
        }
    )


def build_app(*, project_root: Path | None = None) -> Any:
    bootstrap_environment()
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
