"""Queryable, bounded views over disposable local eval review bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evaluation import LocalReviewStore, ReviewStoreError, canonical_sha256

from src.evals.result_integrity import ResultIntegrityError, load_verified_result
from src.evals.run_store import LocalRunStore


def find_run_directory(run_id: str, *, root: Path = Path("eval_results")) -> Path:
    """Resolve exactly one deterministic run directory beneath a local root."""
    normalized = run_id.strip()
    if not normalized or "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError(f"Invalid run id: {run_id!r}.")
    matches = sorted(
        path.parent for path in root.glob(f"**/runs/{normalized}/manifest.json")
    )
    if not matches:
        raise ValueError(f"No local result was found for run {normalized}.")
    if len(matches) > 1:
        raise ValueError(
            f"Run id {normalized} is ambiguous under {root}: "
            + ", ".join(str(path) for path in matches)
        )
    return matches[0]


def materialize_review_index(run_dir: Path) -> Path:
    """Join schema-v1 eval rows to retained review execution manifests."""
    store = _store(run_dir)
    result = _verified_result(run_dir)
    run_store = LocalRunStore(run_dir, run_id=run_dir.name)
    eval_rows = run_store.evaluation_rows()
    expected_execution_ids = [
        str(item["execution_id"]) for item in run_store.read_attempt_records()
    ]
    review_state = store.review_state(expected_execution_ids=expected_execution_ids)
    capture = review_state["capture"]
    failures = {
        str(item.get("execution_id")): item
        for item in capture.get("capture_failures", [])
        if isinstance(item, dict)
    }
    manifests = {
        str(item["execution_id"]): item for item in store.iter_execution_manifests()
    }
    unstable_examples = _unstable_examples(eval_rows)
    rows: list[dict[str, Any]] = []
    for example in eval_rows:
        if not isinstance(example, dict):
            continue
        for run in example.get("runs", []):
            if not isinstance(run, dict):
                continue
            execution_id = str(run.get("execution_id", ""))
            review = manifests.get(execution_id)
            unavailable_reason = (
                None
                if review
                else _review_unavailable_reason(
                    capture, failure=failures.get(execution_id)
                )
            )
            rows.append(
                {
                    "example_id": example.get("example_id"),
                    "unit_id": example.get("unit_id"),
                    "decision_timestamp": example.get("decision_timestamp"),
                    "slice_keys": example.get("slice_keys", []),
                    "benchmark_labels": example.get("benchmark_labels", {}),
                    "run_index": run.get("run_index"),
                    "work_item_id": run.get("work_item_id"),
                    "execution_id": execution_id,
                    "execution_generation": run.get("execution_generation"),
                    "execution_status": run.get("execution_status"),
                    "output_contract_status": run.get("output_contract_status"),
                    "scoring_status": run.get("scoring_status"),
                    "complete_evaluation_correct": run.get(
                        "complete_evaluation_correct"
                    ),
                    "evaluations": run.get("evaluations", {}),
                    "agent_output": run.get("agent_output"),
                    "failure_type": run.get("failure_type"),
                    "error": run.get("error"),
                    "usage": run.get("usage"),
                    "cost": run.get("cost"),
                    "flaky": example.get("example_id") in unstable_examples,
                    "review_status": (
                        review.get("capture_status") if review else "unavailable"
                    ),
                    "review_unavailable_reason": unavailable_reason,
                    "review_sections": (
                        sorted(
                            key
                            for key in review
                            if key
                            not in {
                                "review_schema_version",
                                "manifest_sha256",
                                "run_id",
                                "work_item_id",
                                "execution_id",
                                "capture_status",
                            }
                        )
                        if review
                        else []
                    ),
                }
            )
    rows.sort(
        key=lambda item: (
            str(item.get("example_id", "")),
            int(item.get("run_index") or 0),
            str(item.get("execution_id", "")),
        )
    )
    payload = {
        "result_schema_version": result.get("schema_version"),
        "result_sha256": canonical_sha256(result),
        "attempt_state_sha256": _attempt_state_sha256(run_store),
        "review_state_sha256": review_state["review_state_sha256"],
        "review_integrity": review_state["integrity"],
        "row_count": len(rows),
        "rows": rows,
    }
    return store.write_index(payload)


def inspection_summary(run_dir: Path) -> dict[str, Any]:
    """Return one bounded run/review summary for progressive analysis."""
    store = _store(run_dir)
    result = _verified_result(run_dir)
    index = _ensure_index(run_dir)
    rows = index["rows"]
    expected_execution_ids = [
        str(item["execution_id"])
        for item in LocalRunStore(
            run_dir.resolve(), run_id=run_dir.resolve().name
        ).read_attempt_records()
    ]
    review_state = store.review_state(expected_execution_ids=expected_execution_ids)
    capture = review_state["capture"]
    dimensions = result.get("run", {}).get("dimensions", {})
    benchmark = dimensions.get("benchmark", {})
    model = dimensions.get("model", {})
    return {
        "run_id": store.run_id,
        "run": {
            "agent_version": dimensions.get("agent"),
            "benchmark_key": benchmark.get("key"),
            "benchmark_version_number": benchmark.get("version"),
            "ai_model": model.get("id"),
            "ai_reasoning_effort": model.get("reasoning_effort"),
            "runs_per_example": result.get("run", {}).get("runs_per_example"),
        },
        "summary": result.get("summary", {}),
        "review": {
            **capture,
            "integrity": review_state["integrity"],
            **store.size(),
        },
        "attempt_counts": {
            "total": len(rows),
            "incorrect": sum(
                item.get("complete_evaluation_correct") is False for item in rows
            ),
            "invalid": sum(
                item.get("output_contract_status") == "invalid" for item in rows
            ),
            "failed": sum(item.get("execution_status") == "failed" for item in rows),
            "flaky": sum(bool(item.get("flaky")) for item in rows),
            "review_unavailable": sum(
                item.get("review_status") == "unavailable" for item in rows
            ),
        },
        "filters": [
            "all",
            "incorrect",
            "invalid",
            "failed",
            "flaky",
            "unscored",
            "review-unavailable",
        ],
    }


def all_inspection_rows(run_dir: Path) -> list[dict[str, Any]]:
    """Return every compact attempt row for in-process filtering and pagination."""
    return list(_ensure_index(run_dir)["rows"])


def list_inspection_rows(
    run_dir: Path,
    *,
    filter_name: str = "all",
    limit: int = 100,
) -> dict[str, Any]:
    """Return deterministic compact rows for one supported diagnostic filter."""
    if limit < 1 or limit > 10_000:
        raise ValueError("limit must be between 1 and 10000.")
    index = _ensure_index(run_dir)
    predicates = {
        "all": lambda item: True,
        "incorrect": lambda item: item.get("complete_evaluation_correct") is False,
        "invalid": lambda item: item.get("output_contract_status") == "invalid",
        "failed": lambda item: item.get("execution_status") == "failed",
        "flaky": lambda item: bool(item.get("flaky")),
        "unscored": lambda item: item.get("scoring_status") != "scored",
        "review-unavailable": lambda item: item.get("review_status") == "unavailable",
    }
    predicate = predicates.get(filter_name)
    if predicate is None:
        raise ValueError(
            f"Unsupported inspection filter {filter_name!r}; choose from "
            + ", ".join(sorted(predicates))
            + "."
        )
    selected = [item for item in index["rows"] if predicate(item)]
    return {
        "run_id": index["run_id"],
        "filter": filter_name,
        "matched": len(selected),
        "returned": min(limit, len(selected)),
        "rows": selected[:limit],
    }


def inspect_example(
    run_dir: Path,
    *,
    example_id: str,
    repetition: int | None = None,
    resolve_text: bool = False,
) -> dict[str, Any]:
    """Return compact rows and detailed manifests for one example."""
    store = _store(run_dir)
    rows = [
        item
        for item in _ensure_index(run_dir)["rows"]
        if item.get("example_id") == example_id
        and (repetition is None or item.get("run_index") == repetition)
    ]
    if not rows:
        raise ValueError(f"No attempts found for example {example_id!r}.")
    executions: list[dict[str, Any]] = []
    for row in rows:
        if row.get("review_status") == "unavailable":
            continue
        executions.append(
            store.read_execution(str(row["execution_id"]), resolve_text=resolve_text)
        )
    return {
        "run_id": store.run_id,
        "example_id": example_id,
        "rows": rows,
        "executions": executions,
    }


def inspect_execution(
    run_dir: Path,
    *,
    execution_id: str,
    section: str | None = None,
    resolve_text: bool = False,
) -> dict[str, Any]:
    return _store(run_dir).read_execution(
        execution_id, section=section, resolve_text=resolve_text
    )


def _ensure_index(run_dir: Path) -> dict[str, Any]:
    for _ in range(3):
        store = _store(run_dir)
        sources = _index_sources(run_dir, store=store)
        index = store.read_index() if store.index_path.exists() else {}
        if index.get("review_index_schema_version") != 2 or any(
            index.get(key) != value for key, value in sources.items()
        ):
            materialize_review_index(run_dir)
            index = store.read_index()
        current = _index_sources(run_dir, store=store)
        if index.get("review_index_schema_version") == 2 and all(
            index.get(key) == value for key, value in current.items()
        ):
            return index
    raise ReviewStoreError("Review index inputs changed repeatedly during refresh.")


def _index_sources(
    run_dir: Path, *, store: LocalReviewStore | None = None
) -> dict[str, str]:
    result = _verified_result(run_dir)
    run_store = LocalRunStore(run_dir, run_id=run_dir.name)
    expected_execution_ids = [
        str(item["execution_id"]) for item in run_store.read_attempt_records()
    ]
    review_store = store or _store(run_dir)
    review_state = review_store.review_state(
        expected_execution_ids=expected_execution_ids
    )
    return {
        "result_sha256": canonical_sha256(result),
        "attempt_state_sha256": _attempt_state_sha256(run_store),
        "review_state_sha256": str(review_state["review_state_sha256"]),
    }


def _attempt_state_sha256(run_store: LocalRunStore) -> str:
    records = run_store.read_attempt_records()
    return canonical_sha256(
        [
            {
                "work_item_id": item.get("work_item_id"),
                "execution_id": item.get("execution_id"),
                "generation": item.get("generation"),
            }
            for item in records
        ]
    )


def _store(run_dir: Path) -> LocalReviewStore:
    run_dir = run_dir.resolve()
    return LocalReviewStore(run_dir, run_id=run_dir.name)


def _unstable_examples(rows: list[dict[str, Any]]) -> set[str]:
    unstable: set[str] = set()
    for example in rows:
        if not isinstance(example, dict):
            continue
        outputs = {
            canonical_sha256(run.get("agent_output") or {})
            for run in example.get("runs", [])
            if isinstance(run, dict) and run.get("scoring_status") == "scored"
        }
        if len(outputs) > 1:
            unstable.add(str(example.get("example_id", "")))
    return unstable


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewStoreError(f"Cannot read inspection JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ReviewStoreError(f"Inspection JSON must be an object: {path}")
    return payload


def _review_unavailable_reason(
    capture: dict[str, Any], *, failure: dict[str, Any] | None = None
) -> dict[str, Any]:
    if failure is not None:
        return {
            "code": "capture_failed",
            "error_type": failure.get("error_type"),
            "message": failure.get("reason"),
        }
    status = str(capture.get("status", "absent"))
    if status == "purged":
        return {"code": "purged"}
    if capture.get("mode") == "off":
        return {"code": "disabled" if status != "absent" else "absent"}
    if status == "failed":
        return {"code": "capture_failed"}
    if status in {"partial", "in_progress"}:
        return {"code": "capture_partial"}
    return {"code": "absent"}


def _verified_result(run_dir: Path) -> dict[str, Any]:
    try:
        return load_verified_result(run_dir / "result.json")
    except ResultIntegrityError as error:
        raise ReviewStoreError(str(error)) from error
