"""Evaluate v1_3 against a published benchmark and frozen Azure Blob evidence."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from mi.core.utils.environment import bootstrap_environment

from src.benchmarks import (
    AzurePostgresBenchmarkRepository,
    AzureContainerAppBenchmarkRepository,
    BenchmarkExample,
    BenchmarkRepository,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
)
from src.experimental_core.evals import (
    ErrorActionType,
    EvalAttempt,
    EvalResult,
    EvalSummaryBuilder,
    ReceiptFieldSpec,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalWorkItem,
    RuntimeType,
    build_results_dir_for_pipeline,
    extract_receipt_fields,
    normalize_ai_reasoning_effort,
    normalize_filename_token,
)
from src.experimental_core.evals.cli.prompts import prompt_select_option
from src.pipelines.pipeline_run_from_yaml import run_pipeline
from src.storage.hosted_azure_config import load_hosted_blob_configuration

logger = logging.getLogger(__name__)

BASE_RESULTS_DIR = Path("src/evals/eval_results")
DEFAULT_AZURE_RESOURCE_GROUP = "rg-misprx-dv"
DEFAULT_AZURE_CONTAINER_APP = "label-benchmark"
_NO_EVAL = EvalResult(None, None, None)
_RECEIPT_FIELD_SPECS: tuple[ReceiptFieldSpec, ...] = (
    ReceiptFieldSpec(
        output_name="classification",
        metadata_key="classification",
        value_path=("value",),
        artifact_group="ai_output",
    ),
    ReceiptFieldSpec(
        output_name="root_cause",
        metadata_key="root_cause",
        value_path=("value",),
        artifact_group="ai_output",
    ),
)


@dataclass(frozen=True, slots=True)
class _PipelineArgs:
    yaml_path: Path
    benchmark: BenchmarkVersion
    ai_model: str | None
    ai_reasoning_effort: str | None


@dataclass(frozen=True, slots=True)
class _ExampleEvalResult:
    example: BenchmarkExample
    attempts: tuple[EvalAttempt, ...]
    classification_accuracy: float | None


def run_eval(
    yaml_path: Path,
    *,
    benchmark_key: str,
    benchmark_version: int | None = None,
    project_key: str | None = None,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
    example_ids: list[str] | None = None,
    unit_ids: list[str] | None = None,
    classifications: list[str] | None = None,
    runs_per_example: int = 1,
    runtime: RuntimeType = "threaded",
    max_workers: int = 4,
    error_action: ErrorActionType = "continue",
    repository: BenchmarkRepository | None = None,
    output_root: Path | None = None,
) -> Path:
    """Run repeated evals against one immutable published benchmark version."""
    if runs_per_example < 1:
        raise ValueError("runs_per_example must be at least 1.")
    ai_reasoning_effort = normalize_ai_reasoning_effort(ai_reasoning_effort)
    benchmark_repository = repository or AzurePostgresBenchmarkRepository(
        project_key=project_key
    )
    benchmark = benchmark_repository.load_published_version(
        benchmark_key=benchmark_key,
        version_number=benchmark_version,
    )
    examples = _select_examples(
        benchmark.examples,
        example_ids=example_ids,
        unit_ids=unit_ids,
        classifications=classifications,
    )
    if not examples:
        raise ValueError("No benchmark examples match the provided filters.")

    pipeline_args = _PipelineArgs(
        yaml_path=yaml_path,
        benchmark=benchmark,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
    )
    results = _run_all_examples(
        examples,
        pipeline_args=pipeline_args,
        runs_per_example=runs_per_example,
        runtime=runtime,
        max_workers=max_workers,
        error_action=error_action,
    )
    completed_at = datetime.now(timezone.utc)
    scope = _scope_token(
        example_ids=example_ids,
        unit_ids=unit_ids,
        classifications=classifications,
    )
    payload = {
        "summary": _build_summary(results, runs_per_example=runs_per_example),
        "run_config": {
            "yaml_path": str(yaml_path),
            "project_key": benchmark.project_key,
            "benchmark_key": benchmark.benchmark_key,
            "benchmark_version_id": benchmark.benchmark_version_id,
            "benchmark_version_number": benchmark.version_number,
            "benchmark_source_state_sha256": benchmark.source_state_sha256,
            "benchmark_source": "azure_postgres",
            "evidence_source": "azure_blob",
            "scope": scope,
            "runs_per_example": runs_per_example,
            "runtime": runtime,
            "max_workers": max_workers,
            "error_action": error_action,
            "ai_provider": _extract_provider(ai_model),
            "ai_model": ai_model,
            "ai_reasoning_effort": ai_reasoning_effort,
            "completed_at_utc": completed_at.isoformat(timespec="seconds"),
        },
        "selected_example_ids": [example.example_id for example in examples],
        "results": _build_results(results),
    }
    filename = _results_filename(
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        scope=scope,
        runs_per_example=runs_per_example,
        timestamp=completed_at.strftime("%y-%m-%d-%H-%M"),
    )
    base = output_root or BASE_RESULTS_DIR
    output_dir = build_results_dir_for_pipeline(
        base_results_dir=base,
        yaml_path=yaml_path,
    )
    output_path = (
        output_dir
        / normalize_filename_token(benchmark.benchmark_key)
        / f"v{benchmark.version_number}"
        / scope
        / filename
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Eval results written to %s", output_path)
    return output_path


def _select_examples(
    examples: tuple[BenchmarkExample, ...],
    *,
    example_ids: list[str] | None,
    unit_ids: list[str] | None,
    classifications: list[str] | None,
) -> list[BenchmarkExample]:
    selected = list(examples)
    if example_ids:
        requested = {value.strip() for value in example_ids}
        available = {example.example_id for example in selected}
        missing = requested - available
        if missing:
            raise ValueError(
                "Requested example IDs are absent from the benchmark: "
                + ", ".join(sorted(missing))
            )
        selected = [example for example in selected if example.example_id in requested]
    if unit_ids:
        requested_units = {value.strip() for value in unit_ids}
        selected = [
            example for example in selected if example.unit_id in requested_units
        ]
    if classifications:
        requested_labels = {value.strip() for value in classifications}
        selected = [
            example
            for example in selected
            if example.approved_labels.get("classification") in requested_labels
        ]
    return selected


def _run_all_examples(
    examples: list[BenchmarkExample],
    *,
    pipeline_args: _PipelineArgs,
    runs_per_example: int,
    runtime: RuntimeType,
    max_workers: int,
    error_action: ErrorActionType,
) -> list[_ExampleEvalResult]:
    executor = RepeatedEvalExecutor[BenchmarkExample, EvalAttempt](
        RepeatedEvalExecutorConfig(
            runtime=runtime,
            max_workers=max_workers,
            error_action=error_action,
        ),
        logger=logger,
    )
    records = executor.run(
        examples,
        runs_per_unit=runs_per_example,
        get_unit_id=lambda example: example.example_id,
        run_once=partial(_run_work_item, pipeline_args=pipeline_args),
        build_failure_result=_build_failure_attempt,
        has_error=lambda attempt: attempt.has_error,
    )
    attempts_by_example: dict[str, list[EvalAttempt]] = {}
    for record in records:
        attempts_by_example.setdefault(record.work_item.unit_id, []).append(
            record.result
        )
    results: list[_ExampleEvalResult] = []
    for example in examples:
        attempts = attempts_by_example.get(example.example_id, [])
        flags = [
            attempt.evals.get("classification", _NO_EVAL).is_correct
            for attempt in attempts
        ]
        evaluated = [flag for flag in flags if flag is not None]
        results.append(
            _ExampleEvalResult(
                example=example,
                attempts=tuple(attempts),
                classification_accuracy=EvalSummaryBuilder.safe_accuracy(
                    correct=sum(flag is True for flag in evaluated),
                    total=len(evaluated),
                ),
            )
        )
    return results


def _run_work_item(
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
    *,
    pipeline_args: _PipelineArgs,
) -> EvalAttempt:
    receipt = run_pipeline(
        pipeline_args.yaml_path,
        benchmark=pipeline_args.benchmark,
        example=work_item.payload,
        ai_model=pipeline_args.ai_model,
        ai_reasoning_effort=pipeline_args.ai_reasoning_effort,
    )
    extracted = extract_receipt_fields(
        receipt,
        field_specs=_RECEIPT_FIELD_SPECS,
        stage_name="act",
    )
    actual_values = {
        name: extracted.actual_values.get(name)
        for name in work_item.payload.approved_labels
    }
    evals = {
        name: _evaluate_label(expected, actual_values.get(name))
        for name, expected in work_item.payload.approved_labels.items()
    }
    return EvalAttempt(
        actual_values=actual_values,
        evals=evals,
        success=receipt.success,
        error=None if receipt.success else _receipt_error(receipt),
        artifacts=extracted.artifacts,
        metadata={
            "source_snapshot_id": work_item.payload.source_snapshot_id,
            "run_index": work_item.run_index,
        },
    )


def _evaluate_label(expected: str, actual: str | None) -> EvalResult:
    return EvalResult(
        expected=expected,
        actual=actual,
        is_correct=None if actual is None else expected == actual,
    )


def _build_failure_attempt(
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
    message: str,
    exception: Exception | None,
) -> EvalAttempt:
    if exception is not None:
        logger.warning("Example %s failed: %s", work_item.unit_id, exception)
    return EvalAttempt(
        actual_values={},
        evals={},
        success=False,
        error=message,
        metadata={"run_index": work_item.run_index},
    )


def _receipt_error(receipt: Any) -> str:
    errors = [
        stage.error
        for stage in (
            receipt.retrieve_receipt,
            receipt.process_receipt,
            receipt.act_receipt,
        )
        if stage is not None and stage.error
    ]
    return "; ".join(errors) or "Pipeline receipt reported failure."


def _build_summary(
    results: list[_ExampleEvalResult], *, runs_per_example: int
) -> dict[str, Any]:
    attempts = [attempt for result in results for attempt in result.attempts]
    classification_flags = [
        attempt.evals.get("classification", _NO_EVAL).is_correct
        for attempt in attempts
    ]
    evaluated_classifications = [
        flag for flag in classification_flags if flag is not None
    ]
    label_names = sorted(
        {name for result in results for name in result.example.approved_labels}
    )
    accuracy_by_label: dict[str, float | None] = {}
    for name in label_names:
        flags = [
            attempt.evals.get(name, _NO_EVAL).is_correct for attempt in attempts
        ]
        evaluated = [flag for flag in flags if flag is not None]
        accuracy_by_label[name] = EvalSummaryBuilder.safe_accuracy(
            correct=sum(flag is True for flag in evaluated), total=len(evaluated)
        )
    return {
        "overall_classification_accuracy": EvalSummaryBuilder.safe_accuracy(
            correct=sum(flag is True for flag in evaluated_classifications),
            total=len(evaluated_classifications),
        ),
        "accuracy_by_label": accuracy_by_label,
        "total_examples": len(results),
        "runs_per_example": runs_per_example,
        "total_runs": len(attempts),
        "successful_runs": sum(attempt.success for attempt in attempts),
        "evaluated_runs": len(evaluated_classifications),
        "correct_runs": sum(flag is True for flag in evaluated_classifications),
    }


def _build_results(results: list[_ExampleEvalResult]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for result in results:
        runs: list[dict[str, Any]] = []
        for attempt in result.attempts:
            ai_output = attempt.get_artifact("ai_output")
            runs.append(
                {
                    "run_index": attempt.metadata.get("run_index"),
                    "actual_labels": attempt.actual_values,
                    "label_correctness": {
                        name: evaluation.is_correct
                        for name, evaluation in attempt.evals.items()
                    },
                    "ai_output": ai_output,
                    "success": attempt.success,
                    "error": attempt.error,
                }
            )
        output.append(
            {
                "example_id": result.example.example_id,
                "unit_id": result.example.unit_id,
                "decision_timestamp": result.example.decision_timestamp.isoformat(),
                "source_snapshot_id": result.example.source_snapshot_id,
                "expected_labels": result.example.approved_labels,
                "classification_accuracy": result.classification_accuracy,
                "runs": runs,
                "metadata": result.example.example_metadata,
            }
        )
    return output


def _scope_token(
    *,
    example_ids: list[str] | None,
    unit_ids: list[str] | None,
    classifications: list[str] | None,
) -> str:
    if example_ids:
        return "example_subset"
    if unit_ids:
        return "unit_subset"
    if classifications:
        return normalize_filename_token("_".join(sorted(classifications)))
    return "all"


def _extract_provider(ai_model: str | None) -> str | None:
    return ai_model.split(":", 1)[0] if ai_model and ":" in ai_model else None


def _extract_model_name(ai_model: str | None) -> str:
    if not ai_model:
        return "pipeline_default"
    return ai_model.split(":", 1)[1] if ":" in ai_model else ai_model


def _results_filename(
    *,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
    scope: str,
    runs_per_example: int,
    timestamp: str,
) -> str:
    """Build a benchmark-example-oriented results filename."""
    parts = (
        _extract_provider(ai_model),
        _extract_model_name(ai_model),
        ai_reasoning_effort,
        scope,
    )
    tokens = [normalize_filename_token(part) for part in parts]
    return "_".join(
        [*tokens, f"{runs_per_example}runsPerExample", f"{timestamp}.json"]
    )


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a pipeline against a published Azure PostgreSQL benchmark "
            "using benchmark-frozen Azure Blob evidence."
        )
    )
    parser.add_argument(
        "yaml_path",
        nargs="?",
        type=Path,
        help="Pipeline config. Omit in a terminal to choose from pipeline_configs/.",
    )
    parser.add_argument("--project-key")
    parser.add_argument(
        "--azure-resource-group",
        default=os.getenv(
            "LABEL_BENCHMARK_AZURE_RESOURCE_GROUP", DEFAULT_AZURE_RESOURCE_GROUP
        ),
    )
    parser.add_argument(
        "--azure-container-app",
        default=os.getenv(
            "LABEL_BENCHMARK_AZURE_CONTAINER_APP", DEFAULT_AZURE_CONTAINER_APP
        ),
    )
    parser.add_argument(
        "--benchmark-key",
        help=(
            "Published benchmark key. Omit in an interactive terminal to retrieve "
            "and choose from the Azure benchmark catalog."
        ),
    )
    parser.add_argument("--benchmark-version", type=int)
    parser.add_argument("--example-ids", nargs="*")
    parser.add_argument("--unit-ids", nargs="*")
    parser.add_argument("--classifications", nargs="*")
    parser.add_argument("--runs-per-example", type=int, default=1)
    parser.add_argument(
        "--runtime", choices=["serial", "threaded", "process"], default="threaded"
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--error-action", choices=["stop", "continue"], default="continue")
    parser.add_argument("--ai-model")
    parser.add_argument(
        "--ai-reasoning-effort", choices=["default", "low", "medium", "high"]
    )
    return parser


def _choose_published_benchmark_version(
    versions: tuple[PublishedBenchmarkVersionSummary, ...],
) -> PublishedBenchmarkVersionSummary:
    """Prompt for one benchmark and one immutable published version."""
    if not versions:
        raise ValueError("No published benchmark versions were found in Azure.")

    versions_by_key: dict[str, list[PublishedBenchmarkVersionSummary]] = {}
    for version in versions:
        versions_by_key.setdefault(version.benchmark_key, []).append(version)

    benchmark_labels: dict[str, str] = {}
    for benchmark_key, benchmark_versions in versions_by_key.items():
        name = benchmark_versions[0].benchmark_name
        count = len(benchmark_versions)
        suffix = "version" if count == 1 else "versions"
        benchmark_labels[f"{name} ({benchmark_key}) — {count} published {suffix}"] = (
            benchmark_key
        )
    selected_benchmark_label = prompt_select_option(
        "Choose a published benchmark from Azure:",
        list(benchmark_labels),
    )
    selected_key = benchmark_labels[selected_benchmark_label]

    version_labels: dict[str, PublishedBenchmarkVersionSummary] = {}
    for version in sorted(
        versions_by_key[selected_key], key=lambda item: item.version_number, reverse=True
    ):
        published = version.published_at.isoformat(timespec="seconds")
        label = (
            f"v{version.version_number} — {version.example_count} examples — "
            f"published {published}"
        )
        version_labels[label] = version
    selected_version_label = prompt_select_option(
        f"Choose a version of {versions_by_key[selected_key][0].benchmark_name}:",
        list(version_labels),
    )
    return version_labels[selected_version_label]


def _resolve_cli_benchmark(
    args: argparse.Namespace,
    *,
    repository: BenchmarkRepository,
    project_key: str,
    parser: argparse.ArgumentParser,
) -> tuple[str, int | None]:
    """Resolve flags or launch the Azure-backed terminal chooser."""
    if args.benchmark_key:
        return args.benchmark_key, args.benchmark_version
    if args.benchmark_version is not None:
        parser.error("--benchmark-version requires --benchmark-key.")
    if not sys.stdin.isatty():
        parser.error(
            "--benchmark-key is required when stdin is not interactive; run in a "
            "terminal without it to choose from Azure."
        )

    print(f"Retrieving published benchmarks for {project_key} from Azure...")
    selected = _choose_published_benchmark_version(
        repository.list_published_versions()
    )
    print(
        f"Selected {selected.benchmark_name} "
        f"({selected.benchmark_key}) v{selected.version_number}."
    )
    return selected.benchmark_key, selected.version_number


def _resolve_pipeline_path(
    yaml_path: Path | None,
    *,
    parser: argparse.ArgumentParser,
) -> Path:
    """Use an explicit pipeline path or prompt from repository configs."""
    if yaml_path is not None:
        return yaml_path
    if not sys.stdin.isatty():
        parser.error("yaml_path is required when stdin is not interactive.")
    paths = sorted(Path("pipeline_configs").glob("*.ppln"))
    if not paths:
        parser.error("No pipeline configs were found under pipeline_configs/.")
    labels = {str(path): path for path in paths}
    selected = prompt_select_option("Choose a pipeline config:", list(labels))
    return labels[selected]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    bootstrap_environment()
    parser = _argument_parser()
    args = parser.parse_args()
    yaml_path = _resolve_pipeline_path(args.yaml_path, parser=parser)
    project_key = (args.project_key or os.getenv("APP_PROJECT_KEY", "")).strip()
    if not project_key:
        parser.error("APP_PROJECT_KEY or --project-key is required.")
    repository = AzureContainerAppBenchmarkRepository(
        project_key=project_key,
        resource_group=args.azure_resource_group,
        container_app=args.azure_container_app,
    )
    benchmark_key, benchmark_version = _resolve_cli_benchmark(
        args,
        repository=repository,
        project_key=project_key,
        parser=parser,
    )
    blob_connection, blob_container = load_hosted_blob_configuration(
        resource_group=args.azure_resource_group,
        container_app=args.azure_container_app,
    )
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = blob_connection
    os.environ["AZURE_STORAGE_CONTAINER"] = blob_container
    path = run_eval(
        yaml_path,
        project_key=project_key,
        benchmark_key=benchmark_key,
        benchmark_version=benchmark_version,
        ai_model=args.ai_model,
        ai_reasoning_effort=args.ai_reasoning_effort,
        example_ids=args.example_ids,
        unit_ids=args.unit_ids,
        classifications=args.classifications,
        runs_per_example=args.runs_per_example,
        runtime=args.runtime,
        max_workers=args.max_workers,
        error_action=args.error_action,
        repository=repository,
    )
    print(f"Results written to: {path}")


if __name__ == "__main__":
    main()
