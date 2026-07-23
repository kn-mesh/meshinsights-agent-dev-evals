"""Tests for the derived local catalog and recoverable lifecycle deletion."""

from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path

import pytest
from evaluation import build_comparison_identity, build_run_identity

from src.agent_versions.models import AgentVersionManifest
from src.evals.run_store import LocalRunStore
from src.lifecycle import LifecycleError, LocalLifecycleStore
from src.lifecycle import cli as lifecycle_cli


def _agent_manifest(*, variant: str, cas_content: bytes | None = None):
    assets = []
    if cas_content is not None:
        digest = hashlib.sha256(cas_content).hexdigest()
        assets.append(
            {
                "path": f"captured/{variant}.txt",
                "origin": "cas",
                "content_sha256": digest,
            }
        )
    return AgentVersionManifest.build(
        {
            "variant": variant,
            "source": {"tree_state": "clean", "dirty_overlay": None},
            "source_pipeline": {"path": f"pipeline_configs/{variant}.ppln"},
            "assets": assets,
        }
    )


def _write_run(
    root: Path,
    *,
    manifest: AgentVersionManifest,
    model: str = "azure:test",
    cas_content: bytes | None = None,
) -> tuple[str, Path]:
    run_spec = {
        "benchmark": {"key": "benchmark", "version_number": 1},
        "scope": {"example_ids": [], "content_sha256": "scope"},
        "pipeline": {"path": "pipeline_configs/test.ppln"},
        "agent": {
            "agent_version_id": manifest.agent_version_id,
            "manifest_sha256": manifest.manifest_sha256,
            "lifecycle_state_at_run": "candidate",
        },
        "model": {"id": model},
        "runs_per_example": 1,
        "execution": {"runtime": "serial"},
        "configuration_dimensions": {"prompt": "baseline"},
    }
    run_id, digest = build_run_identity(run_spec)
    run_dir = root / "eval_results/test/benchmark/v1/runs" / run_id
    store = LocalRunStore(run_dir, run_id=run_id)
    store.initialize(
        {
            "schema_version": 1,
            "performance_schema_version": 1,
            "run_id": run_id,
            "run_spec_sha256": digest,
            "run_spec": run_spec,
            "work_items": [],
            "created_at_utc": "2026-07-22T12:00:00+00:00",
            "eval_contract": {
                "schema_version": 1,
                "run": {
                    "schema_version": 1,
                    "run_id": run_id,
                    "dimensions": {
                        "agent": run_spec["agent"],
                        "pipeline": {"path": "pipeline_configs/test.ppln"},
                        "benchmark": {"key": "benchmark", "version": 1},
                        "model": {"id": model, "reasoning_effort": "low"},
                        "configuration": {"prompt": "baseline"},
                    },
                    "runs_per_example": 1,
                },
                "examples": [],
                "output_fields": [],
                "slice_keys": [],
            },
        }
    )
    (run_dir / "agent-version.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    if cas_content is not None:
        digest = hashlib.sha256(cas_content).hexdigest()
        object_path = run_dir / "objects/sha256" / digest[:2] / digest
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(cas_content)
    return run_id, run_dir


def _promote_fixture(
    root: Path,
    manifest: AgentVersionManifest,
    *,
    alias: str,
    source_run_id: str | None,
    cas_content: bytes | None = None,
) -> None:
    agent_root = root / "agent_versions"
    manifest_path = agent_root / "manifests" / f"{manifest.agent_version_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    alias_path = agent_root / "catalog/aliases" / f"{alias}.json"
    alias_path.parent.mkdir(parents=True, exist_ok=True)
    alias_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "alias": alias,
                "agent_version_id": manifest.agent_version_id,
                "manifest_sha256": manifest.manifest_sha256,
            }
        ),
        encoding="utf-8",
    )
    promotion_id = f"prm_{manifest.agent_version_id.removeprefix('av_')}"
    promotion_path = agent_root / "catalog/promotions" / f"{promotion_id}.json"
    promotion_path.parent.mkdir(parents=True, exist_ok=True)
    promotion_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "promotion_id": promotion_id,
                "agent_version_id": manifest.agent_version_id,
                "manifest_sha256": manifest.manifest_sha256,
                "promoted_at_utc": "2026-07-22T12:00:00+00:00",
                "source_run_id": source_run_id,
                "alias": alias,
                "notes": None,
            }
        ),
        encoding="utf-8",
    )
    if cas_content is not None:
        digest = hashlib.sha256(cas_content).hexdigest()
        object_path = agent_root / "objects/sha256" / digest[:2] / digest
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(cas_content)


