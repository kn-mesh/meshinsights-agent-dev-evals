"""Tests for v1_3 runtime configuration overrides."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import yaml
from mi.core.pipeline_builder import PipelineBuilder

from src.pipelines.pipeline_run_from_yaml import (
    _apply_runtime_overrides,
    _load_pipeline_config,
)


def test_runtime_overrides_are_ephemeral_and_ai_scoped() -> None:
    """Inject example and model settings without mutating source configuration."""
    source = _load_pipeline_config(Path("pipeline_configs/v1_3.ppln"))

    runtime = _apply_runtime_overrides(
        source,
        unit="trap-7",
        sensor_id=7,
        decision_timestamp=datetime(2026, 3, 17, 12, 0),
        ai_model="azure:gpt-5.4-mini",
        ai_reasoning_effort="high",
        retrieval_snapshot_mode="strict",
        retrieval_snapshot_dir="data/snapshots",
    )

    assert "metadata" not in source
    assert "metadata_class" in source
    assert runtime["metadata"]["unit"] == "trap-7"
    agent = runtime["process"]["processors"][1]
    assert agent["model"] == "azure:gpt-5.4-mini"
    assert agent["reasoning_effort"] == "high"
    assert "input_tokens_limit" not in agent
    retriever = runtime["retrieve"]["retrievers"][0]
    assert retriever["snapshot_mode"] == "strict"


def test_runtime_config_builds_the_registered_v1_3_pipeline() -> None:
    """Resolve every YAML component through the project registry."""
    source = _load_pipeline_config(Path("pipeline_configs/v1_3.ppln"))
    runtime = _apply_runtime_overrides(
        source,
        unit="trap-7",
        sensor_id=7,
        decision_timestamp=datetime(2026, 3, 17, 12, 0),
        ai_model=None,
        ai_reasoning_effort=None,
        retrieval_snapshot_mode="strict",
        retrieval_snapshot_dir="data/snapshots",
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
