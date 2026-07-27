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
from src.apps.evidence import (
    ProjectEvidenceAdapter,
    ProjectEvidenceAdapterFactory,
    create_unconfigured_project_evidence_adapter,
)
from src.evals.inspection import (
    all_inspection_rows,
    inspect_execution,
    inspection_summary,
)
from src.evals.result_integrity import load_verified_result
from src.evals.run_specs import repository_root
from src.evals.run_store import LocalRunStore
from src.eval_lifecycle import EvalLifecycleService


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
        evidence_adapter: ProjectEvidenceAdapter | None = None,
        evidence_adapter_factory: ProjectEvidenceAdapterFactory | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.eval_root = self.project_root / "eval_results"
        self.lifecycle = EvalLifecycleService(self.project_root)
        self._evidence_adapter = evidence_adapter
        self._evidence_adapter_factory = (
            evidence_adapter_factory or create_unconfigured_project_evidence_adapter
        )
        self._evidence_adapters: dict[
            tuple[str | None, str | None], ProjectEvidenceAdapter
        ] = {}

    def list_runs(self) -> dict[str, Any]:
        return {"runs": self.lifecycle.list_evals(), "findings": []}

    def get_run(self, run_id: str) -> dict[str, Any]:
        entry = self.lifecycle.inspect(run_id)
        run_dir = self._run_dir(run_id)
        if entry["lifecycle_state"] == "retained":
            self.lifecycle.verify(run_id)
            result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
            units = self._retained_units(run_dir)
            return {
                "run_id": run_id,
                "source_run_id": entry["source_run_id"],
                "lifecycle_state": "retained",
                "path": str(run_dir.relative_to(self.project_root)),
                "summary": result.get("summary", {}),
                "run": result.get("run", {}),
                "example_ids": sorted({str(row["example_id"]) for row in units}),
                "inspection": {
                    "review": {
                        "status": "retained_compact",
                        "reason": (
                            "Full final AI outputs and grading are retained; tool "
                            "traces and performance detail were pruned on elevation."
                        ),
                    }
                },
            }
        result = load_verified_result(run_dir / "result.json")
        inspection = inspection_summary(run_dir)
        review = dict(inspection.get("review", {}))
        review.pop("path", None)
        inspection["review"] = review
        return {
            "run_id": run_id,
            "source_run_id": run_id,
            "lifecycle_state": "working",
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
        entry = self.lifecycle.inspect(run_id)
        if entry["lifecycle_state"] == "retained":
            return {
                "run_id": run_id,
                "availability": "unavailable",
                "reason": "Performance detail was pruned when this eval was retained.",
            }
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
                raise ValueError(
                    "Performance model_calls.slowest must be a JSON array."
                )
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
        entry = self.lifecycle.inspect(run_id)
        run_dir = self._run_dir(run_id)
        rows = (
            self._retained_units(run_dir)
            if entry["lifecycle_state"] == "retained"
            else all_inspection_rows(run_dir)
        )
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
        entry = self.lifecycle.inspect(run_id)
        run_dir = self._run_dir(run_id)
        rows = (
            self._retained_units(run_dir)
            if entry["lifecycle_state"] == "retained"
            else all_inspection_rows(run_dir)
        )
        matching = [row for row in rows if row.get("execution_id") == execution_id]
        if len(matching) != 1:
            raise FileNotFoundError(
                f"Expected one attempt {execution_id}; found {len(matching)}."
            )
        review = None
        if (
            entry["lifecycle_state"] == "working"
            and matching[0].get("review_status") != "unavailable"
        ):
            review = inspect_execution(
                run_dir, execution_id=execution_id, resolve_text=True
            )
        performance = (
            {
                "availability": "unavailable",
                "reason": "Performance detail was pruned during elevation.",
            }
            if entry["lifecycle_state"] == "retained"
            else self._attempt_performance(run_dir, execution_id=execution_id)
        )
        benchmark_context = self._benchmark_context_for_entry(
            entry, run_dir, example_id=str(matching[0]["example_id"])
        )
        return {
            "run_id": run_id,
            "row": matching[0],
            "review": review,
            "performance": performance,
            "benchmark_context": benchmark_context,
        }

    def get_evidence(self, run_id: str, example_id: str) -> dict[str, Any]:
        entry = self.lifecycle.inspect(run_id)
        run_dir = self._run_dir(run_id)
        if entry["lifecycle_state"] == "retained":
            return self._retained_evidence(
                run_id, run_dir=run_dir, example_id=example_id
            )
        store = LocalRunStore(run_dir, run_id=run_id)
        manifest = store.read_manifest()
        contract = manifest.get("eval_contract")
        if not isinstance(contract, dict) or contract.get("schema_version") != 2:
            raise ValueError("Run manifest is missing a supported eval contract.")
        config = contract.get("run")
        if not isinstance(config, dict):
            raise ValueError("Run manifest is missing retained run identity.")
        dimensions = config.get("dimensions")
        if not isinstance(dimensions, dict):
            raise ValueError("Run manifest is missing canonical dimensions.")
        benchmark = dimensions.get("benchmark")
        if not isinstance(benchmark, dict):
            raise ValueError("Run manifest is missing benchmark dimensions.")
        benchmark_key = str(benchmark.get("key") or "")
        benchmark_version_id = str(benchmark.get("version_id") or "")
        version = int(benchmark.get("version") or 0)
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
        example = _retained_benchmark_example(matches[0])

        run_evidence = manifest.get("run_spec", {}).get("evidence", {})
        adapter = self._evidence_adapter_for(
            account_url=run_evidence.get("storage_account_url"),
            container=run_evidence.get("storage_container"),
        )
        return adapter.build_view(
            benchmark_key=benchmark_key,
            benchmark_version_id=benchmark_version_id,
            version_number=version,
            example=example,
        )

    def _run_dir(self, run_id: str) -> Path:
        entry = self.lifecycle.inspect(run_id)
        path = (self.project_root / entry["path"]).resolve()
        if not path.is_relative_to(self.eval_root.resolve()):
            raise ValueError("Eval path escapes the eval-results root.")
        return path

    @staticmethod
    def _retained_units(run_dir: Path) -> list[dict[str, Any]]:
        payload = json.loads((run_dir / "units.json").read_text(encoding="utf-8"))
        units = payload.get("units")
        if not isinstance(units, list) or not all(
            isinstance(item, dict) for item in units
        ):
            raise ValueError("Retained units artifact is invalid.")
        return [
            {
                **item,
                # The UI contract needs a route key. A retained work item is already
                # stable and repetition-specific, so expose it without persisting
                # disposable execution identity in the retained artifact.
                "execution_id": item.get("work_item_id"),
            }
            for item in units
        ]

    def _retained_evidence(
        self, run_id: str, *, run_dir: Path, example_id: str
    ) -> dict[str, Any]:
        self.lifecycle.verify(run_id)
        references = json.loads(
            (run_dir / "evidence-references.json").read_text(encoding="utf-8")
        )
        matches = [
            item
            for item in references.get("examples", [])
            if isinstance(item, dict) and item.get("example_id") == example_id
        ]
        unit_matches = [
            item
            for item in self._retained_units(run_dir)
            if item.get("example_id") == example_id
        ]
        if len(matches) != 1 or not unit_matches:
            raise FileNotFoundError(
                f"Expected one retained evidence reference for {example_id}."
            )
        example_payload = {
            **matches[0],
            "benchmark_labels": unit_matches[0].get("benchmark_labels"),
        }
        example = _retained_benchmark_example(example_payload)
        result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
        benchmark = result["run"]["dimensions"]["benchmark"]
        storage = references.get("storage", {})
        adapter = self._evidence_adapter_for(
            account_url=storage.get("account_url"),
            container=storage.get("container"),
        )
        return adapter.build_view(
            benchmark_key=str(benchmark["key"]),
            benchmark_version_id=str(benchmark["version_id"]),
            version_number=int(benchmark["version"]),
            example=example,
        )

    def _evidence_adapter_for(
        self, *, account_url: str | None, container: str | None
    ) -> ProjectEvidenceAdapter:
        if self._evidence_adapter is not None:
            return self._evidence_adapter
        key = (account_url, container)
        if key not in self._evidence_adapters:
            self._evidence_adapters[key] = (
                self._evidence_adapter_factory(
                    self.project_root,
                    account_url=account_url,
                    container=container,
                )
                if account_url is not None and container is not None
                else self._evidence_adapter_factory(self.project_root)
            )
        return self._evidence_adapters[key]

    def _benchmark_context_for_entry(
        self, entry: dict[str, Any], run_dir: Path, *, example_id: str
    ) -> dict[str, Any]:
        if entry["lifecycle_state"] == "working":
            return self._benchmark_context(run_dir, example_id=example_id)
        matches = [
            item
            for item in self._retained_units(run_dir)
            if item.get("example_id") == example_id
        ]
        if not matches:
            raise FileNotFoundError(f"Retained example not found: {example_id}")
        context = matches[0].get("published_review_context")
        if not isinstance(context, dict):
            raise ValueError("Retained eval is missing published review context.")
        return {"availability": "available", **context}

    @staticmethod
    def _benchmark_context(run_dir: Path, *, example_id: str) -> dict[str, Any]:
        manifest = LocalRunStore(run_dir, run_id=run_dir.name).read_manifest()
        examples = manifest.get("eval_contract", {}).get("examples", [])
        matches = [
            item
            for item in examples
            if isinstance(item, dict) and item.get("example_id") == example_id
        ]
        if len(matches) != 1:
            raise FileNotFoundError(
                f"Expected one retained example {example_id}; found {len(matches)}."
            )
        context = matches[0].get("published_review_context")
        if not isinstance(context, dict):
            raise ValueError("Working eval is missing published review context.")
        return {"availability": "available", **context}

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
                "unit_id": examples.get(str(records[-1].get("example_id")), {}).get(
                    "unit_id"
                ),
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
                str(durable[0]["work_item_id"]),
                int(durable[0]["generation"]),
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
            "raw_snapshot_content_sha256": payload.get("raw_snapshot_content_sha256"),
            "raw_source_kind": payload.get("raw_source_kind"),
            "raw_captured_at": payload.get("raw_captured_at"),
            "raw_window_start": payload.get("raw_window_start"),
            "raw_window_end": payload.get("raw_window_end"),
            "raw_known_gaps": payload.get("raw_known_gaps", []),
            "raw_artifacts": payload.get("raw_artifacts"),
            "published_review_context": payload.get("published_review_context"),
        }
    )


def build_app(
    *,
    project_root: Path | None = None,
    evidence_adapter_factory: ProjectEvidenceAdapterFactory | None = None,
) -> Any:
    bootstrap_environment()
    root = repository_root(project_root or Path.cwd())
    return create_app(
        backend=ProjectExplorerBackend(
            root,
            evidence_adapter_factory=evidence_adapter_factory,
        ),
        static_dir=root / "www" / "dist",
    )


app = build_app()


def serve_app(application: Any, argv: list[str] | None = None) -> None:
    """Serve one already-composed local explorer application."""
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
    uvicorn.run(application, host=args.host, port=args.port)


def main(argv: list[str] | None = None) -> None:
    """Serve the neutral reusable explorer composition."""
    serve_app(app, argv)


if __name__ == "__main__":
    main()
