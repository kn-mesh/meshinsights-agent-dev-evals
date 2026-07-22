"""Tests for schema-driven published-benchmark evaluation orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt
import pytest
import yaml

from model_catalog import ModelDefinition, ModelPricing
from evaluation import FieldGrade, GraderRegistry, ScoringStatus
from src.agent_versions import AgentVersionStore, resolve_agent_version

from src.benchmarks import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedLabelSchema,
    SourceArtifact,
)
from src.evals import eval_orchestration
from src.evals.result_integrity import ResultIntegrityError, load_verified_result


PROFILE_PATH = Path("evaluation_configs/spirax-failure-evaluation.eval.yaml")


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
        raw_artifacts=artifacts,
    )


def _benchmark(*examples: BenchmarkExample) -> BenchmarkVersion:
    schema, digest = _schema()
    items = examples or (_example(),)
    return BenchmarkVersion(
        project_key="spirax-pulse",
        benchmark_key="steam-trap-regression",
        benchmark_name="Steam Trap Regression",
        benchmark_version_id="version-id",
        version_number=4,
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
        process_receipt=StageReceipt("process", True, 0.2),
        act_receipt=StageReceipt(
            "act",
            True,
            0.1,
            metadata={
                "example_id": example.example_id,
                "benchmark_key": "steam-trap-regression",
                "benchmark_version_id": "version-id",
                "benchmark_version_number": 4,
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
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        benchmark_version=benchmark.version_number,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
        **overrides,
    )
    return json.loads(path.read_text(encoding="utf-8"))


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


def test_run_eval_writes_schema_v3_full_labels_and_generic_metrics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(benchmark.examples[0])],
        agent_version="spirax-v1.3",
        configuration_dimensions={"prompt_revision": 7, "feature_set": "base"},
    )

    assert list(payload) == ["summary", "run_config", "selected_example_ids", "results"]
    assert payload["run_config"]["eval_result_schema_version"] == 3
    assert payload["run_config"]["evaluation_profile"]["profile_id"] == (
        "spirax-failure-evaluation"
    )
    dimensions = payload["run_config"]["dimensions"]
    assert dimensions["agent"]["agent_version_id"].startswith("av_")
    assert dimensions["agent"]["manifest_sha256"]
    assert dimensions["agent"]["legacy_label"] == "spirax-v1.3"
    assert payload["run_config"]["agent_version"] == {
        key: value
        for key, value in dimensions["agent"].items()
        if key != "legacy_label"
    }
    assert payload["run_config"]["benchmark_name"] == "Steam Trap Regression"
    assert payload["run_config"]["benchmark_source_state_sha256"] == "d" * 64
    assert payload["run_config"]["selected_example_scope_sha256"]
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
    result = payload["results"][0]
    assert result["benchmark_labels"]["review_notes"].startswith("Useful context")
    assert set(result["slice_keys"]) == {"expected-failure", "closed-failure"}
    assert result["runs"][0]["fields"]["classification"]["grader"] == {
        "id": "core.exact",
        "version": 1,
        "config": {},
    }
    assert (
        result["runs"][0]["agent_version_id"] == dimensions["agent"]["agent_version_id"]
    )
    run_dir = next(tmp_path.glob("**/runs/eval_*"))
    capture = json.loads((run_dir / "review" / "capture.json").read_text())
    assert capture["publication"] == "local_only"
    assert capture["execution_counts"]["partial"] == 1
    review_manifest = next((run_dir / "review" / "executions").glob("*/*.json"))
    assert (
        json.loads(review_manifest.read_text())["source_evidence"][0]["write_access"]
        is False
    )


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
    result_path = next(tmp_path.glob("**/runs/eval_*/result.json"))
    assert load_verified_result(result_path) == original

    mutations = (
        lambda value: value["results"][0]["runs"].clear(),
        lambda value: value["results"][0]["runs"][0]["fields"]["classification"].update(
            {"correct": False}
        ),
        lambda value: value["summary"]["usage"].update({"attempts_with_usage": 999}),
        lambda value: value["run_config"]["dimensions"]["model"].update(
            {"id": "azure:edited"}
        ),
        lambda value: value["results"][0]["benchmark_labels"].update(
            {"classification": "Healthy"}
        ),
        lambda value: value["results"][0]["runs"][0].update(
            {"execution_generation": 99}
        ),
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
    failed = payload["results"][0]["runs"][1]
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
    assert payload["run_config"]["run_id"] == captured["run_config"]["run_id"]
    run_dir = next((tmp_path / "off").glob("**/runs/eval_*"))
    assert not (run_dir / "review").exists()


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
    }
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_failed_receipt(stage=failed_stage, telemetry=telemetry)],
    )

    failed = payload["results"][0]["runs"][0]
    assert failed["usage"]["requests"] == 2
    assert failed["retry_telemetry"]["observed_tool_calls"] == 1
    assert failed["cost"] == {
        "status": "unavailable",
        "actual": None,
        "estimated": None,
        "unpriced_usage": {},
        "reason": "No frozen pricing record is configured for this model.",
    }


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
    run = payload["results"][0]["runs"][0]
    assert run["output_contract_status"] == "invalid"
    assert run["failure_type"] == "output_partial"
    assert run["actual_outputs"] == {"classification": "Failure"}
    assert run["agent_output"]["classification"]["value"] == "Failure"


def test_conditional_root_cause_is_not_required_or_scored_for_healthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    example = _example(classification="Healthy", root_cause="N/A")
    benchmark = _benchmark(example)
    receipt = _receipt(example, classification="Healthy", root_cause=None)
    payload = _run(monkeypatch, tmp_path, benchmark, [receipt])

    run = payload["results"][0]["runs"][0]
    assert run["output_contract_status"] == "valid"
    assert run["fields"]["root_cause"]["applicable"] is False
    assert run["fields"]["root_cause"]["correct"] is None
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
    payload = _run(
        monkeypatch,
        tmp_path,
        benchmark,
        [_receipt(healthy, classification="Healthy", root_cause=None)],
        label_filters={"classification": ["Healthy"]},
        slice_keys=["healthy"],
    )

    assert payload["selected_example_ids"] == [healthy.example_id]


def test_missing_example_filter_fails_before_execution(tmp_path: Path) -> None:
    benchmark = _benchmark()
    with pytest.raises(ValueError, match="absent from the benchmark"):
        eval_orchestration.run_eval(
            Path("pipeline_configs/v1_3.ppln"),
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
            Path("pipeline_configs/v1_3.ppln"),
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
        Path("pipeline_configs/v1_3.ppln"), dirty_policy="capture"
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

    assert (
        payload["run_config"]["agent_version"]["lifecycle_state_at_run"] == "promoted"
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
            Path("pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=profile_path,
            benchmark_key="steam-trap-regression",
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
            Path("pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=profile_path,
            benchmark_key="steam-trap-regression",
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
            Path("pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="serial",
            output_root=tmp_path,
        )


def test_identical_run_resumes_without_duplicating_completed_work(
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
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )
    first_performance = json.loads(first.read_text(encoding="utf-8"))["summary"][
        "performance"
    ]
    second = eval_orchestration.run_eval(
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )

    assert first == second
    assert calls == 1
    payload = json.loads(second.read_text(encoding="utf-8"))
    assert payload["summary"]["performance"] == first_performance
    materialized = eval_orchestration.run_eval(
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        materialize_only=True,
        output_root=tmp_path,
    )
    materialized_payload = json.loads(materialized.read_text(encoding="utf-8"))
    assert materialized_payload["summary"]["performance"] == first_performance
    assert calls == 1
    recovery = payload["summary"]["execution_recovery"]
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
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        output_root=tmp_path,
    )
    first_payload = json.loads(first.read_text(encoding="utf-8"))
    assert first_payload["results"][0]["runs"][0]["execution_generation"] == 1

    second = eval_orchestration.run_eval(
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
        resume_mode="failed",
        output_root=tmp_path,
    )
    payload = json.loads(second.read_text(encoding="utf-8"))
    run = payload["results"][0]["runs"][0]
    assert first == second
    assert run["execution_generation"] == 2
    assert [item["failure_type"] for item in run["execution_history"]] == [
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
            Path("pipeline_configs/v1_3.ppln"),
            evaluation_profile_path=PROFILE_PATH,
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            runtime="serial",
            output_root=tmp_path,
        )

    invocation_events = list(tmp_path.glob("**/invocations/*.json"))
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
        Path("pipeline_configs/v1_3.ppln"),
        evaluation_profile_path=PROFILE_PATH,
        benchmark_key=benchmark.benchmark_key,
        repository=_Repository(benchmark),
        runtime="serial",
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


def test_dry_run_resolves_manifest_without_pipeline_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    benchmark = _benchmark()
    monkeypatch.setattr(
        eval_orchestration,
        "run_pipeline",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("pipeline executed")
        ),
    )

    path = eval_orchestration.run_eval(
        Path("pipeline_configs/v1_3.ppln"),
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


def test_run_identity_excludes_progress_interval_but_includes_worker_limit(
    tmp_path: Path,
) -> None:
    benchmark = _benchmark()

    def resolve(*, progress: float, workers: int) -> Path:
        return eval_orchestration.run_eval(
            Path("pipeline_configs/v1_3.ppln"),
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

    assert first == same
    assert first.parent.name != different.parent.name


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
        grader_registry=eval_orchestration.build_project_grader_registry(),
        duration_seconds=1.0,
        stage_durations_seconds={},
        attempt_metadata={"run_index": 1},
    )
    tracker.completed(item, scored)

    assert any("SUCCESS" in message for message in messages)
