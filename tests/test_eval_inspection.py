"""Tests for progressive, bounded eval review inspection."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    LocalReviewStore,
    OutputContractStatus,
    ReviewStoreError,
    ScoringStatus,
    build_run_identity,
    build_work_item_id,
    eval_attempt_to_dict,
)

from src.evals import inspection_cli
from src.evals.inspection import (
    inspect_example,
    inspection_summary,
    list_inspection_rows,
    materialize_review_index,
)
from src.evals.run_store import LocalRunStore


def _run_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    run_spec = {
        "scope": {"example_ids": ["example-a"]},
        "runs_per_example": 2,
    }
    run_id, digest = build_run_identity(run_spec)
    run_dir = tmp_path / "pipeline" / "benchmark" / "v1" / "runs" / run_id
    run_dir.mkdir(parents=True)
    work_items = [
        {
            "example_id": "example-a",
            "repetition_index": index,
            "work_item_id": build_work_item_id(
                run_id=run_id, item_id="example-a", attempt_index=index
            ),
        }
        for index in (1, 2)
    ]
    manifest = {
        "run_id": run_id,
        "run_spec_sha256": digest,
        "run_spec": run_spec,
        "result_schema_version": 3,
        "work_items": work_items,
        "result_materialization": {
            "contract_version": 1,
            "run_config": {
                "eval_result_schema_version": 3,
                "run_id": run_id,
                "run_spec_sha256": digest,
                "benchmark_key": "benchmark",
                "benchmark_version_number": 1,
                "runs_per_example": 2,
            },
            "selected_example_ids": ["example-a"],
            "result_rows": [
                {
                    "example_id": "example-a",
                    "unit_id": "unit-a",
                    "decision_timestamp": "2026-01-01T00:00:00Z",
                    "benchmark_labels": {"classification": "Healthy"},
                    "slice_keys": ["priority"],
                    "runs": [],
                }
            ],
            "output_fields": [
                {
                    "key": "classification",
                    "graded": True,
                    "benchmark_label_path": ["classification"],
                }
            ],
            "slice_keys": ["priority"],
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    run_store = LocalRunStore(run_dir, run_id=run_id)
    for index, (actual, correct) in enumerate(
        (("Healthy", True), ("Failure", False)), start=1
    ):
        work_item = work_items[index - 1]
        attempt = EvalAttempt(
            execution_status=ExecutionStatus.COMPLETED,
            output_contract_status=OutputContractStatus.VALID,
            scoring_status=ScoringStatus.SCORED,
            actual_values={"classification": actual},
            evaluations={
                "classification": FieldEvaluation(
                    expected="Healthy",
                    actual=actual,
                    correct=correct,
                    grader_id="core.exact",
                    grader_version=1,
                )
            },
            applicable_fields=("classification",),
            complete_evaluation_correct=correct,
            duration_seconds=float(index),
            artifacts={"usage": {"input_tokens": 8 + 2 * index}},
        )
        run_store.commit_attempt(
            {
                "run_id": run_id,
                "work_item_id": work_item["work_item_id"],
                "example_id": "example-a",
                "repetition_index": index,
                "execution_id": f"{work_item['work_item_id']}.1",
                "generation": 1,
                "invocation_id": "inv_test",
                "agent_version_id": None,
                "agent_version_manifest_sha256": None,
                "started_at_utc": "2026-01-01T00:00:00+00:00",
                "completed_at_utc": "2026-01-01T00:00:01+00:00",
                "attempt": eval_attempt_to_dict(attempt),
            }
        )
    run_store.write_invocation_event(
        invocation_id="inv_test",
        event="completed",
        payload={"duration_seconds": 0.0, "selected_work_items": 2},
    )
    run_store.materialize_result(
        completed_at_utc="2026-01-01T00:00:01+00:00",
        latest_invocation_id="inv_test",
    )
    return run_dir, run_id, digest


def _result(*, run_id: str, run_spec_sha256: str) -> dict[str, object]:
    work_a = build_work_item_id(run_id=run_id, item_id="example-a", attempt_index=1)
    work_b = build_work_item_id(run_id=run_id, item_id="example-a", attempt_index=2)
    runs = [
        {
            "run_index": 1,
            "work_item_id": work_a,
            "execution_id": f"{work_a}.1",
            "execution_generation": 1,
            "execution_status": "completed",
            "output_contract_status": "valid",
            "scoring_status": "scored",
            "complete_evaluation_correct": True,
            "fields": {"classification": {"correct": True}},
            "actual_outputs": {"classification": "Healthy"},
            "duration_seconds": 1.0,
            "usage": {"input_tokens": 10},
            "cost": {"status": "unavailable"},
        },
        {
            "run_index": 2,
            "work_item_id": work_b,
            "execution_id": f"{work_b}.1",
            "execution_generation": 1,
            "execution_status": "completed",
            "output_contract_status": "valid",
            "scoring_status": "scored",
            "complete_evaluation_correct": False,
            "fields": {"classification": {"correct": False}},
            "actual_outputs": {"classification": "Failure"},
            "duration_seconds": 2.0,
            "usage": {"input_tokens": 12},
            "cost": {"status": "unavailable"},
        },
    ]
    return {
        "summary": {"reliability": {"planned_runs": 2}},
        "run_config": {
            "eval_result_schema_version": 3,
            "run_id": run_id,
            "run_spec_sha256": run_spec_sha256,
            "benchmark_key": "benchmark",
            "benchmark_version_number": 1,
            "runs_per_example": 2,
        },
        "selected_example_ids": ["example-a"],
        "results": [
            {
                "example_id": "example-a",
                "unit_id": "unit-a",
                "decision_timestamp": "2026-01-01T00:00:00Z",
                "benchmark_labels": {"classification": "Healthy"},
                "slice_keys": ["priority"],
                "runs": runs,
            }
        ],
    }


def test_inspection_indexes_filters_and_resolves_one_example(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_dir, run_id, digest = _run_fixture(tmp_path)
    store = LocalReviewStore(run_dir, run_id=run_id)
    store.initialize(run_spec_sha256=digest)
    work_items = [
        build_work_item_id(run_id=run_id, item_id="example-a", attempt_index=index)
        for index in (1, 2)
    ]
    for work_item in work_items:
        store.commit_execution(
            {
                "run_id": run_id,
                "work_item_id": work_item,
                "execution_id": f"{work_item}.1",
                "capture_status": "complete",
                "model_interactions": {"system_prompt": "inspect me"},
            }
        )

    index_path = materialize_review_index(run_dir)
    assert index_path.exists()
    summary = inspection_summary(run_dir)
    assert summary["attempt_counts"]["incorrect"] == 1
    assert summary["attempt_counts"]["flaky"] == 2
    incorrect = list_inspection_rows(run_dir, filter_name="incorrect")
    assert incorrect["matched"] == 1
    assert incorrect["rows"][0]["execution_id"] == f"{work_items[1]}.1"
    detail = inspect_example(run_dir, example_id="example-a")
    assert len(detail["rows"]) == 2
    assert len(detail["executions"]) == 2

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspection_cli",
            "--root",
            str(tmp_path),
            "list",
            "--run",
            run_id,
            "--filter",
            "incorrect",
        ],
    )
    inspection_cli.main()
    assert json.loads(capsys.readouterr().out)["matched"] == 1


def test_inspection_rejects_changed_materialized_result(
    tmp_path: Path,
) -> None:
    run_dir, run_id, digest = _run_fixture(tmp_path)
    initial = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    store = LocalReviewStore(run_dir, run_id=run_id)
    store.initialize(run_spec_sha256=digest)
    materialize_review_index(run_dir)

    changed = json.loads(json.dumps(initial))
    changed["results"][0]["runs"][0]["complete_evaluation_correct"] = False
    (run_dir / "result.json").write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(ReviewStoreError, match="canonical materialization"):
        list_inspection_rows(run_dir, filter_name="incorrect")


def test_inspection_rejects_a_result_from_another_run(tmp_path: Path) -> None:
    run_dir, run_id, digest = _run_fixture(tmp_path)
    result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    result["run_config"]["run_id"] = "eval_other"  # type: ignore[index]
    (run_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ReviewStoreError, match="canonical materialization"):
        materialize_review_index(run_dir)
