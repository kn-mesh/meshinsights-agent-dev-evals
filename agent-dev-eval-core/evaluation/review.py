"""Run-scoped, disposable evaluation review storage."""

from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from evaluation.identity import canonical_sha256
from evaluation.security import is_sensitive_key


CaptureStatus = Literal["in_progress", "complete", "partial", "failed"]

_MAX_FAILURE_OBSERVATIONS = 100

_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "sig",
        "signature",
        "token",
        "access_token",
        "api_key",
        "apikey",
        "code",
    }
)
_BEARER_VALUE = re.compile(r"^\s*(?:bearer|basic)\s+\S+", re.IGNORECASE)
_COMMON_SECRET_VALUE = re.compile(
    r"^\s*(?:sk-[A-Za-z0-9_-]{12,}|gh[opusr]_[A-Za-z0-9_]{12,})\s*$"
)
_EMBEDDED_SECRET_VALUE = re.compile(
    r"(?:"
    r"\bauthorization\s*[:=]\s*(?:bearer|basic)\s+\S+"
    r"|\b(?:api[_-]?key|client[_-]?secret|password|private[_-]?key|"
    r"access[_-]?token|refresh[_-]?token|sas[_-]?token)\s*[:=]\s*\S+"
    r"|https?://\S*[?&](?:sig|signature|token|access_token|api_key|apikey|code)="
    r")",
    re.IGNORECASE,
)
_INLINE_CONTROL_KEYS = frozenset(
    {
        "capture_status",
        "execution_id",
        "run_id",
        "work_item_id",
    }
)


