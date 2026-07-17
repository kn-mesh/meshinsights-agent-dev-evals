"""Integration-contract tests for benchmark-driven v1_3 eval orchestration."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt

from model_catalog import ModelCatalog, ModelDefinition
from src.benchmarks.models import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
    SourceArtifact,
)
from src.evals import eval_orchestration


def _benchmark() -> BenchmarkVersion:
    artifacts = (
        SourceArtifact(
            artifact_kind="telemetry",
            object_key="snapshot/telemetry.parquet",
            content_type="application/parquet",
            byte_size=1,
            content_sha256="a" * 64,
        ),
        SourceArtifact(
            artifact_kind="alarms",
            object_key="snapshot/alarms.jsonl",
            content_type="application/x-ndjson",
            byte_size=1,
            content_sha256="b" * 64,
        ),
    )
    example = BenchmarkExample(
        example_id="250000116|2026-03-04T08:01:36",
        unit_id="250000116",
        decision_timestamp=datetime(2026, 3, 4, 8, 1, 36, tzinfo=timezone.utc),
        approved_labels={
            "classification": "Failure",
            "root_cause": "Closed Failure",
        },
        example_metadata={"sensor_id": "250000116"},
        source_snapshot_id="snapshot-id",
        raw_snapshot_content_sha256="c" * 64,
        raw_source_kind="mongo",
        raw_captured_at=datetime(2026, 3, 5, tzinfo=timezone.utc),
        raw_window_start=datetime(2025, 3, 4, tzinfo=timezone.utc),
        raw_window_end=datetime(2026, 3, 4, 8, 1, 36, tzinfo=timezone.utc),
        raw_artifacts=artifacts,
    )
    return BenchmarkVersion(
        project_key="spirax-pulse",
        benchmark_key="steam-trap-regression",
        benchmark_name="Steam Trap Regression",
        benchmark_version_id="benchmark-version-id",
        version_number=4,
        published_at=datetime(2026, 3, 6, tzinfo=timezone.utc),
        source_state_sha256="d" * 64,
        examples=(example,),
    )


def _benchmark_with_all_scopes() -> BenchmarkVersion:
    benchmark = _benchmark()
    base = benchmark.examples[0]
    examples = tuple(
        base.model_copy(
            update={
                "example_id": f"example-{index}",
                "unit_id": f"unit-{index}",
                "approved_labels": labels,
            }
        )
        for index, labels in enumerate(
            (
                {"classification": "Failure", "root_cause": "Closed Failure"},
                {"classification": "Failure", "root_cause": "Open Failure"},
                {"classification": "Failure", "root_cause": "Unknown"},
                {"classification": "Healthy", "root_cause": "N/A"},
            ),
            start=1,
        )
    )
    return benchmark.model_copy(update={"examples": examples})


def _empty_scope_args() -> argparse.Namespace:
    return argparse.Namespace(
        example_ids=None,
        unit_ids=None,
        classifications=None,
        root_causes=None,
    )


class _Repository:
    def __init__(self, benchmark: BenchmarkVersion) -> None:
        self.benchmark = benchmark

    def load_published_version(
        self, *, benchmark_key: str, version_number: int | None = None
    ) -> BenchmarkVersion:
        assert benchmark_key == self.benchmark.benchmark_key
        assert version_number in {None, self.benchmark.version_number}
        return self.benchmark

    def list_published_versions(self) -> tuple[PublishedBenchmarkVersionSummary, ...]:
        return ()


def _successful_receipt() -> PipelineReceipt:
    receipt = PipelineReceipt(
        pipeline_id="eval-test",
        act_receipt=StageReceipt("act", True, 0.0),
    )
    assert receipt.act_receipt is not None
    receipt.act_receipt.metadata.update(
        {
            "classification": {
                "value": "Failure",
                "confidence": "High",
                "explanation": "The inlet temperature fell first.",
            },
            "root_cause": {
                "value": "Closed Failure",
                "confidence": "High",
                "explanation": "The temperature delta collapsed.",
            },
        }
    )
    return receipt


def test_run_eval_scores_published_examples_and_writes_benchmark_identity(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Evaluate repeated runs against approved labels from Azure PostgreSQL."""
    benchmark = _benchmark()
    calls: list[str] = []

    def fake_run_pipeline(
        yaml_path: str | Path,
        *,
        benchmark: BenchmarkVersion,
        example: BenchmarkExample,
        **kwargs: object,
    ) -> PipelineReceipt:
        _ = yaml_path, benchmark, kwargs
        calls.append(example.example_id)
        return _successful_receipt()

    monkeypatch.setattr(eval_orchestration, "run_pipeline", fake_run_pipeline)

    output_path = eval_orchestration.run_eval(
        Path("pipeline_configs/v1_3.ppln"),
        benchmark_key=benchmark.benchmark_key,
        benchmark_version=benchmark.version_number,
        repository=_Repository(benchmark),
        output_root=tmp_path / "eval_results",
        runs_per_example=2,
        runtime="serial",
        max_workers=1,
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert calls == [benchmark.examples[0].example_id] * 2
    assert list(payload) == [
        "summary",
        "run_config",
        "selected_example_ids",
        "results",
    ]
    assert payload["run_config"]["benchmark_source"] == "azure_postgres"
    assert payload["run_config"]["evidence_source"] == "azure_blob"
    assert payload["run_config"]["benchmark_version_number"] == 4
    assert payload["run_config"]["ai_model"] == "azure:gpt-5.6-luna"
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["accuracy_by_label"]["root_cause"] == 1.0
    assert payload["results"][0]["source_snapshot_id"] == "snapshot-id"
    assert (
        payload["results"][0]["runs"][0]["ai_output"]["classification"]["confidence"]
        == "High"
    )


def test_eval_rejects_example_ids_outside_published_version(tmp_path: Path) -> None:
    benchmark = _benchmark()

    try:
        eval_orchestration.run_eval(
            Path("pipeline_configs/v1_3.ppln"),
            benchmark_key=benchmark.benchmark_key,
            repository=_Repository(benchmark),
            output_root=tmp_path,
            example_ids=["missing-example"],
            runtime="serial",
            max_workers=1,
        )
    except ValueError as error:
        assert "absent from the benchmark" in str(error)
    else:
        raise AssertionError("Expected missing benchmark example to fail.")


def test_terminal_chooser_selects_benchmark_then_specific_version(
    monkeypatch: Any,
) -> None:
    """Select from catalog metadata without loading all frozen examples first."""
    published_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    versions = (
        PublishedBenchmarkVersionSummary(
            project_key="spirax-pulse",
            benchmark_key="steam-trap-regression",
            benchmark_name="Steam Trap Regression",
            benchmark_version_id="steam-v2",
            version_number=2,
            published_at=published_at,
            example_count=12,
        ),
        PublishedBenchmarkVersionSummary(
            project_key="spirax-pulse",
            benchmark_key="steam-trap-regression",
            benchmark_name="Steam Trap Regression",
            benchmark_version_id="steam-v1",
            version_number=1,
            published_at=published_at,
            example_count=8,
        ),
        PublishedBenchmarkVersionSummary(
            project_key="spirax-pulse",
            benchmark_key="other-benchmark",
            benchmark_name="Other Benchmark",
            benchmark_version_id="other-v1",
            version_number=1,
            published_at=published_at,
            example_count=3,
        ),
    )
    prompts: list[tuple[str, list[str]]] = []

    def choose(prompt: str, options: list[str]) -> str:
        prompts.append((prompt, options))
        if len(prompts) == 1:
            return next(
                option for option in options if "steam-trap-regression" in option
            )
        return next(option for option in options if option.startswith("v1 "))

    monkeypatch.setattr(eval_orchestration, "prompt_select_option", choose)

    selected = eval_orchestration._choose_published_benchmark_version(versions)

    assert selected.benchmark_version_id == "steam-v1"
    assert len(prompts) == 2
    assert prompts[1][1][0].startswith("v2 ")


def test_terminal_chooser_rejects_empty_azure_catalog() -> None:
    try:
        eval_orchestration._choose_published_benchmark_version(())
    except ValueError as error:
        assert "No published benchmark versions" in str(error)
    else:
        raise AssertionError("Expected an empty Azure catalog to fail.")


def test_terminal_model_chooser_uses_root_catalog(monkeypatch: Any) -> None:
    catalog = ModelCatalog(
        default_model="azure:gpt-5.6-luna",
        models=(
            ModelDefinition("azure:gpt-5.6-luna", "openai_responses"),
            ModelDefinition("azure:gpt-5.6-sol", "openai_responses"),
        ),
    )
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_select_option",
        lambda prompt, options: options[1],
    )

    selected = eval_orchestration._resolve_cli_model(
        argparse.Namespace(ai_model=None),
        catalog=catalog,
        parser=eval_orchestration._argument_parser(),
    )

    assert selected == "azure:gpt-5.6-sol"


