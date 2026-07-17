"""Tests for benchmark-backed v1_3 runtime configuration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

import yaml
from mi.core.pipeline_builder import PipelineBuilder

from src.benchmarks.models import BenchmarkExample, BenchmarkVersion, SourceArtifact
from src.pipelines.pipeline_run_from_yaml import (
    _apply_runtime_overrides,
    _load_pipeline_config,
)


def _benchmark() -> tuple[BenchmarkVersion, BenchmarkExample]:
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
        example_id="7|2026-03-17T12:00:00",
        unit_id="7",
        decision_timestamp=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        approved_labels={"classification": "Failure"},
        example_metadata={"sensor_id": "7"},
        source_snapshot_id="snapshot-id",
        raw_snapshot_content_sha256="c" * 64,
        raw_source_kind="mongo",
        raw_captured_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        raw_window_start=datetime(2025, 3, 17, tzinfo=timezone.utc),
        raw_window_end=datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc),
        raw_artifacts=artifacts,
    )
    benchmark = BenchmarkVersion(
        project_key="spirax-pulse",
        benchmark_key="steam-trap-regression",
        benchmark_name="Steam Trap Regression",
        benchmark_version_id="version-id",
        version_number=3,
        published_at=datetime(2026, 3, 19, tzinfo=timezone.utc),
        examples=(example,),
    )
    return benchmark, example


def test_runtime_overrides_are_ephemeral_and_benchmark_scoped() -> None:
    source = _load_pipeline_config(Path("pipeline_configs/v1_3.ppln"))
    benchmark, example = _benchmark()

    runtime = _apply_runtime_overrides(
        source,
        benchmark=benchmark,
        example=example,
        ai_model="azure:gpt-5.4-mini",
        ai_reasoning_effort="high",
    )

    assert "metadata" not in source
    assert runtime["metadata"]["example_id"] == example.example_id
    assert runtime["metadata"]["source_snapshot_id"] == "snapshot-id"
    assert runtime["metadata"]["benchmark_version_number"] == 3
    agent = runtime["process"]["processors"][1]
    assert agent["model"] == "azure:gpt-5.4-mini"
    assert agent["reasoning_effort"] == "high"
    assert runtime["retrieve"]["retrievers"] == [
        {"retriever": "AzureBlobBenchmarkEvidenceRetriever"}
    ]


def test_runtime_config_builds_the_registered_v1_3_pipeline() -> None:
    source = _load_pipeline_config(Path("pipeline_configs/v1_3.ppln"))
    benchmark, example = _benchmark()
    runtime = _apply_runtime_overrides(
        source,
        benchmark=benchmark,
        example=example,
        ai_model=None,
        ai_reasoning_effort=None,
    )

    runtime_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ppln",
            dir="pipeline_configs",
            encoding="utf-8",
            delete=False,
        ) as runtime_file:
            yaml.safe_dump(runtime, runtime_file, sort_keys=False)
            runtime_path = Path(runtime_file.name)
        pipeline = PipelineBuilder.from_yaml(runtime_path).build()
    finally:
        if runtime_path is not None:
            runtime_path.unlink(missing_ok=True)

    assert pipeline.config.name == "pulse_alarm_failure_analysis_v1_3"
    assert pipeline.config.version == "1.3.0"
