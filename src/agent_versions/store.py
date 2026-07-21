"""Immutable local manifest/CAS and promotion records."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from typing import Any
import uuid

from evaluation import canonical_json_bytes

from src.agent_versions.models import AgentVersionManifest, ResolvedAgentVersion


class AgentVersionIntegrityError(RuntimeError):
    """Stored agent-version evidence contradicts its identity."""


class AgentVersionStore:
    """Content-addressed project-local agent-version storage."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.manifests = self.root / "manifests"
        self.objects = self.root / "objects" / "sha256"
        self.promotions = self.root / "catalog" / "promotions"
        self.aliases = self.root / "catalog" / "aliases"

    def persist_candidate(self, resolved: ResolvedAgentVersion, directory: Path) -> Path:
        """Persist a run-local immutable candidate and required CAS objects."""
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "agent-version.json"
        _write_create_or_validate(path, resolved.manifest.model_dump(mode="json"))
        for digest, content in resolved.blobs.items():
            _write_blob(directory / "objects" / "sha256", digest, content)
        return path

    def promote(
        self,
        resolved: ResolvedAgentVersion,
        *,
        alias: str | None = None,
        source_run_id: str | None = None,
        notes: str | None = None,
        repository: Path | None = None,
    ) -> Path:
        """Retain a verified candidate globally and append a promotion event."""
        self.verify_resolved(
            resolved, repository=(repository or self.root.parent).resolve()
        )
        manifest_path = self.manifests / f"{resolved.manifest.agent_version_id}.json"
        _write_create_or_validate(
            manifest_path, resolved.manifest.model_dump(mode="json")
        )
        for digest, content in resolved.blobs.items():
            _write_blob(self.objects, digest, content)
        promotion_id = f"prm_{uuid.uuid4().hex}"
        event = {
            "schema_version": 1,
            "promotion_id": promotion_id,
            "agent_version_id": resolved.manifest.agent_version_id,
            "manifest_sha256": resolved.manifest.manifest_sha256,
            "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_run_id": source_run_id,
            "alias": alias,
            "notes": notes,
        }
        _write_exclusive(self.promotions / f"{promotion_id}.json", event)
        if alias is not None:
            normalized = _alias_token(alias)
            _write_create_or_validate(
                self.aliases / f"{normalized}.json",
                {
                    "schema_version": 1,
                    "alias": alias,
                    "agent_version_id": resolved.manifest.agent_version_id,
                    "manifest_sha256": resolved.manifest.manifest_sha256,
                },
            )
        return manifest_path

    def load(self, agent_version_id: str) -> AgentVersionManifest:
        path = self.manifests / f"{agent_version_id}.json"
        if not path.is_file():
            alias_path = self.aliases / f"{_alias_token(agent_version_id)}.json"
            if not alias_path.is_file():
                raise FileNotFoundError(f"Unknown agent version: {agent_version_id}")
            alias = json.loads(alias_path.read_text(encoding="utf-8"))
            path = self.manifests / f"{alias['agent_version_id']}.json"
        return AgentVersionManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def verify(self, manifest: AgentVersionManifest, *, repository: Path) -> None:
        """Verify every asset against its Git base or retained CAS bytes."""
        revision = manifest.identity["source"].get("git_revision")
        overlay = {
            item["path"]: item
            for item in (
                manifest.identity["source"].get("dirty_overlay") or {}
            ).get("entries", [])
        }
        for asset in manifest.identity["assets"]:
            digest = asset["content_sha256"]
            if asset["path"] in overlay or asset["origin"] == "cas":
                blob_path = self.objects / digest[:2] / digest
                if not blob_path.is_file() or hashlib.sha256(blob_path.read_bytes()).hexdigest() != digest:
                    raise AgentVersionIntegrityError(
                        f"Missing or corrupt CAS object {digest}."
                    )
                continue
            result = subprocess.run(
                ["git", "show", f"{revision}:{asset['path']}"],
                cwd=repository,
                capture_output=True,
            )
            if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != digest:
                raise AgentVersionIntegrityError(
                    f"Git asset is unavailable or corrupt: {asset['path']}"
                )

    def verify_resolved(
        self, resolved: ResolvedAgentVersion, *, repository: Path
    ) -> None:
        """Verify in-memory overlay bytes and every clean Git-backed asset."""
        for digest, content in resolved.blobs.items():
            if hashlib.sha256(content).hexdigest() != digest:
                raise AgentVersionIntegrityError(f"Resolved blob hash mismatch: {digest}")
        revision = resolved.manifest.identity["source"].get("git_revision")
        for asset in resolved.manifest.identity["assets"]:
            digest = asset["content_sha256"]
            if asset["origin"] in {"overlay", "cas"}:
                content = resolved.blobs.get(digest)
                if content is None or hashlib.sha256(content).hexdigest() != digest:
                    raise AgentVersionIntegrityError(
                        f"Resolved overlay object is missing: {digest}"
                    )
                continue
            result = subprocess.run(
                ["git", "show", f"{revision}:{asset['path']}"],
                cwd=repository,
                capture_output=True,
            )
            if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != digest:
                raise AgentVersionIntegrityError(
                    f"Git asset is unavailable or corrupt: {asset['path']}"
                )

    def reconstruct(
        self,
        manifest: AgentVersionManifest,
        *,
        repository: Path,
        destination: Path,
    ) -> Path:
        """Reconstruct an immutable version into a new empty directory."""
        destination = destination.resolve()
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Reconstruction destination must be empty.")
        destination.mkdir(parents=True, exist_ok=True)
        revision = manifest.identity["source"].get("git_revision")
        if not revision:
            raise AgentVersionIntegrityError(
                "Versions without a Git base cannot be reconstructed by this store."
            )
        archive = subprocess.run(
            ["git", "archive", "--format=tar", revision],
            cwd=repository,
            check=True,
            capture_output=True,
        ).stdout
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(archive)
            handle.flush()
            with tarfile.open(handle.name, mode="r:") as bundle:
                for member in bundle.getmembers():
                    target = (destination / member.name).resolve()
                    try:
                        target.relative_to(destination)
                    except ValueError as error:
                        raise AgentVersionIntegrityError(
                            f"Unsafe archive path: {member.name}"
                        ) from error
                bundle.extractall(destination, filter="data")
        overlay = (
            manifest.identity["source"].get("dirty_overlay") or {}
        ).get("entries", [])
        for item in overlay:
            target = (destination / item["path"]).resolve()
            try:
                target.relative_to(destination)
            except ValueError as error:
                raise AgentVersionIntegrityError(
                    f"Unsafe overlay path: {item['path']}"
                ) from error
            if item["operation"] == "delete":
                target.unlink(missing_ok=True)
                continue
            digest = item["content_sha256"]
            blob_path = self.objects / digest[:2] / digest
            content = blob_path.read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise AgentVersionIntegrityError(f"Corrupt CAS object: {digest}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(int(item["file_mode"]))
        for asset in manifest.identity["assets"]:
            target = destination / asset["path"]
            if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != asset["content_sha256"]:
                raise AgentVersionIntegrityError(
                    f"Reconstructed asset hash mismatch: {asset['path']}"
                )
        return destination


def load_run_candidate(run_dir: Path) -> ResolvedAgentVersion:
    """Load an immutable run-local candidate and its retained blobs."""
    manifest = AgentVersionManifest.model_validate_json(
        (run_dir / "agent-version.json").read_text(encoding="utf-8")
    )
    blobs: dict[str, bytes] = {}
    object_root = run_dir / "objects" / "sha256"
    if object_root.exists():
        for path in object_root.glob("*/*"):
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if path.name != digest:
                raise AgentVersionIntegrityError(f"Invalid run-local CAS object: {path}")
            blobs[digest] = content
    # The policy is already embedded in identity. Reconstruct the typed policy
    # for promotion APIs without consulting the current checkout.
    from src.agent_versions.models import AgentVersionPolicy, ModelPolicy

    model_policy = dict(manifest.identity["model_policy"])
    model_policy.pop("policy_sha256", None)
    model_policy.pop("default_provider", None)
    model_policy.pop("default_api", None)
    policy = AgentVersionPolicy(
        source_pipeline=manifest.identity["source_pipeline"]["path"],
        model_policy=ModelPolicy.model_validate(model_policy),
        contracts={},
    )
    return ResolvedAgentVersion(
        manifest=manifest,
        blobs=blobs,
        policy=policy,
        pipeline_path=manifest.identity["source_pipeline"]["path"],
    )


def _write_blob(root: Path, digest: str, content: bytes) -> Path:
    if hashlib.sha256(content).hexdigest() != digest:
        raise AgentVersionIntegrityError(f"CAS hash mismatch for {digest}.")
    path = root / digest[:2] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError:
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise AgentVersionIntegrityError(f"Conflicting CAS object: {path}")
        return path
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def _write_create_or_validate(path: Path, payload: dict[str, Any]) -> None:
    try:
        _write_exclusive(path, payload)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if canonical_json_bytes(existing) != canonical_json_bytes(payload):
            raise AgentVersionIntegrityError(f"Conflicting immutable file: {path}")


def _alias_token(value: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "-" for character in value.strip()
    ).strip("-")
    if not normalized:
        raise ValueError("Agent-version alias must contain letters or numbers.")
    return normalized
