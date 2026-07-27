"""Reusable Workbench tests for agent-version resolution, storage, and policy."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

import src.agent_versions.resolver as agent_version_resolver
from src.agent_versions import (
    AgentVersionIntegrityError,
    AgentVersionManifest,
    AgentVersionStore,
    ResolvedAgentVersion,
    resolve_agent_version,
    validate_runtime_overrides,
)
from src.agent_versions.models import AgentVersionPolicy, PolicyAsset


ROOT = Path(__file__).resolve().parents[1]
REAL_DIRTY_RUNTIME_PATHS = agent_version_resolver._dirty_runtime_paths


def _isolated_repository(destination: Path) -> Path:
    """Create a committed repository from the current working tree."""
    shutil.copytree(
        ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            ".coverage",
            "*.egg-info",
            "eval_results",
            "agent_versions",
            "build",
            "dist",
        ),
    )
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=destination,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=destination,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=destination,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=destination, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "fixture"],
        cwd=destination,
        check=True,
    )
    return destination


def _distinct_resolved_version(
    resolved: ResolvedAgentVersion,
) -> ResolvedAgentVersion:
    """Create a second valid identity without depending on another pipeline."""
    identity = copy.deepcopy(resolved.manifest.identity)
    identity["source_pipeline"]["display_version"] = "test-distinct"
    return resolved.model_copy(
        update={"manifest": AgentVersionManifest.build(identity)}
    )


def test_v1_resolution_is_deterministic_and_complete() -> None:
    first = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )

    assert first.manifest == second.manifest
    assert first.manifest.agent_version_id.startswith("av_")
    identity = first.manifest.identity
    assert identity["source_pipeline"]["name"] == ("pulse_alarm_failure_analysis_v1_3")
    assert identity["dependencies"]["lock_sha256"]
    assert identity["contracts"]["evidence_recipe_sha256"]
    assert identity["model_policy"]["default_model"] == "azure:gpt-5.6-luna"
    assert len(identity["components"]) == 10
    assert not any(
        asset["path"].startswith("src/project_bootstrap/")
        for asset in identity["assets"]
    )


def test_resolver_merges_component_and_policy_only_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_policy = agent_version_resolver.load_agent_version_policy

    def policy_with_additional_asset(path: Path) -> AgentVersionPolicy:
        policy = load_policy(path)
        return policy.model_copy(
            update={
                "additional_assets": (
                    PolicyAsset(
                        role="operator_contract",
                        logical_name="project_context",
                        path="../docs/PROJECT_CONTEXT.md",
                        media_type="text/markdown",
                    ),
                )
            }
        )

    monkeypatch.setattr(
        agent_version_resolver,
        "load_agent_version_policy",
        policy_with_additional_asset,
    )

    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    assets = {
        asset["path"]: {role["role"] for role in asset["roles"]}
        for asset in resolved.manifest.identity["assets"]
    }

    assert "output_schema" in assets["use_case/processors/common/structured_outputs.py"]
    assert "operator_contract" in assets["use_case/docs/PROJECT_CONTEXT.md"]


def test_model_override_policy_is_fail_closed() -> None:
    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )

    assert validate_runtime_overrides(
        resolved.policy,
        ai_model="azure:gpt-5.6-sol",
        ai_reasoning_effort="high",
    ) == ("azure:gpt-5.6-sol", "high")
    with pytest.raises(ValueError, match="not permitted"):
        validate_runtime_overrides(
            resolved.policy,
            ai_model="unlisted:model",
            ai_reasoning_effort="high",
        )
    with pytest.raises(ValueError, match="Reasoning override"):
        validate_runtime_overrides(
            resolved.policy,
            ai_model=None,
            ai_reasoning_effort="extreme",
        )


def test_manifest_rejects_identity_mutation() -> None:
    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    payload = resolved.manifest.model_dump(mode="json")
    payload["identity"]["source_pipeline"]["display_version"] = "changed"

    with pytest.raises(ValueError, match="manifest hash is invalid"):
        AgentVersionManifest.model_validate(payload)


def test_candidate_promotion_is_idempotent_and_reconstructable(
    tmp_path: Path,
) -> None:
    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    store = AgentVersionStore(tmp_path / "agent_versions")
    run_dir = tmp_path / "run"
    candidate_path = store.persist_candidate(resolved, run_dir)
    promoted = store.promote(
        resolved,
        alias="pulse-v1-3-test",
        source_run_id="eval_test",
        repository=ROOT,
    )
    repeated = store.promote(
        resolved,
        alias="pulse-v1-3-test",
        source_run_id="eval_test",
        repository=ROOT,
    )

    assert candidate_path.is_file()
    assert promoted == repeated
    assert store.load("pulse-v1-3-test") == resolved.manifest
    reconstructed = store.reconstruct(
        resolved.manifest,
        repository=ROOT,
        destination=tmp_path / "reconstructed",
    )
    assert json.loads(candidate_path.read_text())["agent_version_id"] == (
        resolved.manifest.agent_version_id
    )
    assert (reconstructed / "use_case/pipeline_configs/v1_3.ppln").read_bytes() == (
        (ROOT / "use_case/pipeline_configs/v1_3.ppln").read_bytes()
    )


def test_alias_conflict_does_not_append_a_promotion_event(tmp_path: Path) -> None:
    first = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = _distinct_resolved_version(first)
    store = AgentVersionStore(tmp_path / "agent_versions")
    store.promote(first, alias="current", repository=ROOT)

    with pytest.raises(AgentVersionIntegrityError, match="Conflicting immutable"):
        store.promote(second, alias="current", repository=ROOT)

    assert len(tuple(store.promotions.glob("*.json"))) == 1
    assert store.load("current") == first.manifest


def test_dirty_agent_version_rejects_corrupt_retained_bytes(tmp_path: Path) -> None:
    repository = _isolated_repository(tmp_path / "repository")
    pipeline = repository / "use_case/pipeline_configs/v1_3.ppln"
    pipeline.write_text(
        pipeline.read_text(encoding="utf-8").replace("timeout: 120", "timeout: 121"),
        encoding="utf-8",
    )
    resolved = resolve_agent_version(
        pipeline,
        root=repository,
        dirty_policy="capture",
    )
    store = AgentVersionStore(tmp_path / "agent_versions")
    store.promote(resolved, repository=repository)

    assert resolved.manifest.identity["source"]["tree_state"] == "dirty"
    assert len(resolved.blobs) == 1
    digest = next(iter(resolved.blobs))
    retained = store.objects / digest[:2] / digest
    retained.chmod(0o600)
    retained.write_bytes(b"corrupt retained bytes")

    with pytest.raises(AgentVersionIntegrityError, match="Missing or corrupt CAS"):
        store.verify(resolved.manifest, repository=repository)
    with pytest.raises(AgentVersionIntegrityError, match="Corrupt CAS"):
        store.reconstruct(
            resolved.manifest,
            repository=repository,
            destination=tmp_path / "corrupt-reconstruction",
        )


def test_unreachable_dirty_runtime_path_is_rejected_in_isolated_repository(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = _isolated_repository(tmp_path / "repository")
    unrelated = repository / "use_case/unrelated.py"
    unrelated.write_text(
        "VALUE = 'unrelated runtime change'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        agent_version_resolver,
        "_dirty_runtime_paths",
        REAL_DIRTY_RUNTIME_PATHS,
    )

    with pytest.raises(ValueError, match="not reachable from the resolved agent graph"):
        resolve_agent_version(
            repository / "use_case/pipeline_configs/v1_3.ppln",
            root=repository,
            dirty_policy="capture",
        )


def test_deleted_runtime_path_is_preserved_in_dirty_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted = "src/actions/__init__.py"
    monkeypatch.setattr(
        agent_version_resolver,
        "_dirty_runtime_paths",
        lambda root: ((deleted, False),),
    )
    monkeypatch.setattr(
        agent_version_resolver,
        "_git_file_bytes",
        lambda root, revision, relative: (
            b'"""Old runtime package."""\n' if relative == deleted else None
        ),
    )

    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln",
        dirty_policy="capture",
    )

    overlay = resolved.manifest.identity["source"]["dirty_overlay"]["entries"]
    assert any(
        item["operation"] == "delete" and item["path"] == deleted
        for item in overlay
    )


def test_alias_load_rejects_tampered_alias_identity(tmp_path: Path) -> None:
    first = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = _distinct_resolved_version(first)
    store = AgentVersionStore(tmp_path / "agent_versions")
    store.promote(first, alias="current", repository=ROOT)
    store.promote(second, repository=ROOT)
    alias_path = store.aliases / "current.json"
    valid_alias = json.loads(alias_path.read_text(encoding="utf-8"))
    mutations = (
        {**valid_alias, "alias": "different"},
        {**valid_alias, "manifest_sha256": second.manifest.manifest_sha256},
        {
            **valid_alias,
            "agent_version_id": second.manifest.agent_version_id,
        },
        {**valid_alias, "schema_version": 2},
        {**valid_alias, "unexpected": True},
    )

    for payload in mutations:
        alias_path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(AgentVersionIntegrityError, match="alias"):
            store.load("current")


def test_alias_load_accepts_equivalent_normalized_name(tmp_path: Path) -> None:
    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    store = AgentVersionStore(tmp_path / "agent_versions")
    store.promote(resolved, alias="Current Release", repository=ROOT)

    assert store.load("current-release") == resolved.manifest


def test_local_dependency_graph_excludes_unrelated_mi_core_path(
    tmp_path: Path,
) -> None:
    component = tmp_path / "src/component.py"
    reachable = tmp_path / "mi-core/core/src/mi/core/reachable.py"
    unrelated = tmp_path / "mi-core/core/src/mi/core/unrelated.py"
    component.parent.mkdir(parents=True)
    reachable.parent.mkdir(parents=True)
    component.write_text(
        "from mi.core.reachable import VALUE\n",
        encoding="utf-8",
    )
    reachable.write_text("VALUE = 1\n", encoding="utf-8")
    unrelated.write_text("VALUE = 2\n", encoding="utf-8")

    paths = agent_version_resolver._resolved_local_python_dependencies(
        tmp_path,
        {component: []},
    )

    assert "mi-core/core/src/mi/core/reachable.py" in paths
    assert "mi-core/core/src/mi/core/unrelated.py" not in paths


def test_reachable_dirty_mi_core_path_is_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reachable = "mi-core/core/src/mi/ai/mixins/workflow.py"
    monkeypatch.setattr(
        agent_version_resolver,
        "_dirty_runtime_paths",
        lambda root: ((reachable, True),),
    )

    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )

    matching_assets = [
        asset
        for asset in resolved.manifest.identity["assets"]
        if asset["path"] == reachable
    ]
    assert len(matching_assets) == 1
    assert any(
        role["role"] == "version_surface_guard" for role in matching_assets[0]["roles"]
    )


def test_reachable_dirty_use_case_path_is_captured(tmp_path: Path) -> None:
    repository = _isolated_repository(tmp_path / "repository")
    component = repository / "use_case/processors/common/structured_outputs.py"
    component.write_text(
        component.read_text(encoding="utf-8") + "\n# behavior-bearing change\n",
        encoding="utf-8",
    )

    resolved = resolve_agent_version(
        repository / "use_case/pipeline_configs/v1_3.ppln",
        root=repository,
        dirty_policy="capture",
    )

    assert resolved.manifest.identity["source"]["tree_state"] == "dirty"
    matching = next(
        asset
        for asset in resolved.manifest.identity["assets"]
        if asset["path"] == "use_case/processors/common/structured_outputs.py"
    )
    assert matching["origin"] == "overlay"
    assert matching["content_sha256"] in resolved.blobs


@pytest.mark.parametrize(
    ("asset_path", "message"),
    [
        ("../../../outside.md", "outside the repository"),
        ("../docs/missing.md", "Version asset does not exist"),
    ],
)
def test_policy_assets_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    asset_path: str,
    message: str,
) -> None:
    load_policy = agent_version_resolver.load_agent_version_policy

    def policy_with_invalid_asset(path: Path) -> AgentVersionPolicy:
        policy = load_policy(path)
        return policy.model_copy(
            update={
                "additional_assets": (
                    PolicyAsset(
                        role="operator_contract",
                        logical_name="invalid",
                        path=asset_path,
                    ),
                )
            }
        )

    monkeypatch.setattr(
        agent_version_resolver,
        "load_agent_version_policy",
        policy_with_invalid_asset,
    )

    with pytest.raises(ValueError, match=message):
        resolve_agent_version(
            ROOT / "use_case/pipeline_configs/v1_3.ppln",
            dirty_policy="capture",
        )


def test_workbench_management_code_is_not_agent_execution_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    management_paths = (
        ("src/eval_lifecycle/__init__.py", True),
        ("src/model_configuration.py", True),
    )
    monkeypatch.setattr(
        agent_version_resolver,
        "_dirty_runtime_paths",
        lambda root: management_paths,
    )

    resolved = resolve_agent_version(
        ROOT / "use_case/pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )

    asset_paths = {
        asset["path"] for asset in resolved.manifest.identity["assets"]
    }
    assert not asset_paths.intersection(path for path, _ in management_paths)
