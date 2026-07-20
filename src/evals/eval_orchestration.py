"""Evaluate v1_3 against a published benchmark and frozen Azure Blob evidence."""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import yaml

from evaluation import (
    AttemptStatus,
    ErrorActionType,
    EvalAttempt,
    ExecutionCancelledError,
    FailureType,
    LabelEvaluation,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalWorkItem,
    RuntimeType,
    StructuredOutputSpec,
    build_confidence_accuracy,
    build_performance_summary,
    build_reliability_summary,
    build_results_dir_for_pipeline,
    extract_structured_outputs,
    group_metric_counts,
    metric_counts,
    normalize_filename_token,
    validate_metadata_identity,
    write_json_exclusive,
)
from mi.core.utils.environment import bootstrap_environment

from model_catalog import ModelCatalog, load_model_catalog, resolve_model
from src.benchmarks import (
    AzurePostgresBenchmarkRepository,
    AzureContainerAppBenchmarkRepository,
    BenchmarkExample,
    BenchmarkRepository,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
)
from src.evals.cli_support import (
    normalize_ai_reasoning_effort,
    prompt_positive_int,
    prompt_select_option,
)
from src.pipelines.pipeline_run_from_yaml import run_pipeline
from src.storage.hosted_azure_config import load_hosted_blob_configuration

logger = logging.getLogger(__name__)

_AZURE_HTTP_LOGGER = "azure.core.pipeline.policies.http_logging_policy"
_QUIET_EXECUTOR_LOGGER = logging.getLogger(f"{__name__}.executor_internal")
_QUIET_EXECUTOR_LOGGER.addHandler(logging.NullHandler())
_QUIET_EXECUTOR_LOGGER.propagate = False
_QUIET_EXECUTOR_LOGGER.setLevel(logging.CRITICAL)

