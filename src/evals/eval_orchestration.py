"""Evaluate v1_3 against a published benchmark and frozen Azure Blob evidence."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from src.benchmarks import (
    AzurePostgresBenchmarkRepository,
    BenchmarkExample,
    BenchmarkRepository,
    BenchmarkVersion,
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
from src.pipelines.pipeline_run_from_yaml import run_pipeline

logger = logging.getLogger(__name__)

BASE_RESULTS_DIR = Path("src/evals/eval_results")
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
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument("--project-key")
    parser.add_argument("--benchmark-key", required=True)
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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _argument_parser().parse_args()
    path = run_eval(
        args.yaml_path,
        project_key=args.project_key,
        benchmark_key=args.benchmark_key,
        benchmark_version=args.benchmark_version,
        ai_model=args.ai_model,
        ai_reasoning_effort=args.ai_reasoning_effort,
        example_ids=args.example_ids,
        unit_ids=args.unit_ids,
        classifications=args.classifications,
        runs_per_example=args.runs_per_example,
        runtime=args.runtime,
        max_workers=args.max_workers,
        error_action=args.error_action,
    )
    print(f"Results written to: {path}")


if __name__ == "__main__":
    main()