def test_noninteractive_model_selection_uses_catalog_default(monkeypatch: Any) -> None:
    catalog = ModelCatalog(
        default_model="azure:gpt-5.6-luna",
        models=(
            ModelDefinition("azure:gpt-5.6-luna", "openai_responses"),
            ModelDefinition("azure:gpt-5.6-sol", "openai_responses"),
        ),
    )
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: False)

    selected = eval_orchestration._resolve_cli_model(
        argparse.Namespace(ai_model=None),
        catalog=catalog,
        parser=eval_orchestration._argument_parser(),
    )

    assert selected == "azure:gpt-5.6-luna"


def test_terminal_prompts_for_reasoning_effort(monkeypatch: Any) -> None:
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_select_option",
        lambda prompt, options: options[2],
    )

    selected = eval_orchestration._resolve_cli_reasoning_effort(
        argparse.Namespace(ai_reasoning_effort=None)
    )

    assert selected == "medium"


def test_terminal_prompts_for_runs_per_example(monkeypatch: Any) -> None:
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_positive_int",
        lambda prompt, default: 3,
    )

    selected = eval_orchestration._resolve_cli_runs_per_example(
        argparse.Namespace(runs_per_example=None),
        parser=eval_orchestration._argument_parser(),
    )

    assert selected == 3


