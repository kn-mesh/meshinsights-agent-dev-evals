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
from typing import Any, Literal
import uuid

from evaluation import (
    build_run_identity,
    build_work_item_id,
    canonical_json_bytes,
    canonical_sha256,
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
            for key in ("run_id", "run_spec_sha256", "run_spec", "work_items"):
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

    def write_result(self, payload: dict[str, Any]) -> Path:
        _write_json_atomic(self.result_path, payload)
        return self.result_path


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
