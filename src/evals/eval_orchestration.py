"""Evaluate agent pipelines through versioned schema-driven evaluation profiles."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections.abc import Callable
import _thread
import json
import logging
import os
import shlex
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path
from typing import Any, Iterator

from evaluation import (
    ErrorActionType,
    EvalAttempt,
    ExecutionCancelledError,
    ExecutionStatus,
    FailureType,
    GraderRegistry,
    JsonScalar,
    LocalReviewStore,
    OutputContractStatus,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalWorkItem,
    RuntimeType,
    ScoringStatus,
    build_reliability_summary,
    build_run_identity,
    build_work_item_id,
    benchmark_source_reference,
    build_scoring_coverage,
    metric_counts,
    normalize_filename_token,
    read_path,
    eval_attempt_performance_to_dict,
    eval_attempt_to_dict,
)
from mi.core.utils.environment import bootstrap_environment
from pydantic import BaseModel
import yaml

from model_catalog import (
    ModelCatalog,
    ModelDefinition,
    load_model_catalog,
    resolve_model,
    resolve_model_definition,
)
from src.agent_versions import (
    AgentVersionReference,
    AgentVersionStore,
    resolve_agent_version,
    validate_runtime_overrides,
)
from src.benchmarks import (
    AzurePostgresBenchmarkRepository,
    BenchmarkExample,
    BenchmarkRepository,
    BenchmarkVersion,
    PublishedBenchmarkVersionSummary,
)
from src.benchmarks.compatibility import (
    find_configured_published_benchmark,
    load_project_contract,
    preflight_pipeline_benchmark_contract,
)
from src.evals.cli_support import (
    normalize_ai_reasoning_effort,
    prompt_csv_values,
    prompt_positive_int,
    prompt_select_option,
)
from src.evals.comparisons import build_comparison, build_comparison_manifest
from src.evals.evaluation_profile import (
    EvaluationPreflight,
    EvaluationProfile,
    canonical_sha256,
    load_evaluation_profile,
    preflight_evaluation,
    slice_memberships,
)
from src.evals.graders import build_project_grader_registry
from src.evals.inspection import (
    find_run_directory as find_inspection_run_directory,
    materialize_review_index,
)
from src.evals.scoring import score_receipt_metadata
from src.evals.run_specs import build_source_manifest, repository_root
from src.evals.run_store import (
    LocalRunStore,
    ResumeMode,
    RunStoreIntegrityError,
    new_invocation_id,
    utc_now,
)
from src.model_configuration import format_model
from src.pipelines.pipeline_run_from_yaml import run_pipeline


logger = logging.getLogger(__name__)

_AZURE_HTTP_LOGGER = "azure.core.pipeline.policies.http_logging_policy"
_QUIET_EXECUTOR_LOGGER = logging.getLogger(f"{__name__}.executor_internal")
_QUIET_EXECUTOR_LOGGER.addHandler(logging.NullHandler())
_QUIET_EXECUTOR_LOGGER.propagate = False
_QUIET_EXECUTOR_LOGGER.setLevel(logging.CRITICAL)

BASE_RESULTS_DIR = Path("eval_results")
_INTERRUPTION_GRACE_SECONDS = 30.0


@contextmanager
def _cooperative_signal_cancellation() -> Iterator[Callable[[], bool]]:
    """Translate the first operator signal into cancellation and bound its grace."""
    cancelled = threading.Event()
    if threading.current_thread() is not threading.main_thread():
        yield cancelled.is_set
        return
    previous_handlers: dict[signal.Signals, Any] = {}
    forced_interrupt: threading.Timer | None = None

    def handle_signal(signum: int, _frame: Any) -> None:
        nonlocal forced_interrupt
        if cancelled.is_set():
            raise KeyboardInterrupt
        cancelled.set()
        logger.warning(
            "Interruption requested by %s; stopping submissions and allowing %.0fs "
            "for active attempts to commit.",
            signal.Signals(signum).name,
            _INTERRUPTION_GRACE_SECONDS,
        )
        forced_interrupt = threading.Timer(
            _INTERRUPTION_GRACE_SECONDS,
            _thread.interrupt_main,
        )
        forced_interrupt.daemon = True
        forced_interrupt.start()

    for candidate in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[candidate] = signal.getsignal(candidate)
        signal.signal(candidate, handle_signal)
    try:
        yield cancelled.is_set
    finally:
        if forced_interrupt is not None:
            forced_interrupt.cancel()
        for candidate, previous in previous_handlers.items():
            signal.signal(candidate, previous)


def _resolve_agent_output_schema(yaml_path: Path) -> dict[str, Any]:
    """Resolve the final structured AI output contract without model execution."""
    from mi.core.registry import (
        build_registry_index,
        find_project_root,
        get_record,
        load_pipeline_settings,
        prepare_registry_and_schema,
    )
    from mi.core.registry.utils import import_symbol

    pipeline_config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(pipeline_config, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    process = pipeline_config.get("process")
    if not isinstance(process, dict) or not isinstance(process.get("processors"), list):
        raise ValueError("Evaluation pipeline must configure process-stage processors.")
    settings, resolved_config = load_pipeline_settings(None, start=yaml_path.parent)
    project_root = find_project_root(yaml_path.parent)
    registry, _ = prepare_registry_and_schema(
        project_root,
        settings,
        resolved_config,
        force_scan=True,
    )
    registry_index = build_registry_index(registry)
    schemas: list[type[BaseModel]] = []
    for entry in process["processors"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("processor"), str):
            raise ValueError("Pipeline processor entries require a processor name.")
        record = get_record("processors", entry["processor"], registry_index)
        processor_type = import_symbol(record.import_path, project_root)
        output_schema = getattr(processor_type, "output_schema", None)
        if isinstance(output_schema, type) and issubclass(output_schema, BaseModel):
            schemas.append(output_schema)
    if not schemas:
        raise ValueError(
            "Evaluation pipeline does not declare a structured AI output schema."
        )
    return schemas[-1].model_json_schema()


@dataclass(frozen=True, slots=True)
class _PipelineArgs:
    yaml_path: Path
    benchmark: BenchmarkVersion
    profile: EvaluationProfile
    grader_registry: GraderRegistry
    ai_model: str | None
    ai_reasoning_effort: str | None
    review_capture: bool = False


@dataclass(frozen=True, slots=True)
class _ExampleEvalResult:
    example: BenchmarkExample
    slice_keys: tuple[str, ...]
    attempts: tuple[EvalAttempt, ...]


class _EvalProgressTracker:
    def __init__(self, *, total_runs: int, heartbeat_seconds: float) -> None:
        self._total_runs = total_runs
        self._heartbeat_seconds = heartbeat_seconds
        self._healthy = 0
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
            if attempt.has_error:
                self._failed += 1
            else:
                self._healthy += 1
        if attempt.has_error:
            logger.error(
                "FAILURE: %s run %d | %s",
                work_item.item_id,
                work_item.attempt_index,
                attempt.error or "Evaluation attempt was not scorable.",
            )
        else:
            logger.info(
                "SUCCESS: %d/%d | %s run %d",
                self._healthy,
                self._total_runs,
                work_item.item_id,
                work_item.attempt_index,
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
                    (now - started_at, example_id, run_index)
                    for (example_id, run_index), started_at in self._running.items()
                ),
                reverse=True,
            )[:3]
            completed = self._healthy + self._failed
            queued = self._total_runs - completed - len(self._running)
            details = ", ".join(
                f"{example_id} run {run_index} ({elapsed:.0f}s)"
                for elapsed, example_id, run_index in slowest
            )
            return (
                f"PROGRESS: {self._healthy}/{self._total_runs} healthy, "
                f"{self._failed} failed, {len(self._running)} running, "
                f"{max(queued, 0)} queued | slowest: {details}"
            )


def run_eval(
    yaml_path: Path,
    *,
    evaluation_profile_path: Path,
    benchmark_key: str,
    benchmark_version: int | None = None,
    project_key: str | None = None,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
    example_ids: list[str] | None = None,
    unit_ids: list[str] | None = None,
    label_filters: dict[str, list[JsonScalar]] | None = None,
    slice_keys: list[str] | None = None,
    runs_per_example: int = 1,
    runtime: RuntimeType = "threaded",
    max_workers: int = 4,
    error_action: ErrorActionType = "continue",
    progress_interval_seconds: float = 30.0,
    repository: BenchmarkRepository | None = None,
    benchmark_source: str | None = None,
    grader_registry: GraderRegistry | None = None,
    agent_version_id: str | None = None,
    agent_policy_path: Path | None = None,
    require_promoted_agent_version: bool = False,
    configuration_dimensions: dict[str, JsonScalar] | None = None,
    resume_mode: ResumeMode = "missing",
    rerun_failure_types: set[str] | None = None,
    expected_run_id: str | None = None,
    dry_run: bool = False,
    materialize_only: bool = False,
    output_root: Path | None = None,
    agent_version_store_root: Path | None = None,
    review_capture: str = "full",
) -> Path:
    """Run repeated evals against one immutable published benchmark version."""
    if runs_per_example < 1:
        raise ValueError("runs_per_example must be at least 1.")
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1.")
    if runtime not in {"serial", "threaded", "process"}:
        raise ValueError(f"Unsupported runtime: {runtime}.")
    if error_action not in {"stop", "continue"}:
        raise ValueError(f"Unsupported error_action: {error_action}.")
    if progress_interval_seconds <= 0:
        raise ValueError("progress_interval_seconds must be greater than 0.")
    if dry_run and materialize_only:
        raise ValueError("dry_run and materialize_only cannot be combined.")
    if review_capture not in {"full", "off"}:
        raise ValueError("review_capture must be 'full' or 'off'.")
    if rerun_failure_types and resume_mode not in {"failed", "missing-or-failed"}:
        raise ValueError(
            "rerun_failure_types requires resume_mode 'failed' or 'missing-or-failed'."
        )
    resolved_agent = resolve_agent_version(
        yaml_path,
        policy_path=agent_policy_path,
        dirty_policy="capture",
    )
    ai_model, ai_reasoning_effort = validate_runtime_overrides(
        resolved_agent.policy,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
    )
    ai_model = resolve_model(ai_model)
    ai_reasoning_effort = normalize_ai_reasoning_effort(ai_reasoning_effort)
    project_root = repository_root(Path.cwd())
    promoted_store = AgentVersionStore(
        agent_version_store_root or project_root / "agent_versions"
    )
    requested_version_id = agent_version_id
    lifecycle_state = "candidate"
    if requested_version_id is not None or require_promoted_agent_version:
        expected_id = requested_version_id or resolved_agent.manifest.agent_version_id
        promoted = promoted_store.load(expected_id)
        if (
            promoted.agent_version_id != resolved_agent.manifest.agent_version_id
            or promoted.manifest_sha256 != resolved_agent.manifest.manifest_sha256
        ):
            raise ValueError(
                "The promoted agent version does not match the resolved pipeline "
                "and policy content."
            )
        lifecycle_state = "promoted"
    agent_reference = AgentVersionReference.from_manifest(
        resolved_agent.manifest,
        lifecycle_state=lifecycle_state,
    )
    profile = load_evaluation_profile(evaluation_profile_path)
    dimensions = _validate_configuration_dimensions(configuration_dimensions or {})
    registry = grader_registry or build_project_grader_registry()
    benchmark_repository = repository or AzurePostgresBenchmarkRepository(
        project_key=project_key
    )
    resolved_benchmark_source = benchmark_source or (
        "azure_postgres_entra"
        if isinstance(benchmark_repository, AzurePostgresBenchmarkRepository)
        else type(benchmark_repository).__name__
    )
    benchmark = benchmark_repository.load_published_version(
        benchmark_key=benchmark_key,
        version_number=benchmark_version,
    )
    if benchmark.source_state_sha256 is None:
        raise ValueError(
            "Published benchmark source_state_sha256 is required for linked evals."
        )
    examples = _select_examples(
        benchmark.examples,
        profile=profile,
        example_ids=example_ids,
        unit_ids=unit_ids,
        label_filters=label_filters,
        slice_keys=slice_keys,
    )
    if not examples:
        raise ValueError("No benchmark examples match the provided filters.")
    project_contract = load_project_contract(yaml_path)
    configured_benchmark = find_configured_published_benchmark(
        project_contract, benchmark
    )
    preflight_pipeline_benchmark_contract(
        pipeline_config=yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {},
        benchmark=benchmark,
        examples=examples,
        start_path=yaml_path,
        project_contract=project_contract,
    )
    preflight = preflight_evaluation(
        profile=profile,
        profile_path=evaluation_profile_path,
        benchmark=benchmark,
        examples=examples,
        grader_registry=registry,
        agent_output_schema=_resolve_agent_output_schema(yaml_path),
        allowed_benchmark_label_fields=set(configured_benchmark.label_fields),
    )

    pipeline_args = _PipelineArgs(
        yaml_path=yaml_path,
        benchmark=benchmark,
        profile=profile,
        grader_registry=registry,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        review_capture=review_capture == "full",
    )
    scope = _scope_token(
        example_ids=example_ids,
        unit_ids=unit_ids,
        label_filters=label_filters,
        slice_keys=slice_keys,
    )
    run_spec = _build_resolved_run_spec(
        yaml_path=yaml_path,
        evaluation_profile_path=evaluation_profile_path,
        benchmark=benchmark,
        preflight=preflight,
        examples=examples,
        scope=scope,
        scope_definition={
            "example_ids": sorted(example_ids or []),
            "unit_ids": sorted(unit_ids or []),
            "label_filters": {
                key: sorted(
                    values,
                    key=lambda value: json.dumps(
                        value, sort_keys=True, separators=(",", ":")
                    ),
                )
                for key, values in sorted((label_filters or {}).items())
            },
            "slice_keys": sorted(slice_keys or []),
        },
        runs_per_example=runs_per_example,
        runtime=runtime,
        max_workers=max_workers,
        error_action=error_action,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        agent_reference=agent_reference,
        configuration_dimensions=dimensions,
        evidence_contract={
            "storage_account_url": project_contract.benchmark_studio.storage_account_url,
            "storage_container": project_contract.benchmark_studio.storage_container,
            "evidence_recipe_id": configured_benchmark.evidence_recipe_id,
            "source_snapshot_contract": configured_benchmark.source_snapshot_contract,
        },
    )
    run_id, run_spec_sha256 = build_run_identity(run_spec)
    if expected_run_id is not None and expected_run_id != run_id:
        raise ValueError(
            f"Resolved run id {run_id} does not match requested {expected_run_id}."
        )
    work_plan = [
        {
            "work_item_id": build_work_item_id(
                run_id=run_id,
                item_id=example.example_id,
                attempt_index=attempt_index,
            ),
            "example_id": example.example_id,
            "repetition_index": attempt_index,
        }
        for example in examples
        for attempt_index in range(1, runs_per_example + 1)
    ]
    base = output_root or BASE_RESULTS_DIR
    run_dir = (
        base
        / "working"
        / normalize_filename_token(benchmark.benchmark_key)
        / f"v{benchmark.version_number}"
        / run_id
    )
    store = LocalRunStore(run_dir, run_id=run_id)
    manifest_created_at = (
        str(store.read_manifest()["created_at_utc"])
        if store.manifest_path.exists()
        else utc_now()
    )
    materialization_run_config = _build_run_config(
        yaml_path=yaml_path,
        benchmark=benchmark,
        preflight=preflight,
        scope=scope,
        runs_per_example=runs_per_example,
        runtime=runtime,
        max_workers=max_workers,
        error_action=error_action,
        progress_interval_seconds=progress_interval_seconds,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        agent_reference=agent_reference,
        configuration_dimensions=dimensions,
        benchmark_source=resolved_benchmark_source,
        completed_at=datetime.fromisoformat(manifest_created_at),
    )
    _bind_run_config_to_manifest(
        materialization_run_config,
        run_id=run_id,
        run_spec_sha256=run_spec_sha256,
        run_spec=run_spec,
        manifest_created_at=manifest_created_at,
    )
    materialization_run_config.pop("completed_at_utc", None)
    store.initialize(
        {
            "schema_version": 1,
            "performance_schema_version": 1,
            "coordinator_scope": "local_single_host",
            "run_id": run_id,
            "run_spec_sha256": run_spec_sha256,
            "run_spec": run_spec,
            "work_items": work_plan,
            "created_at_utc": manifest_created_at,
            "eval_contract": {
                "schema_version": 1,
                "run": materialization_run_config,
                "examples": _build_examples(
                    [
                        _ExampleEvalResult(
                            example=example,
                            slice_keys=preflight.example_slices[example.example_id],
                            attempts=(),
                        )
                        for example in examples
                    ],
                    profile=profile,
                ),
                "output_fields": [
                    {
                        "key": field.key,
                        "graded": field.evaluation is not None,
                        "benchmark_label_path": (
                            list(field.evaluation.benchmark_label_path)
                            if field.evaluation is not None
                            else None
                        ),
                    }
                    for field in profile.output_fields
                ],
                "slice_keys": [item.key for item in profile.slices],
            },
        }
    )
    promoted_store.persist_candidate(resolved_agent, run_dir)
    if dry_run:
        selected = store.select_work_items(
            mode=resume_mode,
            failure_types=rerun_failure_types,
        )
        logger.info(
            "DRY RUN: %s | %d selected | state=%s",
            run_id,
            len(selected),
            store.state_counts(),
        )
        return store.manifest_path
    invocation_id = new_invocation_id()
    invocation_started = time.monotonic()
    with store.coordinator_lock(invocation_id=invocation_id):
        selected = store.select_work_items(
            mode=resume_mode,
            failure_types=rerun_failure_types,
        )
        if materialize_only:
            selected = ()
        try:
            store.write_invocation_event(
                invocation_id=invocation_id,
                event="started",
                payload={
                    "resume_mode": resume_mode,
                    "rerun_failure_types": sorted(rerun_failure_types or ()),
                    "selected_work_items": len(selected),
                    "state_counts_before": store.state_counts(),
                    "runtime": runtime,
                    "max_workers": max_workers,
                    "error_action": error_action,
                    "review_capture": review_capture,
                },
            )
        except Exception as error:
            logger.warning(
                "Disposable performance invocation capture failed for %s: %s",
                invocation_id,
                error,
            )
        examples_by_id = {example.example_id: example for example in examples}
        explicit_work = tuple(
            RepeatedEvalWorkItem(
                item_id=item["example_id"],
                payload=examples_by_id[item["example_id"]],
                attempt_index=int(item["repetition_index"]),
            )
            for item in selected
        )
        work_ids = {
            (item["example_id"], int(item["repetition_index"])): item["work_item_id"]
            for item in selected
        }
        generations = {
            item["work_item_id"]: store.next_generation(item["work_item_id"])
            for item in selected
        }
        review_store = (
            LocalReviewStore(run_dir, run_id=run_id)
            if review_capture == "full" and selected
            else None
        )
        if review_store is not None:
            review_store.initialize(
                run_spec_sha256=run_spec_sha256,
                mode="full",
            )

        def commit_terminal(record: Any) -> None:
            work_item = record.work_item
            work_item_id = work_ids[(work_item.item_id, work_item.attempt_index)]
            generation = generations[work_item_id]
            completed_at = datetime.now(timezone.utc)
            started_at = completed_at - timedelta(
                seconds=max(0.0, float(record.duration_seconds))
            )
            review_payload = record.result.metadata.pop("_ephemeral_review", None)
            execution_id = f"{work_item_id}.{generation}"
            store.commit_attempt(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "work_item_id": work_item_id,
                    "example_id": work_item.item_id,
                    "repetition_index": work_item.attempt_index,
                    "execution_id": execution_id,
                    "generation": generation,
                    "invocation_id": invocation_id,
                    "attempt": eval_attempt_to_dict(record.result),
                }
            )
            try:
                store.commit_performance(
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "work_item_id": work_item_id,
                        "execution_id": execution_id,
                        "generation": generation,
                        "invocation_id": invocation_id,
                        "started_at_utc": started_at.isoformat(
                            timespec="microseconds"
                        ),
                        "completed_at_utc": completed_at.isoformat(
                            timespec="microseconds"
                        ),
                        "executor_duration_seconds": record.duration_seconds,
                        "metrics": eval_attempt_performance_to_dict(record.result),
                    }
                )
            except Exception as error:
                logger.warning(
                    "Disposable performance capture failed for %s: %s",
                    execution_id,
                    error,
                )
            if review_store is not None:
                source_artifacts = [
                    benchmark_source_reference(
                        artifact_kind=artifact.artifact_kind,
                        object_key=artifact.object_key,
                        content_type=artifact.content_type,
                        byte_size=artifact.byte_size,
                        content_sha256=artifact.content_sha256,
                        source_snapshot_id=work_item.payload.source_snapshot_id,
                    )
                    for artifact in work_item.payload.raw_artifacts
                ]
                body = review_payload if isinstance(review_payload, dict) else {}
                try:
                    review_store.commit_execution(
                        {
                            "run_id": run_id,
                            "work_item_id": work_item_id,
                            "execution_id": execution_id,
                            "example_id": work_item.item_id,
                            "repetition_index": work_item.attempt_index,
                            "generation": generation,
                            "invocation_id": invocation_id,
                            "agent_version_id": agent_reference.agent_version_id,
                            "benchmark": {
                                "key": benchmark.benchmark_key,
                                "version_id": benchmark.benchmark_version_id,
                                "version_number": benchmark.version_number,
                                "source_snapshot_id": (
                                    work_item.payload.source_snapshot_id
                                ),
                            },
                            "capture_status": body.get(
                                "capture_status",
                                "complete" if body else "failed",
                            ),
                            "capture_errors": body.get(
                                "capture_errors",
                                []
                                if body
                                else ["Pipeline returned no execution review."],
                            ),
                            "source_evidence": source_artifacts,
                            "pipeline": body.get("pipeline", {}),
                            "model_interactions": body.get("model_interactions", {}),
                            "attempt_outcome": {
                                "execution_status": (
                                    record.result.execution_status.value
                                ),
                                "output_contract_status": (
                                    record.result.output_contract_status.value
                                ),
                                "scoring_status": record.result.scoring_status.value,
                                "complete_evaluation_correct": (
                                    record.result.complete_evaluation_correct
                                ),
                                "failure_type": (
                                    record.result.failure_type.value
                                    if record.result.failure_type is not None
                                    else None
                                ),
                            },
                        }
                    )
                except Exception as error:
                    logger.warning(
                        "Review capture failed for %s: %s", execution_id, error
                    )
                    try:
                        review_store.record_failure(
                            execution_id=execution_id,
                            work_item_id=work_item_id,
                            error=error,
                        )
                    except Exception as observation_error:
                        logger.warning(
                            "Review failure observation failed for %s: %s",
                            execution_id,
                            observation_error,
                        )

        def finalize_review_capture() -> None:
            if review_store is None:
                return
            expected_execution_ids = [
                str(item["execution_id"]) for item in store.read_attempt_records()
            ]
            review_store.finalize(expected_execution_ids=expected_execution_ids)

        try:
            with _cooperative_signal_cancellation() as should_cancel:
                _run_all_examples(
                    examples,
                    pipeline_args=pipeline_args,
                    preflight=preflight,
                    runs_per_example=runs_per_example,
                    runtime=runtime,
                    max_workers=max_workers,
                    error_action=error_action,
                    progress_interval_seconds=progress_interval_seconds,
                    work_items=explicit_work,
                    on_completed=commit_terminal,
                    should_cancel=should_cancel,
                )
        except BaseException as error:
            try:
                finalize_review_capture()
            except Exception as review_error:
                logger.warning("Review capture finalization failed: %s", review_error)
            interrupted = isinstance(error, KeyboardInterrupt)
            if interrupted:
                logger.error(
                    "INTERRUPTED RUN: %s | state=%s | manifest=%s",
                    run_id,
                    store.state_counts(),
                    store.manifest_path,
                )
            try:
                store.write_invocation_event(
                    invocation_id=invocation_id,
                    event="interrupted" if interrupted else "failed",
                    payload={
                        "duration_seconds": time.monotonic() - invocation_started,
                        "selected_work_items": len(selected),
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "state_counts_after": store.state_counts(),
                    },
                )
            except Exception as performance_error:
                logger.warning(
                    "Disposable performance invocation finalization failed for %s: %s",
                    invocation_id,
                    performance_error,
                )
            raise
        invocation_duration = time.monotonic() - invocation_started
        try:
            store.write_invocation_event(
                invocation_id=invocation_id,
                event="completed",
                payload={
                    "duration_seconds": invocation_duration,
                    "selected_work_items": len(selected),
                    "state_counts_after": store.state_counts(),
                },
            )
        except Exception as error:
            logger.warning(
                "Disposable performance invocation finalization failed for %s: %s",
                invocation_id,
                error,
            )

        completed_at = datetime.now(timezone.utc)
        result_path = store.materialize_result(
            completed_at_utc=completed_at.isoformat(timespec="seconds"),
            latest_invocation_id=invocation_id,
        )
        try:
            store.materialize_performance()
        except Exception as error:
            logger.warning(
                "Disposable performance summary materialization failed for %s: %s",
                run_id,
                error,
            )
        if review_store is not None:
            try:
                finalize_review_capture()
                materialize_review_index(run_dir)
            except Exception as error:
                logger.warning("Review index materialization failed: %s", error)
        return result_path


def _select_examples(
    examples: tuple[BenchmarkExample, ...],
    *,
    profile: EvaluationProfile,
    example_ids: list[str] | None,
    unit_ids: list[str] | None,
    label_filters: dict[str, list[JsonScalar]] | None,
    slice_keys: list[str] | None,
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
    for path_text, accepted_values in (label_filters or {}).items():
        path = tuple(part for part in path_text.split(".") if part)
        if not path:
            raise ValueError("Label filter paths must not be empty.")
        selected = [
            example
            for example in selected
            if _path_matches(example.approved_label_payload, path, accepted_values)
        ]
    if slice_keys:
        known = {item.key for item in profile.slices}
        requested_slices = {key.strip() for key in slice_keys}
        unknown = requested_slices - known
        if unknown:
            raise ValueError("Unknown evaluation slices: " + ", ".join(sorted(unknown)))
        selected = [
            example
            for example in selected
            if requested_slices.intersection(slice_memberships(example, profile))
        ]
    return selected


def _build_resolved_run_spec(
    *,
    yaml_path: Path,
    evaluation_profile_path: Path,
    benchmark: BenchmarkVersion,
    preflight: EvaluationPreflight,
    examples: list[BenchmarkExample],
    scope: str,
    scope_definition: dict[str, Any],
    runs_per_example: int,
    runtime: RuntimeType,
    max_workers: int,
    error_action: ErrorActionType,
    ai_model: str,
    ai_reasoning_effort: str | None,
    agent_reference: AgentVersionReference,
    configuration_dimensions: dict[str, JsonScalar],
    evidence_contract: dict[str, str],
) -> dict[str, Any]:
    """Resolve every semantic execution/scoring input before model calls."""
    pipeline_config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(pipeline_config, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    root = repository_root(Path.cwd())
    source_manifest = build_source_manifest(
        root=root,
        required_paths=(yaml_path, evaluation_profile_path),
    )
    profile = preflight.profile
    model_definition = resolve_model_definition(ai_model)
    normalized_scope = {
        "token": scope,
        "example_ids": sorted(example.example_id for example in examples),
        "selection": scope_definition,
    }
    resolved_scoring_contract = {
        "evaluation_profile_sha256": profile.content_sha256,
        "grader_set_sha256": profile.grader_set_sha256,
        "slice_definition_sha256": profile.slice_definition_sha256,
        "label_schema_sha256": sorted(
            schema.content_sha256 for schema in benchmark.label_schemas
        ),
    }
    resolved_scoring_contract["content_sha256"] = canonical_sha256(
        resolved_scoring_contract
    )
    return {
        "execution_contract_version": 1,
        "eval_schema_version": 1,
        "project_key": benchmark.project_key,
        "benchmark": {
            "name": benchmark.benchmark_name,
            "key": benchmark.benchmark_key,
            "version_id": benchmark.benchmark_version_id,
            "version_number": benchmark.version_number,
            "published_at": benchmark.published_at.isoformat(),
            "source_state_sha256": benchmark.source_state_sha256,
            "published_contract_schema_version": (
                benchmark.published_contract_schema_version
            ),
            "label_schemas": [
                {
                    "schema_version_id": schema.schema_version_id,
                    "schema_key": schema.schema_key,
                    "version": schema.version,
                    "content_sha256": schema.content_sha256,
                }
                for schema in sorted(
                    benchmark.label_schemas,
                    key=lambda item: item.schema_version_id,
                )
            ],
        },
        "scope": {
            **normalized_scope,
            "content_sha256": canonical_sha256(normalized_scope),
        },
        "pipeline": {
            "name": pipeline_config.get("name"),
            "version": pipeline_config.get("version"),
            "content_sha256": canonical_sha256(pipeline_config),
            "resolved_override_sha256": canonical_sha256(
                {
                    "pipeline": pipeline_config,
                    "ai_model": ai_model,
                    "ai_reasoning_effort": ai_reasoning_effort,
                }
            ),
        },
        "agent": {
            **agent_reference.model_dump(mode="json"),
        },
        "model": {
            "provider": _extract_provider(ai_model),
            "id": ai_model,
            "api": model_definition.api,
            "reasoning_effort": ai_reasoning_effort,
            "pricing": (_pricing_snapshot(model_definition)),
        },
        "evidence": {
            **evidence_contract,
            "benchmark_source_state_sha256": benchmark.source_state_sha256,
        },
        "scoring": resolved_scoring_contract,
        "runs_per_example": runs_per_example,
        "execution": {
            "runtime": runtime,
            "max_workers": max_workers,
            "error_action": error_action,
            "ai_execution_policies": _ai_execution_policies(
                yaml_path,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
            ),
        },
        "configuration_dimensions": configuration_dimensions,
        "source_manifest": source_manifest,
    }


def _path_matches(
    payload: dict[str, Any], path: tuple[str, ...], accepted: list[JsonScalar]
) -> bool:
    found, actual = read_path(payload, path)
    return found and any(
        type(actual) is type(value) and actual == value for value in accepted
    )


def _run_all_examples(
    examples: list[BenchmarkExample],
    *,
    pipeline_args: _PipelineArgs,
    preflight: EvaluationPreflight,
    runs_per_example: int,
    runtime: RuntimeType,
    max_workers: int,
    error_action: ErrorActionType,
    progress_interval_seconds: float,
    work_items: tuple[RepeatedEvalWorkItem[BenchmarkExample], ...] | None = None,
    on_completed: Callable[[Any], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[_ExampleEvalResult]:
    planned_count = (
        len(work_items) if work_items is not None else len(examples) * runs_per_example
    )
    tracker = (
        _EvalProgressTracker(
            total_runs=planned_count,
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
        run_once = partial(
            _run_work_item,
            pipeline_args=pipeline_args,
            progress_tracker=tracker,
        )
        if work_items is None:
            records = executor.run(
                examples,
                attempts_per_item=runs_per_example,
                get_item_id=lambda example: example.example_id,
                run_once=run_once,
                build_failure_result=_build_failure_attempt,
                has_error=lambda attempt: attempt.has_error,
                on_completed=on_completed,
                should_cancel=should_cancel,
            )
        else:
            records = executor.run_work_items(
                work_items,
                run_once=run_once,
                build_failure_result=_build_failure_attempt,
                has_error=lambda attempt: attempt.has_error,
                on_completed=on_completed,
                should_cancel=should_cancel,
            )
    finally:
        if tracker is not None:
            tracker.stop()
    attempts_by_example: dict[str, list[EvalAttempt]] = {}
    for record in records:
        attempts_by_example.setdefault(record.work_item.item_id, []).append(
            record.result
        )
    return [
        _ExampleEvalResult(
            example=example,
            slice_keys=preflight.example_slices[example.example_id],
            attempts=tuple(attempts_by_example.get(example.example_id, [])),
        )
        for example in examples
    ]


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
            review_capture=pipeline_args.review_capture,
        )
        duration_seconds = _receipt_duration(receipt, started_at=started_at)
        stage_durations = _stage_durations(receipt)
        telemetry = _receipt_execution_telemetry(receipt)
        if _receipt_has_failure(receipt):
            receipt_error = _receipt_error(receipt)
            attempt = _failed_attempt(
                message=receipt_error,
                failure_type=_classify_failure_message(
                    receipt_error, default=FailureType.PIPELINE_ERROR
                ),
                duration_seconds=duration_seconds,
                stage_durations_seconds=stage_durations,
                work_item=work_item,
                artifacts={
                    "failure_details": _receipt_failure_details(receipt),
                    **_telemetry_artifacts(
                        telemetry,
                        ai_model=pipeline_args.ai_model,
                    ),
                },
            )
        elif receipt.act_receipt is None or not receipt.act_receipt.success:
            attempt = _failed_attempt(
                message="Pipeline did not produce a successful act-stage receipt.",
                failure_type=FailureType.PIPELINE_ERROR,
                duration_seconds=duration_seconds,
                stage_durations_seconds=stage_durations,
                work_item=work_item,
            )
        else:
            attempt = score_receipt_metadata(
                metadata=receipt.act_receipt.metadata,
                expected_identity={
                    "example_id": work_item.payload.example_id,
                    "benchmark_key": pipeline_args.benchmark.benchmark_key,
                    "benchmark_version_id": pipeline_args.benchmark.benchmark_version_id,
                    "benchmark_version_number": pipeline_args.benchmark.version_number,
                    "source_snapshot_id": work_item.payload.source_snapshot_id,
                },
                example=work_item.payload,
                profile=pipeline_args.profile,
                grader_registry=pipeline_args.grader_registry,
                duration_seconds=duration_seconds,
                stage_durations_seconds=stage_durations,
                attempt_metadata=_attempt_metadata(work_item),
            )
            attempt.artifacts.update(
                _telemetry_artifacts(telemetry, ai_model=pipeline_args.ai_model)
            )
    except Exception as exception:
        if progress_tracker is not None:
            progress_tracker.raised(work_item, exception)
        raise
    attempt.artifacts.setdefault(
        "retry_telemetry",
        {
            "availability": "unavailable",
            "reason": "Observed backend retry events were not present on the receipt.",
        },
    )
    if pipeline_args.review_capture:
        attempt.metadata["_ephemeral_review"] = _receipt_review_payload(receipt)
    attempt.artifacts.setdefault(
        "cost",
        _build_cost_observation(
            ai_model=pipeline_args.ai_model,
            usage=(
                attempt.artifacts.get("usage")
                if isinstance(attempt.artifacts.get("usage"), dict)
                else None
            ),
            provider_cost=None,
        ),
    )
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
        failure_type=FailureType.CANCELLED
        if cancelled
        else _classify_exception(exception),
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
    retained_artifacts = {
        "retry_telemetry": {
            "availability": "unavailable",
            "reason": "Execution failed before observed retry telemetry was retained.",
        },
        "cost": {
            "status": "unavailable",
            "actual": None,
            "estimated": None,
            "unpriced_usage": {},
            "reason": "Execution failed before billable usage was retained.",
        },
    }
    retained_artifacts.update(artifacts or {})
    return EvalAttempt(
        execution_status=(
            ExecutionStatus.CANCELLED if cancelled else ExecutionStatus.FAILED
        ),
        output_contract_status=OutputContractStatus.NOT_PRODUCED,
        scoring_status=ScoringStatus.NOT_SCORED,
        error=message,
        failure_type=failure_type,
        duration_seconds=duration_seconds,
        stage_durations_seconds=stage_durations_seconds,
        artifacts=retained_artifacts,
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
        default=FailureType.EXECUTOR_ERROR,
    )


def _classify_failure_message(message: str, *, default: FailureType) -> FailureType:
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


def _receipt_has_failure(receipt: Any) -> bool:
    return any(
        stage is not None and not stage.success
        for stage in (
            receipt.retrieve_receipt,
            receipt.process_receipt,
            receipt.act_receipt,
        )
    )


def _receipt_failure_details(receipt: Any) -> dict[str, Any]:
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


def _receipt_execution_telemetry(receipt: Any) -> dict[str, Any] | None:
    """Merge retained observations, preferring values from later stages."""
    merged: dict[str, Any] = {}
    for stage_name in ("retrieve", "process", "act"):
        stage = receipt.get_stage_receipt(stage_name)
        if stage is None:
            continue
        telemetry = stage.metadata.get("execution_telemetry")
        if isinstance(telemetry, dict):
            merged.update(
                {key: value for key, value in telemetry.items() if value is not None}
            )
    return merged or None


def _receipt_review_payload(receipt: Any) -> dict[str, Any]:
    """Build a transient, JSON-safe pipeline and model review payload."""
    process = receipt.get_stage_receipt("process")
    interactions = (
        process.metadata.get("execution_review")
        if process is not None and isinstance(process.metadata, dict)
        else None
    )
    processor_reviews = (
        interactions.get("processors", {}) if isinstance(interactions, dict) else {}
    )
    partial_processors = [
        key
        for key, value in processor_reviews.items()
        if isinstance(value, dict) and value.get("capture_status") == "partial"
    ]
    stages: list[dict[str, Any]] = []
    for stage_name in ("retrieve", "process", "act"):
        stage = receipt.get_stage_receipt(stage_name)
        if stage is None:
            continue
        selected_metadata: dict[str, Any] = {}
        if stage_name == "retrieve":
            for key in (
                "example_id",
                "benchmark_key",
                "benchmark_version_id",
                "benchmark_version_number",
                "source_snapshot_id",
                "source_snapshot_content_sha256",
                "artifact_integrity",
                "row_counts",
            ):
                if key in stage.metadata:
                    selected_metadata[key] = stage.metadata[key]
        elif stage_name == "act":
            for key in (
                "example_id",
                "benchmark_key",
                "benchmark_version_id",
                "benchmark_version_number",
                "source_snapshot_id",
                "agent_output",
            ):
                if key in stage.metadata:
                    selected_metadata[key] = stage.metadata[key]
        stages.append(
            {
                "stage": stage_name,
                "success": stage.success,
                "correlation_id": stage.correlation_id,
                "duration_seconds": stage.execution_time_seconds,
                "error": stage.error,
                "metadata": _review_json_value(selected_metadata),
            }
        )
    return {
        "capture_status": (
            "partial"
            if not isinstance(interactions, dict) or partial_processors
            else "complete"
        ),
        "capture_errors": (
            [
                "Partial model interaction capture: "
                + ", ".join(sorted(partial_processors))
            ]
            if partial_processors
            else []
            if isinstance(interactions, dict)
            else ["No mi.ai model interaction was exposed on the process receipt."]
        ),
        "pipeline": {
            "pipeline_id": getattr(receipt, "pipeline_id", None),
            "correlation_id": getattr(receipt, "correlation_id", None),
            "success": getattr(receipt, "success", None),
            "stages": stages,
        },
        "model_interactions": _review_json_value(interactions or {}),
    }


def _review_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _review_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_review_json_value(item) for item in value]
    return {
        "unavailable": True,
        "reason": f"Unsupported review value type: {type(value).__name__}",
    }


def _telemetry_artifacts(
    telemetry: dict[str, Any] | None, *, ai_model: str | None
) -> dict[str, Any]:
    if telemetry is None:
        return {}
    output: dict[str, Any] = {}
    usage = telemetry.get("usage")
    if isinstance(usage, dict):
        output["usage"] = usage
    retry_telemetry = telemetry.get("retry_telemetry")
    if isinstance(retry_telemetry, dict):
        output["retry_telemetry"] = retry_telemetry
    performance = telemetry.get("performance")
    if isinstance(performance, dict):
        output["performance"] = performance
    provider_cost = telemetry.get("cost")
    output["cost"] = _build_cost_observation(
        ai_model=ai_model,
        usage=usage if isinstance(usage, dict) else None,
        provider_cost=provider_cost if isinstance(provider_cost, dict) else None,
    )
    return output


def _build_cost_observation(
    *,
    ai_model: str | None,
    usage: dict[str, Any] | None,
    provider_cost: dict[str, Any] | None,
) -> dict[str, Any]:
    """Label provider actuals distinctly from frozen-catalog estimates."""
    if provider_cost is not None and isinstance(
        provider_cost.get("amount"), (int, float)
    ):
        return {
            "status": "actual",
            "actual": provider_cost,
            "estimated": None,
            "unpriced_usage": {},
        }
    if usage is None:
        return {
            "status": "unavailable",
            "actual": None,
            "estimated": None,
            "unpriced_usage": {},
            "reason": "Token usage is unavailable.",
        }
    definition = resolve_model_definition(ai_model)
    pricing = definition.pricing
    if pricing is None:
        return {
            "status": "unavailable",
            "actual": None,
            "estimated": None,
            "unpriced_usage": {},
            "reason": "No frozen pricing record is configured for this model.",
        }
    cached = usage.get("cached_input_tokens", 0)
    reasoning = usage.get("reasoning_tokens", 0)
    raw_input = usage.get("input_tokens", 0)
    raw_output = usage.get("output_tokens", 0)
    billable_usage = {
        "input_tokens": (
            max(0, raw_input - cached)
            if isinstance(raw_input, int) and isinstance(cached, int)
            else raw_input
        ),
        "output_tokens": (
            max(0, raw_output - reasoning)
            if isinstance(raw_output, int) and isinstance(reasoning, int)
            else raw_output
        ),
        "cached_input_tokens": cached,
        "reasoning_tokens": reasoning,
    }
    token_rates = {
        "input_tokens": pricing.input_per_million_tokens,
        "output_tokens": pricing.output_per_million_tokens,
        "cached_input_tokens": pricing.cached_input_per_million_tokens,
        "reasoning_tokens": pricing.reasoning_per_million_tokens,
    }
    amount = 0.0
    unpriced: dict[str, int] = {}
    priced_usage: dict[str, int] = {}
    for key, rate in token_rates.items():
        tokens = billable_usage.get(key)
        if not isinstance(tokens, int) or tokens <= 0:
            continue
        if rate is None:
            unpriced[key] = tokens
        else:
            priced_usage[key] = tokens
            amount += tokens / 1_000_000 * rate
    return {
        "status": "estimated_partial" if unpriced else "estimated_complete",
        "actual": None,
        "estimated": {
            "amount": amount,
            "currency": pricing.currency,
            "pricing_version": pricing.version,
            "pricing": pricing.to_dict(),
            "pricing_sha256": canonical_sha256(pricing.to_dict()),
            "priced_usage": priced_usage,
        },
        "unpriced_usage": unpriced,
    }


def _build_summary(
    results: list[_ExampleEvalResult],
    *,
    profile: EvaluationProfile,
    runs_per_example: int,
) -> dict[str, Any]:
    attempts = [attempt for result in results for attempt in result.attempts]
    planned_runs = len(results) * runs_per_example
    return {
        "accuracy": _build_accuracy(results, profile=profile, include_slices=True),
        "reliability": build_reliability_summary(
            attempts,
            planned_runs=planned_runs,
        ),
        "scoring_coverage": build_scoring_coverage(
            attempts,
            planned_runs=planned_runs,
        ),
        "execution_recovery": {
            "logical_work_items": planned_runs,
            "recorded_work_items": len(attempts),
            "missing_work_items": planned_runs - len(attempts),
            "execution_generations": sum(
                len(attempt.metadata.get("execution_history", ()))
                for attempt in attempts
            ),
            "rerun_generations": sum(
                max(0, len(attempt.metadata.get("execution_history", ())) - 1)
                for attempt in attempts
            ),
        },
        "usage": _build_usage_summary(attempts),
        "cost": _build_cost_summary(attempts),
        "nondeterminism": _build_nondeterminism_summary(results),
        "total_examples": len(results),
        "runs_per_example": runs_per_example,
    }


def _build_accuracy(
    results: list[_ExampleEvalResult],
    *,
    profile: EvaluationProfile,
    include_slices: bool,
) -> dict[str, Any]:
    attempts = [attempt for result in results for attempt in result.attempts]
    scored = [attempt for attempt in attempts if attempt.contributes_to_accuracy]
    complete = metric_counts(
        attempt.complete_evaluation_correct is True for attempt in scored
    ).to_dict()
    by_field: dict[str, Any] = {}
    for field in profile.output_fields:
        if field.evaluation is None:
            continue
        observations = [
            attempt.evaluations[field.key]
            for attempt in scored
            if field.key in attempt.evaluations
        ]
        expected_groups: dict[str, list[bool]] = {}
        confidence_groups: dict[str, list[bool]] = {}
        for attempt in scored:
            evaluation = attempt.evaluations.get(field.key)
            if evaluation is None:
                continue
            expected_groups.setdefault(_scalar_key(evaluation.expected), []).append(
                evaluation.correct
            )
            confidence = attempt.confidence_values.get(field.key)
            if confidence is not None:
                confidence_groups.setdefault(_scalar_key(confidence), []).append(
                    evaluation.correct
                )
        by_field[field.key] = {
            **metric_counts(item.correct for item in observations).to_dict(),
            "by_expected_value": {
                key: metric_counts(values).to_dict()
                for key, values in sorted(expected_groups.items())
            },
            "by_confidence": {
                key: metric_counts(values).to_dict()
                for key, values in sorted(confidence_groups.items())
            },
        }
    output: dict[str, Any] = {
        "complete_evaluation": complete,
        "by_field": by_field,
    }
    if include_slices:
        output["by_slice"] = {
            item.key: _build_accuracy(
                [result for result in results if item.key in result.slice_keys],
                profile=profile,
                include_slices=False,
            )
            for item in profile.slices
        }
    return output


def _scalar_key(value: JsonScalar) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True)


def _build_usage_summary(attempts: list[EvalAttempt]) -> dict[str, Any]:
    observations = [
        usage
        for attempt in attempts
        if isinstance((usage := attempt.get_artifact("usage")), dict)
    ]
    totals = {
        key: sum(
            int(observation.get(key, 0))
            for observation in observations
            if isinstance(observation.get(key), int)
        )
        for key in (
            "requests",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "tool_calls",
            "output_validation_attempts",
        )
    }
    return {
        "availability": "available" if observations else "unavailable",
        "attempts_with_usage": len(observations),
        "recorded_attempts": len(attempts),
        "totals": totals if observations else None,
    }


def _build_cost_summary(attempts: list[EvalAttempt]) -> dict[str, Any]:
    observations = [
        cost
        for attempt in attempts
        if isinstance((cost := attempt.get_artifact("cost")), dict)
    ]
    status_counts: dict[str, int] = {}
    actual_by_currency: dict[str, float] = {}
    estimated_by_currency: dict[str, float] = {}
    complete_unit_costs: dict[str, list[float]] = {}
    for observation in observations:
        status = str(observation.get("status", "unavailable"))
        status_counts[status] = status_counts.get(status, 0) + 1
        for field, totals in (
            ("actual", actual_by_currency),
            ("estimated", estimated_by_currency),
        ):
            value = observation.get(field)
            if not isinstance(value, dict):
                continue
            amount = value.get("amount")
            currency = value.get("currency")
            if isinstance(amount, (int, float)) and isinstance(currency, str):
                totals[currency] = totals.get(currency, 0.0) + float(amount)
                if status in {"actual", "estimated_complete"}:
                    complete_unit_costs.setdefault(currency, []).append(float(amount))
    complete_count = sum(
        status_counts.get(status, 0) for status in ("actual", "estimated_complete")
    )
    partial_count = status_counts.get("estimated_partial", 0)
    unusable_count = (
        len(attempts)
        - len(observations)
        + status_counts.get("unavailable", 0)
        + sum(
            count
            for status, count in status_counts.items()
            if status
            not in {"actual", "estimated_complete", "estimated_partial", "unavailable"}
        )
    )
    return {
        "attempts_with_cost_observations": len(observations),
        "recorded_attempts": len(attempts),
        "units_with_complete_cost_observations": complete_count,
        "units_with_partial_pricing": partial_count,
        "units_without_usable_cost_information": unusable_count,
        "status_counts": dict(sorted(status_counts.items())),
        "actual_by_currency": dict(sorted(actual_by_currency.items())),
        "estimated_by_currency": dict(sorted(estimated_by_currency.items())),
        "complete_unit_cost_by_currency": {
            currency: _cost_distribution(values)
            for currency, values in sorted(complete_unit_costs.items())
        },
    }


def _cost_distribution(values: list[float]) -> dict[str, float | int]:
    """Summarize complete per-unit cost observations with interpolated percentiles."""
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "total": sum(ordered),
        "average": sum(ordered) / len(ordered),
        "p5": _percentile(ordered, 0.05),
        "p95": _percentile(ordered, 0.95),
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    if not ordered:
        raise ValueError("A percentile requires at least one observation.")
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _build_retry_summary(attempts: list[EvalAttempt]) -> dict[str, Any]:
    observations = [
        telemetry
        for attempt in attempts
        if isinstance((telemetry := attempt.get_artifact("retry_telemetry")), dict)
    ]
    availability_counts: dict[str, int] = {}
    for telemetry in observations:
        availability = str(telemetry.get("availability", "unavailable"))
        availability_counts[availability] = availability_counts.get(availability, 0) + 1
    transport_counts = [
        int(item["observed_transport_attempts"])
        for item in observations
        if isinstance(item.get("observed_transport_attempts"), int)
    ]
    retry_categories: dict[str, int] = {}
    for item in observations:
        categories = item.get("observed_transport_retry_categories")
        if not isinstance(categories, dict):
            continue
        for category, count in categories.items():
            if isinstance(count, int):
                retry_categories[str(category)] = (
                    retry_categories.get(str(category), 0) + count
                )
    return {
        "attempts_with_retry_telemetry": len(observations),
        "recorded_attempts": len(attempts),
        "availability_counts": dict(sorted(availability_counts.items())),
        "observed_model_requests": sum(
            int(item.get("observed_model_requests", 0))
            for item in observations
            if isinstance(item.get("observed_model_requests"), int)
        ),
        "observed_tool_calls": sum(
            int(item.get("observed_tool_calls", 0))
            for item in observations
            if isinstance(item.get("observed_tool_calls"), int)
        ),
        "observed_output_validation_attempts": sum(
            int(item.get("observed_output_validation_attempts", 0))
            for item in observations
            if isinstance(item.get("observed_output_validation_attempts"), int)
        ),
        "observed_transport_attempts": (
            sum(transport_counts) if transport_counts else None
        ),
        "observed_transport_retry_categories": dict(sorted(retry_categories.items())),
    }


def _build_nondeterminism_summary(
    results: list[_ExampleEvalResult],
) -> dict[str, Any]:
    by_example: dict[str, Any] = {}
    eligible = 0
    unanimous = 0
    for result in results:
        scored = [
            attempt for attempt in result.attempts if attempt.contributes_to_accuracy
        ]
        if len(scored) < 2:
            continue
        eligible += 1
        output_counts: dict[str, int] = {}
        correctness_counts = {"correct": 0, "incorrect": 0}
        for attempt in scored:
            output_key = canonical_sha256(attempt.actual_values)
            output_counts[output_key] = output_counts.get(output_key, 0) + 1
            correctness_counts[
                "correct" if attempt.complete_evaluation_correct else "incorrect"
            ] += 1
        if len(output_counts) == 1:
            unanimous += 1
        by_example[result.example.example_id] = {
            "scored_repetitions": len(scored),
            "distinct_output_count": len(output_counts),
            "output_distribution": dict(sorted(output_counts.items())),
            "complete_correctness_distribution": correctness_counts,
        }
    return {
        "examples_with_multiple_scored_repetitions": eligible,
        "unanimous_output_examples": unanimous,
        "unstable_output_examples": eligible - unanimous,
        "output_agreement_rate": None if eligible == 0 else unanimous / eligible,
        "by_example": by_example,
    }


def _build_run_config(
    *,
    yaml_path: Path,
    benchmark: BenchmarkVersion,
    preflight: EvaluationPreflight,
    scope: str,
    runs_per_example: int,
    runtime: RuntimeType,
    max_workers: int,
    error_action: ErrorActionType,
    progress_interval_seconds: float,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
    agent_reference: AgentVersionReference,
    configuration_dimensions: dict[str, JsonScalar],
    benchmark_source: str,
    completed_at: datetime,
) -> dict[str, Any]:
    profile = preflight.profile
    model_definition = resolve_model_definition(ai_model)
    pipeline_config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(pipeline_config, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    dimensions = {
        "benchmark": {
            "project_key": benchmark.project_key,
            "name": benchmark.benchmark_name,
            "key": benchmark.benchmark_key,
            "version_id": benchmark.benchmark_version_id,
            "version": benchmark.version_number,
            "published_at": benchmark.published_at.isoformat(),
            "source_state_sha256": benchmark.source_state_sha256,
            "published_contract_schema_version": (
                benchmark.published_contract_schema_version
            ),
            "source": benchmark_source,
        },
        "evaluation_profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "schema_version": profile.schema_version,
            "path": preflight.profile_path,
            "content_sha256": profile.content_sha256,
            "grader_set_sha256": profile.grader_set_sha256,
            "slice_definition_sha256": profile.slice_definition_sha256,
        },
        "agent": {
            **agent_reference.model_dump(mode="json"),
        },
        "pipeline": {
            "path": str(yaml_path),
            "content_sha256": canonical_sha256(pipeline_config),
        },
        "model": {
            "provider": _extract_provider(ai_model),
            "id": ai_model,
            "api": model_definition.api,
            "reasoning_effort": ai_reasoning_effort,
            "pricing": (_pricing_snapshot(model_definition)),
        },
        "scoring": {
            "grader_set_sha256": profile.grader_set_sha256,
            "slice_definition_sha256": profile.slice_definition_sha256,
            "resolved_contract_sha256": canonical_sha256(
                {
                    "profile": profile.content_sha256,
                    "graders": profile.grader_set_sha256,
                    "slices": profile.slice_definition_sha256,
                    "label_schemas": sorted(
                        schema.content_sha256 for schema in benchmark.label_schemas
                    ),
                }
            ),
        },
        "execution": {
            "runtime": runtime,
            "max_workers": max_workers,
            "error_action": error_action,
            "ai_execution_policies": _ai_execution_policies(
                yaml_path,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
            ),
        },
        "configuration": configuration_dimensions,
    }
    return {
        "schema_version": 1,
        "label_schemas": [
            {
                "schema_version_id": schema.schema_version_id,
                "schema_key": schema.schema_key,
                "version": schema.version,
                "content_sha256": schema.content_sha256,
            }
            for schema in benchmark.label_schemas
        ],
        "dimensions": dimensions,
        "graders": [
            field.evaluation.grader.model_dump(mode="json")
            for field in profile.output_fields
            if field.evaluation is not None
        ],
        "slices": [item.model_dump(mode="json") for item in profile.slices],
        "slice_counts": preflight.slice_counts,
        "scope": scope,
        "runs_per_example": runs_per_example,
        "progress_interval_seconds": progress_interval_seconds,
        "completed_at_utc": completed_at.isoformat(timespec="seconds"),
    }


def _bind_run_config_to_manifest(
    run_config: dict[str, Any],
    *,
    run_id: str,
    run_spec_sha256: str,
    run_spec: dict[str, Any],
    manifest_created_at: str,
) -> None:
    """Add immutable manifest identity to the schema-v1 run metadata."""
    run_config.update(
        {
            "run_id": run_id,
            "run_spec_sha256": run_spec_sha256,
            "run_created_at_utc": manifest_created_at,
            "agent_version_resolver_contract_version": 1,
            "selected_example_scope_sha256": run_spec["scope"]["content_sha256"],
        }
    )
    run_config["dimensions"].update(
        {
            "source": {
                "content_manifest_sha256": run_spec["source_manifest"][
                    "content_sha256"
                ],
                "git_revision": run_spec["source_manifest"]["git_revision"],
                "tree_state": run_spec["source_manifest"]["source_tree_state"],
            },
            "evidence": {
                **run_spec["evidence"],
                "source": "azure_blob",
            },
            "harness": {
                "execution_contract_version": run_spec["execution_contract_version"],
                "eval_schema_version": 1,
            },
        }
    )


def _build_examples(
    results: list[_ExampleEvalResult], *, profile: EvaluationProfile
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for result in results:
        output.append(
            {
                "example_id": result.example.example_id,
                "unit_id": result.example.unit_id,
                "decision_timestamp": result.example.decision_timestamp.isoformat(),
                "source_snapshot_id": result.example.source_snapshot_id,
                "raw_snapshot_content_sha256": (
                    result.example.raw_snapshot_content_sha256
                ),
                "raw_source_kind": result.example.raw_source_kind,
                "raw_captured_at": result.example.raw_captured_at.isoformat(),
                "raw_window_start": (
                    result.example.raw_window_start.isoformat()
                    if result.example.raw_window_start is not None
                    else None
                ),
                "raw_window_end": (
                    result.example.raw_window_end.isoformat()
                    if result.example.raw_window_end is not None
                    else None
                ),
                "raw_known_gaps": list(result.example.raw_known_gaps),
                "raw_artifacts": [
                    artifact.model_dump(mode="json")
                    for artifact in result.example.raw_artifacts
                ],
                "label_schema_version_id": result.example.label_schema_version_id,
                "benchmark_labels": result.example.approved_label_payload,
                "slice_keys": list(result.slice_keys),
                "metadata": result.example.example_metadata,
                "published_review_context": (
                    result.example.published_review_context.model_dump(mode="json")
                ),
            }
        )
    return output


def _scope_token(
    *,
    example_ids: list[str] | None,
    unit_ids: list[str] | None,
    label_filters: dict[str, list[JsonScalar]] | None,
    slice_keys: list[str] | None,
) -> str:
    if example_ids:
        return "example_subset"
    if unit_ids:
        return "unit_subset"
    if slice_keys:
        return normalize_filename_token("_".join(sorted(slice_keys)))
    if label_filters:
        return "label_subset"
    return "all"


def _extract_provider(ai_model: str | None) -> str | None:
    return ai_model.split(":", 1)[0] if ai_model and ":" in ai_model else None


def _pricing_snapshot(model: ModelDefinition) -> dict[str, Any] | None:
    if model.pricing is None:
        return None
    payload = model.pricing.to_dict()
    return {**payload, "content_sha256": canonical_sha256(payload)}


def _validate_configuration_dimensions(
    dimensions: dict[str, JsonScalar],
) -> dict[str, JsonScalar]:
    normalized: dict[str, JsonScalar] = {}
    for raw_key, value in dimensions.items():
        key = raw_key.strip()
        if not key:
            raise ValueError("Configuration dimension keys must not be empty.")
        if key in normalized:
            raise ValueError(f"Duplicate configuration dimension {key!r}.")
        if not (value is None or isinstance(value, (str, int, float, bool))):
            raise ValueError(f"Configuration dimension {key!r} must be a JSON scalar.")
        normalized[key] = value
    return dict(sorted(normalized.items()))


def _ai_execution_policies(
    yaml_path: Path,
    *,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
) -> list[dict[str, Any]]:
    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    process_config = config.get("process", {})
    processors = (
        process_config.get("processors", []) if isinstance(process_config, dict) else []
    )
    policies: list[dict[str, Any]] = []
    for processor in processors:
        if not isinstance(processor, dict):
            continue
        processor_name = str(processor.get("processor", ""))
        if not (
            "AI" in processor_name or "Agent" in processor_name or "model" in processor
        ):
            continue
        transport_attempts = processor.get("transport_retries", 3)
        tool_retries = processor.get("tool_retries", 3)
        configured_output_retries = processor.get("output_retries")
        policies.append(
            {
                "processor": processor_name,
                "model": ai_model or processor.get("model"),
                "reasoning_effort": (
                    ai_reasoning_effort or processor.get("reasoning_effort") or "medium"
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


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate a pipeline against a published benchmark using a versioned "
            "schema-driven evaluation profile."
        )
    )
    parser.add_argument("yaml_path", nargs="?", type=Path)
    parser.add_argument("--evaluation-profile", type=Path)
    parser.add_argument("--project-key")
    parser.add_argument("--azure-postgres-host")
    parser.add_argument("--azure-postgres-database")
    parser.add_argument("--azure-postgres-user")
    parser.add_argument("--azure-storage-account-url")
    parser.add_argument("--azure-storage-container")
    parser.add_argument("--benchmark-key")
    parser.add_argument("--benchmark-version", type=int)
    parser.add_argument("--example-ids", nargs="*")
    parser.add_argument("--unit-ids", nargs="*")
    parser.add_argument(
        "--section",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "Select a named use-case section from the evaluation profile; "
            "repeat to include more than one."
        ),
    )
    parser.add_argument(
        "--all-examples",
        action="store_true",
        help="Explicitly select every example in the published benchmark version.",
    )
    parser.add_argument(
        "--label-filter",
        action="append",
        default=[],
        metavar="PATH=JSON_VALUE",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--slice", action="append", default=[], help=argparse.SUPPRESS
    )
    parser.add_argument("--runs-per-example", type=int, default=1)
    parser.add_argument(
        "--runtime",
        choices=["threaded", "serial"],
        default="threaded",
        help="Use threaded execution normally or serial execution for debugging.",
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--error-action",
        choices=["stop", "continue"],
        default="continue",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--progress-interval-seconds", type=float, default=30.0)
    parser.add_argument(
        "--review-capture",
        choices=["full", "off"],
        default="full",
        help="Capture a disposable local review bundle for executed attempts.",
    )
    parser.add_argument("--ai-model")
    parser.add_argument(
        "--compare-model",
        action="append",
        default=[],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ai-reasoning-effort", choices=["default", "low", "medium", "high"]
    )
    parser.add_argument("--agent-version-id")
    parser.add_argument("--agent-policy", type=Path)
    parser.add_argument(
        "--require-promoted-agent-version",
        action="store_true",
        help="Reject a run unless its exact resolved version is promoted locally.",
    )
    parser.add_argument(
        "--resume-mode",
        choices=["missing", "missing-or-cancelled", "failed", "missing-or-failed"],
        default="missing",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--rerun-failure-type",
        action="append",
        default=[],
        choices=[item.value for item in FailureType],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--run-id",
        help="Require the resolved deterministic run to match this identity.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve identity, preflight, and durable work selection without execution.",
    )
    parser.add_argument(
        "--materialize-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--status-run-id",
        help="Print durable status for an existing local run and exit.",
    )
    parser.add_argument(
        "--compare-result",
        action="append",
        default=[],
        type=Path,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--varying-dimension",
        action="append",
        default=[],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--comparison-output-dir", type=Path, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--dimension",
        action="append",
        default=[],
        metavar="KEY=JSON_VALUE",
        help=argparse.SUPPRESS,
    )
    return parser


def _parse_label_filters(
    values: list[str], parser: argparse.ArgumentParser
) -> dict[str, list[JsonScalar]]:
    filters: dict[str, list[JsonScalar]] = {}
    for raw in values:
        path, separator, encoded = raw.partition("=")
        if not separator or not path.strip():
            parser.error("--label-filter must use PATH=JSON_VALUE.")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            parser.error(f"Invalid JSON label filter {raw!r}: {error.msg}.")
        if not (value is None or isinstance(value, (str, int, float, bool))):
            parser.error("--label-filter values must be JSON scalars.")
        filters.setdefault(path.strip(), []).append(value)
    return filters


def _parse_configuration_dimensions(
    values: list[str], parser: argparse.ArgumentParser
) -> dict[str, JsonScalar]:
    dimensions: dict[str, JsonScalar] = {}
    for raw in values:
        key, separator, encoded = raw.partition("=")
        key = key.strip()
        if not separator or not key:
            parser.error("--dimension must use KEY=JSON_VALUE.")
        if key in dimensions:
            parser.error(f"--dimension key {key!r} was provided more than once.")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            parser.error(f"Invalid JSON dimension {raw!r}: {error.msg}.")
        if not (value is None or isinstance(value, (str, int, float, bool))):
            parser.error("--dimension values must be JSON scalars.")
        dimensions[key] = value
    return dimensions


def _choose_published_benchmark_version(
    versions: tuple[PublishedBenchmarkVersionSummary, ...],
) -> PublishedBenchmarkVersionSummary:
    if not versions:
        raise ValueError("No published benchmark versions were found in Azure.")
    versions_by_key: dict[str, list[PublishedBenchmarkVersionSummary]] = {}
    for version in versions:
        versions_by_key.setdefault(version.benchmark_key, []).append(version)
    benchmark_labels: dict[str, str] = {}
    for benchmark_key, benchmark_versions in versions_by_key.items():
        name = benchmark_versions[0].benchmark_name
        benchmark_labels[f"{name} ({benchmark_key})"] = benchmark_key
    selected_key = benchmark_labels[
        prompt_select_option(
            "Choose a published benchmark from Azure:", list(benchmark_labels)
        )
    ]
    version_labels = {
        f"v{item.version_number} — {item.example_count} examples": item
        for item in sorted(
            versions_by_key[selected_key],
            key=lambda candidate: candidate.version_number,
            reverse=True,
        )
    }
    return version_labels[
        prompt_select_option(
            "Choose a published benchmark version:", list(version_labels)
        )
    ]


def _resolve_cli_benchmark(
    args: argparse.Namespace,
    *,
    repository: BenchmarkRepository,
    project_key: str,
    parser: argparse.ArgumentParser,
) -> tuple[str, int | None]:
    if args.benchmark_key:
        if args.benchmark_version is None and not sys.stdin.isatty():
            parser.error(
                "--benchmark-version is required with --benchmark-key for "
                "non-interactive reproducible runs."
            )
        return args.benchmark_key, args.benchmark_version
    if args.benchmark_version is not None:
        parser.error("--benchmark-version requires --benchmark-key.")
    if not sys.stdin.isatty():
        parser.error("--benchmark-key is required when stdin is not interactive.")
    print(f"Retrieving published benchmarks for {project_key} from Azure...")
    selected = _choose_published_benchmark_version(repository.list_published_versions())
    return selected.benchmark_key, selected.version_number


def _resolve_path(
    explicit: Path | None,
    *,
    directory: str,
    pattern: str,
    label: str,
    parser: argparse.ArgumentParser,
) -> Path:
    if explicit is not None:
        return explicit
    if not sys.stdin.isatty():
        parser.error(f"{label} is required when stdin is not interactive.")
    paths = sorted(Path(directory).glob(pattern))
    if not paths:
        parser.error(f"No {label} files were found under {directory}/.")
    selected = prompt_select_option(f"Choose {label}:", [str(path) for path in paths])
    return Path(selected)


def _resolve_cli_model(
    args: argparse.Namespace, *, catalog: ModelCatalog, parser: argparse.ArgumentParser
) -> str:
    if args.ai_model:
        try:
            selected = resolve_model(args.ai_model, catalog)
        except ValueError as error:
            parser.error(str(error))
        print(f"Selected model: {format_model(catalog.get(selected), default_model=catalog.default_model)}")
        return selected
    if args.compare_model:
        try:
            selected = resolve_model(args.compare_model[0], catalog)
        except ValueError as error:
            parser.error(str(error))
        print(f"Selected model: {format_model(catalog.get(selected), default_model=catalog.default_model)}")
        return selected
    if not sys.stdin.isatty():
        parser.error("--ai-model or --compare-model is required non-interactively.")
    choices = {
        format_model(model, default_model=catalog.default_model): model.id
        for model in catalog.models
    }
    return choices[prompt_select_option(
        f"Choose an AI model (project default: {catalog.default_model}):",
        list(choices),
    )]


def _resolve_cli_reasoning_effort(
    args: argparse.Namespace, *, parser: argparse.ArgumentParser
) -> str | None:
    if args.ai_reasoning_effort is not None:
        return normalize_ai_reasoning_effort(args.ai_reasoning_effort)
    if not sys.stdin.isatty():
        parser.error("--ai-reasoning-effort is required non-interactively.")
    return normalize_ai_reasoning_effort(
        prompt_select_option(
            "Choose AI reasoning effort (default: model default):",
            ["default", "low", "medium", "high"],
        )
    )


def _resolve_cli_runs_per_example(
    args: argparse.Namespace, *, parser: argparse.ArgumentParser
) -> int:
    if args.runs_per_example is not None:
        if args.runs_per_example < 1:
            parser.error("--runs-per-example must be at least 1.")
        return args.runs_per_example
    if not sys.stdin.isatty():
        parser.error("--runs-per-example is required non-interactively.")
    return prompt_positive_int("Number of runs per example", default=1)


def _resolve_cli_scope(
    args: argparse.Namespace,
    *,
    benchmark: BenchmarkVersion,
    profile: EvaluationProfile,
    parser: argparse.ArgumentParser,
) -> tuple[list[str] | None, list[str] | None, dict[str, list[JsonScalar]], list[str]]:
    label_filters = _parse_label_filters(args.label_filter, parser)
    section_keys = _resolve_section_keys(args.section, profile=profile, parser=parser)
    if args.all_examples:
        if (
            args.example_ids
            or args.unit_ids
            or section_keys
            or label_filters
            or args.slice
        ):
            parser.error("--all-examples cannot be combined with scope filters.")
        return None, None, {}, []
    supported_choices = sum(
        bool(value) for value in (args.example_ids, args.unit_ids, section_keys)
    )
    if supported_choices > 1:
        parser.error(
            "Choose one scope: --all-examples, --example-ids, --unit-ids, "
            "or --section."
        )
    if supported_choices:
        if label_filters or args.slice:
            parser.error(
                "Named or explicit scopes cannot be combined with maintenance filters."
            )
        return args.example_ids, args.unit_ids, {}, section_keys
    if label_filters or args.slice:
        return None, None, label_filters, args.slice
    if not sys.stdin.isatty():
        parser.error(
            "An explicit scope is required: --all-examples, --example-ids, "
            "--unit-ids, or --section."
        )
    options = ["Full benchmark", "Explicit unit/example list"]
    if profile.slices:
        options.append("Named use-case section")
    selected = prompt_select_option(
        "Which benchmark scope should be evaluated?", options
    )
    if selected == "Full benchmark":
        return None, None, {}, []
    if selected == "Explicit unit/example list":
        identity_kind = prompt_select_option(
            "Which identifiers are you entering?", ["Example IDs", "Unit IDs"]
        )
        values = prompt_csv_values(f"Enter comma-separated {identity_kind.lower()}")
        return (values, None, {}, []) if identity_kind == "Example IDs" else (
            None,
            values,
            {},
            [],
        )
    labels = {item.label: item.key for item in profile.slices}
    section = prompt_select_option("Choose a named use-case section:", list(labels))
    return None, None, {}, [labels[section]]


def _resolve_section_keys(
    values: list[str],
    *,
    profile: EvaluationProfile,
    parser: argparse.ArgumentParser,
) -> list[str]:
    """Resolve user-facing section keys or labels to profile slice keys."""
    if not values:
        return []
    lookup = {
        alias.casefold(): item.key
        for item in profile.slices
        for alias in (item.key, item.label)
    }
    resolved: list[str] = []
    for value in values:
        key = lookup.get(value.strip().casefold())
        if key is None:
            choices = ", ".join(item.label for item in profile.slices) or "(none)"
            parser.error(f"Unknown use-case section {value!r}. Choose one of: {choices}")
        if key not in resolved:
            resolved.append(key)
    return resolved


def _resolve_cli_runtime(
    args: argparse.Namespace, *, parser: argparse.ArgumentParser
) -> RuntimeType:
    del parser
    return args.runtime


def _configure_cli_logging() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    logging.getLogger(_AZURE_HTTP_LOGGER).setLevel(logging.WARNING)
    if not any(getattr(handler, "_eval_cli", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._eval_cli = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _print_cli_outcome(path: Path) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload["summary"]
    reliability = summary["reliability"]
    coverage = summary["scoring_coverage"]
    planned = int(reliability["planned_runs"])
    scored = int(coverage["scored_runs"])
    failures = planned - scored
    print(f"COMPLETE: {scored}/{planned} attempts scored; {failures} not scored.")
    usage = summary.get("usage", {})
    totals = usage.get("totals") if isinstance(usage, dict) else None
    if isinstance(totals, dict):
        print(
            "TOKENS: "
            f"input={totals.get('input_tokens', 0)}, "
            f"output={totals.get('output_tokens', 0)}, "
            f"total={totals.get('total_tokens', 0)}, "
            f"cached-input={totals.get('cached_input_tokens', 0)}, "
            f"reasoning={totals.get('reasoning_tokens', 0)}."
        )
    cost = summary.get("cost", {})
    if isinstance(cost, dict):
        currencies = sorted(
            set(cost.get("actual_by_currency", {}))
            | set(cost.get("estimated_by_currency", {}))
        )
        for currency in currencies:
            actual = cost.get("actual_by_currency", {}).get(currency, 0.0)
            estimated = cost.get("estimated_by_currency", {}).get(currency, 0.0)
            print(
                f"COST TOTALS ({currency}): actual={actual:.6f}, "
                f"estimated={estimated:.6f}."
            )
        for currency, distribution in cost.get(
            "complete_unit_cost_by_currency", {}
        ).items():
            print(
                f"COST ({currency}): total={distribution['total']:.6f}, "
                f"avg/unit={distribution['average']:.6f}, "
                f"P5={distribution['p5']:.6f}, "
                f"P95={distribution['p95']:.6f} "
                f"across {distribution['count']} complete observations."
            )
        print(
            "COST COVERAGE: "
            f"complete={cost.get('units_with_complete_cost_observations', 0)}, "
            f"partial={cost.get('units_with_partial_pricing', 0)}, "
            "unavailable="
            f"{cost.get('units_without_usable_cost_information', 0)}."
        )
    print(f"Results written to: {path}")
    return failures > 0


def _resume_command(argv: list[str]) -> str:
    """Return a shell-safe command that resolves the same immutable run."""
    return shlex.join(
        [sys.executable, "-m", "src.evals.eval_orchestration", *argv]
    )


def _find_run_directory(run_id: str, *, root: Path = BASE_RESULTS_DIR) -> Path:
    """Resolve a current working run."""
    return find_inspection_run_directory(run_id, root=root)


def _print_run_status(run_dir: Path) -> None:
    run_id = run_dir.name
    store = LocalRunStore(run_dir, run_id=run_id)
    counts = store.state_counts()
    manifest = store.read_manifest()
    print(f"Run: {run_id}")
    print(
        "Work: "
        f"{len(manifest['work_items']) - counts['missing']}/"
        f"{len(manifest['work_items'])} recorded; "
        f"{counts['completed']} completed; {counts['failed']} failed; "
        f"{counts['cancelled']} cancelled; {counts['missing']} missing."
    )
    if store.result_path.exists():
        payload = json.loads(store.result_path.read_text(encoding="utf-8"))
        coverage = payload["summary"]["scoring_coverage"]
        print(f"Scoring: {coverage['scored_runs']}/{coverage['planned_runs']} scored.")
        print(f"Results: {store.result_path}")
    else:
        print("Results: not materialized; resume the run with its original settings.")


def main() -> None:
    _configure_cli_logging()
    parser = _argument_parser()
    args = parser.parse_args()
    if args.status_run_id:
        _print_run_status(_find_run_directory(args.status_run_id))
        return
    if args.compare_result:
        try:
            path = build_comparison(
                args.compare_result,
                varying_dimensions=set(args.varying_dimension),
                output_dir=args.comparison_output_dir,
            )
        except ValueError as error:
            parser.error(str(error))
        print(f"Comparison written to: {path}")
        return
    bootstrap_environment()
    model_catalog = load_model_catalog()
    yaml_path = _resolve_path(
        args.yaml_path,
        directory="pipeline_configs",
        pattern="*.ppln",
        label="pipeline config",
        parser=parser,
    )
    evaluation_profile_path = _resolve_path(
        args.evaluation_profile,
        directory="evaluation_configs",
        pattern="*.eval.yaml",
        label="evaluation profile",
        parser=parser,
    )
    profile = load_evaluation_profile(evaluation_profile_path)
    project_key = (args.project_key or os.getenv("APP_PROJECT_KEY", "")).strip()
    if not project_key:
        parser.error("APP_PROJECT_KEY or --project-key is required.")
    repository: BenchmarkRepository = AzurePostgresBenchmarkRepository(
        project_key=project_key,
        host=args.azure_postgres_host,
        database=args.azure_postgres_database,
        user=args.azure_postgres_user,
    )
    benchmark_source = "azure_postgres_entra"
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
    example_ids, unit_ids, label_filters, slice_keys = _resolve_cli_scope(
        args,
        benchmark=benchmark,
        profile=profile,
        parser=parser,
    )
    ai_model = _resolve_cli_model(args, catalog=model_catalog, parser=parser)
    ai_reasoning_effort = _resolve_cli_reasoning_effort(args, parser=parser)
    runs_per_example = _resolve_cli_runs_per_example(args, parser=parser)
    runtime = _resolve_cli_runtime(args, parser=parser)
    configuration_dimensions = _parse_configuration_dimensions(args.dimension, parser)
    evidence_account_url = (
        (args.azure_storage_account_url or os.getenv("AZURE_STORAGE_ACCOUNT_URL", ""))
        .strip()
        .rstrip("/")
    )
    evidence_container = (
        args.azure_storage_container or os.getenv("AZURE_STORAGE_CONTAINER", "")
    ).strip()
    if not evidence_account_url.startswith("https://") or not evidence_container:
        parser.error(
            "direct Entra access requires AZURE_STORAGE_ACCOUNT_URL and "
            "AZURE_STORAGE_CONTAINER (or the corresponding CLI flags)."
        )
    os.environ["AZURE_STORAGE_ACCOUNT_URL"] = evidence_account_url
    os.environ["AZURE_STORAGE_CONTAINER"] = evidence_container
    requested_models = [ai_model]
    for requested in args.compare_model:
        try:
            resolved = resolve_model(requested, model_catalog)
        except ValueError as error:
            parser.error(str(error))
        if resolved not in requested_models:
            requested_models.append(resolved)
    if args.run_id and len(requested_models) > 1:
        parser.error("--run-id cannot identify more than one compared model run.")

    def run_model(model: str, *, dry_run: bool, materialize_only: bool) -> Path:
        return run_eval(
            yaml_path,
            evaluation_profile_path=evaluation_profile_path,
            project_key=project_key,
            benchmark_key=benchmark_key,
            benchmark_version=benchmark.version_number,
            ai_model=model,
            ai_reasoning_effort=ai_reasoning_effort,
            example_ids=example_ids,
            unit_ids=unit_ids,
            label_filters=label_filters,
            slice_keys=slice_keys,
            runs_per_example=runs_per_example,
            runtime=runtime,
            max_workers=args.max_workers,
            error_action=args.error_action,
            progress_interval_seconds=args.progress_interval_seconds,
            agent_version_id=args.agent_version_id,
            agent_policy_path=args.agent_policy,
            require_promoted_agent_version=(args.require_promoted_agent_version),
            configuration_dimensions=configuration_dimensions,
            resume_mode=args.resume_mode,
            rerun_failure_types=set(args.rerun_failure_type) or None,
            expected_run_id=args.run_id,
            dry_run=dry_run,
            materialize_only=materialize_only,
            repository=repository,
            benchmark_source=benchmark_source,
            review_capture=args.review_capture,
        )

    comparison_manifest: Path | None = None
    try:
        if len(requested_models) > 1:
            preflight_paths = [
                run_model(model, dry_run=True, materialize_only=False)
                for model in requested_models
            ]
            comparison_manifest = build_comparison_manifest(
                preflight_paths,
                varying_dimensions={"model"},
                output_dir=args.comparison_output_dir,
            )
            paths = (
                preflight_paths
                if args.dry_run
                else [
                    run_model(
                        model,
                        dry_run=False,
                        materialize_only=args.materialize_only,
                    )
                    for model in requested_models
                ]
            )
        else:
            paths = [
                run_model(
                    requested_models[0],
                    dry_run=args.dry_run,
                    materialize_only=args.materialize_only,
                )
            ]
    except KeyboardInterrupt:
        print("INTERRUPTED: completed attempts are durable and the run is incomplete.")
        print(f"Resume missing units with: {_resume_command(sys.argv[1:])}")
        raise SystemExit(130) from None
    except RunStoreIntegrityError as error:
        print(f"STORAGE INTEGRITY FAILURE: {error}")
        raise SystemExit(4) from error
    except ValueError as error:
        parser.error(str(error))
    terminal_failures = False
    for path in paths:
        if args.dry_run:
            print(f"Run manifest written to: {path}")
        else:
            terminal_failures = _print_cli_outcome(path) or terminal_failures
    if args.dry_run:
        if comparison_manifest is not None:
            print(f"Comparison manifest written to: {comparison_manifest}")
        return
    if len(paths) > 1:
        comparison = build_comparison(
            paths,
            varying_dimensions={"model"},
            output_dir=args.comparison_output_dir,
            comparison_manifest_path=comparison_manifest,
        )
        print(f"Comparison written to: {comparison}")
    if terminal_failures:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