BASE_RESULTS_DIR = Path("eval_results")
DEFAULT_AZURE_RESOURCE_GROUP = "rg-misprx-dv"
DEFAULT_AZURE_CONTAINER_APP = "label-benchmark"
_STRUCTURED_OUTPUT_SPECS: tuple[StructuredOutputSpec, ...] = (
    StructuredOutputSpec(
        name="classification",
        metadata_key="classification",
        value_path=("value",),
        confidence_path=("confidence",),
    ),
    StructuredOutputSpec(
        name="root_cause",
        metadata_key="root_cause",
        value_path=("value",),
        confidence_path=("confidence",),
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


class _EvalProgressTracker:
    """Report completions, failures, and genuinely running slow work."""

    def __init__(self, *, total_runs: int, heartbeat_seconds: float) -> None:
        self._total_runs = total_runs
        self._heartbeat_seconds = heartbeat_seconds
        self._successful = 0
        self._failed = 0
        self._running: dict[tuple[str, int], float] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="eval-progress-heartbeat",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def started(self, work_item: RepeatedEvalWorkItem[BenchmarkExample]) -> None:
        with self._lock:
            self._running[(work_item.item_id, work_item.attempt_index)] = (
                time.monotonic()
            )

    def completed(
        self,
        work_item: RepeatedEvalWorkItem[BenchmarkExample],
        attempt: EvalAttempt,
    ) -> None:
        with self._lock:
            self._running.pop((work_item.item_id, work_item.attempt_index), None)
            if attempt.success:
                self._successful += 1
                successful = self._successful
            else:
                self._failed += 1
                successful = None
        if successful is not None:
            logger.info(
                "SUCCESS: %d/%d | %s run %d",
                successful,
                self._total_runs,
                work_item.item_id,
                work_item.attempt_index,
            )
        else:
            logger.error(
                "FAILURE: %s run %d | %s",
                work_item.item_id,
                work_item.attempt_index,
                attempt.error or "Pipeline receipt reported failure.",
            )

    def raised(
        self,
        work_item: RepeatedEvalWorkItem[BenchmarkExample],
        exception: Exception,
    ) -> None:
        with self._lock:
            self._running.pop((work_item.item_id, work_item.attempt_index), None)
            self._failed += 1
        logger.error(
            "FAILURE: %s run %d | %s",
            work_item.item_id,
            work_item.attempt_index,
            exception,
        )
        setattr(exception, "_eval_failure_reported", True)

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_seconds):
            message = self._heartbeat_message()
            if message is not None:
                logger.info(message)

    def _heartbeat_message(self) -> str | None:
        now = time.monotonic()
        with self._lock:
            if not self._running:
                return None
            slowest = sorted(
                (
                    (now - started_at, unit_id, run_index)
                    for (unit_id, run_index), started_at in self._running.items()
                ),
                reverse=True,
            )[:3]
            completed = self._successful + self._failed
            queued = self._total_runs - completed - len(self._running)
            details = ", ".join(
                f"{unit_id} run {run_index} ({elapsed:.0f}s)"
                for elapsed, unit_id, run_index in slowest
            )
            return (
                f"PROGRESS: {self._successful}/{self._total_runs} succeeded, "
                f"{self._failed} failed, {len(self._running)} running, "
                f"{max(queued, 0)} queued | slowest: {details}"
            )


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
    root_causes: list[str] | None = None,
    runs_per_example: int = 1,
    runtime: RuntimeType = "threaded",
    max_workers: int = 4,
    error_action: ErrorActionType = "continue",
    progress_interval_seconds: float = 30.0,
    repository: BenchmarkRepository | None = None,
    output_root: Path | None = None,
) -> Path:
    """Run repeated evals against one immutable published benchmark version."""
    if runs_per_example < 1:
        raise ValueError("runs_per_example must be at least 1.")
    if progress_interval_seconds <= 0:
        raise ValueError("progress_interval_seconds must be greater than 0.")
    ai_model = resolve_model(ai_model)
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
        root_causes=root_causes,
    )
    if not examples:
        raise ValueError("No benchmark examples match the provided filters.")

    pipeline_args = _PipelineArgs(
        yaml_path=yaml_path,
        benchmark=benchmark,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
    )
    evaluation_started_at = time.monotonic()
    results = _run_all_examples(
        examples,
        pipeline_args=pipeline_args,
        runs_per_example=runs_per_example,
        runtime=runtime,
        max_workers=max_workers,
        error_action=error_action,
        progress_interval_seconds=progress_interval_seconds,
    )
    evaluation_wall_time_seconds = time.monotonic() - evaluation_started_at
    completed_at = datetime.now(timezone.utc)
    scope = _scope_token(
        example_ids=example_ids,
        unit_ids=unit_ids,
        classifications=classifications,
        root_causes=root_causes,
    )
    payload = {
        "summary": _build_summary(
            results,
            runs_per_example=runs_per_example,
            evaluation_wall_time_seconds=evaluation_wall_time_seconds,
        ),
        "run_config": {
            "eval_result_schema_version": 2,
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
            "progress_interval_seconds": progress_interval_seconds,
            "ai_provider": _extract_provider(ai_model),
            "ai_model": ai_model,
            "ai_reasoning_effort": ai_reasoning_effort,
            "ai_execution_policies": _ai_execution_policies(
                yaml_path,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
            ),
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
    return write_json_exclusive(output_path, payload)


def _select_examples(
    examples: tuple[BenchmarkExample, ...],
    *,
    example_ids: list[str] | None,
    unit_ids: list[str] | None,
    classifications: list[str] | None,
    root_causes: list[str] | None,
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
    if root_causes:
        requested_root_causes = {value.strip() for value in root_causes}
        selected = [
            example
            for example in selected
            if example.approved_labels.get("root_cause") in requested_root_causes
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
    progress_interval_seconds: float,
) -> list[_ExampleEvalResult]:
    tracker = (
        _EvalProgressTracker(
            total_runs=len(examples) * runs_per_example,
            heartbeat_seconds=progress_interval_seconds,
        )
        if runtime != "process"
        else None
    )
    executor = RepeatedEvalExecutor[BenchmarkExample, EvalAttempt](
        RepeatedEvalExecutorConfig(
            runtime=runtime,
            max_workers=max_workers,
            error_action=error_action,
            pending_heartbeat_seconds=progress_interval_seconds,
        ),
        logger=logger if runtime == "process" else _QUIET_EXECUTOR_LOGGER,
    )
    if tracker is not None:
        tracker.start()
    try:
        records = executor.run(
            examples,
            attempts_per_item=runs_per_example,
            get_item_id=lambda example: example.example_id,
            run_once=partial(
                _run_work_item,
                pipeline_args=pipeline_args,
                progress_tracker=tracker,
            ),
            build_failure_result=_build_failure_attempt,
            has_error=lambda attempt: attempt.has_error,
        )
    finally:
        if tracker is not None:
            tracker.stop()
    attempts_by_example: dict[str, list[EvalAttempt]] = {}
    for record in records:
        attempts_by_example.setdefault(record.work_item.item_id, []).append(
            record.result
        )
    results: list[_ExampleEvalResult] = []
    for example in examples:
        attempts = attempts_by_example.get(example.example_id, [])
        flags = [
            attempt.evaluations["classification"].is_correct
            for attempt in attempts
            if "classification" in attempt.evaluations
        ]
        results.append(
            _ExampleEvalResult(
                example=example,
                attempts=tuple(attempts),
                classification_accuracy=metric_counts(flags).accuracy,
            )
        )
    return results


def _run_work_item(
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
    *,
    pipeline_args: _PipelineArgs,
    progress_tracker: _EvalProgressTracker | None = None,
) -> EvalAttempt:
    if progress_tracker is not None:
        progress_tracker.started(work_item)
    started_at = time.monotonic()
    try:
        receipt = run_pipeline(
            pipeline_args.yaml_path,
            benchmark=pipeline_args.benchmark,
            example=work_item.payload,
            ai_model=pipeline_args.ai_model,
            ai_reasoning_effort=pipeline_args.ai_reasoning_effort,
            pipeline_log_level="CRITICAL",
        )
        duration_seconds = _receipt_duration(receipt, started_at=started_at)
        stage_durations = _stage_durations(receipt)
        if not receipt.success:
            receipt_error = _receipt_error(receipt)
            attempt = _failed_attempt(
                message=receipt_error,
                failure_type=_classify_failure_message(
                    receipt_error,
                    default=FailureType.PIPELINE_ERROR,
                ),
                duration_seconds=duration_seconds,
                stage_durations_seconds=stage_durations,
                work_item=work_item,
                artifacts={"failure_details": _receipt_failure_details(receipt)},
            )
        elif receipt.act_receipt is None or not receipt.act_receipt.success:
            attempt = _failed_attempt(
                message="Pipeline did not produce a successful act-stage receipt.",
                failure_type=FailureType.RECEIPT_CONTRACT_ERROR,
                duration_seconds=duration_seconds,
                stage_durations_seconds=stage_durations,
                work_item=work_item,
            )
        else:
            act_metadata = receipt.act_receipt.metadata
            identity_errors = validate_metadata_identity(
                act_metadata,
                expected={
                    "example_id": work_item.payload.example_id,
                    "benchmark_key": pipeline_args.benchmark.benchmark_key,
                    "benchmark_version_id": (
                        pipeline_args.benchmark.benchmark_version_id
                    ),
                    "benchmark_version_number": pipeline_args.benchmark.version_number,
                    "source_snapshot_id": work_item.payload.source_snapshot_id,
                },
            )
            expected_names = set(work_item.payload.approved_labels)
            specs = tuple(
                spec for spec in _STRUCTURED_OUTPUT_SPECS if spec.name in expected_names
            )
            extracted = extract_structured_outputs(act_metadata, specs=specs)
            contract_errors = (*identity_errors, *extracted.errors)
            if contract_errors:
                attempt = _failed_attempt(
                    message="; ".join(contract_errors),
                    failure_type=FailureType.RECEIPT_CONTRACT_ERROR,
                    duration_seconds=duration_seconds,
                    stage_durations_seconds=stage_durations,
                    work_item=work_item,
                    artifacts={"ai_output": extracted.raw_outputs},
                )
            else:
                actual_values = {
                    name: extracted.actual_values[name] for name in expected_names
                }
                attempt = EvalAttempt(
                    status=AttemptStatus.SUCCEEDED,
                    actual_values=actual_values,
                    evaluations={
                        name: LabelEvaluation(
                            expected=expected,
                            actual=actual_values[name],
                            is_correct=expected == actual_values[name],
                        )
                        for name, expected in work_item.payload.approved_labels.items()
                    },
                    confidence_values={
                        name: confidence
                        for name, confidence in extracted.confidence_values.items()
                        if name in expected_names
                    },
                    duration_seconds=duration_seconds,
                    stage_durations_seconds=stage_durations,
                    artifacts={"ai_output": extracted.raw_outputs},
                    metadata=_attempt_metadata(work_item),
                )
    except Exception as exception:
        if progress_tracker is not None:
            progress_tracker.raised(work_item, exception)
        raise
    if progress_tracker is not None:
        progress_tracker.completed(work_item, attempt)
    return attempt


def _build_failure_attempt(
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
    message: str,
    exception: Exception | None,
    duration_seconds: float,
) -> EvalAttempt:
    if exception is not None and not getattr(
        exception, "_eval_failure_reported", False
    ):
        logger.error(
            "FAILURE: %s run %d | %s",
            work_item.item_id,
            work_item.attempt_index,
            exception,
        )
    cancelled = isinstance(exception, ExecutionCancelledError)
    return _failed_attempt(
        message=message,
        failure_type=(
            FailureType.CANCELLED if cancelled else _classify_exception(exception)
        ),
        duration_seconds=duration_seconds,
        stage_durations_seconds={},
        work_item=work_item,
        cancelled=cancelled,
    )


def _failed_attempt(
    *,
    message: str,
    failure_type: FailureType,
    duration_seconds: float,
    stage_durations_seconds: dict[str, float],
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
    artifacts: dict[str, Any] | None = None,
    cancelled: bool = False,
) -> EvalAttempt:
    return EvalAttempt(
        status=AttemptStatus.CANCELLED if cancelled else AttemptStatus.FAILED,
        error=message,
        failure_type=failure_type,
        duration_seconds=duration_seconds,
        stage_durations_seconds=stage_durations_seconds,
        artifacts=artifacts or {},
        metadata=_attempt_metadata(work_item),
    )


def _attempt_metadata(
    work_item: RepeatedEvalWorkItem[BenchmarkExample],
) -> dict[str, Any]:
    return {
        "source_snapshot_id": work_item.payload.source_snapshot_id,
        "run_index": work_item.attempt_index,
    }


def _classify_exception(exception: Exception | None) -> FailureType:
    if isinstance(exception, TimeoutError):
        return FailureType.TIMEOUT
    if exception is None:
        return FailureType.UNKNOWN
    return _classify_failure_message(
        f"{type(exception).__name__}: {exception}",
        default=FailureType.PIPELINE_ERROR,
    )


def _classify_failure_message(
    message: str,
    *,
    default: FailureType,
) -> FailureType:
    normalized = message.lower()
    if "timeout" in normalized or "timed out" in normalized:
        return FailureType.TIMEOUT
    transport_markers = (
        "connection error",
        "connectionerror",
        "connecterror",
        "network error",
        "networkerror",
        "readerror",
        "writeerror",
        "remoteprotocolerror",
    )
    if any(marker in normalized for marker in transport_markers):
        return FailureType.TRANSPORT_ERROR
    provider_markers = ("status_code", "model request", "rate limit", "provider")
    if any(marker in normalized for marker in provider_markers):
        return FailureType.PROVIDER_ERROR
    return default


def _receipt_duration(receipt: Any, *, started_at: float) -> float:
    reported = getattr(receipt, "total_execution_time_seconds", 0.0)
    return (
        reported
        if isinstance(reported, (int, float)) and reported > 0
        else time.monotonic() - started_at
    )


def _stage_durations(receipt: Any) -> dict[str, float]:
    durations: dict[str, float] = {}
    for stage_name in ("retrieve", "process", "act"):
        stage = receipt.get_stage_receipt(stage_name)
        if stage is not None and stage.execution_time_seconds >= 0:
            durations[stage_name] = stage.execution_time_seconds
    return durations


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


def _receipt_failure_details(receipt: Any) -> dict[str, Any]:
    """Return structured, correlation-safe diagnostics for failed stages."""
    stages: list[dict[str, Any]] = []
    for stage_name in ("retrieve", "process", "act"):
        stage = receipt.get_stage_receipt(stage_name)
        if stage is None or stage.success:
            continue
        details: dict[str, Any] = {
            "stage": stage_name,
            "correlation_id": stage.correlation_id,
            "duration_seconds": stage.execution_time_seconds,
            "error": stage.error,
        }
        error_details = stage.metadata.get("error_details")
        if isinstance(error_details, dict):
            details["error_details"] = error_details
        stages.append(details)
    return {
        "pipeline_id": getattr(receipt, "pipeline_id", None),
        "correlation_id": getattr(receipt, "correlation_id", None),
        "failed_stages": stages,
    }


def _ai_execution_policies(
    yaml_path: Path,
    *,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
) -> list[dict[str, Any]]:
    """Describe effective AI request safeguards persisted with an eval run."""
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    process_config = config.get("process", {})
    processors = (
        process_config.get("processors", [])
        if isinstance(process_config, dict)
        else []
    )
    policies: list[dict[str, Any]] = []
    for processor in processors:
        if not isinstance(processor, dict):
            continue
        processor_name = str(processor.get("processor", ""))
        if not (
            "AI" in processor_name
            or "Agent" in processor_name
            or "model" in processor
        ):
            continue
        legacy_retries = processor.get("retries")
        transport_attempts = (
            max(1, legacy_retries)
            if isinstance(legacy_retries, int)
            else processor.get("transport_retries", 3)
        )
        tool_retries = (
            legacy_retries
            if isinstance(legacy_retries, int)
            else processor.get("tool_retries", 3)
        )
        configured_output_retries = processor.get("output_retries")
        policies.append(
            {
                "processor": processor_name,
                "model": ai_model or processor.get("model"),
                "reasoning_effort": (
                    ai_reasoning_effort
                    or processor.get("reasoning_effort")
                    or "medium"
                ),
                "timeout_seconds_per_attempt": processor.get("timeout"),
                "transport_attempts": transport_attempts,
                "output_retries": (
                    tool_retries
                    if configured_output_retries is None
                    else configured_output_retries
                ),
            }
        )
    return policies


def _build_summary(
    results: list[_ExampleEvalResult],
    *,
    runs_per_example: int,
    evaluation_wall_time_seconds: float,
) -> dict[str, Any]:
    attempts = [attempt for result in results for attempt in result.attempts]
    valid_attempts = [attempt for attempt in attempts if attempt.success]
    classification_flags = [
        attempt.evaluations["classification"].is_correct
        for attempt in valid_attempts
        if "classification" in attempt.evaluations
    ]
    label_names = sorted(
        {name for result in results for name in result.example.approved_labels}
    )
    accuracy_by_label: dict[str, float | None] = {}
    for name in label_names:
        counts = metric_counts(
            attempt.evaluations[name].is_correct
            for attempt in valid_attempts
            if name in attempt.evaluations
        )
        accuracy_by_label[name] = counts.accuracy
    accuracy: dict[str, Any] = {
        "overall_classification_accuracy": metric_counts(classification_flags).accuracy,
        "accuracy_by_label": accuracy_by_label,
        "accuracy_by_classification": _accuracy_by_expected_label(
            results,
            label_name="classification",
        ),
        "accuracy_by_failure_root_cause": _accuracy_by_expected_label(
            _failure_results(results),
            label_name="root_cause",
        ),
        "evaluated_runs": len(valid_attempts),
        "correct_classification_runs": sum(classification_flags),
    }
    configured_confidence_labels = {
        spec.name
        for spec in _STRUCTURED_OUTPUT_SPECS
        if spec.confidence_path is not None
    }
    if "classification" in configured_confidence_labels:
        accuracy["classification_accuracy_by_confidence"] = _accuracy_by_confidence(
            results,
            label_name="classification",
            group_name="by_classification",
        )
    if "root_cause" in configured_confidence_labels:
        accuracy["root_cause_accuracy_by_confidence"] = _accuracy_by_confidence(
            _failure_results(results),
            label_name="root_cause",
            group_name="by_failure_root_cause",
        )
    return {
        "accuracy": accuracy,
        "reliability": build_reliability_summary(
            attempts,
            planned_runs=len(results) * runs_per_example,
        ),
        "performance": build_performance_summary(
            attempts,
            evaluation_wall_time_seconds=evaluation_wall_time_seconds,
        ),
        "total_examples": len(results),
        "runs_per_example": runs_per_example,
    }


def _failure_results(
    results: list[_ExampleEvalResult],
) -> list[_ExampleEvalResult]:
    """Return examples whose approved classification requires root-cause scoring."""
    return [
        result
        for result in results
        if result.example.approved_labels.get("classification") == "Failure"
    ]


def _accuracy_by_expected_label(
    results: list[_ExampleEvalResult],
    *,
    label_name: str,
) -> dict[str, float | None]:
    """Compute run accuracy grouped by the approved value for one label."""
    observations: list[tuple[str, bool]] = []
    expected_values: set[str] = set()
    for result in results:
        expected = result.example.approved_labels.get(label_name)
        if expected is None:
            continue
        expected_values.add(expected)
        for attempt in result.attempts:
            evaluation = attempt.evaluations.get(label_name)
            if evaluation is not None:
                observations.append((expected, evaluation.is_correct))
    grouped = group_metric_counts(
        observations,
        key_fn=lambda observation: observation[0],
        correct_fn=lambda observation: observation[1],
        expected_keys=expected_values,
    )
    return {expected: counts.accuracy for expected, counts in grouped.items()}


def _accuracy_by_confidence(
    results: list[_ExampleEvalResult],
    *,
    label_name: str,
    group_name: str,
) -> dict[str, Any]:
    """Compute accuracy for each model confidence, overall and by expected label."""
    expected_values = {
        expected
        for result in results
        if (expected := result.example.approved_labels.get(label_name)) is not None
    }
    summary = build_confidence_accuracy(
        (attempt for result in results for attempt in result.attempts),
        label_name=label_name,
        expected_values=expected_values,
    )
    return {
        "confidence_coverage": summary["confidence_coverage"],
        "all": summary["all"],
        group_name: summary["by_expected_value"],
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
                    "status": attempt.status.value,
                    "actual_labels": attempt.actual_values,
                    "label_correctness": {
                        name: evaluation.is_correct
                        for name, evaluation in attempt.evaluations.items()
                    },
                    "confidence": attempt.confidence_values,
                    "ai_output": ai_output,
                    "success": attempt.success,
                    "failure_type": (
                        attempt.failure_type.value
                        if attempt.failure_type is not None
                        else None
                    ),
                    "error": attempt.error,
                    "failure_details": attempt.get_artifact("failure_details"),
                    "duration_seconds": attempt.duration_seconds,
                    "stage_durations_seconds": attempt.stage_durations_seconds,
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
    root_causes: list[str] | None,
) -> str:
    if example_ids:
        return "example_subset"
    if unit_ids:
        return "unit_subset"
    if classifications:
        return normalize_filename_token("_".join(sorted(classifications)))
    if root_causes:
        return normalize_filename_token("_".join(sorted(root_causes)))
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
    return "_".join([*tokens, f"{runs_per_example}runsPerExample", f"{timestamp}.json"])


def _write_results_file(output_path: Path, payload: dict[str, Any]) -> Path:
    """Compatibility wrapper for the core immutable evidence writer."""
    return write_json_exclusive(output_path, payload)


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
    parser.add_argument("--root-causes", nargs="*")
    parser.add_argument("--runs-per-example", type=int)
    parser.add_argument(
        "--runtime", choices=["serial", "threaded", "process"], default="threaded"
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--error-action", choices=["stop", "continue"], default="continue"
    )
    parser.add_argument(
        "--progress-interval-seconds",
        type=float,
        default=30.0,
        help="Seconds between slow-running pipeline heartbeats.",
    )
    parser.add_argument(
        "--ai-model",
        help="Model from the project-owned models.yaml catalog.",
    )
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
        versions_by_key[selected_key],
        key=lambda item: item.version_number,
        reverse=True,
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
    selected = _choose_published_benchmark_version(repository.list_published_versions())
    print(
        f"Selected {selected.benchmark_name} "
        f"({selected.benchmark_key}) v{selected.version_number}."
    )
    return selected.benchmark_key, selected.version_number


def _resolve_cli_model(
    args: argparse.Namespace,
    *,
    catalog: ModelCatalog,
    parser: argparse.ArgumentParser,
) -> str:
    """Validate an explicit model or prompt from the project-owned catalog."""
    if args.ai_model:
        try:
            return resolve_model(args.ai_model, catalog)
        except ValueError as error:
            parser.error(str(error))
    if not sys.stdin.isatty():
        return catalog.default_model
    return prompt_select_option(
        f"Choose an AI model (project default: {catalog.default_model}):",
        list(catalog.model_ids),
    )


def _resolve_cli_reasoning_effort(args: argparse.Namespace) -> str | None:
    """Use an explicit effort or prompt for one in an interactive terminal."""
    if args.ai_reasoning_effort is not None:
        return normalize_ai_reasoning_effort(args.ai_reasoning_effort)
    if not sys.stdin.isatty():
        return None
    selected = prompt_select_option(
        "Choose AI reasoning effort (default: model default):",
        ["default", "low", "medium", "high"],
    )
    return normalize_ai_reasoning_effort(selected)


def _resolve_cli_runs_per_example(
    args: argparse.Namespace, *, parser: argparse.ArgumentParser
) -> int:
    """Use an explicit run count or prompt in an interactive terminal."""
    if args.runs_per_example is not None:
        if args.runs_per_example < 1:
            parser.error("--runs-per-example must be at least 1.")
        return args.runs_per_example
    if not sys.stdin.isatty():
        return 1
    return prompt_positive_int("Number of runs per example", default=1)


def _resolve_cli_example_scope(
    args: argparse.Namespace,
    *,
    benchmark: BenchmarkVersion,
    parser: argparse.ArgumentParser,
) -> tuple[list[str] | None, list[str] | None, list[str] | None, list[str] | None]:
    """Use explicit filters or prompt for a benchmark example category."""
    explicit_filters = (
        args.example_ids,
        args.unit_ids,
        args.classifications,
        args.root_causes,
    )
    if any(value is not None for value in explicit_filters):
        return explicit_filters
    if not sys.stdin.isatty():
        return None, None, None, None

    options = [
        "All examples",
        "Closed failures",
        "Open failures",
        "Unknown failures",
        "Healthy",
        "Single example (random)",
    ]
    selected = prompt_select_option(
        "Which benchmark examples should be analyzed?", options
    )
    if selected == "All examples":
        return None, None, None, None
    if selected == "Healthy":
        filters = (None, None, ["Healthy"], None)
    elif selected == "Closed failures":
        filters = (None, None, None, ["Closed Failure"])
    elif selected == "Open failures":
        filters = (None, None, None, ["Open Failure"])
    elif selected == "Unknown failures":
        filters = (None, None, None, ["Unknown"])
    else:
        example = random.choice(benchmark.examples)
        print(
            f"Randomly selected example: {example.example_id} (unit {example.unit_id})."
        )
        return [example.example_id], None, None, None

    matching = _select_examples(
        benchmark.examples,
        example_ids=filters[0],
        unit_ids=filters[1],
        classifications=filters[2],
        root_causes=filters[3],
    )
    if not matching:
        parser.error(f"No benchmark examples match the selected scope: {selected}.")
    return filters


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


def _configure_cli_logging() -> None:
    """Keep operator output useful without Azure SDK request/response dumps."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    logging.getLogger(_AZURE_HTTP_LOGGER).setLevel(logging.WARNING)
    if not any(getattr(handler, "_eval_cli", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._eval_cli = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _print_cli_outcome(path: Path) -> None:
    """Print one clear outcome for a completed evaluation."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    reliability = payload["summary"]["reliability"]
    total_runs = int(reliability["planned_runs"])
    successful_runs = int(reliability["successful_runs"])
    failed_runs = int(reliability["failed_runs"]) + int(reliability["cancelled_runs"])
    if failed_runs:
        print(
            f"FAILED: {successful_runs}/{total_runs} succeeded; {failed_runs} failed."
        )
    else:
        print(f"SUCCESS: {successful_runs}/{total_runs} succeeded; 0 failed.")
    print(f"Results written to: {path}")


def main() -> None:
    _configure_cli_logging()
    bootstrap_environment()
    parser = _argument_parser()
    args = parser.parse_args()
    model_catalog = load_model_catalog()
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
    benchmark = repository.load_published_version(
        benchmark_key=benchmark_key,
        version_number=benchmark_version,
    )
    benchmark_version = benchmark.version_number
    example_ids, unit_ids, classifications, root_causes = _resolve_cli_example_scope(
        args,
        benchmark=benchmark,
        parser=parser,
    )
    ai_model = _resolve_cli_model(args, catalog=model_catalog, parser=parser)
    ai_reasoning_effort = _resolve_cli_reasoning_effort(args)
    runs_per_example = _resolve_cli_runs_per_example(args, parser=parser)
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
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        example_ids=example_ids,
        unit_ids=unit_ids,
        classifications=classifications,
        root_causes=root_causes,
        runs_per_example=runs_per_example,
        runtime=args.runtime,
        max_workers=args.max_workers,
        error_action=args.error_action,
        progress_interval_seconds=args.progress_interval_seconds,
        repository=repository,
    )
    _print_cli_outcome(path)


if __name__ == "__main__":
    main()