def test_noninteractive_eval_settings_keep_defaults(monkeypatch: Any) -> None:
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: False)
    parser = eval_orchestration._argument_parser()

    reasoning_effort = eval_orchestration._resolve_cli_reasoning_effort(
        argparse.Namespace(ai_reasoning_effort=None)
    )
    runs_per_example = eval_orchestration._resolve_cli_runs_per_example(
        argparse.Namespace(runs_per_example=None), parser=parser
    )

    assert reasoning_effort is None
    assert runs_per_example == 1


def test_explicit_eval_settings_skip_terminal_prompts(monkeypatch: Any) -> None:
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_select_option",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompted")),
    )
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_positive_int",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompted")),
    )
    parser = eval_orchestration._argument_parser()

    reasoning_effort = eval_orchestration._resolve_cli_reasoning_effort(
        argparse.Namespace(ai_reasoning_effort="high")
    )
    runs_per_example = eval_orchestration._resolve_cli_runs_per_example(
        argparse.Namespace(runs_per_example=4), parser=parser
    )

    assert reasoning_effort == "high"
    assert runs_per_example == 4


def test_terminal_prompts_for_example_scope_categories(monkeypatch: Any) -> None:
    benchmark = _benchmark_with_all_scopes()
    parser = eval_orchestration._argument_parser()
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    expected_by_selection = {
        "All examples": (None, None, None, None),
        "Closed failures": (None, None, None, ["Closed Failure"]),
        "Open failures": (None, None, None, ["Open Failure"]),
        "Unknown failures": (None, None, None, ["Unknown"]),
        "Healthy": (None, None, ["Healthy"], None),
    }

    for selection, expected in expected_by_selection.items():
        monkeypatch.setattr(
            eval_orchestration,
            "prompt_select_option",
            lambda prompt, options, selected=selection: selected,
        )
        resolved = eval_orchestration._resolve_cli_example_scope(
            _empty_scope_args(), benchmark=benchmark, parser=parser
        )
        assert resolved == expected


