"""Tests for dimension-safe evaluation result comparisons."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evals.comparisons import build_comparison, build_comparison_manifest


def _write_result(path: Path, *, run_id: str, model: str, correct: bool = True) -> Path:
    payload = {
        "summary": {
            "accuracy": {
                "complete_evaluation": {
                    "accuracy": 1.0,
                    "correct_runs": 1,
                    "evaluated_runs": 1,
                }
            },
            "reliability": {"planned_runs": 1},
            "scoring_coverage": {"scored_runs": 1},
            "performance": {"evaluation_wall_time_seconds": 1.0},
            "usage": {"availability": "unavailable"},
            "cost": {},
            "nondeterminism": {
                "examples_with_multiple_scored_repetitions": 0,
                "unstable_output_examples": 0,
            },
        },
        "run_config": {
            "run_id": run_id,
            "runs_per_example": 1,
            "dimensions": {
                "benchmark": {"key": "benchmark", "version": 1},
                "pipeline": {"content_sha256": "a" * 64},
                "model": {"id": model, "reasoning_effort": "high"},
                "scoring": {"resolved_contract_sha256": "b" * 64},
            },
        },
        "selected_example_ids": ["example-a"],
        "results": [
            {
                "example_id": "example-a",
                "slice_keys": ["priority"],
                "runs": [
                    {
                        "run_index": 1,
                        "complete_evaluation_correct": correct,
                        "execution_status": "completed",
                        "output_contract_status": "valid",
                        "scoring_status": "scored",
                        "duration_seconds": 1.0 if correct else 2.0,
                        "fields": {"classification": {"correct": correct}},
                        "usage": {"requests": 1 if correct else 2},
                        "cost": {
                            "estimated": {
                                "amount": 0.1 if correct else 0.2,
                                "currency": "USD",
                            }
                        },
                    }
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
    assert [item["run_id"] for item in payload["runs"]] == ["eval_a", "eval_b"]
    assert payload["paired_complete_correctness"]["agreement_rate"] == 0.0
    delta = payload["paired_deltas"][0]
    assert delta["complete_evaluation"]["regressed"] == 1
    assert delta["complete_evaluation"]["delta_rate"] == -1.0
    assert delta["by_field"]["classification"]["jointly_observed"] == 1
    assert delta["by_slice"]["priority"]["regressed"] == 1
    assert delta["performance"]["delta_mean"] == 1.0
    assert delta["usage"]["requests"]["delta_total"] == 1.0
    assert delta["cost"]["USD"]["delta_total"] == pytest.approx(0.1)
    assert (
        payload["runs"][0]["nondeterminism"][
            "examples_with_multiple_scored_repetitions"
        ]
        == 0
    )


def _write_manifest(path: Path, *, run_id: str, model: str) -> Path:
    payload = {
        "run_id": run_id,
        "run_spec": {
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
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
    assert payload["comparison_spec"]["run_ids"] == ["eval_a", "eval_b"]

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