class ReviewStoreError(RuntimeError):
    """Review storage is corrupt or points outside its validated run."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class LocalReviewStore:
    """Disposable review manifests and objects scoped to one eval run."""

    schema_version = 1

    def __init__(
        self,
        run_dir: Path,
        *,
        run_id: str,
        inline_text_bytes: int = 4096,
    ) -> None:
        if inline_text_bytes < 0:
            raise ValueError("inline_text_bytes must be non-negative.")
        self.run_dir = run_dir.resolve()
        self.run_id = run_id
        self.inline_text_bytes = inline_text_bytes
        self.review_dir = self.run_dir / "review"
        self.capture_path = self.review_dir / "capture.json"
        self.index_path = self.review_dir / "index.json"
        self.executions_dir = self.review_dir / "executions"
        self.objects_dir = self.review_dir / "objects" / "sha256"
        self.staging_dir = self.review_dir / ".staging"
        self.lock_path = self.run_dir / ".review.lock"
        self.diagnosis_dir = self.run_dir / "diagnosis"
        self._capture_lock = threading.RLock()

    def initialize(self, *, run_spec_sha256: str, mode: str = "full") -> Path:
        """Create or validate the local-only capture descriptor."""
        with self._write_lock():
            return self._initialize_unlocked(
                run_spec_sha256=run_spec_sha256,
                mode=mode,
            )

    def _initialize_unlocked(self, *, run_spec_sha256: str, mode: str = "full") -> Path:
        if mode not in {"full", "off"}:
            raise ValueError(f"Unsupported review capture mode: {mode}.")
        self._validate_run_dir()
        self._recover_execution_transactions()
        payload = {
            "review_schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_spec_sha256": run_spec_sha256,
            "mode": mode,
            "publication": "local_only",
            "redaction_policy": "core.secrets-v1",
            "inline_text_bytes": self.inline_text_bytes,
            "status": "in_progress",
            "created_at_utc": utc_now(),
            "updated_at_utc": utc_now(),
            "execution_counts": {
                "complete": 0,
                "partial": 0,
                "failed": 0,
            },
            "object_count": 0,
            "logical_bytes": 0,
            "stored_bytes": 0,
            "expected_execution_ids": [],
            "capture_failure_count": 0,
            "capture_failures": [],
        }
        if self.capture_path.exists():
            existing = self._read_json(self.capture_path)
            for key, value in (
                ("review_schema_version", self.schema_version),
                ("run_id", self.run_id),
                ("run_spec_sha256", run_spec_sha256),
                ("publication", "local_only"),
            ):
                if existing.get(key) != value:
                    raise ReviewStoreError(
                        f"Review capture descriptor conflicts at {key!r}."
                    )
            existing["status"] = "in_progress"
            existing["updated_at_utc"] = utc_now()
            existing.setdefault("expected_execution_ids", [])
            existing.setdefault("capture_failure_count", 0)
            existing.setdefault("capture_failures", [])
            self._atomic_write_json(self.capture_path, existing)
            self._discard_staging()
            return self.capture_path
        self._atomic_write_json(self.capture_path, payload)
        self._discard_staging()
        return self.capture_path

    def commit_execution(self, manifest: dict[str, Any]) -> Path:
        """Persist one hash-verified execution review manifest."""
        with self._write_lock():
            return self._commit_execution_unlocked(manifest)

    def _commit_execution_unlocked(self, manifest: dict[str, Any]) -> Path:
        self._validate_run_dir()
        if manifest.get("run_id") != self.run_id:
            raise ReviewStoreError("Execution review has the wrong run id.")
        execution_id = str(manifest.get("execution_id", "")).strip()
        work_item_id = str(manifest.get("work_item_id", "")).strip()
        if not execution_id or not work_item_id:
            raise ReviewStoreError(
                "Execution review requires execution_id and work_item_id."
            )
        if not execution_id.startswith(f"{work_item_id}."):
            raise ReviewStoreError("Execution review identity is inconsistent.")
        status = str(manifest.get("capture_status", "complete"))
        if status not in {"complete", "partial", "failed"}:
            raise ReviewStoreError(f"Invalid execution capture status: {status}.")

        path = (
            self.executions_dir
            / self._safe_token(work_item_id)[:2]
            / f"{self._safe_token(execution_id)}.json"
        )
        self._assert_within_review(path)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        transaction = Path(tempfile.mkdtemp(prefix="execution-", dir=self.staging_dir))
        staged_objects = transaction / "objects" / "sha256"
        published: list[Path] = []
        try:
            safe_payload = self._externalize(
                self._redact(manifest), object_root=staged_objects
            )
            unsigned = {
                "review_schema_version": self.schema_version,
                **safe_payload,
            }
            unsigned.pop("manifest_sha256", None)
            encoded = {**unsigned, "manifest_sha256": canonical_sha256(unsigned)}
            staged_manifest = transaction / "manifest.json"
            self._write_json_create(staged_manifest, encoded)
            object_relative_paths = [
                (self.objects_dir / staged.parent.name / staged.name)
                .relative_to(self.review_dir)
                .as_posix()
                for staged in sorted(staged_objects.glob("*/*"))
            ]
            journal_path = transaction / "journal.json"
            journal = {
                "review_transaction_schema_version": 1,
                "run_id": self.run_id,
                "execution_id": execution_id,
                "manifest_relative_path": path.relative_to(self.review_dir).as_posix(),
                "manifest_sha256": encoded["manifest_sha256"],
                "object_relative_paths": object_relative_paths,
                "phase": "staged",
            }
            self._write_json_create(journal_path, journal)

            # The manifest is the commit point. Objects are promoted under the same
            # process lock and rolled back if publishing the manifest fails.
            with self._capture_lock:
                if path.exists():
                    existing = self._read_json(path)
                    if existing != encoded:
                        raise ReviewStoreError(
                            f"Conflicting execution review manifest: {path}"
                        )
                else:
                    try:
                        journal["phase"] = "publishing"
                        self._atomic_write_json(journal_path, journal)
                        for staged in sorted(staged_objects.glob("*/*")):
                            destination = (
                                self.objects_dir / staged.parent.name / staged.name
                            )
                            self._assert_within_review(destination)
                            if destination.exists():
                                if (
                                    hashlib.sha256(destination.read_bytes()).hexdigest()
                                    != staged.name
                                ):
                                    raise ReviewStoreError(
                                        f"Review object digest mismatch: {destination}"
                                    )
                            else:
                                destination.parent.mkdir(parents=True, exist_ok=True)
                                os.replace(staged, destination)
                                published.append(destination)
                        self._write_bytes_create(path, staged_manifest.read_bytes())
                        journal["phase"] = "committed"
                        self._atomic_write_json(journal_path, journal)
                    except BaseException:
                        for object_path in published:
                            object_path.unlink(missing_ok=True)
                        raise
                self._refresh_capture_progress()
        finally:
            shutil.rmtree(transaction, ignore_errors=True)
        return path

    def record_failure(
        self,
        *,
        execution_id: str,
        work_item_id: str,
        error: BaseException,
    ) -> None:
        """Record a bounded, redacted capture failure without failing the eval."""
        with self._write_lock():
            self._record_failure_unlocked(
                execution_id=execution_id,
                work_item_id=work_item_id,
                error=error,
            )

    def _record_failure_unlocked(
        self,
        *,
        execution_id: str,
        work_item_id: str,
        error: BaseException,
    ) -> None:
        self._safe_token(execution_id)
        self._safe_token(work_item_id)
        observation = self._redact(
            {
                "execution_id": execution_id,
                "work_item_id": work_item_id,
                "error_type": type(error).__name__,
                "reason": str(error)[:1000],
                "observed_at_utc": utc_now(),
            }
        )
        with self._capture_lock:
            capture = self._read_json(self.capture_path)
            failures = list(capture.get("capture_failures", []))
            failures = [
                item for item in failures if item.get("execution_id") != execution_id
            ]
            failures.append(observation)
            capture["capture_failures"] = failures[-_MAX_FAILURE_OBSERVATIONS:]
            capture["capture_failure_count"] = max(
                int(capture.get("capture_failure_count", 0)) + 1,
                len(capture["capture_failures"]),
            )
            capture["status"] = "in_progress"
            capture["updated_at_utc"] = utc_now()
            self._atomic_write_json(self.capture_path, capture)

    def finalize(self, *, expected_execution_ids: list[str]) -> dict[str, Any]:
        """Finalize capture against the durable executions that should be reviewable."""
        with self._write_lock():
            return self._finalize_unlocked(
                expected_execution_ids=expected_execution_ids
            )

    def _finalize_unlocked(
        self, *, expected_execution_ids: list[str]
    ) -> dict[str, Any]:
        expected = sorted({self._safe_token(item) for item in expected_execution_ids})
        with self._capture_lock:
            capture = self._read_json(self.capture_path)
            capture["expected_execution_ids"] = expected
            summary = self._derive_capture_summary(
                capture, expected_execution_ids=expected
            )
            if summary.get("status") == "complete":
                capture.pop("review_unavailable_reason", None)
            capture.update(summary)
            capture["updated_at_utc"] = utc_now()
            self._atomic_write_json(self.capture_path, capture)
            return capture

    def review_state(
        self, *, expected_execution_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Derive capture, integrity, and a stable index source fingerprint."""
        self._validate_run_dir()
        if not self.capture_path.exists():
            capture = {
                "status": "absent",
                "mode": "off",
                "review_unavailable_reason": {"code": "absent"},
            }
            fingerprint = canonical_sha256(
                {
                    "capture": None,
                    "expected_execution_ids": sorted(expected_execution_ids or ()),
                    "manifests": [],
                    "objects": [],
                    "staging": [],
                }
            )
            return {
                "capture": capture,
                "integrity": {"status": "valid", "errors": []},
                "review_state_sha256": fingerprint,
            }
        capture = self._read_json(self.capture_path)
        expected = expected_execution_ids
        if expected is None:
            raw_expected = capture.get("expected_execution_ids", [])
            expected = [str(item) for item in raw_expected if isinstance(item, str)]
        integrity_errors: list[str] = []
        manifests: tuple[dict[str, Any], ...]
        try:
            manifests = self.iter_execution_manifests()
        except ReviewStoreError as error:
            manifests = ()
            integrity_errors.append(str(error))
        references = list(self._local_references(manifests))
        referenced_paths = {str(item.get("relative_path")) for item in references}
        object_inventory: list[dict[str, Any]] = []
        for path in self._object_paths():
            relative = path.relative_to(self.review_dir).as_posix()
            try:
                content = path.read_bytes()
                actual_sha256 = hashlib.sha256(content).hexdigest()
            except OSError as error:
                actual_sha256 = f"unreadable:{type(error).__name__}"
                integrity_errors.append(f"Cannot read review object: {path}")
            object_inventory.append(
                {
                    "relative_path": relative,
                    "byte_size": path.stat().st_size,
                    "actual_sha256": actual_sha256,
                }
            )
        stored_paths = {item["relative_path"] for item in object_inventory}
        inventory_by_relative = {
            str(item["relative_path"]): item for item in object_inventory
        }
        orphaned = sorted(stored_paths - referenced_paths)
        missing = sorted(referenced_paths - stored_paths)
        if orphaned:
            integrity_errors.append(
                f"Orphaned review objects found: {', '.join(orphaned[:5])}"
            )
        if missing:
            integrity_errors.append(
                f"Missing review objects found: {', '.join(missing[:5])}"
            )
        for reference in references:
            relative = str(reference.get("relative_path"))
            digest = str(reference.get("content_sha256"))
            inventory = inventory_by_relative.get(relative)
            if inventory is not None and inventory["actual_sha256"] != digest:
                integrity_errors.append(
                    f"Review object digest mismatch: {self.review_dir / relative}"
                )
        staging = (
            sorted(
                path.relative_to(self.review_dir).as_posix()
                for path in self.staging_dir.rglob("*")
            )
            if self.staging_dir.exists()
            else []
        )
        if staging:
            integrity_errors.append("Unfinished review capture staging content exists.")
        derived = self._derive_capture_summary(
            capture,
            expected_execution_ids=expected,
            preserve_in_progress=capture.get("status") == "in_progress",
            manifests=manifests,
        )
        descriptor_mismatches = [
            key
            for key in (
                "status",
                "execution_counts",
                "object_count",
                "logical_bytes",
                "stored_bytes",
            )
            if capture.get(key) != derived.get(key)
        ]
        integrity_errors.extend(
            f"Capture descriptor mismatch at {key!r}." for key in descriptor_mismatches
        )
        manifest_fingerprints = [
            {
                "execution_id": item.get("execution_id"),
                "manifest_sha256": item.get("manifest_sha256"),
            }
            for item in manifests
        ]
        fingerprint = canonical_sha256(
            {
                "capture": capture,
                "expected_execution_ids": sorted(expected),
                "manifests": manifest_fingerprints,
                "objects": object_inventory,
                "staging": staging,
                "integrity_errors": integrity_errors,
            }
        )
        derived_capture = {
            **capture,
            **derived,
        }
        return {
            "capture": derived_capture,
            "integrity": {
                "status": "invalid" if integrity_errors else "valid",
                "errors": integrity_errors[:_MAX_FAILURE_OBSERVATIONS],
                "orphaned_object_count": len(orphaned),
                "missing_object_count": len(missing),
                "unfinished_transaction_count": len(
                    [path for path in staging if path.endswith("journal.json")]
                ),
            },
            "review_state_sha256": fingerprint,
        }

    def read_execution(
        self,
        execution_id: str,
        *,
        resolve_text: bool = False,
        section: str | None = None,
    ) -> dict[str, Any]:
        """Read one execution manifest and optionally resolve text references."""
        self._validate_run_dir()
        matches = tuple(
            self.executions_dir.glob(f"*/{self._safe_token(execution_id)}.json")
        )
        if len(matches) != 1:
            raise ReviewStoreError(
                f"Expected one review manifest for {execution_id}; found {len(matches)}."
            )
        payload = self._read_json(matches[0])
        self._verify_manifest(payload, matches[0])
        if section is not None:
            if section not in payload:
                raise ReviewStoreError(f"Review execution has no section {section!r}.")
            payload = {
                "run_id": payload["run_id"],
                "execution_id": payload["execution_id"],
                "capture_status": payload["capture_status"],
                section: payload[section],
            }
        return self._resolve_text_references(payload) if resolve_text else payload

    def iter_execution_manifests(self) -> tuple[dict[str, Any], ...]:
        """Return verified manifests ordered by execution identity."""
        self._validate_run_dir()
        if not self.executions_dir.exists():
            return ()
        output: list[dict[str, Any]] = []
        for path in sorted(self.executions_dir.glob("*/*.json")):
            payload = self._read_json(path)
            self._verify_manifest(payload, path)
            output.append(payload)
        return tuple(sorted(output, key=lambda item: str(item.get("execution_id", ""))))

    def write_index(self, payload: dict[str, Any]) -> Path:
        """Write the replaceable compact review index."""
        self._validate_run_dir()
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ReviewStoreError("Review index requires a rows list.")
        encoded = {
            "review_index_schema_version": 2,
            "run_id": self.run_id,
            **payload,
        }
        self._atomic_write_json(self.index_path, encoded)
        return self.index_path

    def read_index(self) -> dict[str, Any]:
        self._validate_run_dir()
        payload = self._read_json(self.index_path)
        if payload.get("run_id") != self.run_id:
            raise ReviewStoreError("Review index has the wrong run id.")
        return payload

    def write_diagnosis(
        self,
        payload: dict[str, Any],
        *,
        markdown: str | None = None,
    ) -> tuple[Path, Path | None]:
        """Retain one compact diagnosis outside the disposable review tree."""
        self._validate_run_dir()
        identity_payload = {"run_id": self.run_id, **self._redact(payload)}
        diagnosis_id = f"diag_{canonical_sha256(identity_payload)[:24]}"
        document = {
            "diagnosis_schema_version": 1,
            "diagnosis_id": diagnosis_id,
            "run_id": self.run_id,
            "recorded_at_utc": utc_now(),
            **identity_payload,
        }
        json_path = self.diagnosis_dir / f"{diagnosis_id}.json"
        self._assert_within_run(json_path)
        self._write_json_create(json_path, document)
        markdown_path: Path | None = None
        if markdown is not None:
            markdown_path = self.diagnosis_dir / f"{diagnosis_id}.md"
            self._assert_within_run(markdown_path)
            safe_markdown = self._redact(markdown, key="diagnosis_markdown")
            if isinstance(safe_markdown, dict) and safe_markdown.get("redacted"):
                safe_markdown = f"[REDACTED: {safe_markdown.get('reason', 'secret')}]"
            if not isinstance(safe_markdown, str):
                raise ReviewStoreError(
                    "Diagnosis Markdown redaction produced invalid text."
                )
            self._write_bytes_create(markdown_path, safe_markdown.encode("utf-8"))
        return json_path, markdown_path

    def verify(self) -> dict[str, Any]:
        """Verify every retained manifest and local object."""
        self._validate_run_dir()
        if not self.capture_path.exists():
            raise ReviewStoreError("Review capture descriptor does not exist.")
        capture = self._read_json(self.capture_path)
        if capture.get("run_id") != self.run_id:
            raise ReviewStoreError("Capture descriptor has the wrong run id.")
        state = self.review_state(
            expected_execution_ids=[
                str(item) for item in capture.get("expected_execution_ids", [])
            ]
        )
        integrity = state["integrity"]
        if integrity.get("status") != "valid":
            errors = integrity.get("errors", [])
            raise ReviewStoreError(
                str(errors[0]) if errors else "Review bundle failed integrity checks."
            )
        manifests = self.iter_execution_manifests()
        references = list(self._local_references(manifests))
        derived = state["capture"]
        return {
            "run_id": self.run_id,
            "status": derived.get("status"),
            "execution_manifests": len(manifests),
            "local_references": len(references),
            "unique_local_objects": len(
                {str(item["content_sha256"]) for item in references}
            ),
            "verified": True,
        }

    def size(self) -> dict[str, Any]:
        """Return bounded file and byte counts for the disposable review tree."""
        self._validate_run_dir()
        files = [path for path in self.review_dir.rglob("*") if path.is_file()]
        return {
            "run_id": self.run_id,
            "path": str(self.review_dir),
            "file_count": len(files),
            "bytes": sum(path.stat().st_size for path in files),
        }

    def _externalize(
        self,
        value: Any,
        *,
        key: str | None = None,
        object_root: Path,
    ) -> Any:
        if isinstance(value, dict):
            base64_data = value.get("base64_data")
            is_pydantic_binary = False
            if base64_data is None and value.get("kind") == "binary":
                base64_data = value.get("data")
                is_pydantic_binary = True
            media_type = value.get("media_type")
            if isinstance(base64_data, str) and isinstance(media_type, str):
                try:
                    content = base64.b64decode(
                        base64_data,
                        altchars=b"-_" if is_pydantic_binary else None,
                        validate=True,
                    )
                except (ValueError, binascii.Error) as error:
                    raise ReviewStoreError("Invalid base64 review artifact.") from error
                return self._store_object(
                    content,
                    media_type=media_type,
                    artifact_kind=str(value.get("kind", key or "binary")),
                    object_root=object_root,
                )
            return {
                str(item_key): self._externalize(
                    item, key=str(item_key), object_root=object_root
                )
                for item_key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self._externalize(item, key=key, object_root=object_root)
                for item in value
            ]
        if isinstance(value, tuple):
            return [
                self._externalize(item, key=key, object_root=object_root)
                for item in value
            ]
        if isinstance(value, bytes):
            return self._store_object(
                value,
                media_type="application/octet-stream",
                artifact_kind=key or "binary",
                object_root=object_root,
            )
        if (
            isinstance(value, str)
            and key not in _INLINE_CONTROL_KEYS
            and len(value.encode("utf-8")) > self.inline_text_bytes
        ):
            return self._store_object(
                value.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                artifact_kind=key or "text",
                object_root=object_root,
            )
        return value

    def _store_object(
        self,
        content: bytes,
        *,
        media_type: str,
        artifact_kind: str,
        object_root: Path,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        path = object_root / digest[:2] / digest
        self._assert_within_review(path)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ReviewStoreError(f"Review object digest mismatch: {path}")
        else:
            self._write_bytes_create(path, content)
        return {
            "storage": "local_object",
            "content_sha256": digest,
            "media_type": media_type,
            "artifact_kind": artifact_kind,
            "logical_bytes": len(content),
            "stored_bytes": len(content),
            "relative_path": (
                Path("objects") / "sha256" / digest[:2] / digest
            ).as_posix(),
            "redaction_status": "checked",
        }

    def _resolve_text_references(self, value: Any) -> Any:
        if isinstance(value, dict):
            if value.get("storage") == "local_object" and str(
                value.get("media_type", "")
            ).startswith(("text/", "application/json")):
                content = self._read_local_object(value)
                return {**value, "content": content.decode("utf-8")}
            return {
                key: self._resolve_text_references(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_text_references(item) for item in value]
        return value

    def _read_local_object(self, reference: dict[str, Any]) -> bytes:
        relative = reference.get("relative_path")
        digest = reference.get("content_sha256")
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ReviewStoreError("Local review reference is incomplete.")
        path = (self.review_dir / relative).resolve()
        self._assert_within_review(path)
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ReviewStoreError(f"Review object digest mismatch: {path}")
        return content

    def _local_references(self, values: Any):
        if isinstance(values, dict):
            if values.get("storage") == "local_object":
                yield values
            for value in values.values():
                yield from self._local_references(value)
        elif isinstance(values, (list, tuple)):
            for value in values:
                yield from self._local_references(value)

    def _verify_manifest(self, payload: dict[str, Any], path: Path) -> None:
        if payload.get("run_id") != self.run_id:
            raise ReviewStoreError(f"Wrong run id in review manifest: {path}")
        unsigned = dict(payload)
        expected = unsigned.pop("manifest_sha256", None)
        if expected != canonical_sha256(unsigned):
            raise ReviewStoreError(f"Invalid review manifest hash: {path}")

    def _refresh_capture_progress(self) -> None:
        if not self.capture_path.exists():
            return
        capture = self._read_json(self.capture_path)
        capture.update(self._derive_capture_summary(capture, preserve_in_progress=True))
        capture["updated_at_utc"] = utc_now()
        self._atomic_write_json(self.capture_path, capture)

    def _derive_capture_summary(
        self,
        capture: dict[str, Any],
        *,
        expected_execution_ids: list[str] | None = None,
        preserve_in_progress: bool = False,
        manifests: tuple[dict[str, Any], ...] | None = None,
    ) -> dict[str, Any]:
        manifests = (
            manifests if manifests is not None else self.iter_execution_manifests()
        )
        statuses = [str(item.get("capture_status", "failed")) for item in manifests]
        manifest_ids = {str(item.get("execution_id", "")) for item in manifests}
        expected = set(expected_execution_ids or ())
        missing = sorted(expected - manifest_ids)
        if preserve_in_progress:
            status = "in_progress"
        elif expected:
            if not manifests:
                status = "failed"
            elif not missing and all(item == "complete" for item in statuses):
                status = "complete"
            elif all(item == "failed" for item in statuses):
                status = "failed"
            else:
                status = "partial"
        elif statuses:
            status = (
                "failed"
                if all(item == "failed" for item in statuses)
                else "partial"
                if any(item != "complete" for item in statuses)
                else "complete"
            )
        else:
            status = (
                "in_progress" if capture.get("status") == "in_progress" else "failed"
            )
        object_paths = self._object_paths()
        result: dict[str, Any] = {
            "status": status,
            "execution_counts": {
                key: statuses.count(key) for key in ("complete", "partial", "failed")
            },
            "expected_execution_count": len(expected),
            "captured_execution_count": len(manifests),
            "missing_execution_count": len(missing),
            "missing_execution_ids": missing[:_MAX_FAILURE_OBSERVATIONS],
            "object_count": len(object_paths),
            "logical_bytes": sum(path.stat().st_size for path in object_paths),
            "stored_bytes": sum(path.stat().st_size for path in object_paths),
        }
        if status != "complete":
            result["review_unavailable_reason"] = {
                "code": ("capture_failed" if status == "failed" else "capture_partial")
            }
        else:
            result.pop("review_unavailable_reason", None)
        return result

    def _object_paths(self) -> list[Path]:
        return (
            [path for path in self.objects_dir.glob("*/*") if path.is_file()]
            if self.objects_dir.exists()
            else []
        )

    def _recover_execution_transactions(self) -> None:
        """Resolve journaled capture transactions interrupted between files."""
        self._assert_within_review(self.staging_dir)
        if not self.staging_dir.exists():
            return
        if self.staging_dir.is_symlink():
            raise ReviewStoreError("Review staging directory must not be a symlink.")
        transactions = sorted(
            path for path in self.staging_dir.iterdir() if path.is_dir()
        )
        for transaction in transactions:
            journal_path = transaction / "journal.json"
            if not journal_path.is_file():
                shutil.rmtree(transaction)
                continue
            journal = self._read_json(journal_path)
            if (
                journal.get("review_transaction_schema_version") != 1
                or journal.get("run_id") != self.run_id
            ):
                raise ReviewStoreError(
                    f"Invalid review transaction journal: {journal_path}"
                )
            manifest_relative = journal.get("manifest_relative_path")
            manifest_sha256 = journal.get("manifest_sha256")
            raw_objects = journal.get("object_relative_paths")
            if (
                not isinstance(manifest_relative, str)
                or not isinstance(manifest_sha256, str)
                or not isinstance(raw_objects, list)
                or not all(isinstance(item, str) for item in raw_objects)
            ):
                raise ReviewStoreError(
                    f"Incomplete review transaction journal: {journal_path}"
                )
            manifest_path = (self.review_dir / manifest_relative).resolve()
            self._assert_within_review(manifest_path)
            if not manifest_path.is_relative_to(self.executions_dir.resolve()):
                raise ReviewStoreError(
                    f"Review transaction manifest escapes executions: {manifest_path}"
                )
            validated_objects: list[tuple[str, Path]] = []
            for relative in raw_objects:
                object_path = (self.review_dir / relative).resolve()
                self._assert_within_review(object_path)
                if not object_path.is_relative_to(self.objects_dir.resolve()):
                    raise ReviewStoreError(
                        f"Review transaction object escapes CAS: {object_path}"
                    )
                validated_objects.append((relative, object_path))
            committed = False
            if manifest_path.is_file():
                try:
                    manifest = self._read_json(manifest_path)
                    self._verify_manifest(manifest, manifest_path)
                except ReviewStoreError:
                    manifest_path.unlink(missing_ok=True)
                else:
                    if manifest.get("manifest_sha256") != manifest_sha256:
                        raise ReviewStoreError(
                            "Review transaction journal conflicts with its "
                            f"published manifest: {manifest_path}"
                        )
                    committed = True

            manifests = self.iter_execution_manifests()
            referenced = {
                str(item["relative_path"]) for item in self._local_references(manifests)
            }
            if not committed:
                for relative, object_path in validated_objects:
                    if relative not in referenced:
                        object_path.unlink(missing_ok=True)
            shutil.rmtree(transaction)
        if self.staging_dir.exists() and not any(self.staging_dir.iterdir()):
            self.staging_dir.rmdir()

    @contextmanager
    def _write_lock(self):
        """Serialize review mutation and recovery across local processes."""
        self._validate_run_dir()
        self._assert_within_run(self.lock_path)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with self._capture_lock:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _discard_staging(self) -> None:
        self._assert_within_review(self.staging_dir)
        if self.staging_dir.is_symlink():
            raise ReviewStoreError("Review staging directory must not be a symlink.")
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)

    def _redact(self, value: Any, *, key: str | None = None) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for raw_key, item in value.items():
                item_key = str(raw_key)
                if is_sensitive_key(item_key):
                    output[item_key] = {"redacted": True, "reason": "secret_key"}
                else:
                    output[item_key] = self._redact(item, key=item_key)
            return output
        if isinstance(value, list):
            return [self._redact(item, key=key) for item in value]
        if isinstance(value, tuple):
            return [self._redact(item, key=key) for item in value]
        if isinstance(value, str):
            if _BEARER_VALUE.match(value) or _COMMON_SECRET_VALUE.match(value):
                return {"redacted": True, "reason": "secret_value"}
            try:
                parsed = urlsplit(value)
            except ValueError:
                if _EMBEDDED_SECRET_VALUE.search(value):
                    return {"redacted": True, "reason": "embedded_secret"}
                return value
            query_keys = {item_key.lower() for item_key, _ in parse_qsl(parsed.query)}
            has_embedded_credentials = parsed.username is not None
            has_sensitive_query = bool(query_keys.intersection(_SENSITIVE_QUERY_KEYS))
            is_named_url = bool(
                key and self._normalized_key(key).endswith(("url", "uri"))
            )
            if (
                parsed.scheme
                and parsed.netloc
                and (has_embedded_credentials or has_sensitive_query or is_named_url)
            ):
                hostname = parsed.hostname or ""
                if ":" in hostname and not hostname.startswith("["):
                    hostname = f"[{hostname}]"
                netloc = hostname
                if parsed.port is not None:
                    netloc = f"{netloc}:{parsed.port}"
                return urlunsplit(
                    (parsed.scheme, netloc, parsed.path, "", parsed.fragment)
                )
            if _EMBEDDED_SECRET_VALUE.search(value):
                return {"redacted": True, "reason": "embedded_secret"}
        return value

    @staticmethod
    def _normalized_key(key: str) -> str:
        return re.sub(r"[^a-z0-9]", "", key.lower())

    def _validate_run_dir(self) -> None:
        manifest = self.run_dir / "manifest.json"
        if not manifest.is_file():
            raise ReviewStoreError(f"Run manifest does not exist: {manifest}")
        payload = self._read_json(manifest)
        if payload.get("run_id") != self.run_id or self.run_dir.name != self.run_id:
            raise ReviewStoreError("Review store does not match the requested run.")
        self._assert_within_run(self.review_dir)
        if self.review_dir.is_symlink():
            raise ReviewStoreError("Review directory must not be a symlink.")

    def _assert_within_run(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved == self.run_dir or not resolved.is_relative_to(self.run_dir):
            raise ReviewStoreError(f"Path escapes the validated run: {resolved}")

    def _assert_within_review(self, path: Path) -> None:
        resolved = path.resolve()
        review = self.review_dir.resolve()
        if resolved == review or not resolved.is_relative_to(review):
            raise ReviewStoreError(f"Path escapes the review directory: {resolved}")

    @staticmethod
    def _safe_token(value: str) -> str:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
        if not value or any(char not in allowed for char in value):
            raise ReviewStoreError(f"Unsafe review identity: {value!r}")
        return value

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ReviewStoreError(f"Cannot read review JSON: {path}") from error
        if not isinstance(payload, dict):
            raise ReviewStoreError(f"Review JSON must be an object: {path}")
        return payload

    @staticmethod
    def _write_json_create(path: Path, payload: dict[str, Any]) -> None:
        encoded = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        LocalReviewStore._write_bytes_create(path, encoded)

    @staticmethod
    def _write_bytes_create(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            payload, ensure_ascii=False, indent=2, sort_keys=True
        ).encode("utf-8")
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def benchmark_source_reference(
    *,
    artifact_kind: str,
    object_key: str,
    content_type: str,
    byte_size: int,
    content_sha256: str,
    source_snapshot_id: str,
) -> dict[str, Any]:
    """Build a credential-free reference to immutable Benchmark Studio evidence."""
    return {
        "storage": "benchmark_source",
        "artifact_kind": artifact_kind,
        "object_key": object_key,
        "media_type": content_type,
        "size_bytes": byte_size,
        "content_sha256": content_sha256,
        "source_snapshot_id": source_snapshot_id,
        "write_access": False,
    }