def test_terminal_random_scope_selects_one_benchmark_example(
    monkeypatch: Any, capsys: Any
) -> None:
    benchmark = _benchmark_with_all_scopes()
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_select_option",
        lambda prompt, options: "Single example (random)",
    )
    monkeypatch.setattr(
        eval_orchestration.random, "choice", lambda examples: examples[1]
    )

    resolved = eval_orchestration._resolve_cli_example_scope(
        _empty_scope_args(),
        benchmark=benchmark,
        parser=eval_orchestration._argument_parser(),
    )

    assert resolved == (["example-2"], None, None, None)
    assert (
        "Randomly selected example: example-2 (unit unit-2)." in capsys.readouterr().out
    )


def test_explicit_scope_filters_skip_terminal_prompt(monkeypatch: Any) -> None:
    monkeypatch.setattr(eval_orchestration.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(
        eval_orchestration,
        "prompt_select_option",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompted")),
    )
    args = argparse.Namespace(
        example_ids=None,
        unit_ids=["unit-7"],
        classifications=None,
        root_causes=None,
    )

    resolved = eval_orchestration._resolve_cli_example_scope(
        args,
        benchmark=_benchmark(),
        parser=eval_orchestration._argument_parser(),
    )

    assert resolved == (None, ["unit-7"], None, None)


def test_root_cause_scope_filters_benchmark_examples() -> None:
    benchmark = _benchmark_with_all_scopes()

    selected = eval_orchestration._select_examples(
        benchmark.examples,
        example_ids=None,
        unit_ids=None,
        classifications=None,
        root_causes=["Open Failure"],
    )

    assert [example.example_id for example in selected] == ["example-2"]


def test_cli_logging_suppresses_azure_http_diagnostics() -> None:
    azure_http_logger = logging.getLogger(eval_orchestration._AZURE_HTTP_LOGGER)
    previous_level = azure_http_logger.level
    try:
        eval_orchestration._configure_cli_logging()
        assert azure_http_logger.level == logging.WARNING
    finally:
        azure_http_logger.setLevel(previous_level)


def test_cli_outcome_reports_success(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps({"summary": {"total_runs": 2, "successful_runs": 2}}),
        encoding="utf-8",
    )

    eval_orchestration._print_cli_outcome(path)

    output = capsys.readouterr().out
    assert "SUCCESS: 2/2 succeeded; 0 failed." in output
    assert f"Results written to: {path}" in output


def test_cli_outcome_reports_failed_runs(tmp_path: Path, capsys: Any) -> None:
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps({"summary": {"total_runs": 3, "successful_runs": 1}}),
        encoding="utf-8",
    )

    eval_orchestration._print_cli_outcome(path)

    output = capsys.readouterr().out
    assert "FAILED: 1/3 succeeded; 2 failed." in output
    assert f"Results written to: {path}" in output


def test_progress_tracker_reports_success_failure_and_slowest_running(
    monkeypatch: Any,
) -> None:
    messages: list[str] = []

    def capture(message: str, *args: object) -> None:
        messages.append(message % args if args else message)

    monkeypatch.setattr(eval_orchestration.logger, "info", capture)
    monkeypatch.setattr(eval_orchestration.logger, "error", capture)
    tracker = eval_orchestration._EvalProgressTracker(
        total_runs=3,
        heartbeat_seconds=30.0,
    )
    first = eval_orchestration.RepeatedEvalWorkItem(
        unit_id="example-a", payload=_benchmark().examples[0], run_index=1
    )
    second = eval_orchestration.RepeatedEvalWorkItem(
        unit_id="example-b", payload=_benchmark().examples[0], run_index=1
    )
    tracker.started(first)
    tracker.started(second)
    with tracker._lock:
        tracker._running[(first.unit_id, first.run_index)] -= 45.0
        tracker._running[(second.unit_id, second.run_index)] -= 10.0

    heartbeat = tracker._heartbeat_message()
    tracker.completed(
        second,
        eval_orchestration.EvalAttempt(actual_values={}, evals={}, success=True),
    )
    tracker.completed(
        first,
        eval_orchestration.EvalAttempt(
            actual_values={},
            evals={},
            success=False,
            error="model request failed",
        ),
    )

    assert heartbeat is not None
    assert "0/3 succeeded, 0 failed, 2 running, 1 queued" in heartbeat
    assert "slowest: example-a run 1 (45s)" in heartbeat
    assert "SUCCESS: 1/3 | example-b run 1" in messages
    assert "FAILURE: example-a run 1 | model request failed" in messages
