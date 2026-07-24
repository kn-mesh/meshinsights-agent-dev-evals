"""Durable local storage for resumable evaluation execution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, cast
import uuid

if TYPE_CHECKING:
    from src.evals.evaluation_profile import EvaluationProfile

from evaluation import (
    build_performance_summary,
    build_run_identity,
    build_work_item_id,
    canonical_json_bytes,
    canonical_sha256,
    eval_attempt_from_dict,
    verify_eval_run_identity,
)


ResumeMode = Literal[
    "missing",
    "missing-or-cancelled",
    "failed",
    "missing-or-failed",
]


class RunStoreIntegrityError(RuntimeError):
    """Persisted run evidence contradicts its deterministic identity."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_invocation_id() -> str:
    """Return an occurrence identity distinct from deterministic run identity."""
    return f"inv_{uuid.uuid4().hex}"


class LocalRunStore:
    """Tracked evaluation evidence plus disposable performance observations."""

    def __init__(self, run_dir: Path, *, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.manifest_path = run_dir / "manifest.json"
        self.result_path = run_dir / "result.json"
        self.attempts_dir = run_dir / "attempts"
        self.performance_dir = run_dir / "performance"
        self.performance_attempts_dir = self.performance_dir / "attempts"
        self.performance_summary_path = self.performance_dir / "summary.json"
        self.invocations_dir = self.performance_dir / "invocations"
        self.lock_path = self.performance_dir / ".coordinator.lock"

    def initialize(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create an immutable manifest or validate the existing identity."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            existing = self.read_manifest()
            for key in (
                "schema_version",
                "run_id",
                "run_spec_sha256",
                "run_spec",
                "work_items",
                "occurrence_seed",
            ):
                if existing.get(key) != manifest.get(key):
                    raise RunStoreIntegrityError(
                        f"Existing run manifest conflicts at {key!r}: "
                        f"{self.manifest_path}"
                    )
            return existing
        try:
            _write_json_create(self.manifest_path, manifest)
            return manifest
        except FileExistsError:
            # Another process may have created the same deterministic manifest
            # between the existence check and exclusive commit.
            return self.initialize(manifest)

    def read_manifest(self) -> dict[str, Any]:
        payload = _read_json(self.manifest_path)
        if payload.get("run_id") != self.run_id:
            raise RunStoreIntegrityError(
                f"Manifest run id does not match directory: {self.manifest_path}"
            )
        expected = payload.get("run_spec_sha256")
        run_spec = payload.get("run_spec")
        if not isinstance(run_spec, dict):
            raise RunStoreIntegrityError(
                f"Manifest run specification is invalid: {self.manifest_path}"
            )
        derived_hash = canonical_sha256(run_spec)
        schema_version = payload.get("schema_version")
        valid_identity = False
        if schema_version == 1:
            derived_run_id, _ = build_run_identity(run_spec)
            valid_identity = self.run_id == derived_run_id
        elif schema_version == 2:
            occurrence_seed = payload.get("occurrence_seed")
            valid_identity = isinstance(
                occurrence_seed, dict
            ) and verify_eval_run_identity(
                self.run_id,
                occurrence_seed=occurrence_seed,
                run_spec_sha256=derived_hash,
            )
        if expected != derived_hash or not valid_identity:
            raise RunStoreIntegrityError(
                f"Manifest run specification identity is invalid: {self.manifest_path}"
            )
        return payload

    @contextmanager
    def coordinator_lock(self, *, invocation_id: str) -> Iterator[None]:
        """Allow one local coordinator for a deterministic run."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                lock_file.seek(0)
                holder = lock_file.read().strip() or "unknown invocation"
                raise RuntimeError(
                    f"Run {self.run_id} is already active ({holder})."
                ) from error
            lock_file.seek(0)
            lock_file.truncate()
            lock_file.write(
                json.dumps(
                    {"invocation_id": invocation_id, "started_at_utc": utc_now()}
                )
            )
            lock_file.flush()
            os.fsync(lock_file.fileno())
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def write_invocation_event(
        self, *, invocation_id: str, event: str, payload: dict[str, Any]
    ) -> Path:
        if event not in {"started", "completed", "interrupted", "failed"}:
            raise ValueError(f"Unsupported invocation event: {event}.")
        path = self.invocations_dir / f"{invocation_id}.{event}.json"
        _write_json_create(
            path,
            {
                "schema_version": 1,
                "run_id": self.run_id,
                "invocation_id": invocation_id,
                "event": event,
                "recorded_at_utc": utc_now(),
                **payload,
            },
        )
        return path

    def attempt_path(self, *, work_item_id: str, generation: int) -> Path:
        if generation < 1:
            raise ValueError("Attempt generation must be at least 1.")
        return (
            self.attempts_dir / work_item_id[:2] / f"{work_item_id}.{generation}.json"
        )

    def commit_attempt(self, record: dict[str, Any]) -> Path:
        """Exclusively persist one immutable terminal execution generation."""
        if record.get("schema_version") != 1:
            raise RunStoreIntegrityError("Attempt record schema must be v1.")
        if record.get("run_id") != self.run_id:
            raise RunStoreIntegrityError("Attempt record has the wrong run id.")
        work_item_id = str(record.get("work_item_id", ""))
        generation = int(record.get("generation", 0))
        expected_work_item_id = build_work_item_id(
            run_id=self.run_id,
            item_id=str(record.get("example_id", "")),
            attempt_index=int(record.get("repetition_index", 0)),
        )
        if work_item_id != expected_work_item_id:
            raise RunStoreIntegrityError("Attempt work-item identity is invalid.")
        planned_ids = {
            item["work_item_id"] for item in self.read_manifest()["work_items"]
        }
        if work_item_id not in planned_ids:
            raise RunStoreIntegrityError("Attempt work item is absent from the plan.")
        expected_execution_id = f"{work_item_id}.{generation}"
        if record.get("execution_id") != expected_execution_id:
            raise RunStoreIntegrityError("Attempt execution identity is invalid.")
        unsigned = dict(record)
        supplied_hash = unsigned.pop("record_sha256", None)
        actual_hash = canonical_sha256(unsigned)
        if supplied_hash not in {None, actual_hash}:
            raise RunStoreIntegrityError("Attempt record payload hash is invalid.")
        encoded_record = {**unsigned, "record_sha256": actual_hash}
        path = self.attempt_path(
            work_item_id=work_item_id,
            generation=generation,
        )
        try:
            _write_json_create(path, encoded_record)
        except FileExistsError:
            if canonical_json_bytes(_read_json(path)) != canonical_json_bytes(
                encoded_record
            ):
                raise RunStoreIntegrityError(
                    f"Conflicting immutable attempt record: {path}"
                )
        return path

    def performance_attempt_path(self, *, work_item_id: str, generation: int) -> Path:
        if generation < 1:
            raise ValueError("Performance generation must be at least 1.")
        return (
            self.performance_attempts_dir
            / work_item_id[:2]
            / f"{work_item_id}.{generation}.json"
        )

    def commit_performance(self, record: dict[str, Any]) -> Path:
        """Persist disposable performance evidence for one execution generation."""
        if record.get("schema_version") != 1:
            raise RunStoreIntegrityError("Performance record schema must be v1.")
        if record.get("run_id") != self.run_id:
            raise RunStoreIntegrityError("Performance record has the wrong run id.")
        work_item_id = str(record.get("work_item_id", ""))
        generation = int(record.get("generation", 0))
        if record.get("execution_id") != f"{work_item_id}.{generation}":
            raise RunStoreIntegrityError("Performance execution identity is invalid.")
        unsigned = dict(record)
        supplied_hash = unsigned.pop("record_sha256", None)
        actual_hash = canonical_sha256(unsigned)
        if supplied_hash not in {None, actual_hash}:
            raise RunStoreIntegrityError("Performance record hash is invalid.")
        encoded = {**unsigned, "record_sha256": actual_hash}
        path = self.performance_attempt_path(
            work_item_id=work_item_id,
            generation=generation,
        )
        try:
            _write_json_create(path, encoded)
        except FileExistsError:
            if canonical_json_bytes(_read_json(path)) != canonical_json_bytes(encoded):
                raise RunStoreIntegrityError(f"Conflicting performance record: {path}")
        return path

    def read_performance_records(
        self,
        *,
        generations: set[tuple[str, int]] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Read performance records, optionally for exact execution generations.

        Supplying generations avoids touching superseded disposable records. This
        matters because stale performance is neither part of durable integrity nor
        allowed to prevent materialization of the current run view.
        """
        records: list[dict[str, Any]] = []
        if not self.performance_attempts_dir.exists():
            return ()
        paths = (
            sorted(self.performance_attempts_dir.glob("*/*.json"))
            if generations is None
            else sorted(
                self.performance_attempt_path(
                    work_item_id=work_item_id,
                    generation=generation,
                )
                for work_item_id, generation in generations
            )
        )
        for path in paths:
            if not path.is_file():
                continue
            record = _read_json(path)
            unsigned = dict(record)
            expected = unsigned.pop("record_sha256", None)
            if (
                record.get("schema_version") != 1
                or record.get("run_id") != self.run_id
                or expected != canonical_sha256(unsigned)
            ):
                raise RunStoreIntegrityError(f"Invalid performance record: {path}")
            records.append(record)
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    str(item["work_item_id"]),
                    int(item["generation"]),
                ),
            )
        )

    def read_attempt_records(self) -> tuple[dict[str, Any], ...]:
        records: list[dict[str, Any]] = []
        if not self.attempts_dir.exists():
            return ()
        manifest = self.read_manifest()
        planned = {item["work_item_id"]: item for item in manifest["work_items"]}
        for path in sorted(self.attempts_dir.glob("*/*.json")):
            record = _read_json(path)
            unsigned = dict(record)
            expected = unsigned.pop("record_sha256", None)
            if record.get("run_id") != self.run_id:
                raise RunStoreIntegrityError(f"Wrong run id in attempt: {path}")
            if record.get("schema_version") != 1:
                raise RunStoreIntegrityError(f"Wrong attempt schema: {path}")
            plan_item = planned.get(record.get("work_item_id"))
            if plan_item is None:
                raise RunStoreIntegrityError(f"Unplanned work item in attempt: {path}")
            if record.get("example_id") != plan_item["example_id"] or int(
                record.get("repetition_index", 0)
            ) != int(plan_item["repetition_index"]):
                raise RunStoreIntegrityError(f"Attempt plan identity mismatch: {path}")
            if expected != canonical_sha256(unsigned):
                raise RunStoreIntegrityError(f"Invalid attempt hash: {path}")
            records.append(record)
        return tuple(
            sorted(
                records,
                key=lambda item: (
                    str(item["work_item_id"]),
                    int(item["generation"]),
                ),
            )
        )

    def records_by_work_item(self) -> dict[str, tuple[dict[str, Any], ...]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in self.read_attempt_records():
            grouped.setdefault(str(record["work_item_id"]), []).append(record)
        return {
            work_item_id: tuple(sorted(items, key=lambda item: int(item["generation"])))
            for work_item_id, items in grouped.items()
        }

    def next_generation(self, work_item_id: str) -> int:
        records = self.records_by_work_item().get(work_item_id, ())
        return 1 if not records else int(records[-1]["generation"]) + 1

    def select_work_items(
        self,
        *,
        mode: ResumeMode,
        failure_types: set[str] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Select manifest slots without ever duplicating healthy completed work."""
        manifest = self.read_manifest()
        records = self.records_by_work_item()
        selected: list[dict[str, Any]] = []
        for item in manifest["work_items"]:
            history = records.get(item["work_item_id"], ())
            latest = history[-1] if history else None
            state = _record_state(latest)
            include = (
                (mode == "missing" and state == "missing")
                or (
                    mode == "missing-or-cancelled" and state in {"missing", "cancelled"}
                )
                or (mode == "failed" and state in {"failed", "cancelled"})
                or (
                    mode == "missing-or-failed"
                    and state in {"missing", "failed", "cancelled"}
                )
            )
            if include and failure_types and latest is not None:
                failure_type = latest.get("attempt", {}).get("failure_type")
                include = failure_type in failure_types
            if include:
                selected.append(dict(item))
        return tuple(selected)

    def state_counts(self) -> dict[str, int]:
        manifest = self.read_manifest()
        records = self.records_by_work_item()
        counts = {"missing": 0, "completed": 0, "failed": 0, "cancelled": 0}
        for item in manifest["work_items"]:
            history = records.get(item["work_item_id"], ())
            counts[_record_state(history[-1] if history else None)] += 1
        return counts

    def execution_invocation_wall_time_seconds(
        self, *, invocation_ids: set[str] | None = None
    ) -> float:
        """Sum terminal invocation time only for invocations that selected work.

        Invocation events are operator-history evidence.  A completed no-op resume
        or materialization pass must not change execution performance, while an
        interrupted or failed invocation that selected work still consumed wall
        time and belongs in the total.
        """
        total = 0.0
        if not self.invocations_dir.exists():
            return total
        terminal_events = ("completed", "interrupted", "failed")
        for event in terminal_events:
            for path in self.invocations_dir.glob(f"*.{event}.json"):
                payload = _read_json(path)
                if (
                    invocation_ids is not None
                    and payload.get("invocation_id") not in invocation_ids
                ):
                    continue
                selected = payload.get("selected_work_items")
                duration = payload.get("duration_seconds")
                if (
                    isinstance(selected, int)
                    and not isinstance(selected, bool)
                    and selected > 0
                    and isinstance(duration, (int, float))
                    and not isinstance(duration, bool)
                    and duration >= 0
                ):
                    total += float(duration)
        return total

    def materialize_result(
        self,
        *,
        completed_at_utc: str,
        latest_invocation_id: str,
    ) -> Path:
        """Build and atomically replace the canonical eval summary."""
        payload = self.build_result(
            completed_at_utc=completed_at_utc,
            latest_invocation_id=latest_invocation_id,
        )
        _write_json_atomic(self.result_path, payload)
        return self.result_path

    def read_verified_result(self) -> dict[str, Any]:
        """Read a complete result view and verify it against durable evidence."""
        payload = _read_json(self.result_path)
        self._validate_result(payload)
        return payload

    def _validate_result(self, payload: dict[str, Any]) -> None:
        """Require the canonical view of the manifest and latest attempts."""
        manifest_schema = self.read_manifest().get("schema_version")
        if payload.get("schema_version") != manifest_schema or manifest_schema not in {
            1,
            2,
        }:
            raise RunStoreIntegrityError(
                "Evaluation result schema must match the run manifest."
            )
        config = payload.get("run")
        if not isinstance(config, dict):
            raise RunStoreIntegrityError("Evaluation result is missing run metadata.")
        completed_at_utc = config.get("completed_at_utc")
        latest_invocation_id = config.get("latest_invocation_id")
        if not isinstance(completed_at_utc, str) or not completed_at_utc:
            raise RunStoreIntegrityError(
                "Evaluation result completed_at_utc is invalid."
            )
        if not isinstance(latest_invocation_id, str) or not latest_invocation_id:
            raise RunStoreIntegrityError(
                "Evaluation result latest_invocation_id is invalid."
            )
        timing = payload.get("summary", {}).get("timing", {})
        active_wall_seconds = timing.get("evaluation_active_wall_seconds")
        if manifest_schema == 2 and (
            not isinstance(active_wall_seconds, (int, float))
            or isinstance(active_wall_seconds, bool)
            or active_wall_seconds < 0
        ):
            raise RunStoreIntegrityError(
                "Evaluation result active wall time is invalid."
            )
        expected = self.build_result(
            completed_at_utc=completed_at_utc,
            latest_invocation_id=latest_invocation_id,
            evaluation_active_wall_seconds=active_wall_seconds,
        )
        if canonical_json_bytes(payload) != canonical_json_bytes(expected):
            raise RunStoreIntegrityError(
                "Evaluation result content does not match its canonical materialization."
            )

    def build_result(
        self,
        *,
        completed_at_utc: str,
        latest_invocation_id: str,
        evaluation_active_wall_seconds: float | None = None,
    ) -> dict[str, Any]:
        """Rebuild the compact summary from tracked eval evidence."""
        manifest = self.read_manifest()
        schema_version = int(manifest["schema_version"])
        state = self._evaluation_state()
        expected_config = state["run"]
        expected_config["completed_at_utc"] = completed_at_utc
        expected_config["latest_invocation_id"] = latest_invocation_id

        # Lazy import avoids the orchestration -> comparison -> integrity cycle.
        from src.evals.eval_orchestration import _build_summary

        summary = _build_summary(
            state["summary_rows"],
            profile=cast("EvaluationProfile", state["profile"]),
            runs_per_example=int(expected_config["runs_per_example"]),
            frozen_pricing=(
                expected_config.get("dimensions", {}).get("model", {}).get("pricing")
            ),
        )
        if schema_version >= 2:
            summary["timing"] = {
                "evaluation_active_wall_seconds": (
                    self.execution_invocation_wall_time_seconds()
                    if evaluation_active_wall_seconds is None
                    else float(evaluation_active_wall_seconds)
                )
            }
        return {
            "schema_version": schema_version,
            "summary": summary,
            "run": expected_config,
            "artifacts": {
                "manifest": "manifest.json",
                "agent_version": "agent-version.json",
                "attempts": "attempts/",
            },
        }

    def evaluation_rows(self) -> list[dict[str, Any]]:
        """Return an on-demand detailed eval view without persisting duplication."""
        return list(self._evaluation_state()["rows"])

    def _evaluation_state(self) -> dict[str, Any]:
        manifest = self.read_manifest()
        contract = manifest.get("eval_contract")
        if (
            not isinstance(contract, dict)
            or contract.get("schema_version") != manifest.get("schema_version")
            or contract.get("schema_version") not in {1, 2}
        ):
            raise RunStoreIntegrityError(
                "Run manifest is missing its matching eval contract."
            )
        expected_config = dict(contract.get("run", {}))

        histories = self.records_by_work_item()
        plans = list(manifest.get("work_items", []))
        planned_ids = {str(item["work_item_id"]) for item in plans}
        if set(histories) != planned_ids:
            raise RunStoreIntegrityError(
                "A complete result requires a latest attempt for every planned work item."
            )

        static_rows = contract.get("examples")
        fields = contract.get("output_fields")
        if not isinstance(static_rows, list) or not isinstance(fields, list):
            raise RunStoreIntegrityError("Eval contract is malformed.")
        selected = [str(row["example_id"]) for row in static_rows]
        rows_by_example = {str(row["example_id"]): dict(row) for row in static_rows}
        attempts_by_example: dict[str, list[Any]] = {}
        for plan in plans:
            history = histories[str(plan["work_item_id"])]
            latest = history[-1]
            attempt = eval_attempt_from_dict(latest["attempt"])
            attempt.metadata.update(_attempt_metadata(plan, latest, history))
            attempts_by_example.setdefault(str(plan["example_id"]), []).append(attempt)

        expected_rows: list[dict[str, Any]] = []
        summary_rows: list[Any] = []
        for example_id in selected:
            row = rows_by_example[str(example_id)]
            attempts = attempts_by_example.get(str(example_id), [])
            row["runs"] = [
                _materialized_attempt(attempt, field_contracts=fields)
                for attempt in attempts
            ]
            expected_rows.append(row)
            summary_rows.append(
                SimpleNamespace(
                    example=SimpleNamespace(example_id=str(example_id)),
                    slice_keys=tuple(row.get("slice_keys", ())),
                    attempts=tuple(attempts),
                )
            )

        summary_profile = SimpleNamespace(
            output_fields=tuple(
                SimpleNamespace(
                    key=str(field["key"]),
                    evaluation=object() if field.get("graded") else None,
                )
                for field in fields
            ),
            slices=tuple(
                SimpleNamespace(key=str(key)) for key in contract.get("slice_keys", [])
            ),
        )
        return {
            "run": expected_config,
            "rows": expected_rows,
            "summary_rows": summary_rows,
            "profile": summary_profile,
        }

    def materialize_performance(self) -> Path | None:
        """Build a disposable schema-v1 performance summary when traces exist."""
        latest_durable = {
            (str(items[-1]["work_item_id"]), int(items[-1]["generation"])): items[-1]
            for items in self.records_by_work_item().values()
            if items
        }
        performance_records = self.read_performance_records(
            generations=set(latest_durable)
        )
        if not performance_records:
            self.performance_summary_path.unlink(missing_ok=True)
            return None
        attempts: list[Any] = []
        model_calls: list[dict[str, Any]] = []
        for record in performance_records:
            key = (str(record["work_item_id"]), int(record["generation"]))
            durable_record = latest_durable.get(key)
            if durable_record is None:
                continue
            metrics = dict(record.get("metrics", {}))
            attempt = eval_attempt_from_dict(durable_record["attempt"])
            artifacts = dict(attempt.artifacts)
            retry = metrics.get("retry_telemetry")
            if isinstance(retry, dict):
                artifacts["retry_telemetry"] = retry
            attempt = replace(
                attempt,
                duration_seconds=float(metrics.get("duration_seconds", 0.0)),
                stage_durations_seconds={
                    str(name): float(value)
                    for name, value in dict(
                        metrics.get("stage_durations_seconds", {})
                    ).items()
                },
                artifacts=artifacts,
            )
            attempts.append(attempt)
            for call in _collect_model_calls(metrics.get("backend")):
                model_calls.append(
                    {
                        "work_item_id": record["work_item_id"],
                        "execution_id": record["execution_id"],
                        "generation": record["generation"],
                        **call,
                    }
                )

        from src.evals.eval_orchestration import _build_retry_summary

        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "summary": build_performance_summary(
                attempts,
                evaluation_wall_time_seconds=(
                    self.execution_invocation_wall_time_seconds(
                        invocation_ids={
                            str(record["invocation_id"])
                            for record in performance_records
                        }
                    )
                ),
            ),
            "retries": _build_retry_summary(attempts),
            "model_calls": _duration_summary(model_calls),
            "recorded_executions": len(performance_records),
        }
        _write_json_atomic(self.performance_summary_path, payload)
        return self.performance_summary_path


def _attempt_metadata(
    plan: dict[str, Any],
    latest: dict[str, Any],
    history: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    return {
        "run_index": int(plan["repetition_index"]),
        "work_item_id": plan["work_item_id"],
        "execution_id": latest["execution_id"],
        "execution_generation": int(latest["generation"]),
        "invocation_id": latest["invocation_id"],
        "execution_history": [
            {
                "execution_id": record["execution_id"],
                "generation": int(record["generation"]),
                "invocation_id": record["invocation_id"],
                "execution_status": record["attempt"]["execution_status"],
                "output_contract_status": record["attempt"]["output_contract_status"],
                "scoring_status": record["attempt"]["scoring_status"],
                "failure_type": record["attempt"].get("failure_type"),
            }
            for record in history
        ],
    }


def _materialized_attempt(
    attempt: Any,
    *,
    field_contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for contract in field_contracts:
        key = str(contract["key"])
        evaluation = attempt.evaluations.get(key)
        fields[key] = {
            "applicable": key in attempt.applicable_fields,
            "graded": bool(contract.get("graded")),
            "confidence": attempt.confidence_values.get(key),
            "correct": evaluation.correct if evaluation is not None else None,
            "normalized_expected": (
                evaluation.normalized_expected if evaluation is not None else None
            ),
            "normalized_actual": (
                evaluation.normalized_actual if evaluation is not None else None
            ),
            "details": evaluation.details if evaluation is not None else {},
        }
    metadata = attempt.metadata
    return {
        "run_index": metadata.get("run_index"),
        "work_item_id": metadata.get("work_item_id"),
        "execution_id": metadata.get("execution_id"),
        "execution_generation": metadata.get("execution_generation"),
        "invocation_id": metadata.get("invocation_id"),
        "execution_status": attempt.execution_status.value,
        "output_contract_status": attempt.output_contract_status.value,
        "scoring_status": attempt.scoring_status.value,
        "complete_evaluation_correct": attempt.complete_evaluation_correct,
        "evaluations": fields,
        "contract_errors": list(attempt.contract_errors),
        "agent_output": attempt.get_artifact("agent_output"),
        "failure_type": attempt.failure_type.value if attempt.failure_type else None,
        "error": attempt.error,
        "failure_details": attempt.get_artifact("failure_details"),
        "usage": attempt.get_artifact("usage"),
        "cost": attempt.get_artifact("cost")
        or {
            "status": "unavailable",
            "actual": None,
            "estimated": None,
            "reason": "Provider cost telemetry is not available.",
        },
    }


def _collect_model_calls(value: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    if isinstance(value, dict):
        calls = value.get("model_calls")
        if isinstance(calls, list):
            output.extend(item for item in calls if isinstance(item, dict))
        for item in value.values():
            output.extend(_collect_model_calls(item))
    elif isinstance(value, list):
        for item in value:
            output.extend(_collect_model_calls(item))
    return output


def _duration_summary(calls: list[dict[str, Any]]) -> dict[str, Any]:
    durations = sorted(
        float(item["duration_seconds"])
        for item in calls
        if isinstance(item.get("duration_seconds"), (int, float))
        and not isinstance(item.get("duration_seconds"), bool)
    )
    statuses: dict[str, int] = {}
    duration_exceeded_timeout = 0
    retry_categories: dict[str, int] = {}
    for item in calls:
        status = str(item.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
        if item.get("duration_exceeded_configured_timeout") is True:
            duration_exceeded_timeout += 1
        attempts = item.get("transport_attempts")
        for attempt in attempts if isinstance(attempts, list) else []:
            if not isinstance(attempt, dict):
                continue
            category = attempt.get("retry_category")
            if isinstance(category, str):
                retry_categories[category] = retry_categories.get(category, 0) + 1

    def percentile(fraction: float) -> float | None:
        if not durations:
            return None
        index = min(len(durations) - 1, int((len(durations) - 1) * fraction + 0.5))
        return durations[index]

    p95 = percentile(0.95)
    return {
        "count": len(calls),
        "status_counts": dict(sorted(statuses.items())),
        "duration_exceeded_configured_timeout_count": duration_exceeded_timeout,
        "transport_retry_categories": dict(sorted(retry_categories.items())),
        "long_tail_at_or_above_p95_count": (
            sum(value >= p95 for value in durations) if p95 is not None else 0
        ),
        "duration_seconds": {
            "minimum": durations[0] if durations else None,
            "median": percentile(0.5),
            "p95": p95,
            "maximum": durations[-1] if durations else None,
        },
        "slowest": sorted(
            (
                {
                    key: item.get(key)
                    for key in (
                        "work_item_id",
                        "execution_id",
                        "generation",
                        "sequence",
                        "duration_seconds",
                        "status",
                        "timeout_seconds",
                        "duration_exceeded_configured_timeout",
                        "transport_attempts_observed",
                        "provider_response_id",
                        "error_type",
                    )
                }
                for item in calls
            ),
            key=lambda item: float(item.get("duration_seconds") or 0.0),
            reverse=True,
        )[:10],
    }


def _record_state(record: dict[str, Any] | None) -> str:
    if record is None:
        return "missing"
    attempt = record["attempt"]
    if attempt["execution_status"] == "cancelled":
        return "cancelled"
    healthy = (
        attempt["execution_status"] == "completed"
        and attempt["output_contract_status"] == "valid"
        and attempt["scoring_status"] in {"scored", "no_applicable_targets"}
    )
    return "completed" if healthy else "failed"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RunStoreIntegrityError(f"Expected a JSON object: {path}")
    return payload


def _write_json_create(path: Path, payload: dict[str, Any]) -> None:
    """Atomically create one exact path and fail if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _write_temporary(path, payload)
    try:
        os.link(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomically replace a deterministic materialized view."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _write_temporary(path, payload)
    try:
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_temporary(path: Path, payload: dict[str, Any]) -> Path:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_file.write(encoded)
        temporary_file.flush()
        os.fsync(temporary_file.fileno())
        return Path(temporary_file.name)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