def _write_comparison(root: Path, *run_ids: str) -> str:
    spec = {
        "comparison_schema_version": 1,
        "run_ids": list(run_ids),
        "varying_dimensions": ["model"],
        "invariant_dimensions": {},
        "aligned_example_ids": [],
        "runs_per_example": 1,
    }
    comparison_id, digest = build_comparison_identity(spec)
    directory = root / "eval_results/test/benchmark/v1/comparisons"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "comparison_id": comparison_id,
        "comparison_spec_sha256": digest,
        "comparison_spec": spec,
        "warnings": [],
        "child_manifests": [],
    }
    (directory / f"{comparison_id}.manifest.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (directory / f"{comparison_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return comparison_id


def test_catalog_derives_runs_versions_comparisons_and_references(
    tmp_path: Path,
) -> None:
    first = _agent_manifest(variant="first")
    second = _agent_manifest(variant="second")
    first_run_id, _ = _write_run(tmp_path, manifest=first, model="azure:first")
    second_run_id, _ = _write_run(tmp_path, manifest=second, model="azure:second")
    _promote_fixture(
        tmp_path,
        first,
        alias="current",
        source_run_id=first_run_id,
    )
    comparison_id = _write_comparison(tmp_path, first_run_id, second_run_id)

    catalog = LocalLifecycleStore(tmp_path).catalog()

    assert not catalog.findings
    assert [item.run_id for item in catalog.runs] == sorted(
        [first_run_id, second_run_id]
    )
    versions = {item.agent_version_id: item for item in catalog.versions}
    assert versions[first.agent_version_id].lifecycle_state == "promoted"
    assert versions[first.agent_version_id].aliases == ("current",)
    assert versions[second.agent_version_id].lifecycle_state == "candidate"
    assert catalog.comparisons[0].comparison_id == comparison_id
    relations = {item.relation for item in catalog.references}
    assert relations == {
        "compares_run",
        "names_version",
        "promoted_from_run",
        "promotes_version",
        "uses_agent_version",
    }


def test_run_delete_preview_quarantine_and_restore_are_recoverable(
    tmp_path: Path,
) -> None:
    manifest = _agent_manifest(variant="first")
    run_id, run_dir = _write_run(tmp_path, manifest=manifest)
    other_id, _ = _write_run(
        tmp_path,
        manifest=_agent_manifest(variant="other"),
        model="azure:other",
    )
    comparison_id = _write_comparison(tmp_path, run_id, other_id)
    store = LocalLifecycleStore(tmp_path)

    plan = store.plan_delete("run", run_id)

    assert plan.paths[0].path.endswith(f"/runs/{run_id}")
    assert any(comparison_id in warning for warning in plan.warnings)
    assert not (run_dir / ".coordinator.lock").exists()

    operation = store.quarantine("run", run_id, confirmed=True)
    assert operation.state == "quarantined"
    assert not run_dir.exists()
    assert store.load_operation(operation.operation_id).state == "quarantined"

    restored = store.restore(operation.operation_id, confirmed=True)
    assert restored.state == "restored"
    assert run_dir.is_dir()
    assert store.catalog().runs[0].run_id in {run_id, other_id}


def test_quarantined_run_can_be_permanently_purged(tmp_path: Path) -> None:
    run_id, run_dir = _write_run(tmp_path, manifest=_agent_manifest(variant="purge"))
    store = LocalLifecycleStore(tmp_path)
    operation = store.quarantine("run", run_id, confirmed=True)

    preview = store.preview_operation(operation.operation_id, "purge")
    assert preview["dry_run"] is True
    purged = store.purge(operation.operation_id, confirmed=True)

    assert purged.state == "purged"
    assert not run_dir.exists()
    assert not (store.quarantine_dir / operation.operation_id).exists()
    assert store.load_operation(operation.operation_id).state == "purged"


def test_restore_rejects_changed_quarantine_content(tmp_path: Path) -> None:
    run_id, _ = _write_run(
        tmp_path, manifest=_agent_manifest(variant="tampered-quarantine")
    )
    store = LocalLifecycleStore(tmp_path)
    operation = store.quarantine("run", run_id, confirmed=True)
    quarantined_run = (
        store.quarantine_dir
        / operation.operation_id
        / "payload"
        / operation.paths[0].path
    )
    (quarantined_run / "agent-version.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(LifecycleError, match="content changed"):
        store.restore(operation.operation_id, confirmed=True)


def test_restore_recovers_an_interrupted_staging_operation(tmp_path: Path) -> None:
    run_id, run_dir = _write_run(
        tmp_path, manifest=_agent_manifest(variant="interrupted-stage")
    )
    store = LocalLifecycleStore(tmp_path)
    operation = store.quarantine("run", run_id, confirmed=True)
    staging = operation.model_copy(update={"state": "staging"})
    store._write_operation(staging, create=False)

    restored = store.restore(operation.operation_id, confirmed=True)

    assert restored.state == "restored"
    assert run_dir.is_dir()


def test_purge_recovers_an_interrupted_purging_operation(tmp_path: Path) -> None:
    run_id, _ = _write_run(
        tmp_path, manifest=_agent_manifest(variant="interrupted-purge")
    )
    store = LocalLifecycleStore(tmp_path)
    operation = store.quarantine("run", run_id, confirmed=True)
    operation_root = store.quarantine_dir / operation.operation_id
    staging_path = store.quarantine_dir / f".{operation.operation_id}.purge"
    operation_root.rename(staging_path)
    purging = operation.model_copy(update={"state": "purging"})
    store._write_operation(purging, create=False)

    purged = store.purge(operation.operation_id, confirmed=True)

    assert purged.state == "purged"
    assert not staging_path.exists()


def test_promoted_version_uses_same_flow_and_preserves_shared_cas(
    tmp_path: Path,
) -> None:
    shared = b"shared retained object"
    first = _agent_manifest(variant="first", cas_content=shared)
    second = _agent_manifest(variant="second", cas_content=shared)
    run_id, _ = _write_run(tmp_path, manifest=first, cas_content=shared)
    _promote_fixture(
        tmp_path,
        first,
        alias="first",
        source_run_id=run_id,
        cas_content=shared,
    )
    _promote_fixture(
        tmp_path,
        second,
        alias="second",
        source_run_id=None,
        cas_content=shared,
    )
    digest = hashlib.sha256(shared).hexdigest()
    object_path = tmp_path / "agent_versions/objects/sha256" / digest[:2] / digest
    store = LocalLifecycleStore(tmp_path)

    plan = store.plan_delete("version", first.agent_version_id)
    assert all(
        item.path != object_path.relative_to(tmp_path).as_posix() for item in plan.paths
    )
    assert any(run_id in warning for warning in plan.warnings)

    operation = store.quarantine("version", first.agent_version_id, confirmed=True)
    assert operation.state == "quarantined"
    assert object_path.is_file()
    remaining = {item.agent_version_id for item in store.catalog().versions}
    assert first.agent_version_id in remaining  # run-local candidate remains
    assert second.agent_version_id in remaining


def test_version_delete_quarantines_unreachable_cas_and_owned_catalog_records(
    tmp_path: Path,
) -> None:
    content = b"unique promoted object"
    manifest = _agent_manifest(variant="unique", cas_content=content)
    _promote_fixture(
        tmp_path,
        manifest,
        alias="unique",
        source_run_id=None,
        cas_content=content,
    )
    store = LocalLifecycleStore(tmp_path)
    plan = store.plan_delete("version", manifest.agent_version_id)

    reasons = {item.reason for item in plan.paths}
    assert reasons == {
        "promoted version manifest",
        "version alias",
        "promotion event",
        "unreachable promoted-version CAS object",
    }
    operation = store.quarantine("version", manifest.agent_version_id, confirmed=True)
    assert operation.state == "quarantined"
    assert store.catalog().versions == ()


def test_deletion_rejects_symlinks_and_active_runs(tmp_path: Path) -> None:
    run_id, run_dir = _write_run(tmp_path, manifest=_agent_manifest(variant="unsafe"))
    external = tmp_path / "external.txt"
    external.write_text("outside evidence", encoding="utf-8")
    (run_dir / "unsafe-link").symlink_to(external)
    store = LocalLifecycleStore(tmp_path)

    with pytest.raises(LifecycleError, match="symlink"):
        store.plan_delete("run", run_id)
    (run_dir / "unsafe-link").unlink()

    lock_path = run_dir / ".coordinator.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(LifecycleError, match="active"):
            store.plan_delete("run", run_id)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_cli_emits_stable_json_catalog_and_delete_preview(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_id, _ = _write_run(tmp_path, manifest=_agent_manifest(variant="cli"))

    assert (
        lifecycle_cli.main(["--project-root", str(tmp_path), "catalog", "--json"]) == 0
    )
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["catalog_schema_version"] == 1
    assert catalog["runs"][0]["run_id"] == run_id

    assert (
        lifecycle_cli.main(
            [
                "--project-root",
                str(tmp_path),
                "delete",
                "run",
                run_id,
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert preview["target_id"] == run_id
