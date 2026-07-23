"""Tests for dimension-safe evaluation result comparisons."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_run_identity,
    build_work_item_id,
    eval_attempt_to_dict,
)

from src.evals.comparisons import build_comparison, build_comparison_manifest
from src.evals.run_store import LocalRunStore


def _write_result(path: Path, *, run_id: str, model: str, correct: bool = True) -> Path:
    del run_id
    run_spec = _run_spec(model)
    actual_run_id, run_spec_sha256 = build_run_identity(run_spec)
    run_dir = path.parent / actual_run_id
    work_item_id = build_work_item_id(
        run_id=actual_run_id, item_id="example-a", attempt_index=1
    )
    manifest_path = _write_run_manifest(run_dir / "manifest.json", run_spec=run_spec)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    store = LocalRunStore(run_dir, run_id=actual_run_id)
    attempt = EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.SCORED,
        actual_values={"classification": "ok" if correct else "bad"},
        evaluations={
            "classification": FieldEvaluation(
                expected="ok",
                actual="ok" if correct else "bad",
                correct=correct,
                grader_id="core.exact",
                grader_version=1,
            )
        },
        applicable_fields=("classification",),
        complete_evaluation_correct=correct,
        duration_seconds=1.0 if correct else 2.0,
        artifacts={
            "agent_output": {"classification": "ok" if correct else "bad"},
            "usage": {"requests": 1 if correct else 2},
            "cost": {
                "estimated": {
                    "amount": 0.1 if correct else 0.2,
                    "currency": "USD",
                }
            },
        },
    )
    store.commit_attempt(
        {
            "schema_version": 1,
            "run_id": actual_run_id,
            "work_item_id": work_item_id,
            "example_id": "example-a",
            "repetition_index": 1,
            "execution_id": f"{work_item_id}.1",
            "generation": 1,
            "invocation_id": "inv_test",
            "attempt": eval_attempt_to_dict(attempt),
        }
    )
    run_config = {
        "run_id": actual_run_id,
        "run_spec_sha256": run_spec_sha256,
        "schema_version": 1,
        "runs_per_example": 1,
        "dimensions": {
            "benchmark": {"key": "benchmark", "version": 1},
            "agent": {"agent_version_id": "av_a"},
            "pipeline": {"content_sha256": "pipeline"},
            "model": {"id": model, "reasoning_effort": "high"},
            "execution": {
                "runtime": "serial",
                "max_workers": 1,
                "error_action": "continue",
            },
            "scoring": {"resolved_contract_sha256": "b" * 64},
            "configuration": {},
        },
    }
    manifest["eval_contract"] = {
        "schema_version": 1,
        "run": run_config,
        "examples": [
            {
                "example_id": "example-a",
                "benchmark_labels": {"classification": "ok"},
                "slice_keys": ["priority"],
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
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert manifest["run_id"] == actual_run_id
    return store.materialize_result(
        completed_at_utc="2026-01-01T00:00:01+00:00",
        latest_invocation_id="inv_test",
    )


def test_comparison_requires_every_changed_dimension_to_be_declared(
    tmp_path: Path,
) -> None:
    first = _write_result(tmp_path / "a.json", run_id="eval_a", model="p:a")
    second = _write_result(tmp_path / "b.json", run_id="eval_b", model="p:b")

    with pytest.raises(ValueError, match="undeclared dimensions"):
        build_comparison([first, second], varying_dimensions=set())


def test_comparison_persists_aligned_quality_and_reliability(tmp_path: Path) -> None:
    first = _write_result(tmp_path / "a.json", run_id="eval_a", model="p:a")
    second = _write_result(
        tmp_path / "b.json", run_id="eval_b", model="p:b", correct=False
    )

    path = build_comparison(
        [first, second],
        varying_dimensions={"model.id"},
        output_dir=tmp_path / "comparisons",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["comparison_id"].startswith("cmp_")
    assert [item["run_id"] for item in payload["runs"]] == [
        json.loads(first.read_text())["run"]["run_id"],
        json.loads(second.read_text())["run"]["run_id"],
    ]
    assert payload["paired_complete_correctness"]["agreement_rate"] == 0.0
    delta = payload["paired_deltas"][0]
    assert delta["complete_evaluation"]["regressed"] == 1
    assert delta["complete_evaluation"]["delta_rate"] == -1.0
    assert delta["by_field"]["classification"]["jointly_observed"] == 1
    assert delta["by_slice"]["priority"]["regressed"] == 1
    assert delta["usage"]["requests"]["delta_total"] == 1.0
    assert delta["cost"]["USD"]["delta_total"] == pytest.approx(0.1)
    assert delta["work_items"]["regressed"] == [
        {
            "example_id": "example-a",
            "run_index": 1,
            "baseline_work_item_id": _attempt_row(first)["work_item_id"],
            "candidate_work_item_id": _attempt_row(second)["work_item_id"],
            "baseline_execution_id": _attempt_row(first)["execution_id"],
            "candidate_execution_id": _attempt_row(second)["execution_id"],
        }
    ]
    assert (
        payload["runs"][0]["nondeterminism"][
            "examples_with_multiple_scored_repetitions"
        ]
        == 0
    )


def _run_spec(model: str) -> dict[str, object]:
    return {
        "benchmark": {"key": "benchmark", "version_number": 1},
        "scope": {"example_ids": ["example-a"], "content_sha256": "scope"},
        "pipeline": {
            "content_sha256": "pipeline",
            "resolved_override_sha256": f"override-{model}",
        },
        "agent": {"agent_version_id": "av_a"},
        "model": {"id": model},
        "scoring": {"content_sha256": "scoring"},
        "runs_per_example": 1,
        "execution": {
            "runtime": "serial",
            "max_workers": 1,
            "error_action": "continue",
            "ai_execution_policies": [{"model": model}],
        },
        "configuration_dimensions": {},
        "source_manifest": {"content_sha256": "source"},
    }


def _write_run_manifest(path: Path, *, run_spec: dict[str, object]) -> Path:
    run_id, digest = build_run_identity(run_spec)
    work_item_id = build_work_item_id(
        run_id=run_id, item_id="example-a", attempt_index=1
    )
    payload = {
        "schema_version": 1,
        "performance_schema_version": 1,
        "run_id": run_id,
        "run_spec_sha256": digest,
        "run_spec": run_spec,
        "work_items": [
            {
                "example_id": "example-a",
                "repetition_index": 1,
                "work_item_id": work_item_id,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_manifest(path: Path, *, run_id: str, model: str) -> Path:
    del run_id
    run_spec = _run_spec(model)
    actual_run_id, _ = build_run_identity(run_spec)
    return _write_run_manifest(
        path.parent / actual_run_id / "manifest.json", run_spec=run_spec
    )


def test_comparison_manifest_validates_children_before_results(tmp_path: Path) -> None:
    first = _write_manifest(tmp_path / "a.manifest.json", run_id="eval_a", model="p:a")
    second = _write_manifest(tmp_path / "b.manifest.json", run_id="eval_b", model="p:b")

    path = build_comparison_manifest(
        [first, second],
        varying_dimensions={"model"},
        output_dir=tmp_path / "comparisons",
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.name.endswith(".manifest.json")
    assert payload["comparison_spec"]["run_ids"] == [
        json.loads(first.read_text())["run_id"],
        json.loads(second.read_text())["run_id"],
    ]

    first_result = _write_result(
        tmp_path / "a.result.json", run_id="eval_a", model="p:a"
    )
    second_result = _write_result(
        tmp_path / "b.result.json", run_id="eval_b", model="p:b"
    )
    result_path = build_comparison(
        [first_result, second_result],
        varying_dimensions={"model"},
        output_dir=tmp_path / "comparisons",
        comparison_manifest_path=path,
    )

    assert (
        json.loads(result_path.read_text(encoding="utf-8"))["comparison_id"]
        == payload["comparison_id"]
    )


def test_comparison_rejects_a_result_from_a_different_manifest(tmp_path: Path) -> None:
    first = _write_result(tmp_path / "a.json", run_id="eval_a", model="p:a")
    second = _write_result(tmp_path / "b.json", run_id="eval_b", model="p:b")
    tampered = json.loads(second.read_text(encoding="utf-8"))
    tampered["run"]["run_id"] = json.loads(first.read_text(encoding="utf-8"))["run"][
        "run_id"
    ]
    second.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="canonical materialization"):
        build_comparison(
            [first, second],
            varying_dimensions={"model.id"},
            output_dir=tmp_path / "comparisons",
        )


def _attempt_row(path: Path) -> dict[str, object]:
    run_dir = path.parent
    return LocalRunStore(run_dir, run_id=run_dir.name).evaluation_rows()[0]["runs"][0]
