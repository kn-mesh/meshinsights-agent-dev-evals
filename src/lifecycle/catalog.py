"""Deterministic discovery of managed local Agent Workbench evidence."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation import LocalReviewStore, build_comparison_identity

from src.agent_versions.models import AgentVersionManifest
from src.agent_versions.store import AgentVersionIntegrityError, AgentVersionStore
from src.evals.run_store import LocalRunStore
from src.lifecycle.models import (
    CatalogFinding,
    CatalogReference,
    ComparisonCatalogEntry,
    LifecycleCatalog,
    RunCatalogEntry,
    VersionCatalogEntry,
)


class LocalLifecycleCatalog:
    """Rebuild a catalog from immutable managed records without writing state."""

    def __init__(
        self,
        project_root: Path,
        *,
        eval_root: Path | None = None,
        agent_root: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.eval_root = (eval_root or self.project_root / "eval_results").resolve()
        self.agent_root = (agent_root or self.project_root / "agent_versions").resolve()
        self._require_within(self.eval_root)
        self._require_within(self.agent_root)

    def build(self) -> LifecycleCatalog:
        findings: list[CatalogFinding] = []
        runs = self._scan_runs(findings)
        comparisons = self._scan_comparisons(findings)
        versions, promotion_sources = self._scan_versions(runs, findings)
        run_ids = {item.run_id for item in runs}
        version_ids = {item.agent_version_id for item in versions}
        references: list[CatalogReference] = []

        for run in runs:
            references.append(
                CatalogReference(
                    source_kind="run",
                    source_id=run.run_id,
                    target_kind="version",
                    target_id=run.agent_version_id,
                    relation="uses_agent_version",
                )
            )
            if run.agent_version_id not in version_ids:
                findings.append(
                    CatalogFinding(
                        code="missing_agent_version",
                        message=(
                            f"Run {run.run_id} references agent version "
                            f"{run.agent_version_id} without a valid candidate manifest."
                        ),
                        path=run.path,
                        entity_kind="run",
                        entity_id=run.run_id,
                    )
                )
        for version in versions:
            for alias in version.aliases:
                references.append(
                    CatalogReference(
                        source_kind="alias",
                        source_id=alias,
                        target_kind="version",
                        target_id=version.agent_version_id,
                        relation="names_version",
                    )
                )
            for promotion_id in version.promotion_ids:
                references.append(
                    CatalogReference(
                        source_kind="promotion",
                        source_id=promotion_id,
                        target_kind="version",
                        target_id=version.agent_version_id,
                        relation="promotes_version",
                    )
                )
        for comparison in comparisons:
            for run_id in comparison.run_ids:
                references.append(
                    CatalogReference(
                        source_kind="comparison",
                        source_id=comparison.comparison_id,
                        target_kind="run",
                        target_id=run_id,
                        relation="compares_run",
                    )
                )
                if run_id not in run_ids:
                    findings.append(
                        CatalogFinding(
                            code="missing_comparison_run",
                            message=(
                                f"Comparison {comparison.comparison_id} references "
                                f"missing run {run_id}."
                            ),
                            path=comparison.manifest_path,
                            entity_kind="comparison",
                            entity_id=comparison.comparison_id,
                        )
                    )
        for version_id, source_records in promotion_sources.items():
            for promotion_id, run_id in source_records:
                references.append(
                    CatalogReference(
                        source_kind="promotion",
                        source_id=promotion_id,
                        target_kind="run",
                        target_id=run_id,
                        relation="promoted_from_run",
                    )
                )
                if run_id not in run_ids:
                    findings.append(
                        CatalogFinding(
                            code="missing_promotion_source_run",
                            message=(
                                f"Promoted version {version_id} records missing source "
                                f"run {run_id}."
                            ),
                            entity_kind="version",
                            entity_id=version_id,
                        )
                    )

        return LifecycleCatalog(
            project_root=str(self.project_root),
            runs=tuple(sorted(runs, key=lambda item: item.run_id)),
            versions=tuple(sorted(versions, key=lambda item: item.agent_version_id)),
            comparisons=tuple(sorted(comparisons, key=lambda item: item.comparison_id)),
            references=tuple(
                sorted(
                    references,
                    key=lambda item: (
                        item.source_kind,
                        item.source_id,
                        item.target_kind,
                        item.target_id,
                        item.relation,
                    ),
                )
            ),
            findings=tuple(
                sorted(
                    findings,
                    key=lambda item: (
                        item.code,
                        item.entity_id or "",
                        item.path or "",
                    ),
                )
            ),
        )

    def _scan_runs(self, findings: list[CatalogFinding]) -> list[RunCatalogEntry]:
        runs: list[RunCatalogEntry] = []
        seen: set[str] = set()
        if not self.eval_root.exists():
            return runs
        for manifest_path in sorted(self.eval_root.glob("**/runs/*/manifest.json")):
            run_dir = manifest_path.parent
            run_id = run_dir.name
            relative = self._relative(run_dir)
            try:
                if run_id in seen:
                    raise ValueError(f"Duplicate managed run id: {run_id}")
                store = LocalRunStore(run_dir, run_id=run_id)
                manifest = store.read_manifest()
                candidate = AgentVersionManifest.model_validate_json(
                    (run_dir / "agent-version.json").read_text(encoding="utf-8")
                )
                configured_agent = manifest["run_spec"].get("agent", {})
                if (
                    configured_agent.get("agent_version_id")
                    != candidate.agent_version_id
                    or configured_agent.get("manifest_sha256")
                    != candidate.manifest_sha256
                ):
                    raise ValueError("Run candidate contradicts its run specification.")
                self._verify_candidate_objects(run_dir, candidate)
                result = (
                    store.read_verified_result()
                    if store.result_path.is_file()
                    else None
                )
                config = self._run_config(manifest, result)
                dimensions = config.get("dimensions", {})
                benchmark = dimensions.get("benchmark", {})
                model = dimensions.get("model", {})
                agent = dimensions.get("agent", configured_agent)
                records = store.read_attempt_records()
                review_status = self._review_status(
                    run_dir,
                    expected_execution_ids=[
                        str(item["execution_id"]) for item in records
                    ],
                )
                file_count, byte_count = self._size(run_dir)
                runs.append(
                    RunCatalogEntry(
                        run_id=run_id,
                        path=relative,
                        created_at_utc=manifest.get("created_at_utc"),
                        result_status=(
                            "materialized" if result is not None else "incomplete"
                        ),
                        agent_version_id=candidate.agent_version_id,
                        agent_lifecycle_state_at_run=agent.get(
                            "lifecycle_state_at_run"
                        ),
                        pipeline_path=dimensions.get("pipeline", {}).get("path"),
                        benchmark_key=benchmark.get("key"),
                        benchmark_version=self._optional_int(
                            benchmark.get("version")
                        ),
                        model=model.get("id"),
                        reasoning_effort=model.get("reasoning_effort"),
                        configuration=dict(dimensions.get("configuration", {})),
                        planned_attempts=len(manifest.get("work_items", [])),
                        recorded_attempts=len(records),
                        review_status=review_status,
                        diagnosis_count=len(
                            tuple((run_dir / "diagnosis").glob("diag_*.json"))
                        ),
                        file_count=file_count,
                        bytes=byte_count,
                    )
                )
                seen.add(run_id)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_run",
                        message=str(error),
                        path=relative,
                        entity_kind="run",
                        entity_id=run_id,
                    )
                )
        return runs

    def _scan_versions(
        self,
        runs: list[RunCatalogEntry],
        findings: list[CatalogFinding],
    ) -> tuple[
        list[VersionCatalogEntry],
        dict[str, tuple[tuple[str, str], ...]],
    ]:
        candidates: dict[str, AgentVersionManifest] = {}
        for run in runs:
            try:
                path = self.project_root / run.path / "agent-version.json"
                candidates[run.agent_version_id] = (
                    AgentVersionManifest.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                )
            except (OSError, ValueError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_candidate_version",
                        message=str(error),
                        path=run.path,
                        entity_kind="run",
                        entity_id=run.run_id,
                    )
                )

        promoted: dict[str, AgentVersionManifest] = {}
        manifests_dir = self.agent_root / "manifests"
        for path in sorted(manifests_dir.glob("av_*.json")):
            try:
                manifest = AgentVersionManifest.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
                if path.stem != manifest.agent_version_id:
                    raise ValueError("Manifest filename contradicts its identity.")
                promoted[manifest.agent_version_id] = manifest
            except (OSError, ValueError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_promoted_version",
                        message=str(error),
                        path=self._relative(path),
                        entity_kind="version",
                        entity_id=path.stem,
                    )
                )

        promoted_store = AgentVersionStore(self.agent_root)
        for version_id, manifest in sorted(promoted.items()):
            try:
                promoted_store.verify(manifest, repository=self.project_root)
            except (OSError, ValueError, AgentVersionIntegrityError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_promoted_version_content",
                        message=str(error),
                        path=self._relative(manifests_dir / f"{version_id}.json"),
                        entity_kind="version",
                        entity_id=version_id,
                    )
                )

        aliases: dict[str, list[str]] = defaultdict(list)
        alias_paths = self.agent_root / "catalog" / "aliases"
        for path in sorted(alias_paths.glob("*.json")):
            try:
                payload = self._read_object(path)
                target = str(payload["agent_version_id"])
                manifest = promoted[target]
                if (
                    payload.get("schema_version") != 1
                    or payload.get("manifest_sha256") != manifest.manifest_sha256
                ):
                    raise ValueError("Alias identity is invalid.")
                aliases[target].append(str(payload["alias"]))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_version_alias",
                        message=str(error),
                        path=self._relative(path),
                    )
                )

        promotion_ids: dict[str, list[str]] = defaultdict(list)
        source_runs: dict[str, list[str]] = defaultdict(list)
        source_run_records: dict[str, list[tuple[str, str]]] = defaultdict(list)
        promotion_paths = self.agent_root / "catalog" / "promotions"
        for path in sorted(promotion_paths.glob("*.json")):
            try:
                payload = self._read_object(path)
                target = str(payload["agent_version_id"])
                manifest = promoted[target]
                if (
                    payload.get("schema_version") != 1
                    or payload.get("promotion_id") != path.stem
                    or payload.get("manifest_sha256") != manifest.manifest_sha256
                ):
                    raise ValueError("Promotion identity is invalid.")
                promotion_ids[target].append(path.stem)
                source_run = payload.get("source_run_id")
                if source_run:
                    source_runs[target].append(str(source_run))
                    source_run_records[target].append((path.stem, str(source_run)))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_promotion",
                        message=str(error),
                        path=self._relative(path),
                    )
                )

        versions: list[VersionCatalogEntry] = []
        run_ids_by_version: dict[str, list[str]] = defaultdict(list)
        for run in runs:
            run_ids_by_version[run.agent_version_id].append(run.run_id)
        for version_id in sorted(set(candidates) | set(promoted)):
            manifest = promoted.get(version_id) or candidates[version_id]
            candidate = candidates.get(version_id)
            global_manifest = promoted.get(version_id)
            if (
                candidate is not None
                and global_manifest is not None
                and candidate.manifest_sha256 != global_manifest.manifest_sha256
            ):
                findings.append(
                    CatalogFinding(
                        code="invalid_version_collision",
                        message=(
                            f"Candidate and promoted manifests disagree for {version_id}."
                        ),
                        entity_kind="version",
                        entity_id=version_id,
                    )
                )
            digests = tuple(sorted(self._cas_digests(manifest)))
            if version_id in promoted:
                for digest in digests:
                    object_path = (
                        self.agent_root / "objects" / "sha256" / digest[:2] / digest
                    )
                    try:
                        content = object_path.read_bytes()
                        if hashlib.sha256(content).hexdigest() != digest:
                            raise ValueError(
                                "CAS object digest does not match its path."
                            )
                    except (OSError, ValueError) as error:
                        findings.append(
                            CatalogFinding(
                                code="invalid_version_cas",
                                message=f"{object_path}: {error}",
                                path=self._relative(object_path),
                                entity_kind="version",
                                entity_id=version_id,
                            )
                        )
            versions.append(
                VersionCatalogEntry(
                    agent_version_id=version_id,
                    manifest_sha256=manifest.manifest_sha256,
                    lifecycle_state=(
                        "promoted" if version_id in promoted else "candidate"
                    ),
                    manifest_path=(
                        self._relative(manifests_dir / f"{version_id}.json")
                        if version_id in promoted
                        else None
                    ),
                    aliases=tuple(sorted(aliases.get(version_id, []))),
                    promotion_ids=tuple(sorted(promotion_ids.get(version_id, []))),
                    source_run_ids=tuple(sorted(set(source_runs.get(version_id, [])))),
                    associated_run_ids=tuple(
                        sorted(set(run_ids_by_version.get(version_id, [])))
                    ),
                    global_cas_objects=digests,
                )
            )
        return versions, {
            key: tuple(sorted(set(value))) for key, value in source_run_records.items()
        }

    def _scan_comparisons(
        self, findings: list[CatalogFinding]
    ) -> list[ComparisonCatalogEntry]:
        comparisons: list[ComparisonCatalogEntry] = []
        seen: set[str] = set()
        if not self.eval_root.exists():
            return comparisons
        for path in sorted(self.eval_root.glob("**/comparisons/cmp_*.manifest.json")):
            comparison_id = path.name.removesuffix(".manifest.json")
            try:
                if comparison_id in seen:
                    raise ValueError(f"Duplicate comparison id: {comparison_id}")
                payload = self._read_object(path)
                spec = payload.get("comparison_spec")
                if not isinstance(spec, dict):
                    raise ValueError(
                        "Comparison manifest is missing its specification."
                    )
                expected_id, expected_hash = build_comparison_identity(spec)
                if (
                    comparison_id != expected_id
                    or payload.get("comparison_id") != expected_id
                    or payload.get("comparison_spec_sha256") != expected_hash
                ):
                    raise ValueError("Comparison manifest identity is invalid.")
                run_ids = tuple(str(item) for item in spec.get("run_ids", []))
                if len(run_ids) < 2:
                    raise ValueError("Comparison requires at least two child runs.")
                result_path = path.with_name(f"{comparison_id}.json")
                if result_path.exists():
                    result = self._read_object(result_path)
                    if (
                        result.get("comparison_id") != expected_id
                        or result.get("comparison_spec_sha256") != expected_hash
                        or result.get("comparison_spec") != spec
                    ):
                        raise ValueError("Comparison result identity is invalid.")
                paths = [path] + ([result_path] if result_path.exists() else [])
                comparisons.append(
                    ComparisonCatalogEntry(
                        comparison_id=comparison_id,
                        manifest_path=self._relative(path),
                        result_path=(
                            self._relative(result_path)
                            if result_path.exists()
                            else None
                        ),
                        run_ids=run_ids,
                        varying_dimensions=tuple(
                            str(item) for item in spec.get("varying_dimensions", [])
                        ),
                        file_count=len(paths),
                        bytes=sum(item.stat().st_size for item in paths),
                    )
                )
                seen.add(comparison_id)
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                findings.append(
                    CatalogFinding(
                        code="invalid_comparison",
                        message=str(error),
                        path=self._relative(path),
                        entity_kind="comparison",
                        entity_id=comparison_id,
                    )
                )
        return comparisons

    @staticmethod
    def _run_config(
        manifest: dict[str, Any], result: dict[str, Any] | None
    ) -> dict[str, Any]:
        if result is not None:
            return dict(result.get("run", {}))
        contract = manifest.get("eval_contract", {})
        return dict(contract.get("run", {}))

    @staticmethod
    def _cas_digests(manifest: AgentVersionManifest) -> set[str]:
        digests: set[str] = set()
        for asset in manifest.identity.get("assets", []):
            if asset.get("origin") in {"cas", "overlay"}:
                digest = asset.get("content_sha256")
                if isinstance(digest, str):
                    digests.add(digest)
        overlay = manifest.identity.get("source", {}).get("dirty_overlay") or {}
        for item in overlay.get("entries", []):
            digest = item.get("content_sha256")
            if isinstance(digest, str):
                digests.add(digest)
        return digests

    def _verify_candidate_objects(
        self, run_dir: Path, manifest: AgentVersionManifest
    ) -> None:
        for digest in self._cas_digests(manifest):
            path = run_dir / "objects" / "sha256" / digest[:2] / digest
            try:
                content = path.read_bytes()
            except OSError as error:
                raise ValueError(f"Run-local CAS object is missing: {path}") from error
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"Run-local CAS object is corrupt: {path}")

    @staticmethod
    def _review_status(run_dir: Path, *, expected_execution_ids: list[str]) -> str:
        capture = run_dir / "review" / "capture.json"
        if not capture.is_file():
            return "unavailable"
        try:
            store = LocalReviewStore(run_dir, run_id=run_dir.name)
            state = store.review_state(expected_execution_ids=expected_execution_ids)
            if state.get("integrity", {}).get("status") != "valid":
                return "invalid"
            return str(state.get("capture", {}).get("status", "unknown"))
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
            return "invalid"

    @staticmethod
    def _size(path: Path) -> tuple[int, int]:
        files = [item for item in path.rglob("*") if item.is_file()]
        return len(files), sum(item.stat().st_size for item in files)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _read_object(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected a JSON object: {path}")
        return payload

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.project_root).as_posix()

    def _require_within(self, path: Path) -> None:
        try:
            path.relative_to(self.project_root)
        except ValueError as error:
            raise ValueError(
                f"Lifecycle root is outside the project: {path}"
            ) from error
