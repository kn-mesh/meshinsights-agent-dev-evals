"""Reusable Workbench tests for evaluation orchestration."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt
import pytest
import yaml

from workbench.models.catalog import ModelDefinition, ModelPricing
from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldGrade,
    GraderRegistry,
    OutputContractStatus,
    ScoringStatus,
    build_default_grader_registry,
)
from workbench.agent_versions import AgentVersionStore, resolve_agent_version
from workbench.apps.eval_explorer import ProjectExplorerBackend

from workbench.benchmarks import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedLabelSchema,
    PublishedReviewContext,
    PublishedReviewerCoverage,
    PublishedVerification,
    SourceArtifact,
)
from workbench.evals import eval_orchestration
from workbench.evals.result_integrity import ResultIntegrityError, load_verified_result
from workbench.evals.run_store import LocalRunStore
from workbench.eval_lifecycle import EvalLifecycleError, EvalLifecycleService


PROFILE_PATH = Path("use_case/evaluation_configs/spirax-failure-evaluation.eval.yaml")


class _Repository:
    def __init__(self, benchmark: BenchmarkVersion) -> None:
        self.benchmark = benchmark

    def load_published_version(
        self, *, benchmark_key: str, version_number: int | None = None
    ) -> BenchmarkVersion:
        assert benchmark_key == self.benchmark.benchmark_key
        assert version_number in {None, self.benchmark.version_number}
        return self.benchmark

    def list_published_versions(self) -> tuple[Any, ...]:
        return ()


def _schema() -> tuple[dict[str, Any], str]:
    schema = {
        "schema_key": "spirax-steam-trap-label",
        "version": "v1",
        "fields": [
            {
                "key": "classification",
                "required": True,
                "values": ["Healthy", "Failure"],
            },
            {
                "key": "root_cause",
                "required": True,
                "values": ["Closed Failure", "Open Failure", "Unknown", "N/A"],
            },
            {"key": "review_notes", "required": False},
        ],
    }
    digest = hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return schema, digest


def _example(
    *,
    example_id: str = "250000116|2026-03-04T08:01:36",
    classification: str = "Failure",
    root_cause: str = "Closed Failure",
) -> BenchmarkExample:
    artifacts = (
        SourceArtifact(
            artifact_kind="telemetry",
            object_key=f"{example_id}/telemetry.parquet",
            content_type="application/parquet",
            byte_size=1,
            content_sha256="a" * 64,
        ),
        SourceArtifact(
            artifact_kind="alarms",
            object_key=f"{example_id}/alarms.jsonl",
            content_type="application/x-ndjson",
            byte_size=1,
            content_sha256="b" * 64,
        ),
    )
    return BenchmarkExample(
        example_id=example_id,
        unit_id=example_id.split("|", 1)[0],
        decision_timestamp=datetime(2026, 3, 4, 8, 1, 36, tzinfo=timezone.utc),
        approved_label_payload={
            "classification": classification,
            "root_cause": root_cause,
            "review_notes": "Useful context that is intentionally not graded.",
        },
        label_schema_version_id="schema-v1",
        example_metadata={"sensor_id": example_id.split("|", 1)[0]},
        source_snapshot_id=f"snapshot-{example_id}",
        raw_snapshot_content_sha256="c" * 64,
        raw_source_kind="mongo",
        raw_captured_at=datetime(2026, 3, 5, tzinfo=timezone.utc),
        raw_window_start=datetime(2025, 3, 4, tzinfo=timezone.utc),
        raw_window_end=datetime(2026, 3, 4, 8, 1, 36, tzinfo=timezone.utc),
        published_review_context=PublishedReviewContext(),
        raw_artifacts=artifacts,
    )


def _benchmark(*examples: BenchmarkExample) -> BenchmarkVersion:
    schema, digest = _schema()
    items = examples or (_example(),)
    return BenchmarkVersion(
        project_key="spirax-pulse",
        benchmark_key="phase-1-benchmark-3fb7f544",
        benchmark_name="Phase 1 Benchmark",
        benchmark_version_id="version-id",
        version_number=1,
        published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        source_state_sha256="d" * 64,
        published_contract_schema_version=2,
        eval_label_field_hints=("classification", "root_cause"),
        label_schemas=(
            PublishedLabelSchema(
                schema_version_id="schema-v1",
                schema_key="spirax-steam-trap-label",
                version="v1",
                schema=schema,
                content_sha256=digest,
            ),
        ),
        examples=tuple(items),
    )


def _receipt(
    example: BenchmarkExample,
    *,
    classification: str = "Failure",
    root_cause: str | None = "Closed Failure",
    confidence: str | None = "High",
    execution_review: dict[str, Any] | None = None,
) -> PipelineReceipt:
    classification_payload: dict[str, Any] = {"value": classification}
    if confidence is not None:
        classification_payload["confidence"] = confidence
    agent_output: dict[str, Any] = {"classification": classification_payload}
    if root_cause is not None:
        root_payload: dict[str, Any] = {"value": root_cause}
        if confidence is not None:
            root_payload["confidence"] = confidence
        agent_output["root_cause"] = root_payload
    return PipelineReceipt(
        pipeline_id="test",
        retrieve_receipt=StageReceipt("retrieve", True, 0.1),
        process_receipt=StageReceipt(
            "process",
            True,
            0.2,
            metadata=(
                {"execution_review": execution_review}
                if execution_review is not None
                else {}
            ),
        ),
        act_receipt=StageReceipt(
            "act",
            True,
            0.1,
            metadata={
                "example_id": example.example_id,
                "benchmark_key": "phase-1-benchmark-3fb7f544",
                "benchmark_version_id": "version-id",
                "benchmark_version_number": 1,
                "source_snapshot_id": example.source_snapshot_id,
                "agent_output": agent_output,
            },
        ),
    )


def _failed_receipt(
    *, stage: str = "process", telemetry: dict[str, Any] | None = None
) -> PipelineReceipt:
    failed_stage = StageReceipt(
        stage,
        False,
        0.2,
        error="provider unavailable",
        metadata={"execution_telemetry": telemetry} if telemetry is not None else {},
    )
    return PipelineReceipt(
        pipeline_id="test",
        retrieve_receipt=(
            failed_stage if stage == "retrieve" else StageReceipt("retrieve", True, 0.1)
        ),
        process_receipt=(failed_stage if stage == "process" else None),
        act_receipt=(failed_stage if stage == "act" else None),
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    benchmark: BenchmarkVersion,
    receipts: list[PipelineReceipt],
    **overrides: Any,
) -> dict[str, Any]:
    iterator = iter(receipts)
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: next(iterator),
    )
    path = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        benchmark_version=benchmark.version_number,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
        **overrides,
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _run_dir(root: Path) -> Path:
    return next(root.glob("**/working/**/eval_*"))


def _rows(root: Path) -> list[dict[str, Any]]:
    run_dir = _run_dir(root)
    return LocalRunStore(run_dir, run_id=run_dir.name).evaluation_rows()


def _performance(root: Path) -> dict[str, Any]:
    return json.loads((_run_dir(root) / "performance" / "summary.json").read_text())


class _ExplodingGrader:
    grader_id = "test.exploding"
    grader_version = 1

    def grade(
        self,
        *,
        expected: Any,
        actual: Any,
        config: Any,
    ) -> FieldGrade:
        raise RuntimeError("simulated grader defect")


def test_run_eval_writes_schema_v2_tracked_results_and_split_performance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
        configuration_dimensions={"prompt_revision": 7, "feature_set": "base"},
    )

    assert list(payload) == ["schema_version", "summary", "run", "artifacts"]
    assert payload["schema_version"] == 2
    assert payload["run"]["schema_version"] == 2
    assert payload["run"]["eval_run_id"] == payload["run"]["run_id"]
    assert payload["summary"]["timing"]["evaluation_active_wall_seconds"] >= 0
    assert payload["run"]["dimensions"]["evaluation_profile"]["id"] == (
        "spirax-failure-evaluation"
    )
    dimensions = payload["run"]["dimensions"]
    assert (
        not {
            "agent_version",
            "yaml_path",
            "project_key",
            "benchmark_name",
            "benchmark_key",
            "benchmark_version_id",
            "benchmark_version_number",
            "benchmark_published_at",
            "benchmark_source_state_sha256",
            "published_contract_schema_version",
            "benchmark_source",
            "evidence_source",
            "evaluation_profile",
            "runtime",
            "max_workers",
            "error_action",
            "ai_provider",
            "ai_model",
            "ai_reasoning_effort",
            "ai_execution_policies",
        }
        & payload["run"].keys()
    )
    assert dimensions["agent"]["agent_version_id"].startswith("av_")
    assert dimensions["agent"]["manifest_sha256"]
    assert dimensions["benchmark"]["name"] == "Phase 1 Benchmark"
    assert dimensions["benchmark"]["source_state_sha256"] == "d" * 64
    assert payload["run"]["selected_example_scope_sha256"]
    assert dimensions["model"]["id"] == "azure:gpt-5.6-luna"
    assert dimensions["pipeline"]["content_sha256"]
    assert dimensions["configuration"] == {
        "feature_set": "base",
        "prompt_revision": 7,
    }
    assert payload["summary"]["accuracy"]["complete_evaluation"] == {
        "accuracy": 1.0,
        "correct_runs": 1,
        "evaluated_runs": 1,
    }
    assert payload["summary"]["accuracy"]["by_field"]["root_cause"]["accuracy"] == 1.0
    assert payload["summary"]["reliability"]["output_contract_validity_rate"] == 1.0
    assert payload["summary"]["scoring_coverage"]["coverage"] == 1.0
    assert "performance" not in payload["summary"]
    assert "retries" not in payload["summary"]
    result = _rows(tmp_path)[0]
    assert result["benchmark_labels"]["review_notes"].startswith("Useful context")
    assert set(result["slice_keys"]) == {"expected-failure", "closed-failure"}
    assert result["runs"][0]["evaluations"]["classification"]["correct"] is True
    assert result["runs"][0]["agent_output"]["classification"]["value"] == "Failure"
    performance = _performance(tmp_path)
    assert performance["schema_version"] == 1
    assert performance["summary"]["stage_duration_seconds"]["process"]["count"] == 1
    run_dir = _run_dir(tmp_path)
    capture = json.loads((run_dir / "review" / "capture.json").read_text())
    assert capture["publication"] == "local_only"
    assert capture["execution_counts"]["partial"] == 1
    review_manifest = next((run_dir / "review" / "executions").glob("*/*.json"))
    assert (
        json.loads(review_manifest.read_text())["source_evidence"][0]["write_access"]
        is False
    )


def test_disposable_performance_can_be_deleted_without_invalidating_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    original = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )
    run_dir = _run_dir(tmp_path)

    shutil.rmtree(run_dir / "performance")

    assert load_verified_result(run_dir / "result.json") == original
    assert LocalRunStore(run_dir, run_id=run_dir.name).evaluation_rows()[0]["runs"][0][
        "agent_output"
    ] == {
        "classification": {"value": "Failure", "confidence": "High"},
        "root_cause": {"value": "Closed Failure", "confidence": "High"},
    }


def test_status_resolver_finds_new_working_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )
    run_dir = _run_dir(tmp_path)

    assert (
        eval_orchestration._find_run_directory(  # noqa: SLF001
            payload["run"]["run_id"],
            root=tmp_path,
        )
        == run_dir.resolve()
    )


@pytest.mark.parametrize(
    ("method_name", "warning_text"),
    [
        ("write_invocation_event", "Disposable performance invocation capture failed"),
        ("commit_performance", "Disposable performance capture failed"),
        (
            "materialize_performance",
            "Disposable performance summary materialization failed",
        ),
    ],
)
def test_disposable_performance_failure_does_not_fail_durable_eval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    method_name: str,
    warning_text: str,
) -> None:
    benchmark = _benchmark()

    def fail_performance(*args: Any, **kwargs: Any) -> None:
        raise OSError("simulated disposable telemetry failure")

    monkeypatch.setattr(LocalRunStore, method_name, fail_performance)
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )

    run_dir = _run_dir(tmp_path)
    assert payload["summary"]["scoring_coverage"]["scored_runs"] == 1
    assert load_verified_result(run_dir / "result.json") == payload
    assert len(LocalRunStore(run_dir, run_id=run_dir.name).read_attempt_records()) == 1
    assert warning_text in caplog.text
    if method_name == "commit_performance":
        assert not (run_dir / "performance" / "summary.json").exists()


def test_result_integrity_rejects_any_materialized_content_edit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    original = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )
    result_path = next(tmp_path.glob("**/working/**/eval_*/result.json"))
    assert load_verified_result(result_path) == original

    mutations = (
        lambda value: value.update({"schema_version": 1}),
        lambda value: value["summary"]["usage"].update({"attempts_with_usage": 999}),
        lambda value: value["run"]["dimensions"]["model"].update(
            {"id": "azure:edited"}
        ),
        lambda value: value["artifacts"].update({"attempts": "edited/"}),
    )
    for mutate in mutations:
        changed = json.loads(json.dumps(original))
        mutate(changed)
        result_path.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ResultIntegrityError, match="verification"):
            load_verified_result(result_path)

    result_path.write_text(json.dumps(original), encoding="utf-8")
    assert load_verified_result(result_path) == original


def test_failed_execution_is_debuggable_and_excluded_from_accuracy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0]), _failed_receipt()],
        runs_per_example=2,
    )

    assert payload["summary"]["accuracy"]["complete_evaluation"]["accuracy"] == 1.0
    assert payload["summary"]["accuracy"]["complete_evaluation"]["evaluated_runs"] == 1
    assert payload["summary"]["scoring_coverage"]["coverage"] == 0.5
    assert payload["summary"]["reliability"]["failures_by_type"] == {
        "provider_error": 1
    }
    failed = _rows(tmp_path)[0]["runs"][1]
    assert failed["execution_status"] == "failed"
    assert failed["output_contract_status"] == "not_produced"
    assert failed["failure_details"]["failed_stages"][0]["stage"] == "process"


def test_grader_exception_becomes_non_scoring_attempt() -> None:
    benchmark = _benchmark()
    example = benchmark.examples[0]
    receipt = _receipt(example)
    assert receipt.act_receipt is not None
    profile = eval_orchestration.load_evaluation_profile(PROFILE_PATH)
    profile_payload = profile.model_dump(mode="json")
    profile_payload["output_fields"][0]["evaluation"]["grader"] = {
        "id": "test.exploding",
        "version": 1,
        "config": {},
    }
    registry = GraderRegistry()
    registry.register(_ExplodingGrader)

    attempt = eval_orchestration.score_receipt_metadata(
        metadata=receipt.act_receipt.metadata,
        expected_identity={
            "example_id": example.example_id,
            "benchmark_key": benchmark.benchmark_key,
            "benchmark_version_id": benchmark.benchmark_version_id,
            "benchmark_version_number": benchmark.version_number,
            "source_snapshot_id": example.source_snapshot_id,
        },
        example=example,
        profile=eval_orchestration.EvaluationProfile.model_validate(profile_payload),
        grader_registry=registry,
        duration_seconds=1.0,
        stage_durations_seconds={"process": 0.5},
        attempt_metadata={"run_index": 1},
    )

    assert attempt.scoring_status is ScoringStatus.GRADER_ERROR
    assert not attempt.contributes_to_accuracy
    assert attempt.evaluations == {}
    assert attempt.actual_values["classification"] == "Failure"
    assert attempt.error == "Deterministic grading failed: simulated grader defect"


def test_review_capture_can_be_disabled_without_changing_result_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    captured = _run(
        monkeypatch,
        tmp_path / "captured",
        benchmark,
        [_receipt(benchmark.examples[0])],
        review_capture="full",
    )
    payload = _run(
        monkeypatch,
        tmp_path / "off",
        benchmark,
        [_receipt(benchmark.examples[0])],
        review_capture="off",
    )

    assert payload["summary"]["scoring_coverage"]["scored_runs"] == 1
    assert payload["run"]["run_id"] != captured["run"]["run_id"]
    assert payload["run"]["run_spec_sha256"] == captured["run"]["run_spec_sha256"]
    run_dir = next((tmp_path / "off").glob("**/working/**/eval_*"))
    assert not (run_dir / "review").exists()


def test_run_eval_transactionally_captures_urlsafe_binary_review(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    binary = bytes(range(256))
    urlsafe = base64.urlsafe_b64encode(binary).decode("ascii")
    _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [
            _receipt(
                benchmark.examples[0],
                execution_review={
                    "processors": {
                        "classifier": {
                            "messages": [
                                {
                                    "kind": "binary",
                                    "data": urlsafe,
                                    "media_type": "image/png",
                                }
                            ]
                        }
                    }
                },
            )
        ],
        review_capture="full",
    )
    run_dir = _run_dir(tmp_path)
    capture = json.loads((run_dir / "review" / "capture.json").read_text())
    assert capture["status"] == "complete"
    assert capture["expected_execution_count"] == 1
    assert capture["captured_execution_count"] == 1
    assert (
        next((run_dir / "review" / "objects" / "sha256").glob("*/*")).read_bytes()
        == binary
    )


def test_review_capture_failure_is_nonfatal_and_finalizes_as_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    result = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [
            _receipt(
                benchmark.examples[0],
                execution_review={
                    "processors": {
                        "classifier": {
                            "messages": [
                                {
                                    "kind": "binary",
                                    "data": "not***base64",
                                    "media_type": "image/png",
                                }
                            ]
                        }
                    }
                },
            )
        ],
        review_capture="full",
    )
    run_dir = _run_dir(tmp_path)
    capture = json.loads((run_dir / "review" / "capture.json").read_text())

    assert result["summary"]["scoring_coverage"]["scored_runs"] == 1
    assert capture["status"] == "failed"
    assert capture["captured_execution_count"] == 0
    assert capture["capture_failure_count"] == 1
    assert capture["capture_failures"][0]["error_type"] == "ReviewStoreError"
    assert not tuple((run_dir / "review" / "objects" / "sha256").glob("*/*"))


@pytest.mark.parametrize("failed_stage", ["retrieve", "process", "act"])
def test_failed_execution_preserves_observed_telemetry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failed_stage: str
) -> None:
    benchmark = _benchmark()
    telemetry = {
        "usage": {
            "requests": 2,
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
            "tool_calls": 1,
            "output_validation_attempts": 1,
        },
        "retry_telemetry": {
            "availability": "partial",
            "observed_model_requests": 2,
            "observed_tool_calls": 1,
            "observed_output_validation_attempts": 1,
            "observed_transport_attempts": None,
            "reason": "Transport retries unavailable.",
        },
        "performance": {
            "schema_version": 1,
            "processors": {
                "analysis_performance": {
                    "schema_version": 1,
                    "model_calls": [
                        {
                            "sequence": 1,
                            "duration_seconds": 4.25,
                            "status": "failed",
                            "timeout_seconds": 30.0,
                            "duration_exceeded_configured_timeout": False,
                        }
                    ],
                }
            },
        },
    }
    _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_failed_receipt(stage=failed_stage, telemetry=telemetry)],
    )

    failed = _rows(tmp_path)[0]["runs"][0]
    assert failed["usage"]["requests"] == 2
    assert failed["cost"]["status"] == "estimated_complete"
    assert failed["cost"]["actual"] is None
    assert failed["cost"]["estimated"]["currency"] == "USD"
    assert failed["cost"]["estimated"]["amount"] == pytest.approx(0.00022)
    assert failed["cost"]["unpriced_usage"] == {}
    slowest = _performance(tmp_path)["model_calls"]["slowest"][0]
    assert slowest["work_item_id"] == failed["work_item_id"]
    assert slowest["execution_id"] == failed["execution_id"]
    assert slowest["generation"] == 1
    assert slowest["duration_seconds"] == 4.25
    performance_record = LocalRunStore(
        _run_dir(tmp_path), run_id=_run_dir(tmp_path).name
    ).read_performance_records()[0]
    assert performance_record["metrics"]["retry_telemetry"]["observed_tool_calls"] == 1


def test_repeated_scored_outputs_report_nondeterminism(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [
            _receipt(benchmark.examples[0]),
            _receipt(benchmark.examples[0], classification="Healthy"),
        ],
        runs_per_example=2,
    )

    nondeterminism = payload["summary"]["nondeterminism"]
    assert nondeterminism["examples_with_multiple_scored_repetitions"] == 1
    assert nondeterminism["unstable_output_examples"] == 1
    assert nondeterminism["output_agreement_rate"] == 0.0


def test_partial_output_is_preserved_and_excluded_from_accuracy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    receipt = _receipt(benchmark.examples[0], root_cause=None)
    payload = _run(monkeypatch, tmp_path, benchmark, [receipt])

    assert payload["summary"]["accuracy"]["complete_evaluation"]["accuracy"] is None
    assert payload["summary"]["scoring_coverage"]["coverage"] == 0.0
    run = _rows(tmp_path)[0]["runs"][0]
    assert run["output_contract_status"] == "invalid"
    assert run["failure_type"] == "output_partial"
    assert run["agent_output"]["classification"]["value"] == "Failure"


def test_conditional_root_cause_is_not_required_or_scored_for_healthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = _example(classification="Healthy", root_cause="N/A")
    benchmark = _benchmark(example)
    receipt = _receipt(example, classification="Healthy", root_cause=None)
    payload = _run(monkeypatch, tmp_path, benchmark, [receipt])

    run = _rows(tmp_path)[0]["runs"][0]
    assert run["output_contract_status"] == "valid"
    assert run["evaluations"]["root_cause"]["applicable"] is False
    assert run["evaluations"]["root_cause"]["correct"] is None
    assert (
        payload["summary"]["accuracy"]["by_field"]["root_cause"]["evaluated_runs"] == 0
    )


def test_generic_label_and_slice_filters_select_examples(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    failure = _example()
    healthy = _example(
        example_id="250000117|2026-03-04T08:01:36",
        classification="Healthy",
        root_cause="N/A",
    )
    benchmark = _benchmark(failure, healthy)
    _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(healthy, classification="Healthy", root_cause=None)],
        label_filters={"classification": ["Healthy"]},
        slice_keys=["healthy"],
    )

    assert [row["example_id"] for row in _rows(tmp_path)] == [healthy.example_id]


def test_missing_example_filter_fails_before_execution(tmp_path: Path) -> None:
    benchmark = _benchmark()
    with pytest.raises(ValueError, match="absent from the benchmark"):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            example_ids=["missing"],
            runtime="serial",
            output_root=tmp_path,
        )


def test_linked_eval_requires_benchmark_source_state(tmp_path: Path) -> None:
    benchmark = _benchmark().model_copy(update={"source_state_sha256": None})
    with pytest.raises(ValueError, match="source_state_sha256 is required"):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="serial",
            output_root=tmp_path,
        )


def test_eval_can_require_exact_promoted_agent_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    resolved = resolve_agent_version(
        Path("use_case/pipeline_configs/v1_3.ppln"), dirty_policy="capture"
    )
    version_store_root = tmp_path / "versions"
    AgentVersionStore(version_store_root).promote(
        resolved,
        repository=Path.cwd(),
    )
    payload = _run(
        monkeypatch,
        tmp_path / "results",
        benchmark,
        [_receipt(benchmark.examples[0])],
        agent_version_id=resolved.manifest.agent_version_id,
        require_promoted_agent_version=True,
        agent_version_store_root=version_store_root,
    )

    assert payload["run"]["dimensions"]["agent"]["lifecycle_state_at_run"] == (
        "promoted"
    )


def test_invalid_receipt_path_fails_preflight_before_pipeline_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile_payload = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_payload["output_fields"][0]["actual"]["receipt_metadata_path"] = [
        "agent_output",
        "classification_typo",
        "value",
    ]
    profile_path = tmp_path / "invalid.eval.yaml"
    profile_path.write_text(yaml.safe_dump(profile_payload), encoding="utf-8")
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline executed")
        ),
    )

    with pytest.raises(ValueError, match="absent from the pipeline output schema"):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=profile_path,
            benchmark_key="phase-1-benchmark-3fb7f544",
            repository=_Repository(_benchmark()),
            runtime="serial",
            output_root=tmp_path,
        )


def test_project_contract_rejects_grading_an_unconfigured_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile_payload = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    profile_payload["output_fields"][0]["evaluation"]["benchmark_label_path"] = [
        "review_notes"
    ]
    profile_path = tmp_path / "unconfigured-label.eval.yaml"
    profile_path.write_text(yaml.safe_dump(profile_payload), encoding="utf-8")
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline executed")
        ),
    )

    with pytest.raises(ValueError, match="not enabled by workbench.project.json"):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=profile_path,
            benchmark_key="phase-1-benchmark-3fb7f544",
            repository=_Repository(_benchmark()),
            runtime="serial",
            output_root=tmp_path,
        )


def test_incompatible_benchmark_target_type_fails_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    schema, _ = _schema()
    schema["fields"][0]["values"] = [1]
    digest = hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    base = _benchmark()
    example = base.examples[0].model_copy(
        update={
            "approved_label_payload": {
                **base.examples[0].approved_label_payload,
                "classification": 1,
            }
        }
    )
    benchmark = base.model_copy(
        update={
            "examples": (example,),
            "label_schemas": (
                PublishedLabelSchema(
                    schema_version_id="schema-v1",
                    schema_key="spirax-steam-trap-label",
                    version="v1",
                    schema=schema,
                    content_sha256=digest,
                ),
            ),
        }
    )
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline executed")
        ),
    )

    with pytest.raises(ValueError, match="incompatible with declared output type"):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="serial",
            output_root=tmp_path,
        )


def test_identical_spec_starts_fresh_and_exact_id_resumes_without_new_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    calls = 0

    def run_once(*args: Any, **kwargs: Any) -> PipelineReceipt:
        nonlocal calls
        calls += 1
        return _receipt(benchmark.examples[0])

    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        run_once,
    )
    first = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )
    second = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )

    assert first != second
    assert calls == 2
    first_payload = json.loads(first.read_text(encoding="utf-8"))
    second_payload = json.loads(second.read_text(encoding="utf-8"))
    assert (
        first_payload["run"]["run_spec_sha256"]
        == second_payload["run"]["run_spec_sha256"]
    )
    resumed = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        expected_run_id=first.parent.name,
        materialize_only=True,
        output_root=tmp_path,
    )
    assert resumed == first
    assert calls == 2
    recovery = json.loads(resumed.read_text(encoding="utf-8"))["summary"][
        "execution_recovery"
    ]
    assert recovery["logical_work_items"] == 1
    assert recovery["execution_generations"] == 1


def test_later_empty_stage_telemetry_does_not_hide_process_observations() -> None:
    receipt = PipelineReceipt(
        pipeline_id="test",
        process_receipt=StageReceipt(
            "process",
            True,
            0.1,
            metadata={"execution_telemetry": {"usage": {"requests": 1}}},
        ),
        act_receipt=StageReceipt(
            "act", True, 0.1, metadata={"execution_telemetry": {}}
        ),
    )

    assert eval_orchestration._receipt_execution_telemetry(receipt) == {
        "usage": {"requests": 1}
    }


def test_failed_work_can_be_rerun_without_replacing_first_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    receipts = iter([_failed_receipt(), _receipt(benchmark.examples[0])])
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: next(receipts),
    )
    first = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )
    assert _rows(tmp_path)[0]["runs"][0]["execution_generation"] == 1

    second = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        expected_run_id=first.parent.name,
        resume_mode="failed",
        output_root=tmp_path,
    )
    payload = json.loads(second.read_text(encoding="utf-8"))
    run = _rows(tmp_path)[0]["runs"][0]
    assert first == second
    assert run["execution_generation"] == 2
    records = LocalRunStore(
        _run_dir(tmp_path), run_id=_run_dir(tmp_path).name
    ).read_attempt_records()
    assert [item["attempt"]["failure_type"] for item in records] == [
        "provider_error",
        None,
    ]
    assert payload["summary"]["execution_recovery"] == {
        "logical_work_items": 1,
        "recorded_work_items": 1,
        "missing_work_items": 0,
        "execution_generations": 2,
        "rerun_generations": 1,
    }
    performance = _performance(tmp_path)
    assert performance["recorded_executions"] == 1
    assert performance["summary"]["run_duration_seconds"]["count"] == 1


def test_interruption_preserves_completed_work_and_resume_runs_only_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first_example = _example()
    second_example = _example(
        example_id="250000117|2026-03-04T08:01:36",
        classification="Healthy",
        root_cause="N/A",
    )
    benchmark = _benchmark(first_example, second_example)
    calls: list[str] = []

    def interrupted(*args: Any, **kwargs: Any) -> PipelineReceipt:
        example = kwargs["example"]
        calls.append(example.example_id)
        if example.example_id == second_example.example_id:
            raise KeyboardInterrupt()
        return _receipt(first_example)

    monkeypatch.setattr(eval_orchestration, "run_pipeline", interrupted)
    with pytest.raises(KeyboardInterrupt):
        eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="serial",
            output_root=tmp_path,
        )
    interrupted_run_id = _run_dir(tmp_path).name

    invocation_events = list(tmp_path.glob("**/performance/invocations/*.json"))
    assert any(path.name.endswith(".interrupted.json") for path in invocation_events)
    assert not any(path.name.endswith(".failed.json") for path in invocation_events)

    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (
            calls.append(kwargs["example"].example_id)
            or _receipt(
                second_example,
                classification="Healthy",
                root_cause=None,
            )
        ),
    )
    path = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        expected_run_id=interrupted_run_id,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert calls == [
        first_example.example_id,
        second_example.example_id,
        second_example.example_id,
    ]
    assert payload["summary"]["execution_recovery"]["recorded_work_items"] == 2
    assert payload["summary"]["execution_recovery"]["execution_generations"] == 2


def test_dry_run_resolves_manifest_and_continues_same_occurrence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = _example().model_copy(
        update={
            "published_review_context": PublishedReviewContext(
                reviewer_coverage=(
                    PublishedReviewerCoverage(
                        review_event_id="review-event-a",
                        label_revision=2,
                        reviewer_user_id="reviewer-user-a",
                        reviewer_display_name="Alex Labeler",
                        reviewer_project_role="domain_reviewer",
                        submitted_at=datetime(2026, 3, 18, 8, tzinfo=timezone.utc),
                        is_selected_label_revision=True,
                    ),
                ),
                verification=PublishedVerification(
                    source="operator_feedback",
                    note="Confirmed by customer.",
                    recorded_at=datetime(2026, 3, 19, tzinfo=timezone.utc),
                    source_content_sha256="e" * 64,
                    context_schema_key="spirax_customer_verification",
                    context_schema_version="1",
                    source_fields={"failure_cause": "Trap failed closed"},
                ),
            )
        }
    )
    benchmark = _benchmark(example)
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline executed")
        ),
    )

    path = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        dry_run=True,
        output_root=tmp_path,
    )
    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert path.name == "manifest.json"
    assert manifest["run_id"].startswith("eval_")
    assert len(manifest["work_items"]) == 1
    retained_example = manifest["eval_contract"]["examples"][0]
    assert (
        retained_example["source_snapshot_id"]
        == benchmark.examples[0].source_snapshot_id
    )
    assert retained_example["raw_snapshot_content_sha256"] == "c" * 64
    assert [item["artifact_kind"] for item in retained_example["raw_artifacts"]] == [
        "telemetry",
        "alarms",
    ]
    context = retained_example["published_review_context"]
    assert context["reviewer_coverage"][0]["label_revision"] == 2
    assert context["reviewer_coverage"][0]["is_selected_label_revision"] is True
    assert "explanation" not in context["reviewer_coverage"][0]
    assert context["verification"]["source"] == "operator_feedback"
    assert context["verification"]["source_fields"] == {
        "failure_cause": "Trap failed closed"
    }
    assert not tuple(path.parent.glob("attempts/**/*.json"))

    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: _receipt(example),
    )
    result_path = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        expected_run_id=manifest["run_id"],
        output_root=tmp_path,
    )

    assert result_path == path.parent / "result.json"
    assert len(tuple(tmp_path.glob("**/working/**/eval_*"))) == 1


def test_run_identity_excludes_progress_interval_but_includes_worker_limit(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark()

    def resolve(*, progress: float, workers: int) -> Path:
        return eval_orchestration.run_eval(
            Path("use_case/pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="threaded",
            max_workers=workers,
            progress_interval_seconds=progress,
            dry_run=True,
            output_root=tmp_path,
        )

    first = resolve(progress=1.0, workers=1)
    same = resolve(progress=99.0, workers=1)
    different = resolve(progress=1.0, workers=2)

    assert first != same
    assert first.parent.name != different.parent.name
    first_manifest = json.loads(first.read_text(encoding="utf-8"))
    same_manifest = json.loads(same.read_text(encoding="utf-8"))
    different_manifest = json.loads(different.read_text(encoding="utf-8"))
    assert first_manifest["run_spec_sha256"] == same_manifest["run_spec_sha256"]
    assert first_manifest["run_spec_sha256"] != different_manifest["run_spec_sha256"]


def test_cli_outcome_reports_scoring_coverage(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "summary": {
                    "reliability": {"planned_runs": 3},
                    "scoring_coverage": {"scored_runs": 2},
                }
            }
        ),
        encoding="utf-8",
    )

    eval_orchestration._print_cli_outcome(path)

    assert "2/3 attempts scored; 1 not scored" in capsys.readouterr().out


def test_configuration_dimensions_require_unique_json_scalars() -> None:
    parser = eval_orchestration._argument_parser()

    assert eval_orchestration._parse_configuration_dimensions(
        ["prompt_revision=7", 'feature_set="base"'], parser
    ) == {"prompt_revision": 7, "feature_set": "base"}
    with pytest.raises(SystemExit):
        eval_orchestration._parse_configuration_dimensions(["feature_set={}"], parser)


def test_normal_cli_exposes_only_three_scope_forms_and_supported_runtimes() -> None:
    parser = eval_orchestration._argument_parser()
    help_text = parser.format_help()

    assert "--all-examples" in help_text
    assert "--example-ids" in help_text
    assert "--unit-ids" in help_text
    assert "--section" in help_text
    assert "--runtime {threaded,serial}" in help_text
    for unsupported in (
        "--label-filter",
        "--slice",
        "--resume-mode",
        "--rerun-failure-type",
        "--materialize-only",
        "--compare-model",
        "--compare-result",
        "process",
    ):
        assert unsupported not in help_text

    defaults = parser.parse_args([])
    assert defaults.runtime == "threaded"
    assert defaults.runs_per_example == 1
    assert (
        eval_orchestration._resolve_cli_runtime(defaults, parser=parser) == "threaded"
    )


def test_named_section_resolves_label_and_explicit_list_is_distinct() -> None:
    parser = eval_orchestration._argument_parser()
    profile = eval_orchestration.load_evaluation_profile(PROFILE_PATH)
    benchmark = _benchmark()

    named = parser.parse_args(["--section", "Open Failure"])
    assert eval_orchestration._resolve_cli_scope(
        named, benchmark=benchmark, profile=profile, parser=parser
    ) == (None, None, {}, ["open-failure"])

    explicit = parser.parse_args(["--unit-ids", "250000116"])
    assert eval_orchestration._resolve_cli_scope(
        explicit, benchmark=benchmark, profile=profile, parser=parser
    ) == (None, ["250000116"], {}, [])


def test_resume_command_is_shell_safe() -> None:
    command = eval_orchestration._resume_command(
        ["pipeline configs/agent.ppln", "--all-examples", "--dry-run"],
        run_id="eval_" + "a" * 24,
    )

    assert "'pipeline configs/agent.ppln'" in command
    assert "--dry-run" not in command
    assert "--run-id eval_aaaaaaaaaaaaaaaaaaaaaaaa" in command
    assert command.endswith("--run-id eval_" + "a" * 24)


def test_cost_estimate_uses_frozen_model_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        eval_orchestration,
        "resolve_model_definition",
        lambda model: ModelDefinition(
            id=str(model),
            api="openai_responses",
            pricing=ModelPricing(
                version="2026-07",
                currency="USD",
                input_per_million_tokens=2.0,
                output_per_million_tokens=10.0,
            ),
        ),
    )

    cost = eval_orchestration._build_cost_observation(
        ai_model="azure:test",
        usage={"input_tokens": 1_000_000, "output_tokens": 100_000},
        provider_cost=None,
    )

    assert cost["status"] == "estimated_complete"
    assert cost["estimated"]["amount"] == 3.0
    assert cost["actual"] is None


def test_cost_estimate_prices_reasoning_at_output_rate_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        eval_orchestration,
        "resolve_model_definition",
        lambda model: ModelDefinition(
            id=str(model),
            api="openai_responses",
            pricing=ModelPricing(
                version="2026-07",
                currency="USD",
                input_per_million_tokens=2.0,
                output_per_million_tokens=10.0,
            ),
        ),
    )

    cost = eval_orchestration._build_cost_observation(
        ai_model="azure:test",
        usage={
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "reasoning_tokens": 40_000,
        },
        provider_cost=None,
    )

    assert cost["status"] == "estimated_complete"
    assert cost["estimated"]["amount"] == 3.0
    assert cost["estimated"]["priced_usage"]["output_tokens"] == 60_000
    assert cost["estimated"]["priced_usage"]["reasoning_tokens"] == 40_000


def test_cost_estimate_assumes_all_legacy_input_tokens_are_uncached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        eval_orchestration,
        "resolve_model_definition",
        lambda model: ModelDefinition(
            id=str(model),
            api="openai_responses",
            pricing=ModelPricing(
                version="2026-07",
                currency="USD",
                input_per_million_tokens=2.0,
                cached_input_per_million_tokens=0.2,
                output_per_million_tokens=10.0,
            ),
        ),
    )

    cost = eval_orchestration._build_cost_observation(
        ai_model="azure:test",
        usage={
            "input_tokens": 1_000_000,
            "cached_input_tokens": 900_000,
            "output_tokens": 0,
        },
        provider_cost=None,
    )

    assert cost["status"] == "estimated_complete"
    assert cost["estimated"]["amount"] == 2.0
    assert cost["estimated"]["input_pricing_policy"] == "assume_uncached"
    assert cost["estimated"]["priced_usage"] == {"input_tokens": 1_000_000}


@pytest.mark.parametrize(
    ("pricing", "request_usage", "expected_amount", "expected_meters"),
    [
        (
            ModelPricing(
                version="azure-2026-07",
                currency="USD",
                billing_provider="azure_openai",
                billing_plan="global-standard",
                input_per_million_tokens=1.0,
                cached_input_per_million_tokens=0.1,
                cache_write_per_million_tokens=1.25,
                output_per_million_tokens=6.0,
            ),
            {
                "provider": "azure_openai",
                "model": "gpt-5.6-luna",
                "reported": {"input_tokens": 100, "output_tokens": 10},
                "billable": {
                    "input_uncached_tokens": 100,
                    "input_cache_read_tokens": 0,
                    "input_cache_write_tokens": 0,
                    "input_cache_write_5m_tokens": 0,
                    "input_cache_write_1h_tokens": 0,
                    "output_visible_tokens": 10,
                    "output_reasoning_tokens": 0,
                },
                "billable_usage_gaps": [],
            },
            0.00016,
            {"input_tokens", "output_visible_tokens"},
        ),
        (
            ModelPricing(
                version="claude-2026-07",
                currency="USD",
                billing_provider="azure_claude",
                billing_plan="foundry-ccu-list-price",
                input_per_million_tokens=1.0,
                cached_input_per_million_tokens=0.1,
                cache_write_5m_per_million_tokens=1.25,
                cache_write_1h_per_million_tokens=2.0,
                output_per_million_tokens=5.0,
            ),
            {
                "provider": "azure_claude",
                "model": "claude-haiku-4-5",
                "reported": {"input_tokens": 1_800, "output_tokens": 100},
                "billable": {
                    "input_uncached_tokens": 100,
                    "input_cache_read_tokens": 500,
                    "input_cache_write_tokens": 1_200,
                    "input_cache_write_5m_tokens": 1_000,
                    "input_cache_write_1h_tokens": 200,
                    "output_visible_tokens": 100,
                    "output_reasoning_tokens": 0,
                },
                "billable_usage_gaps": [],
            },
            0.0023,
            {
                "input_tokens",
                "output_visible_tokens",
            },
        ),
        (
            ModelPricing(
                version="google-2026-07",
                currency="USD",
                billing_provider="google_direct",
                billing_plan="developer-api-standard",
                input_per_million_tokens=0.25,
                cached_input_per_million_tokens=0.025,
                output_per_million_tokens=1.5,
            ),
            {
                "provider": "google_direct",
                "model": "gemini-3.1-flash-lite",
                "reported": {"input_tokens": 50, "output_tokens": 500},
                "billable": {
                    "input_uncached_tokens": 40,
                    "input_cache_read_tokens": 10,
                    "input_cache_write_tokens": 0,
                    "input_cache_write_5m_tokens": 0,
                    "input_cache_write_1h_tokens": 0,
                    "output_visible_tokens": 100,
                    "output_reasoning_tokens": 400,
                },
                "billable_usage_gaps": [],
            },
            0.0007625,
            {
                "input_tokens",
                "output_visible_tokens",
                "output_reasoning_tokens",
            },
        ),
    ],
)
def test_request_level_costing_assumes_provider_inputs_are_uncached(
    pricing: ModelPricing,
    request_usage: dict[str, Any],
    expected_amount: float,
    expected_meters: set[str],
) -> None:
    cost = eval_orchestration._estimate_cost_from_usage(  # noqa: SLF001
        {"model_requests": [request_usage]},
        pricing,
    )

    assert cost["status"] == "estimated_complete"
    assert cost["estimated"]["amount"] == pytest.approx(expected_amount)
    assert cost["estimated"]["input_pricing_policy"] == "assume_uncached"
    assert {
        line["meter"] for line in cost["estimated"]["requests"][0]["line_items"]
    } == expected_meters


def test_request_level_costing_ignores_cache_gaps_under_uncached_assumption() -> None:
    cost = eval_orchestration._estimate_cost_from_usage(  # noqa: SLF001
        {
            "model_requests": [
                {
                    "provider": "azure_openai",
                    "model": "gpt-5.6-luna",
                    "reported": {"input_tokens": 1_100, "output_tokens": 10},
                    "billable": {
                        "input_uncached_tokens": 1_100,
                        "input_cache_read_tokens": 0,
                        "input_cache_write_tokens": 0,
                        "input_cache_write_5m_tokens": 0,
                        "input_cache_write_1h_tokens": 0,
                        "output_visible_tokens": 10,
                        "output_reasoning_tokens": 0,
                    },
                    "billable_usage_gaps": ["input_cache_write_tokens_unreported"],
                }
            ]
        },
        ModelPricing(
            version="azure-2026-07",
            currency="USD",
            billing_provider="azure_openai",
            input_per_million_tokens=1.0,
            cached_input_per_million_tokens=0.1,
            cache_write_per_million_tokens=1.25,
            output_per_million_tokens=6.0,
        ),
    )

    assert cost["status"] == "estimated_complete"
    assert cost["estimated"]["amount"] == pytest.approx(0.00116)
    assert cost["estimated"]["priced_usage"] == {
        "input_tokens": 1_100,
        "output_visible_tokens": 10,
    }
    assert cost["unpriced_usage"] == {}


def test_run_identity_freezes_selected_pricing_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pricing = ModelPricing(
        version="reviewed-2026-07",
        currency="USD",
        input_per_million_tokens=1.25,
        output_per_million_tokens=5.0,
        effective_date="2026-07-01",
        source="reviewed price sheet",
    )
    monkeypatch.setattr(
        eval_orchestration,
        "resolve_model_definition",
        lambda model: ModelDefinition(
            id=str(model), api="openai_responses", pricing=pricing
        ),
    )
    manifest = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=_benchmark().benchmark_key,
        repository=_Repository(_benchmark()),
        ai_model="azure:gpt-5.6-terra",
        runtime="serial",
        dry_run=True,
        output_root=tmp_path,
    )

    selected = json.loads(manifest.read_text())["run_spec"]["model"]["pricing"]
    assert selected["version"] == "reviewed-2026-07"
    assert selected["input_per_million_tokens"] == 1.25
    assert len(selected["content_sha256"]) == 64
    run_model = json.loads(manifest.read_text())["run_spec"]["model"]
    assert run_model["input_pricing_policy"] == "assume_uncached"


def test_cost_summary_reports_complete_partial_and_unavailable_unit_coverage() -> None:
    def attempt(cost: dict[str, Any] | None) -> EvalAttempt:
        return EvalAttempt(
            execution_status=ExecutionStatus.COMPLETED,
            output_contract_status=OutputContractStatus.VALID,
            scoring_status=ScoringStatus.NO_APPLICABLE_TARGETS,
            artifacts={} if cost is None else {"cost": cost},
        )

    summary = eval_orchestration._build_cost_summary(
        [
            attempt(
                {
                    "status": "actual",
                    "actual": {"amount": 1.0, "currency": "USD"},
                    "estimated": None,
                }
            ),
            attempt(
                {
                    "status": "estimated_complete",
                    "actual": None,
                    "estimated": {"amount": 3.0, "currency": "USD"},
                }
            ),
            attempt(
                {
                    "status": "estimated_partial",
                    "actual": None,
                    "estimated": {"amount": 0.5, "currency": "USD"},
                }
            ),
            attempt(
                {
                    "status": "unavailable",
                    "actual": None,
                    "estimated": None,
                }
            ),
            attempt(None),
        ]
    )

    assert summary["units_with_complete_cost_observations"] == 2
    assert summary["units_with_partial_pricing"] == 1
    assert summary["units_without_usable_cost_information"] == 2
    assert summary["actual_by_currency"] == {"USD": 1.0}
    assert summary["estimated_by_currency"] == {"USD": 3.5}
    assert summary["complete_unit_cost_by_currency"]["USD"] == {
        "count": 2,
        "total": 4.0,
        "average": 2.0,
        "p5": 1.1,
        "p95": 2.9,
    }


def test_cost_summary_rebuilds_estimates_from_usage_and_frozen_pricing() -> None:
    attempt = EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.NO_APPLICABLE_TARGETS,
        artifacts={
            "usage": {
                "input_tokens": 1_000_000,
                "output_tokens": 100_000,
                "reasoning_tokens": 40_000,
            },
            "cost": {
                "status": "estimated_partial",
                "estimated": {"amount": 2.6, "currency": "USD"},
                "actual": None,
            },
        },
    )

    summary = eval_orchestration._build_cost_summary(
        [attempt],
        frozen_pricing={
            "version": "2026-07",
            "currency": "USD",
            "input_per_million_tokens": 2.0,
            "output_per_million_tokens": 10.0,
        },
    )

    assert summary["status_counts"] == {"estimated_complete": 1}
    assert summary["units_with_complete_cost_observations"] == 1
    assert summary["complete_unit_cost_by_currency"]["USD"] == {
        "count": 1,
        "total": 3.0,
        "average": 3.0,
        "p5": 3.0,
        "p95": 3.0,
    }


def test_complete_working_eval_elevates_to_compact_verified_retained_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    eval_root = tmp_path / ".workbench/evals"
    payload = _run(
        monkeypatch,
        eval_root,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )
    run_id = payload["run"]["run_id"]
    service = EvalLifecycleService(tmp_path)

    class _EvidenceAdapter:
        def build_view(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "verified": True,
                "example_id": kwargs["example"].example_id,
            }

    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
    )
    working_evidence = backend.get_evidence(
        run_id, benchmark.examples[0].example_id
    )
    preview = service.preview_elevation(run_id)
    elevated = service.elevate(run_id, confirmed=True)
    retained_dir = tmp_path / elevated["path"]

    assert preview["source_run_id"] == run_id
    assert preview["prunes"] == [
        "per-attempt files",
        "performance, speed, latency, retry, and invocation detail",
        "tool traces and intermediate review objects",
        "local copies of Azure evidence",
        "the complete source working eval after retained verification",
    ]
    assert elevated["verified"] is True
    assert elevated["source_deleted"] is True
    assert not (
        eval_root
        / "working"
        / benchmark.benchmark_key
        / f"v{benchmark.version_number}"
        / run_id
    ).exists()
    assert {path.name for path in retained_dir.iterdir()} == {
        "manifest.json",
        "result.json",
        "units.json",
        "agent-provenance.json",
        "evidence-references.json",
        *(["agent.patch"] if (retained_dir / "agent.patch").exists() else []),
    }
    assert not any(path.is_dir() for path in retained_dir.iterdir())
    retained_manifest = json.loads((retained_dir / "manifest.json").read_text())
    retained_result = json.loads((retained_dir / "result.json").read_text())
    units = json.loads((retained_dir / "units.json").read_text())
    assert retained_manifest["schema_version"] == 2
    assert retained_manifest["identity_seed"]["source_eval_run_id"] == run_id
    assert "artifacts" not in retained_manifest["identity_seed"]
    assert retained_result["summary"]["timing"] == payload["summary"]["timing"]
    assert units["units"][0]["agent_output"]["classification"]["value"] == "Failure"
    assert units["units"][0]["benchmark_labels"]["classification"] == "Failure"
    assert units["units"][0]["evaluations"]["classification"]["correct"] is True
    assert "usage" in units["units"][0]
    assert "cost" in units["units"][0]
    assert "latest_invocation_id" not in retained_result["run"]
    assert {
        "execution_id",
        "execution_generation",
        "execution_history",
        "invocation_id",
        "failure_details",
        "review_status",
        "review_unavailable_reason",
        "flaky",
    }.isdisjoint(units["units"][0])
    evidence = json.loads((retained_dir / "evidence-references.json").read_text())
    assert evidence["storage"]["account_url"].startswith("https://")
    assert evidence["examples"][0]["raw_artifacts"][0]["content_sha256"]
    provenance = json.loads((retained_dir / "agent-provenance.json").read_text())
    if provenance["git"]["tree_state"] == "dirty":
        assert (retained_dir / "agent.patch").read_text(encoding="utf-8")
    else:
        assert not (retained_dir / "agent.patch").exists()

    listed = backend.list_runs()["runs"]
    assert {item["lifecycle_state"] for item in listed} == {"retained"}
    assert all(item["cost"] == payload["summary"]["cost"] for item in listed)
    retained_id = elevated["retained_eval_id"]
    attempts = backend.list_attempts(
        retained_id,
        state="all",
        search="",
        field=None,
        slice_key=None,
        offset=0,
        limit=100,
    )
    assert attempts["rows"][0]["agent_output"]["classification"]["value"] == "Failure"
    detail = backend.get_attempt(retained_id, attempts["rows"][0]["execution_id"])
    assert detail["review"] is None
    assert detail["performance"]["availability"] == "unavailable"
    retained_evidence = backend.get_evidence(
        retained_id, benchmark.examples[0].example_id
    )
    assert retained_evidence == working_evidence
    unexpected = retained_dir / "unexpected"
    unexpected.mkdir()
    with pytest.raises(EvalLifecycleError, match="non-file"):
        service.verify(retained_id)
    unexpected.rmdir()


def test_incomplete_working_eval_refuses_elevation(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark()
    manifest = eval_orchestration.run_eval(
        Path("use_case/pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        dry_run=True,
        output_root=tmp_path,
    )
    service = EvalLifecycleService(tmp_path, eval_root=tmp_path)

    with pytest.raises(EvalLifecycleError, match="incomplete"):
        service.preview_elevation(manifest.parent.name)


def test_permanent_delete_preserves_shared_retained_agent_until_last_reference(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    first = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
    )
    second = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0]), _receipt(benchmark.examples[0])],
        runs_per_example=2,
    )
    service = EvalLifecycleService(tmp_path, eval_root=tmp_path)
    retained_a = service.elevate(first["run"]["run_id"], confirmed=True)
    retained_b = service.elevate(second["run"]["run_id"], confirmed=True)
    assert retained_a["agent_version_id"] == retained_b["agent_version_id"]
    agent_dir = (
        tmp_path / "retained" / "agent_versions" / retained_a["agent_version_id"]
    )

    removed_a = service.delete_retained(
        retained_a["retained_eval_id"],
        confirmation=retained_a["retained_eval_id"],
    )
    assert removed_a["recoverable"] is False
    assert removed_a["agent_version_removed"] is False
    assert agent_dir.is_dir()

    removed_b = service.delete_retained(
        retained_b["retained_eval_id"],
        confirmation=retained_b["retained_eval_id"],
    )
    assert removed_b["agent_version_removed"] is True
    assert not agent_dir.exists()
    assert service.list_evals("working") == []


def test_progress_tracker_reports_healthy_failure_and_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[str] = []
    monkeypatch.setattr(
        eval_orchestration.logger,
        "info",
        lambda message, *args: messages.append(message % args if args else message),
    )
    monkeypatch.setattr(
        eval_orchestration.logger,
        "error",
        lambda message, *args: messages.append(message % args if args else message),
    )
    benchmark = _benchmark()
    item = eval_orchestration.RepeatedEvalWorkItem(
        item_id=benchmark.examples[0].example_id,
        payload=benchmark.examples[0],
        attempt_index=1,
    )
    tracker = eval_orchestration._EvalProgressTracker(
        total_runs=2,
        heartbeat_seconds=30.0,
    )
    tracker.started(item)
    assert "running" in (tracker._heartbeat_message() or "")

    receipt = _receipt(benchmark.examples[0])
    assert receipt.act_receipt is not None
    scored = eval_orchestration.score_receipt_metadata(
        metadata=receipt.act_receipt.metadata,
        expected_identity={
            "example_id": benchmark.examples[0].example_id,
            "benchmark_key": benchmark.benchmark_key,
            "benchmark_version_id": benchmark.benchmark_version_id,
            "benchmark_version_number": benchmark.version_number,
            "source_snapshot_id": benchmark.examples[0].source_snapshot_id,
        },
        example=benchmark.examples[0],
        profile=eval_orchestration.load_evaluation_profile(PROFILE_PATH),
        grader_registry=build_default_grader_registry(),
        duration_seconds=1.0,
        stage_durations_seconds={},
        attempt_metadata={"run_index": 1},
    )
    tracker.completed(item, scored)

    assert any("SUCCESS" in message for message in messages)
