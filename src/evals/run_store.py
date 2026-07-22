"""Durable local storage for resumable evaluation execution."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
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
    build_run_identity,
    build_work_item_id,
    canonical_json_bytes,
    canonical_sha256,
    eval_attempt_from_dict,
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
    """Append-only attempt generations plus a materialized result view."""

    def __init__(self, run_dir: Path, *, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.manifest_path = run_dir / "manifest.json"
        self.result_path = run_dir / "result.json"
        self.attempts_dir = run_dir / "attempts"
        self.invocations_dir = run_dir / "invocations"
        self.lock_path = run_dir / ".coordinator.lock"

    def initialize(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Create an immutable manifest or validate the existing identity."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            existing = self.read_manifest()
            for key in (
                "run_id",
                "run_spec_sha256",
                "run_spec",
                "work_items",
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
        derived_run_id, derived_hash = build_run_identity(run_spec)
        if expected != derived_hash or self.run_id != derived_run_id:
            raise RunStoreIntegrityError(
                f"Manifest run specification identity is invalid: {self.manifest_path}"
            )
        return payload

    @contextmanager
    def coordinator_lock(self, *, invocation_id: str) -> Iterator[None]:
        """Allow one local coordinator for a deterministic run."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
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
        agent = self.read_manifest()["run_spec"].get("agent", {})
        if record.get("agent_version_id") != agent.get(
            "agent_version_id"
        ) or record.get("agent_version_manifest_sha256") != agent.get(
            "manifest_sha256"
        ):
            raise RunStoreIntegrityError("Attempt agent-version identity is invalid.")
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
            agent = manifest["run_spec"].get("agent", {})
            if record.get("agent_version_id") != agent.get(
                "agent_version_id"
            ) or record.get("agent_version_manifest_sha256") != agent.get(
                "manifest_sha256"
            ):
                raise RunStoreIntegrityError(
                    f"Attempt agent-version identity mismatch: {path}"
                )
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

    def execution_invocation_wall_time_seconds(self) -> float:
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
        """Build and atomically replace the canonical schema-v3 result view."""
        payload = self.build_result(
            completed_at_utc=completed_at_utc,
            latest_invocation_id=latest_invocation_id,
        )
        _write_json_atomic(self.result_path, payload)
        return self.result_path

    def write_result(self, payload: dict[str, Any]) -> Path:
        """Validate a caller-provided view before replacing the canonical result."""
        self._validate_result(payload)
        _write_json_atomic(self.result_path, payload)
        return self.result_path

    def read_verified_result(self) -> dict[str, Any]:
        """Read a complete result view and verify it against durable evidence."""
        payload = _read_json(self.result_path)
        self._validate_result(payload)
        return payload

    def _validate_result(self, payload: dict[str, Any]) -> None:
        """Require the canonical view of the manifest and latest attempts."""
        config = payload.get("run_config")
        if not isinstance(config, dict):
            raise RunStoreIntegrityError("Evaluation result is missing run_config.")
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
        expected = self.build_result(
            completed_at_utc=completed_at_utc,
            latest_invocation_id=latest_invocation_id,
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
    ) -> dict[str, Any]:
        """Rebuild schema-v3 output from immutable run contracts and attempts."""
        manifest = self.read_manifest()
        contract = manifest.get("result_materialization")
        if not isinstance(contract, dict) or contract.get("contract_version") != 1:
            raise RunStoreIntegrityError(
                "Run manifest is missing its result materialization contract."
            )
        expected_config = dict(contract.get("run_config", {}))
        expected_config["completed_at_utc"] = completed_at_utc
        expected_config["latest_invocation_id"] = latest_invocation_id
        if not any(self.invocations_dir.glob(f"{latest_invocation_id}.*.json")):
            raise RunStoreIntegrityError(
                "Evaluation result references an unknown invocation."
            )

        histories = self.records_by_work_item()
        plans = list(manifest.get("work_items", []))
        planned_ids = {str(item["work_item_id"]) for item in plans}
        if set(histories) != planned_ids:
            raise RunStoreIntegrityError(
                "A complete result requires a latest attempt for every planned work item."
            )

        static_rows = contract.get("result_rows")
        selected = contract.get("selected_example_ids")
        fields = contract.get("output_fields")
        if (
            not isinstance(static_rows, list)
            or not isinstance(selected, list)
            or not isinstance(fields, list)
        ):
            raise RunStoreIntegrityError(
                "Result materialization contract is malformed."
            )
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
                _materialized_attempt(attempt, row=row, field_contracts=fields)
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
        # Lazy import avoids the orchestration -> comparison -> integrity cycle.
        from src.evals.eval_orchestration import _build_summary

        return {
            "summary": _build_summary(
                summary_rows,
                profile=cast("EvaluationProfile", summary_profile),
                runs_per_example=int(expected_config["runs_per_example"]),
                evaluation_wall_time_seconds=(
                    self.execution_invocation_wall_time_seconds()
                ),
            ),
            "run_config": expected_config,
            "selected_example_ids": selected,
            "results": expected_rows,
        }


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
        "agent_version_id": latest["agent_version_id"],
        "agent_version_manifest_sha256": latest["agent_version_manifest_sha256"],
        "started_at_utc": latest["started_at_utc"],
        "completed_at_utc": latest["completed_at_utc"],
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
    row: dict[str, Any],
    field_contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for contract in field_contracts:
        key = str(contract["key"])
        evaluation = attempt.evaluations.get(key)
        expected = None
        if key in attempt.applicable_fields and contract.get("graded"):
            expected = _read_path(
                row.get("benchmark_labels", {}),
                contract.get("benchmark_label_path") or (),
            )
        fields[key] = {
            "applicable": key in attempt.applicable_fields,
            "graded": bool(contract.get("graded")),
            "expected": expected,
            "actual": attempt.actual_values.get(key),
            "confidence": attempt.confidence_values.get(key),
            "correct": evaluation.correct if evaluation is not None else None,
            "grader": (
                {
                    "id": evaluation.grader_id,
                    "version": evaluation.grader_version,
                    "config": evaluation.grader_config,
                }
                if evaluation is not None
                else None
            ),
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
        "agent_version_id": metadata.get("agent_version_id"),
        "agent_version_manifest_sha256": metadata.get("agent_version_manifest_sha256"),
        "started_at_utc": metadata.get("started_at_utc"),
        "completed_at_utc": metadata.get("completed_at_utc"),
        "execution_history": metadata.get("execution_history", []),
        "execution_status": attempt.execution_status.value,
        "output_contract_status": attempt.output_contract_status.value,
        "scoring_status": attempt.scoring_status.value,
        "complete_evaluation_correct": attempt.complete_evaluation_correct,
        "fields": fields,
        "actual_outputs": attempt.actual_values,
        "contract_errors": list(attempt.contract_errors),
        "agent_output": attempt.get_artifact("agent_output"),
        "output_observations": attempt.get_artifact("output_observations"),
        "failure_type": attempt.failure_type.value if attempt.failure_type else None,
        "error": attempt.error,
        "failure_details": attempt.get_artifact("failure_details"),
        "duration_seconds": attempt.duration_seconds,
        "stage_durations_seconds": attempt.stage_durations_seconds,
        "usage": attempt.get_artifact("usage"),
        "retry_telemetry": attempt.get_artifact("retry_telemetry"),
        "cost": attempt.get_artifact("cost")
        or {
            "status": "unavailable",
            "actual": None,
            "estimated": None,
            "reason": "Provider cost telemetry is not available.",
        },
    }


def _read_path(payload: Any, path: Any) -> Any:
    current = payload
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


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
