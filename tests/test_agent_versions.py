"""Tests for immutable agent-version resolution, storage, and policy checks."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

import src.agent_versions.resolver as agent_version_resolver
from src.agent_versions import (
    AgentVersionIntegrityError,
    AgentVersionManifest,
    AgentVersionStore,
    resolve_agent_version,
    validate_runtime_overrides,
)


ROOT = Path(__file__).resolve().parents[1]


def test_v1_resolution_is_deterministic_and_complete() -> None:
    first = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
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


def test_v2_resolution_freezes_skills_tools_prompts_and_schemas() -> None:
    resolved = resolve_agent_version(
        ROOT / "pipeline_configs/v2.ppln", dirty_policy="capture"
    )
    roles = [
        role
        for asset in resolved.manifest.identity["assets"]
        for role in asset["roles"]
    ]
    declarations = [
        declaration
        for component in resolved.manifest.identity["components"]
        for declaration in component["declarations"]
    ]

    assert {item["logical_name"] for item in roles if item["role"] == "skill"} == {
        "open-failure-investigation",
        "closed-vs-shutdown",
        "modulation-vs-failure",
        "history-and-sensor-integrity",
    }
    assert (
        len([item for item in declarations if item["role"] == "tool_definition"]) == 5
    )
    assert any(item["role"] == "prompt" for item in declarations)
    assert any(item["role"] == "output_schema" for item in declarations)
    contracts = resolved.manifest.identity["contracts"]
    assert len(contracts["normalized_input_schemas"]) == 1
    assert len(contracts["normalized_output_schemas"]) == 2
    assert all(
        item["content_sha256"] for item in contracts["normalized_output_schemas"]
    )


def test_model_override_policy_is_fail_closed() -> None:
    resolved = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
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
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    payload = resolved.manifest.model_dump(mode="json")
    payload["identity"]["source_pipeline"]["display_version"] = "changed"

    with pytest.raises(ValueError, match="manifest hash is invalid"):
        AgentVersionManifest.model_validate(payload)


def test_candidate_promotion_is_idempotent_and_reconstructable(
    tmp_path: Path,
) -> None:
    resolved = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
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
    assert (reconstructed / "pipeline_configs/v1_3.ppln").read_bytes() == (
        (ROOT / "pipeline_configs/v1_3.ppln").read_bytes()
    )


def test_alias_conflict_does_not_append_a_promotion_event(tmp_path: Path) -> None:
    first = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = resolve_agent_version(
        ROOT / "pipeline_configs/v2.ppln", dirty_policy="capture"
    )
    store = AgentVersionStore(tmp_path / "agent_versions")
    store.promote(first, alias="current", repository=ROOT)

    with pytest.raises(AgentVersionIntegrityError, match="Conflicting immutable"):
        store.promote(second, alias="current", repository=ROOT)

    assert len(tuple(store.promotions.glob("*.json"))) == 1
    assert store.load("current") == first.manifest


def test_dirty_agent_version_rejects_corrupt_retained_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(repository)],
        check=True,
    )
    pipeline = repository / "pipeline_configs/v1_3.ppln"
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


def test_alias_load_rejects_tampered_alias_identity(tmp_path: Path) -> None:
    first = resolve_agent_version(
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
    )
    second = resolve_agent_version(
        ROOT / "pipeline_configs/v2.ppln", dirty_policy="capture"
    )
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
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
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
        ROOT / "pipeline_configs/v1_3.ppln", dirty_policy="capture"
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
