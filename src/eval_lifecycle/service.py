"""Simple permanent lifecycle for working and retained evaluation results."""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Literal
import uuid

from evaluation import canonical_json_bytes, canonical_sha256

from src.agent_versions.models import AgentVersionManifest
from src.evals.result_integrity import load_verified_result
from src.evals.run_store import LocalRunStore


LifecycleState = Literal["working", "retained"]
_RUN_ID = re.compile(r"^eval_[0-9a-f]{24}$")
_RETAINED_ID = re.compile(r"^ret_[0-9a-f]{24}$")


class EvalLifecycleError(RuntimeError):
    """A lifecycle request is unsafe, incomplete, or internally inconsistent."""


class EvalLifecycleService:
    """Elevate, verify, list, and permanently delete exact eval entities."""

    def __init__(self, project_root: Path, *, eval_root: Path | None = None) -> None:
        self.project_root = project_root.resolve()
        self.eval_root = (eval_root or self.project_root / "eval_results").resolve()
        self.working_root = self.eval_root / "working"
        self.retained_root = self.eval_root / "retained"
        self.retained_agents_root = self.retained_root / "agent_versions"
        self._require_within(self.eval_root)

    def list_evals(self, state: str = "all") -> list[dict[str, Any]]:
        """Return current working and retained eval entries."""
        if state not in {"all", "working", "retained"}:
            raise ValueError("Lifecycle state must be all, working, or retained.")
        entries: list[dict[str, Any]] = []
        if state in {"all", "working"}:
            entries.extend(self._working_entries())
        if state in {"all", "retained"}:
            entries.extend(self._retained_entries())
        return sorted(
            entries,
            key=lambda item: (str(item.get("created_at_utc") or ""), item["run_id"]),
            reverse=True,
        )

    def inspect(self, entity_id: str) -> dict[str, Any]:
        matches = [item for item in self.list_evals() if item["run_id"] == entity_id]
        if len(matches) != 1:
            raise EvalLifecycleError(
                f"Expected one eval {entity_id}; found {len(matches)}."
            )
        return matches[0]

    def preview_elevation(self, run_id: str) -> dict[str, Any]:
        prepared = self._prepare_elevation(run_id)
        return {
            "operation": "elevate",
            "confirmed": False,
            "source_run_id": run_id,
            "retained_eval_id": prepared["retained_eval_id"],
            "source_path": self._relative(prepared["run_dir"]),
            "destination_path": self._relative(prepared["destination"]),
            "agent_version_id": prepared["agent_version_id"],
            "planned_attempts": prepared["planned_attempts"],
            "unit_records": len(prepared["units"]["units"]),
            "artifacts": sorted(prepared["artifacts"]),
            "preserves": [
                "aggregate result and accuracy/reliability summaries",
                "full final AI outputs, expected outputs, validation, and grading",
                "token usage and cost observations",
                "benchmark, evidence, model, pricing, grader, and agent identity",
                "Git revision and relevant dirty/untracked agent patch",
            ],
            "prunes": [
                "per-attempt files",
                "performance, speed, latency, retry, and invocation detail",
                "tool traces and intermediate review objects",
                "local copies of Azure evidence",
            ],
        }

    def elevate(self, run_id: str, *, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise EvalLifecycleError("Elevation requires explicit --yes confirmation.")
        prepared = self._prepare_elevation(run_id)
        destination: Path = prepared["destination"]
        if destination.exists():
            self.verify(prepared["retained_eval_id"])
            return {
                "operation": "elevate",
                "created": False,
                "retained_eval_id": prepared["retained_eval_id"],
                "path": self._relative(destination),
                "agent_version_id": prepared["agent_version_id"],
            }

        staging_root = self.retained_root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{prepared['retained_eval_id']}.{uuid.uuid4().hex}"
        staged_eval = staging / "eval"
        staged_agent = staging / "agent"
        staged_eval.mkdir(parents=True)
        staged_agent.mkdir(parents=True)
        try:
            for name, payload in prepared["artifacts"].items():
                _write_artifact(staged_eval / name, payload)
            agent_artifacts = {
                "agent-provenance.json": _shared_agent_provenance(
                    prepared["agent_provenance"]
                ),
                **(
                    {"agent.patch": prepared["agent_patch"]}
                    if prepared["agent_patch"] is not None
                    else {}
                ),
            }
            for name, payload in agent_artifacts.items():
                _write_artifact(staged_agent / name, payload)

            self._verify_artifact_manifest(staged_eval, prepared["retained_manifest"])
            agent_destination = self.retained_agents_root / prepared["agent_version_id"]
            agent_created = False
            if agent_destination.exists():
                self._verify_agent_artifacts(
                    agent_destination,
                    agent_provenance=prepared["agent_provenance"],
                    agent_patch=prepared["agent_patch"],
                )
            else:
                agent_destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_agent, agent_destination)
                agent_created = True

            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(staged_eval, destination)
            except BaseException:
                if agent_created:
                    shutil.rmtree(agent_destination)
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        verified = self.verify(prepared["retained_eval_id"])
        return {
            "operation": "elevate",
            "created": True,
            "retained_eval_id": prepared["retained_eval_id"],
            "path": self._relative(destination),
            "agent_version_id": prepared["agent_version_id"],
            "verified": verified["verified"],
        }

    def verify(self, retained_eval_id: str) -> dict[str, Any]:
        retained_dir = self._find_retained(retained_eval_id)
        manifest = _read_json(retained_dir / "manifest.json")
        schema_version = manifest.get("schema_version")
        if schema_version not in {1, 2}:
            raise EvalLifecycleError("Retained eval manifest schema is invalid.")
        if schema_version == 1:
            identity = {
                key: manifest[key]
                for key in (
                    "schema_version",
                    "lifecycle_state",
                    "source_run_id",
                    "source_run_spec_sha256",
                    "agent_version_id",
                    "benchmark",
                )
            }
        else:
            identity = manifest.get("identity_seed")
            if not isinstance(identity, dict) or identity.get("schema_version") != 2:
                raise EvalLifecycleError("Retained eval identity seed is invalid.")
            if any(manifest.get(key) != value for key, value in identity.items()):
                raise EvalLifecycleError(
                    "Retained eval manifest contradicts its identity seed."
                )
        expected_id = f"ret_{canonical_sha256(identity)[:24]}"
        if (
            retained_eval_id != expected_id
            or manifest.get("retained_eval_id") != expected_id
        ):
            raise EvalLifecycleError("Retained eval identity is invalid.")
        self._verify_artifact_manifest(retained_dir, manifest)
        provenance = _read_json(retained_dir / "agent-provenance.json")
        if schema_version == 2:
            source_provenance = manifest.get("source_provenance")
            git = provenance.get("git")
            if not isinstance(source_provenance, dict) or not isinstance(git, dict):
                raise EvalLifecycleError("Retained source provenance is invalid.")
            if source_provenance != {
                "git_revision": git.get("git_revision"),
                "tree_state": git.get("tree_state"),
                "dirty_overlay_sha256": git.get("dirty_overlay_sha256"),
            }:
                raise EvalLifecycleError(
                    "Retained source provenance contradicts the agent artifact."
                )
        patch_path = retained_dir / "agent.patch"
        patch = patch_path.read_text(encoding="utf-8") if patch_path.is_file() else None
        self._verify_agent_artifacts(
            self.retained_agents_root / manifest["agent_version_id"],
            agent_provenance=provenance,
            agent_patch=patch,
        )
        units = _read_json(retained_dir / "units.json")
        result = _read_json(retained_dir / "result.json")
        if units.get("retained_eval_id") != retained_eval_id:
            raise EvalLifecycleError("Retained unit aggregate has the wrong identity.")
        if (
            result.get("run", {}).get(
                "eval_run_id", result.get("run", {}).get("run_id")
            )
            != manifest["source_run_id"]
        ):
            raise EvalLifecycleError("Retained result has the wrong source run.")
        return {
            "verified": True,
            "retained_eval_id": retained_eval_id,
            "path": self._relative(retained_dir),
            "agent_version_id": manifest["agent_version_id"],
            "unit_records": len(units.get("units", [])),
        }

    def delete_working(self, run_id: str, *, confirmed: bool) -> dict[str, Any]:
        if not confirmed:
            raise EvalLifecycleError(
                "Permanent working-eval deletion requires explicit --yes."
            )
        run_dir = self._find_working(run_id)
        self._reject_symlinks(run_dir)
        store = LocalRunStore(run_dir, run_id=run_id)
        with store.coordinator_lock(invocation_id=f"delete-{uuid.uuid4().hex}"):
            file_count, byte_count = _tree_size(run_dir)
            shutil.rmtree(run_dir)
        return {
            "operation": "delete",
            "lifecycle_state": "working",
            "entity_id": run_id,
            "permanent": True,
            "recoverable": False,
            "files_deleted": file_count,
            "bytes_deleted": byte_count,
        }

    def delete_retained(
        self, retained_eval_id: str, *, confirmation: str | None
    ) -> dict[str, Any]:
        if confirmation != retained_eval_id:
            raise EvalLifecycleError(
                "Retained deletion requires --confirm-retained with the exact "
                f"retained eval ID {retained_eval_id}."
            )
        retained_dir = self._find_retained(retained_eval_id)
        verified = self.verify(retained_eval_id)
        self._reject_symlinks(retained_dir)
        agent_version_id = verified["agent_version_id"]
        file_count, byte_count = _tree_size(retained_dir)
        shutil.rmtree(retained_dir)
        remaining = [
            item
            for item in self._retained_entries()
            if item["agent_version_id"] == agent_version_id
        ]
        agent_removed = False
        if not remaining:
            agent_dir = self.retained_agents_root / agent_version_id
            if agent_dir.exists():
                self._reject_symlinks(agent_dir)
                shutil.rmtree(agent_dir)
                agent_removed = True
        return {
            "operation": "delete",
            "lifecycle_state": "retained",
            "entity_id": retained_eval_id,
            "agent_version_id": agent_version_id,
            "agent_version_removed": agent_removed,
            "permanent": True,
            "recoverable": False,
            "files_deleted": file_count,
            "bytes_deleted": byte_count,
        }

    def _prepare_elevation(self, run_id: str) -> dict[str, Any]:
        run_dir = self._find_working(run_id)
        store = LocalRunStore(run_dir, run_id=run_id)
        with store.coordinator_lock(invocation_id=f"elevate-{uuid.uuid4().hex}"):
            if not store.result_path.is_file():
                raise EvalLifecycleError(
                    f"Working eval {run_id} is incomplete and cannot be elevated."
                )
            result = load_verified_result(run_dir / "result.json")
            manifest = store.read_manifest()
            recovery = result.get("summary", {}).get("execution_recovery", {})
            planned = len(manifest.get("work_items", []))
            if (
                recovery.get("missing_work_items") != 0
                or recovery.get("recorded_work_items") != planned
            ):
                raise EvalLifecycleError(
                    f"Working eval {run_id} is incomplete and cannot be elevated."
                )
            candidate = AgentVersionManifest.model_validate_json(
                (run_dir / "agent-version.json").read_text(encoding="utf-8")
            )
            configured_agent = manifest.get("run_spec", {}).get("agent", {})
            if (
                configured_agent.get("agent_version_id") != candidate.agent_version_id
                or configured_agent.get("manifest_sha256") != candidate.manifest_sha256
            ):
                raise EvalLifecycleError(
                    "Working eval candidate contradicts its immutable run identity."
                )
            self._verify_candidate_overlay(run_dir, candidate)
            evidence = self._evidence_references(manifest)
            units = self._unit_aggregate(store, run_id=run_id)
            provenance = self._agent_provenance(
                manifest, candidate=candidate, run_id=run_id
            )
            patch = self._agent_patch(run_dir, candidate=candidate)

        benchmark = result["run"]["dimensions"]["benchmark"]
        created_at = datetime.now(timezone.utc).isoformat()
        retained_schema_version = 2 if manifest.get("schema_version") == 2 else 1
        provisional_artifacts: dict[str, Any] = {
            "result.json": result,
            "units.json": units,
            "agent-provenance.json": provenance,
            "evidence-references.json": evidence,
            **({"agent.patch": patch} if patch is not None else {}),
        }
        retained_identity = {
            "schema_version": retained_schema_version,
            "lifecycle_state": "retained",
            "source_run_id": run_id,
            "source_run_spec_sha256": manifest["run_spec_sha256"],
            "agent_version_id": candidate.agent_version_id,
            "benchmark": {
                "key": benchmark["key"],
                "version": benchmark["version"],
                "version_id": benchmark["version_id"],
            },
        }
        if retained_schema_version == 2:
            retained_identity.update(
                {
                    "source_eval_run_id": run_id,
                    "agent_version_manifest_sha256": candidate.manifest_sha256,
                }
            )
            retained_identity["benchmark"]["source_state_sha256"] = benchmark[
                "source_state_sha256"
            ]
        retained_eval_id = f"ret_{canonical_sha256(retained_identity)[:24]}"
        units["retained_eval_id"] = retained_eval_id
        provisional_artifacts["units.json"] = units
        artifact_index = {
            name: _artifact_identity(payload)
            for name, payload in provisional_artifacts.items()
        }
        retained_manifest = {
            **retained_identity,
            **(
                {"identity_seed": retained_identity}
                if retained_schema_version == 2
                else {}
            ),
            "created_at_utc": created_at,
            "artifacts": artifact_index,
            **(
                {
                    "source_provenance": {
                        "git_revision": candidate.identity["source"].get(
                            "git_revision"
                        ),
                        "tree_state": candidate.identity["source"].get("tree_state"),
                        "dirty_overlay_sha256": candidate.identity["source"].get(
                            "dirty_overlay_sha256"
                        ),
                    }
                }
                if retained_schema_version == 2
                else {}
            ),
            "pruned_categories": [
                "attempt_files",
                "performance",
                "review_tool_traces",
                "review_intermediate_objects",
                "local_evidence_copies",
            ],
            "retained_eval_id": retained_eval_id,
        }
        provisional_artifacts["manifest.json"] = retained_manifest
        return {
            "run_dir": run_dir,
            "destination": (
                self.retained_root
                / str(benchmark["key"])
                / f"v{benchmark['version']}"
                / retained_eval_id
            ),
            "retained_eval_id": retained_eval_id,
            "agent_version_id": candidate.agent_version_id,
            "planned_attempts": planned,
            "units": units,
            "agent_provenance": provenance,
            "agent_patch": patch,
            "retained_manifest": retained_manifest,
            "artifacts": provisional_artifacts,
        }

    def _working_entries(self) -> list[dict[str, Any]]:
        paths = (
            set(self.working_root.glob("**/eval_*/manifest.json"))
            if self.working_root.exists()
            else set()
        )
        entries = []
        for path in sorted(paths):
            run_dir = path.parent
            try:
                store = LocalRunStore(run_dir, run_id=run_dir.name)
                manifest = store.read_manifest()
                result = (
                    load_verified_result(run_dir / "result.json")
                    if (run_dir / "result.json").is_file()
                    else None
                )
                config = (
                    result["run"]
                    if result is not None
                    else manifest["eval_contract"]["run"]
                )
                dimensions = config.get("dimensions", {})
                benchmark = dimensions.get("benchmark", {})
                model = dimensions.get("model", {})
                agent = dimensions.get(
                    "agent", manifest.get("run_spec", {}).get("agent", {})
                )
                records = store.read_attempt_records()
                file_count, byte_count = _tree_size(run_dir)
                entries.append(
                    {
                        "run_id": run_dir.name,
                        "source_run_id": run_dir.name,
                        "lifecycle_state": "working",
                        "path": self._relative(run_dir),
                        "created_at_utc": manifest.get("created_at_utc"),
                        "result_status": (
                            "materialized" if result is not None else "incomplete"
                        ),
                        "agent_version_id": agent.get("agent_version_id"),
                        "pipeline_path": dimensions.get("pipeline", {}).get("path"),
                        "benchmark_key": benchmark.get("key"),
                        "benchmark_version": benchmark.get("version"),
                        "model": model.get("id"),
                        "reasoning_effort": model.get("reasoning_effort"),
                        "configuration": dimensions.get("configuration", {}),
                        "planned_attempts": len(manifest.get("work_items", [])),
                        "recorded_attempts": len(records),
                        "review_status": (
                            "available"
                            if (run_dir / "review").is_dir()
                            else "unavailable"
                        ),
                        "file_count": file_count,
                        "bytes": byte_count,
                        "accuracy": (
                            result.get("summary", {}).get("accuracy")
                            if result is not None
                            else None
                        ),
                        "cost": (
                            result.get("summary", {}).get("cost")
                            if result is not None
                            else None
                        ),
                    }
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return entries

    def _retained_entries(self) -> list[dict[str, Any]]:
        if not self.retained_root.exists():
            return []
        entries = []
        for path in sorted(self.retained_root.glob("**/ret_*/manifest.json")):
            retained_dir = path.parent
            try:
                manifest = _read_json(path)
                result = _read_json(retained_dir / "result.json")
                run = result["run"]
                dimensions = run["dimensions"]
                benchmark = dimensions["benchmark"]
                model = dimensions["model"]
                units = _read_json(retained_dir / "units.json").get("units", [])
                file_count, byte_count = _tree_size(retained_dir)
                entries.append(
                    {
                        "run_id": retained_dir.name,
                        "source_run_id": manifest["source_run_id"],
                        "lifecycle_state": "retained",
                        "path": self._relative(retained_dir),
                        "created_at_utc": manifest.get("created_at_utc"),
                        "result_status": "materialized",
                        "agent_version_id": manifest["agent_version_id"],
                        "pipeline_path": dimensions.get("pipeline", {}).get("path"),
                        "benchmark_key": benchmark.get("key"),
                        "benchmark_version": benchmark.get("version"),
                        "model": model.get("id"),
                        "reasoning_effort": model.get("reasoning_effort"),
                        "configuration": dimensions.get("configuration", {}),
                        "planned_attempts": len(units),
                        "recorded_attempts": len(units),
                        "review_status": "retained_compact",
                        "file_count": file_count,
                        "bytes": byte_count,
                        "accuracy": result.get("summary", {}).get("accuracy"),
                        "cost": result.get("summary", {}).get("cost"),
                    }
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
        return entries

    def _find_working(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise EvalLifecycleError(f"Invalid working eval ID: {run_id}")
        matches = [
            self.project_root / item["path"]
            for item in self._working_entries()
            if item["run_id"] == run_id
        ]
        if len(matches) != 1:
            raise EvalLifecycleError(
                f"Expected one working eval {run_id}; found {len(matches)}."
            )
        return matches[0]

    def _find_retained(self, retained_eval_id: str) -> Path:
        if not _RETAINED_ID.fullmatch(retained_eval_id):
            raise EvalLifecycleError(f"Invalid retained eval ID: {retained_eval_id}")
        matches = [
            self.project_root / item["path"]
            for item in self._retained_entries()
            if item["run_id"] == retained_eval_id
        ]
        if len(matches) != 1:
            raise EvalLifecycleError(
                f"Expected one retained eval {retained_eval_id}; found {len(matches)}."
            )
        return matches[0]

    def _evidence_references(self, manifest: dict[str, Any]) -> dict[str, Any]:
        run_spec = manifest.get("run_spec", {})
        evidence = run_spec.get("evidence")
        if not isinstance(evidence, dict):
            raise EvalLifecycleError(
                "Working eval predates complete Azure evidence storage identity "
                "and cannot be elevated."
            )
        required = (
            "storage_account_url",
            "storage_container",
            "evidence_recipe_id",
            "source_snapshot_contract",
            "benchmark_source_state_sha256",
        )
        if any(not evidence.get(key) for key in required):
            raise EvalLifecycleError(
                "Working eval has incomplete Azure evidence identity."
            )
        examples = manifest.get("eval_contract", {}).get("examples")
        if not isinstance(examples, list) or not examples:
            raise EvalLifecycleError(
                "Working eval has no retained evidence references."
            )
        schema_version = int(manifest.get("schema_version", 1))
        return {
            "schema_version": 2 if schema_version == 2 else 1,
            "storage": {
                "account_url": evidence["storage_account_url"],
                "container": evidence["storage_container"],
                "access": "read_only_on_demand",
            },
            "evidence_recipe_id": evidence["evidence_recipe_id"],
            "source_snapshot_contract": evidence["source_snapshot_contract"],
            "benchmark_source_state_sha256": evidence["benchmark_source_state_sha256"],
            "examples": [
                {
                    key: example.get(key)
                    for key in (
                        "example_id",
                        "unit_id",
                        "decision_timestamp",
                        "source_snapshot_id",
                        "raw_snapshot_content_sha256",
                        "raw_source_kind",
                        "raw_captured_at",
                        "raw_window_start",
                        "raw_window_end",
                        "raw_known_gaps",
                        "raw_artifacts",
                        "label_schema_version_id",
                        "metadata",
                        "published_review_context",
                    )
                }
                for example in examples
                if isinstance(example, dict)
            ],
        }

    @staticmethod
    def _unit_aggregate(store: LocalRunStore, *, run_id: str) -> dict[str, Any]:
        units: list[dict[str, Any]] = []
        for example in store.evaluation_rows():
            base = {key: value for key, value in example.items() if key != "runs"}
            for run in example.get("runs", []):
                units.append(
                    {
                        **base,
                        **run,
                        "review_status": "retained_compact",
                        "review_unavailable_reason": {
                            "code": "pruned",
                            "message": (
                                "Tool traces and intermediate review objects were "
                                "pruned during elevation."
                            ),
                        },
                        "flaky": False,
                    }
                )
        schema_version = store.read_manifest().get("schema_version")
        return {
            "schema_version": 2 if schema_version == 2 else 1,
            "retained_eval_id": None,
            "source_run_id": run_id,
            "units": units,
        }

    @staticmethod
    def _agent_provenance(
        manifest: dict[str, Any],
        *,
        candidate: AgentVersionManifest,
        run_id: str,
    ) -> dict[str, Any]:
        run_spec = manifest["run_spec"]
        schema_version = int(manifest.get("schema_version", 1))
        return {
            "schema_version": 2 if schema_version == 2 else 1,
            "source_run_id": run_id,
            "agent_version_id": candidate.agent_version_id,
            "manifest_sha256": candidate.manifest_sha256,
            "git": {
                key: candidate.identity["source"].get(key)
                for key in (
                    "repository_id",
                    "git_revision",
                    "git_tree",
                    "tree_state",
                    "dirty_overlay_sha256",
                )
            },
            "agent_identity": candidate.identity,
            "configuration_hashes": {
                "pipeline": run_spec["pipeline"]["content_sha256"],
                "pipeline_resolved_override": run_spec["pipeline"][
                    "resolved_override_sha256"
                ],
                "evaluation_profile": run_spec["scoring"]["evaluation_profile_sha256"],
                "grader_set": run_spec["scoring"]["grader_set_sha256"],
                "resolved_scoring": run_spec["scoring"]["content_sha256"],
                "source_manifest": run_spec["source_manifest"]["content_sha256"],
                "model_pricing": (
                    run_spec["model"].get("pricing", {}).get("content_sha256")
                    if isinstance(run_spec["model"].get("pricing"), dict)
                    else None
                ),
            },
            "benchmark": run_spec["benchmark"],
            "evidence": run_spec["evidence"],
            "model": run_spec["model"],
        }

    def _agent_patch(
        self, run_dir: Path, *, candidate: AgentVersionManifest
    ) -> str | None:
        overlay = (candidate.identity.get("source", {}).get("dirty_overlay") or {}).get(
            "entries", []
        )
        if not overlay:
            return None
        revision = candidate.identity["source"].get("git_revision")
        patches: list[str] = []
        for item in overlay:
            relative = str(item["path"])
            base = _git_content(self.project_root, revision, relative)
            current: bytes | None = None
            if item["operation"] != "delete":
                digest = str(item["content_sha256"])
                object_path = run_dir / "objects" / "sha256" / digest[:2] / digest
                current = object_path.read_bytes()
                if hashlib.sha256(current).hexdigest() != digest:
                    raise EvalLifecycleError(
                        f"Dirty agent object is missing or corrupt: {relative}"
                    )
            try:
                before = [] if base is None else base.decode("utf-8").splitlines(True)
                after = (
                    [] if current is None else current.decode("utf-8").splitlines(True)
                )
            except UnicodeDecodeError as error:
                raise EvalLifecycleError(
                    f"Relevant dirty agent file is not text and cannot be retained "
                    f"as agent.patch: {relative}"
                ) from error
            patches.extend(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile="/dev/null" if base is None else f"a/{relative}",
                    tofile="/dev/null" if current is None else f"b/{relative}",
                )
            )
        return "".join(patches)

    @staticmethod
    def _verify_candidate_overlay(
        run_dir: Path, candidate: AgentVersionManifest
    ) -> None:
        for item in (
            candidate.identity.get("source", {}).get("dirty_overlay") or {}
        ).get("entries", []):
            digest = item.get("content_sha256")
            if not digest:
                continue
            path = run_dir / "objects" / "sha256" / digest[:2] / digest
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest
            ):
                raise EvalLifecycleError(
                    f"Candidate overlay object is missing or corrupt: {digest}"
                )

    @staticmethod
    def _verify_artifact_manifest(directory: Path, manifest: dict[str, Any]) -> None:
        children = tuple(directory.iterdir())
        if any(path.is_symlink() or not path.is_file() for path in children):
            raise EvalLifecycleError(
                "Retained eval contains a non-file or symbolic-link artifact."
            )
        for name, identity in manifest["artifacts"].items():
            path = directory / name
            if not path.is_file():
                raise EvalLifecycleError(f"Retained artifact is missing: {name}")
            content = path.read_bytes()
            if (
                len(content) != identity["byte_size"]
                or hashlib.sha256(content).hexdigest() != identity["sha256"]
            ):
                raise EvalLifecycleError(f"Retained artifact hash is invalid: {name}")
        allowed = {"manifest.json", *manifest["artifacts"]}
        actual = {path.name for path in children}
        if actual != allowed:
            raise EvalLifecycleError("Retained eval contains undeclared artifacts.")

    @staticmethod
    def _verify_agent_artifacts(
        directory: Path,
        *,
        agent_provenance: dict[str, Any],
        agent_patch: str | None,
    ) -> None:
        if not directory.is_dir():
            raise EvalLifecycleError("Retained agent version is missing.")
        children = tuple(directory.iterdir())
        if any(path.is_symlink() or not path.is_file() for path in children):
            raise EvalLifecycleError(
                "Retained agent version contains a non-file or symbolic-link artifact."
            )
        stored = _read_json(directory / "agent-provenance.json")
        expected = _shared_agent_provenance(agent_provenance)
        if canonical_json_bytes(stored) != canonical_json_bytes(expected):
            raise EvalLifecycleError("Retained agent provenance does not match.")
        patch_path = directory / "agent.patch"
        if agent_patch is None:
            if patch_path.exists():
                raise EvalLifecycleError(
                    "Clean retained agent has an unexpected patch."
                )
        elif (
            not patch_path.is_file()
            or patch_path.read_text(encoding="utf-8") != agent_patch
        ):
            raise EvalLifecycleError("Retained agent patch does not match.")
        allowed = {
            "agent-provenance.json",
            *(["agent.patch"] if agent_patch is not None else []),
        }
        if {path.name for path in children} != allowed:
            raise EvalLifecycleError(
                "Retained agent version contains undeclared artifacts."
            )

    def _reject_symlinks(self, target: Path) -> None:
        self._require_within(target)
        if target.is_symlink() or any(path.is_symlink() for path in target.rglob("*")):
            raise EvalLifecycleError(f"Lifecycle target contains a symlink: {target}")

    def _require_within(self, path: Path) -> None:
        if not path.resolve().is_relative_to(self.project_root):
            raise EvalLifecycleError(f"Lifecycle path escapes project root: {path}")

    def _relative(self, path: Path) -> str:
        self._require_within(path)
        return path.resolve().relative_to(self.project_root).as_posix()


def _artifact_identity(payload: Any) -> dict[str, Any]:
    content = _artifact_bytes(payload)
    return {"sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content)}


def _shared_agent_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    """Return only identity that is stable across evals using the same agent."""
    return {
        key: provenance[key]
        for key in (
            "schema_version",
            "agent_version_id",
            "manifest_sha256",
            "git",
            "agent_identity",
        )
    }


def _artifact_bytes(payload: Any) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        + b"\n"
    )


def _write_artifact(path: Path, payload: Any) -> None:
    path.write_bytes(_artifact_bytes(payload))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvalLifecycleError(f"JSON artifact must be an object: {path}")
    return payload


def _tree_size(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def _git_content(root: Path, revision: str | None, relative: str) -> bytes | None:
    if revision is None:
        return None
    completed = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=root,
        capture_output=True,
    )
    return completed.stdout if completed.returncode == 0 else None
