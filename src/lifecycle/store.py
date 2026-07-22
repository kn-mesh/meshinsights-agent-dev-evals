"""Recoverable quarantine operations over the derived lifecycle catalog."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator
import uuid

from evaluation import canonical_sha256

from src.lifecycle.catalog import LocalLifecycleCatalog
from src.lifecycle.models import (
    DeletionPlan,
    EntityKind,
    LifecycleOperation,
    PlannedPath,
)


class LifecycleError(RuntimeError):
    """A lifecycle operation is unsafe, ambiguous, or inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class LocalLifecycleStore:
    """Plan and execute exact, recoverable local evidence deletion."""

    def __init__(
        self,
        project_root: Path,
        *,
        eval_root: Path | None = None,
        agent_root: Path | None = None,
        lifecycle_root: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.eval_root = (eval_root or self.project_root / "eval_results").resolve()
        self.agent_root = (agent_root or self.project_root / "agent_versions").resolve()
        self.lifecycle_root = (
            lifecycle_root or self.project_root / ".workbench" / "lifecycle"
        ).resolve()
        self.operations_dir = self.lifecycle_root / "operations"
        self.quarantine_dir = self.lifecycle_root / "quarantine"
        self.lock_path = self.lifecycle_root / ".lock"
        for root in (self.eval_root, self.agent_root, self.lifecycle_root):
            self._require_within(root)

    def catalog(self):
        return LocalLifecycleCatalog(
            self.project_root,
            eval_root=self.eval_root,
            agent_root=self.agent_root,
        ).build()

    def plan_delete(self, target_kind: EntityKind, target_id: str) -> DeletionPlan:
        target_id = target_id.strip()
        if not target_id:
            raise LifecycleError("Lifecycle target id must not be empty.")
        catalog = self.catalog()
        invalid_findings = [
            finding
            for finding in catalog.findings
            if finding.code.startswith("invalid_")
        ]
        if invalid_findings:
            raise LifecycleError(
                "Managed lifecycle evidence is corrupt; run verify before deletion: "
                + "; ".join(item.message for item in invalid_findings)
            )

        raw_paths: list[tuple[Path, str]] = []
        if target_kind == "run":
            matches = [item for item in catalog.runs if item.run_id == target_id]
            if len(matches) != 1:
                raise LifecycleError(
                    f"Expected one managed run {target_id}; found {len(matches)}."
                )
            run = matches[0]
            run_path = self.project_root / run.path
            self._require_in_root(run_path, self.eval_root)
            self._require_inactive_run(run_path)
            raw_paths.append((run_path, "managed eval run"))
        elif target_kind == "comparison":
            matches = [
                item for item in catalog.comparisons if item.comparison_id == target_id
            ]
            if len(matches) != 1:
                raise LifecycleError(
                    f"Expected one managed comparison {target_id}; found {len(matches)}."
                )
            comparison = matches[0]
            raw_paths.append(
                (
                    self.project_root / comparison.manifest_path,
                    "comparison manifest",
                )
            )
            if comparison.result_path is not None:
                raw_paths.append(
                    (self.project_root / comparison.result_path, "comparison result")
                )
        elif target_kind == "version":
            matches = [
                item for item in catalog.versions if item.agent_version_id == target_id
            ]
            if len(matches) != 1:
                raise LifecycleError(
                    f"Expected one managed agent version {target_id}; found {len(matches)}."
                )
            version = matches[0]
            if version.lifecycle_state != "promoted" or version.manifest_path is None:
                raise LifecycleError(
                    "Candidate-only versions are retained by their eval runs; delete "
                    "the owning runs instead."
                )
            raw_paths.append(
                (self.project_root / version.manifest_path, "promoted version manifest")
            )
            raw_paths.extend(self._version_catalog_paths(target_id))
            retained_digests = {
                digest
                for item in catalog.versions
                if item.lifecycle_state == "promoted"
                and item.agent_version_id != target_id
                for digest in item.global_cas_objects
            }
            for digest in version.global_cas_objects:
                if digest not in retained_digests:
                    raw_paths.append(
                        (
                            self.agent_root
                            / "objects"
                            / "sha256"
                            / digest[:2]
                            / digest,
                            "unreachable promoted-version CAS object",
                        )
                    )
        else:  # pragma: no cover - Literal plus CLI choices constrain this
            raise LifecycleError(f"Unsupported lifecycle target kind: {target_kind}")

        planned_paths = tuple(
            self._planned_path(path, reason)
            for path, reason in self._deduplicate_paths(raw_paths)
        )
        warnings = tuple(
            sorted(
                self._reference_warning(reference, target_kind, target_id)
                for reference in catalog.references
                if reference.target_kind == target_kind
                and reference.target_id == target_id
                and not (
                    target_kind == "version"
                    and reference.source_kind in {"alias", "promotion"}
                )
            )
        )
        unsigned = {
            "deletion_plan_schema_version": 1,
            "target_kind": target_kind,
            "target_id": target_id,
            "paths": [item.model_dump(mode="json") for item in planned_paths],
            "warnings": list(warnings),
            "file_count": sum(item.file_count for item in planned_paths),
            "bytes": sum(item.bytes for item in planned_paths),
        }
        return DeletionPlan(
            **unsigned,
            plan_sha256=canonical_sha256(unsigned),
        )

    def quarantine(
        self, target_kind: EntityKind, target_id: str, *, confirmed: bool
    ) -> LifecycleOperation:
        if not confirmed:
            raise LifecycleError("Lifecycle deletion requires explicit confirmation.")
        with self._operation_lock():
            plan = self.plan_delete(target_kind, target_id)
            operation_id = f"del_{uuid.uuid4().hex}"
            payload_root = self.quarantine_dir / operation_id / "payload"
            self._require_within(payload_root)
            timestamp = utc_now()
            operation = LifecycleOperation(
                operation_id=operation_id,
                state="staging",
                target_kind=target_kind,
                target_id=target_id,
                plan_sha256=plan.plan_sha256,
                paths=plan.paths,
                warnings=plan.warnings,
                created_at_utc=timestamp,
                updated_at_utc=timestamp,
            )
            self._write_operation(operation, create=True)
            moved: list[tuple[Path, Path]] = []
            try:
                for item in plan.paths:
                    source = self.project_root / item.path
                    destination = payload_root / item.path
                    self._verify_planned_at(source, item)
                    if destination.exists() or destination.is_symlink():
                        raise LifecycleError(
                            f"Quarantine destination already exists: {destination}"
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
                    moved.append((source, destination))
                operation = operation.model_copy(
                    update={"state": "quarantined", "updated_at_utc": utc_now()}
                )
                self._write_operation(operation, create=False)
            except BaseException:
                for source, destination in reversed(moved):
                    if destination.exists() and not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(destination, source)
                operation = operation.model_copy(
                    update={"state": "restored", "updated_at_utc": utc_now()}
                )
                self._write_operation(operation, create=False)
                raise
            return operation

    def restore(self, operation_id: str, *, confirmed: bool) -> LifecycleOperation:
        if not confirmed:
            raise LifecycleError("Lifecycle restore requires explicit confirmation.")
        with self._operation_lock():
            operation = self.load_operation(operation_id)
            if operation.state not in {"staging", "quarantined", "restoring"}:
                raise LifecycleError(
                    f"Operation cannot be restored from state {operation.state}."
                )
            if operation.state != "restoring":
                operation = operation.model_copy(
                    update={"state": "restoring", "updated_at_utc": utc_now()}
                )
                self._write_operation(operation, create=False)
            payload_root = self.quarantine_dir / operation.operation_id / "payload"
            pairs: list[tuple[Path, Path, Any]] = []
            for item in operation.paths:
                source = payload_root / item.path
                destination = self.project_root / item.path
                self._require_within(source)
                self._require_within(destination)
                source_exists = source.exists() or source.is_symlink()
                destination_exists = destination.exists() or destination.is_symlink()
                if source_exists and destination_exists:
                    raise LifecycleError(
                        f"Both quarantine and restore paths exist: {item.path}"
                    )
                if not source_exists and not destination_exists:
                    raise LifecycleError(
                        f"Lifecycle operation path is missing: {item.path}"
                    )
                self._verify_planned_at(
                    source if source_exists else destination,
                    item,
                )
                pairs.append((source, destination, item))
            for source, destination, _ in pairs:
                if source.exists() or source.is_symlink():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
            restored = operation.model_copy(
                update={"state": "restored", "updated_at_utc": utc_now()}
            )
            self._write_operation(restored, create=False)
            return restored

    def purge(self, operation_id: str, *, confirmed: bool) -> LifecycleOperation:
        if not confirmed:
            raise LifecycleError("Lifecycle purge requires explicit confirmation.")
        with self._operation_lock():
            operation = self.load_operation(operation_id)
            if operation.state not in {"quarantined", "purging"}:
                raise LifecycleError(
                    f"Operation cannot be purged from state {operation.state}."
                )
            operation_root = self.quarantine_dir / operation.operation_id
            self._require_within(operation_root)
            staging = self.quarantine_dir / f".{operation.operation_id}.purge"
            self._require_within(staging)
            if staging.exists() or staging.is_symlink():
                if operation.state != "purging":
                    raise LifecycleError(
                        f"Purge staging path already exists: {staging}"
                    )
            else:
                if operation_root.is_symlink():
                    raise LifecycleError(
                        "Quarantine operation directory must not be a symlink."
                    )
                if not operation_root.is_dir():
                    raise LifecycleError(
                        f"Quarantine operation directory is missing: {operation_root}"
                    )
                if operation.state == "purging" and not operation_root.exists():
                    raise LifecycleError(
                        f"Interrupted purge has no recoverable payload: {operation_id}"
                    )
                operation = operation.model_copy(
                    update={"state": "purging", "updated_at_utc": utc_now()}
                )
                self._write_operation(operation, create=False)
                os.replace(operation_root, staging)
            try:
                shutil.rmtree(staging)
            except BaseException:
                if staging.exists() and not operation_root.exists():
                    os.replace(staging, operation_root)
                raise
            purged = operation.model_copy(
                update={"state": "purged", "updated_at_utc": utc_now()}
            )
            self._write_operation(purged, create=False)
            return purged

    def preview_operation(self, operation_id: str, action: str) -> dict[str, Any]:
        operation = self.load_operation(operation_id)
        if action not in {"restore", "purge"}:
            raise LifecycleError(f"Unsupported lifecycle action: {action}")
        allowed = (
            {"staging", "quarantined", "restoring"}
            if action == "restore"
            else {"quarantined", "purging"}
        )
        if operation.state not in allowed:
            raise LifecycleError(
                f"Operation cannot be {action}d from state {operation.state}."
            )
        return {
            "action": action,
            "dry_run": True,
            **operation.model_dump(mode="json"),
        }

    def load_operation(self, operation_id: str) -> LifecycleOperation:
        if not operation_id.startswith("del_") or not operation_id[4:].isalnum():
            raise LifecycleError(f"Invalid lifecycle operation id: {operation_id}")
        path = self.operations_dir / f"{operation_id}.json"
        self._require_within(path)
        try:
            return LifecycleOperation.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as error:
            raise LifecycleError(
                f"Unknown or invalid lifecycle operation: {operation_id}"
            ) from error

    def _version_catalog_paths(self, version_id: str) -> list[tuple[Path, str]]:
        output: list[tuple[Path, str]] = []
        for directory, reason in (
            (self.agent_root / "catalog" / "aliases", "version alias"),
            (self.agent_root / "catalog" / "promotions", "promotion event"),
        ):
            for path in sorted(directory.glob("*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise LifecycleError(
                        f"Invalid version catalog record: {path}"
                    ) from error
                if (
                    isinstance(payload, dict)
                    and payload.get("agent_version_id") == version_id
                ):
                    output.append((path, reason))
        return output

    def _planned_path(self, path: Path, reason: str) -> PlannedPath:
        self._validate_source(path)
        file_count, byte_count, content_sha256 = self._path_evidence(path)
        return PlannedPath(
            path=path.resolve().relative_to(self.project_root).as_posix(),
            kind="directory" if path.is_dir() else "file",
            file_count=file_count,
            bytes=byte_count,
            content_sha256=content_sha256,
            reason=reason,
        )

    def _validate_source(self, path: Path) -> None:
        self._require_within(path)
        if path == self.project_root or path in {
            self.eval_root,
            self.agent_root,
            self.lifecycle_root,
        }:
            raise LifecycleError(f"Refusing broad lifecycle target: {path}")
        if not path.exists() and not path.is_symlink():
            raise LifecycleError(f"Lifecycle target does not exist: {path}")
        if path.is_symlink():
            raise LifecycleError(f"Lifecycle target must not be a symlink: {path}")
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_symlink():
                    raise LifecycleError(
                        f"Lifecycle target contains a symlink: {child}"
                    )

    @staticmethod
    def _path_evidence(path: Path) -> tuple[int, int, str]:
        if path.is_file():
            content = path.read_bytes()
            return (
                1,
                len(content),
                canonical_sha256(
                    {
                        "kind": "file",
                        "bytes": len(content),
                        "content_sha256": hashlib.sha256(content).hexdigest(),
                    }
                ),
            )
        files = [item for item in path.rglob("*") if item.is_file()]
        entries = []
        for item in sorted(files):
            content = item.read_bytes()
            entries.append(
                {
                    "path": item.relative_to(path).as_posix(),
                    "bytes": len(content),
                    "content_sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        return (
            len(entries),
            sum(item["bytes"] for item in entries),
            canonical_sha256({"kind": "directory", "files": entries}),
        )

    def _verify_planned_at(self, path: Path, planned: Any) -> None:
        self._validate_source(path)
        file_count, byte_count, content_sha256 = self._path_evidence(path)
        if (
            file_count != planned.file_count
            or byte_count != planned.bytes
            or content_sha256 != planned.content_sha256
        ):
            raise LifecycleError(
                f"Lifecycle operation content changed for {planned.path}."
            )

    @staticmethod
    def _deduplicate_paths(
        paths: list[tuple[Path, str]],
    ) -> list[tuple[Path, str]]:
        output: list[tuple[Path, str]] = []
        seen: set[Path] = set()
        for path, reason in paths:
            resolved = path.resolve()
            if resolved not in seen:
                output.append((path, reason))
                seen.add(resolved)
        return output

    @staticmethod
    def _reference_warning(reference: Any, target_kind: str, target_id: str) -> str:
        return (
            f"{reference.source_kind} {reference.source_id} retains "
            f"{reference.relation} -> {target_kind} {target_id}"
        )

    def _require_inactive_run(self, run_dir: Path) -> None:
        lock_path = run_dir / ".coordinator.lock"
        if not lock_path.exists():
            return
        if lock_path.is_symlink():
            raise LifecycleError(
                f"Run coordinator lock must not be a symlink: {lock_path}"
            )
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise LifecycleError(f"Eval run is active: {run_dir.name}") from error
            finally:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    @contextmanager
    def _operation_lock(self) -> Iterator[None]:
        self.lifecycle_root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_operation(self, operation: LifecycleOperation, *, create: bool) -> None:
        path = self.operations_dir / f"{operation.operation_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if create and path.exists():
            raise LifecycleError(f"Lifecycle operation already exists: {path}")
        encoded = (
            json.dumps(
                operation.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        try:
            if create:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _require_within(self, path: Path) -> None:
        try:
            path.resolve().relative_to(self.project_root)
        except ValueError as error:
            raise LifecycleError(
                f"Lifecycle path escapes the project: {path}"
            ) from error

    @staticmethod
    def _require_in_root(path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise LifecycleError(
                f"Lifecycle target is outside its managed root: {path}"
            ) from error
