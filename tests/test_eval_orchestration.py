"""Integration-contract tests for benchmark-driven v1_3 eval orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt

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


class _Repository:
    def __init__(self, benchmark: BenchmarkVersion) -> None:
        self.benchmark = benchmark

    def load_published_version(
        self, *, benchmark_key: str, version_number: int | None = None
    ) -> BenchmarkVersion:
        assert benchmark_key == self.benchmark.benchmark_key
        assert version_number in {None, self.benchmark.version_number}
        return self.benchmark


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
    assert payload["summary"]["total_runs"] == 2
    assert payload["summary"]["accuracy_by_label"]["root_cause"] == 1.0
    assert payload["results"][0]["source_snapshot_id"] == "snapshot-id"
    assert payload["results"][0]["runs"][0]["ai_output"]["classification"][
        "confidence"
    ] == "High"


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
            return next(option for option in options if "steam-trap-regression" in option)
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
