"""Run one published benchmark example through the Pulse agent pipeline."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any

import yaml
from mi.core.pipeline_builder import PipelineBuilder
from mi.core.pipeline_receipt import PipelineReceipt

from model_catalog import resolve_model, resolve_model_definition
from src.benchmarks import (
    AzurePostgresBenchmarkRepository,
    BenchmarkExample,
    BenchmarkVersion,
)


def run_pipeline(
    yaml_path: str | Path,
    *,
    benchmark: BenchmarkVersion,
    example: BenchmarkExample,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
    pipeline_log_level: str | None = None,
) -> PipelineReceipt:
    """Run the exact raw inputs frozen for one published benchmark example."""
    ai_model = resolve_model(ai_model)
    canonical_example = benchmark.get_example(example.example_id)
    if canonical_example != example:
        raise ValueError(
            "The example content does not match the supplied benchmark version."
        )
    source_path = Path(yaml_path).resolve()
    config = _load_pipeline_config(source_path)
    runtime_config = _apply_runtime_overrides(
        config,
        benchmark=benchmark,
        example=example,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        pipeline_log_level=pipeline_log_level,
    )
    return _execute_runtime_config(source_path, runtime_config)


def load_benchmark_example(
    *,
    benchmark_key: str,
    example_id: str,
    benchmark_version: int | None = None,
    project_key: str | None = None,
) -> tuple[BenchmarkVersion, BenchmarkExample]:
    """Load one exact example from Azure PostgreSQL for pipeline execution."""
    benchmark = AzurePostgresBenchmarkRepository(
        project_key=project_key
    ).load_published_version(
        benchmark_key=benchmark_key,
        version_number=benchmark_version,
    )
    return benchmark, benchmark.get_example(example_id)


def _load_pipeline_config(path: Path) -> dict[str, Any]:
    """Load and validate a pipeline YAML mapping."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    return payload


def _apply_runtime_overrides(
    pipeline_config: dict[str, Any],
    *,
    benchmark: BenchmarkVersion,
    example: BenchmarkExample,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
    pipeline_log_level: str | None = None,
) -> dict[str, Any]:
    """Build an ephemeral benchmark runtime config without mutating source YAML."""
    runtime = copy.deepcopy(pipeline_config)
    if pipeline_log_level is not None:
        logger_config = runtime.setdefault("logger", {})
        if not isinstance(logger_config, dict):
            raise ValueError("Pipeline logger configuration must be a mapping.")
        logger_config["level"] = pipeline_log_level
    metadata_class = str(
        runtime.pop("metadata_class", "BenchmarkExamplePipelineMetadata")
    )
    runtime["metadata"] = {
        "metadata": metadata_class,
        "unit": example.unit_id,
        "example_id": example.example_id,
        "sensor_id": example.sensor_id,
        "decision_timestamp": example.decision_timestamp.isoformat(),
        "benchmark_key": benchmark.benchmark_key,
        "benchmark_version_id": benchmark.benchmark_version_id,
        "benchmark_version_number": benchmark.version_number,
        "source_snapshot_id": example.source_snapshot_id,
        "source_snapshot_content_sha256": example.raw_snapshot_content_sha256,
        "source_kind": example.raw_source_kind,
        "raw_captured_at": example.raw_captured_at.isoformat(),
        "raw_window_start": (
            example.raw_window_start.isoformat()
            if example.raw_window_start is not None
            else None
        ),
        "raw_window_end": (
            example.raw_window_end.isoformat()
            if example.raw_window_end is not None
            else None
        ),
        "raw_known_gaps": list(example.raw_known_gaps),
        "raw_artifacts": [
            artifact.model_dump(mode="json") for artifact in example.raw_artifacts
        ],
        "example_metadata": example.example_metadata,
    }

    normalized_model = _normalize_override(ai_model)
    normalized_effort = _normalize_override(ai_reasoning_effort)
    model_definition = (
        resolve_model_definition(normalized_model)
        if normalized_model is not None
        else None
    )
    for processor in runtime.get("process", {}).get("processors", []):
        if not isinstance(processor, dict) or not _is_ai_processor(processor):
            continue
        if normalized_model is not None:
            processor["model"] = normalized_model
            backend_options = processor.setdefault("backend_options", {})
            if not isinstance(backend_options, dict):
                raise ValueError("AI processor backend_options must be a mapping.")
            assert model_definition is not None
            backend_options["model_api"] = model_definition.api
        if normalized_effort is not None:
            processor["reasoning_effort"] = normalized_effort
        elif normalized_model is not None:
            processor.pop("reasoning_effort", None)
    return runtime


def _execute_runtime_config(
    source_path: Path, runtime_config: dict[str, Any]
) -> PipelineReceipt:
    """Build and execute an ephemeral YAML configuration."""
    runtime_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ppln",
            prefix=f".{source_path.stem}.runtime.",
            dir=source_path.parent,
            encoding="utf-8",
            delete=False,
        ) as runtime_file:
            yaml.safe_dump(runtime_config, runtime_file, sort_keys=False)
            runtime_path = Path(runtime_file.name)
        return PipelineBuilder.from_yaml(runtime_path).build().run()
    finally:
        if runtime_path is not None:
            runtime_path.unlink(missing_ok=True)


def _normalize_override(value: str | None) -> str | None:
    """Normalize a nullable CLI override."""
    if value is None:
        return None
    normalized = value.strip()
    return None if not normalized or normalized.lower() == "default" else normalized


def _is_ai_processor(processor: dict[str, Any]) -> bool:
    """Return whether a processor config represents an AI execution stage."""
    name = str(processor.get("processor", ""))
    return "Agent" in name or "AI" in name or "model" in processor


def _receipt_summary(receipt: PipelineReceipt) -> dict[str, Any]:
    """Create a compact JSON-safe CLI result."""
    return {
        "success": receipt.success,
        "pipeline_name": receipt.get_config("name"),
        "pipeline_version": receipt.get_config("version"),
        "retrieve_metadata": (
            receipt.retrieve_receipt.metadata if receipt.retrieve_receipt else {}
        ),
        "act_metadata": receipt.act_receipt.metadata if receipt.act_receipt else {},
        "process_error": (
            receipt.process_receipt.error if receipt.process_receipt else None
        ),
        "act_error": receipt.act_receipt.error if receipt.act_receipt else None,
    }


def _argument_parser() -> argparse.ArgumentParser:
    """Build the benchmark-aware command-line interface."""
    parser = argparse.ArgumentParser(
        description=(
            "Run a published benchmark example using its immutable Azure Blob "
            "source evidence."
        )
    )
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument("--project-key")
    parser.add_argument("--benchmark-key", required=True)
    parser.add_argument("--benchmark-version", type=int)
    parser.add_argument("--example-id", required=True)
    parser.add_argument(
        "--ai-model",
        help="Model from the project-owned models.yaml catalog.",
    )
    parser.add_argument("--ai-reasoning-effort")
    return parser


def main() -> None:
    """Load and run one published benchmark example."""
    args = _argument_parser().parse_args()
    benchmark, example = load_benchmark_example(
        project_key=args.project_key,
        benchmark_key=args.benchmark_key,
        benchmark_version=args.benchmark_version,
        example_id=args.example_id,
    )
    receipt = run_pipeline(
        args.yaml_path,
        benchmark=benchmark,
        example=example,
        ai_model=args.ai_model,
        ai_reasoning_effort=args.ai_reasoning_effort,
    )
    print(json.dumps(_receipt_summary(receipt), indent=2))


if __name__ == "__main__":
    main()
