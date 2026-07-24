"""Focused contracts for selective immutable cloud publication."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from evaluation import canonical_sha256
from src.eval_publication.cli import _parser
from src.eval_publication.service import EvalPublicationError, EvalPublicationService


EVAL_RUN_ID = "eval_" + "1" * 24
RUN_SPEC_SHA256 = "2" * 64
SCOPE_SHA256 = "3" * 64
AGENT_VERSION_ID = "av_" + "4" * 24
AGENT_MANIFEST_SHA256 = "5" * 64
GIT_COMMIT = "6" * 40
BENCHMARK_KEY = "benchmark-a"


class _MemoryStore:
    def __init__(self, *, corrupt_payload_reads: bool = False) -> None:
        self.blobs: dict[str, bytes] = {}
        self.operations: list[tuple[str, str]] = []
        self.corrupt_payload_reads = corrupt_payload_reads

    def create(self, blob_name: str, content: bytes) -> None:
        self.operations.append(("create", blob_name))
        if blob_name in self.blobs:
            raise FileExistsError(blob_name)
        self.blobs[blob_name] = content

    def read(self, blob_name: str) -> bytes:
        self.operations.append(("read", blob_name))
        content = self.blobs[blob_name]
        if self.corrupt_payload_reads and not blob_name.endswith(
            "publication-manifest.json"
        ):
            return content + b"corrupt"
        return content


def _json_bytes(payload: Any) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode()
        + b"\n"
    )


def _identity(payload: Any) -> dict[str, Any]:
    content = _json_bytes(payload)
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "byte_size": len(content),
    }


def _retained_fixture(
    root: Path,
    *,
    execution_status: str = "completed",
    tree_state: str = "clean",
) -> str:
    (root / "workbench.project.json").write_text(
        json.dumps(
            {
                "project": {
                    "key": "workbench-project",
                    "use_case_key": "test-use-case",
                }
            }
        ),
        encoding="utf-8",
    )
    benchmark = {
        "project_key": "benchmark-project",
        "key": BENCHMARK_KEY,
        "version_id": "benchmark-version-id",
        "version": 7,
        "source_state_sha256": "7" * 64,
    }
    result = {
        "schema_version": 2,
        "summary": {
            "accuracy": {"complete_evaluation": {"accuracy": 1.0}},
            "reliability": {"planned_runs": 1},
            "scoring_coverage": {"coverage": 1.0},
            "usage": {"totals": {"total_tokens": 10}},
            "cost": {"units_with_complete_cost_observations": 1},
            "timing": {"evaluation_active_wall_seconds": 4.5},
        },
        "run": {
            "schema_version": 2,
            "run_id": EVAL_RUN_ID,
            "eval_run_id": EVAL_RUN_ID,
            "run_spec_sha256": RUN_SPEC_SHA256,
            "selected_example_scope_sha256": SCOPE_SHA256,
            "started_at_utc": "2026-07-23T00:00:00+00:00",
            "completed_at_utc": "2026-07-23T00:01:00+00:00",
            "latest_invocation_id": "inv_local",
            "dimensions": {
                "benchmark": benchmark,
                "model": {
                    "provider": "azure",
                    "id": "azure:model",
                    "api": "openai_responses",
                    "pricing": {"currency": "USD", "content_sha256": "8" * 64},
                },
                "scoring": {"grader_set_sha256": "9" * 64},
                "agent": {
                    "agent_version_id": AGENT_VERSION_ID,
                    "source_tree_state": tree_state,
                },
                "pipeline": {
                    "path": "/local/pipeline.ppln",
                    "content_sha256": "a" * 64,
                },
                "evaluation_profile": {
                    "path": "/local/profile.eval.yaml",
                    "content_sha256": "b" * 64,
                },
            },
            "graders": [{"id": "core.exact", "version": 1, "config": {}}],
        },
        "artifacts": {"manifest": "manifest.json", "attempts": "attempts/"},
    }
    units = {
        "schema_version": 2,
        "retained_eval_id": None,
        "source_run_id": EVAL_RUN_ID,
        "units": [
            {
                "example_id": "example-a",
                "unit_id": "unit-a",
                "decision_timestamp": "2026-07-23T00:00:00+00:00",
                "source_snapshot_id": "snapshot-a",
                "work_item_id": "work-a",
                "execution_status": execution_status,
                "output_contract_status": "valid",
                "scoring_status": "scored",
                "agent_output": {"answer": "yes"},
                "benchmark_labels": {"answer": "yes"},
                "evaluations": {"answer": {"correct": True}},
                "usage": {"total_tokens": 10},
                "cost": {"status": "actual", "amount": 0.1},
                "invocation_id": "inv_local",
                "execution_history": [{"execution_status": execution_status}],
            }
        ],
    }
    evidence = {
        "schema_version": 2,
        "storage": {
            "account_url": "https://evidence.blob.core.windows.net",
            "container": "source-snapshots",
            "access": "read_only_on_demand",
        },
        "evidence_recipe_id": "recipe@1",
        "source_snapshot_contract": "azure-blob-sha256-v1",
        "benchmark_source_state_sha256": benchmark["source_state_sha256"],
        "examples": [{"example_id": "example-a", "source_snapshot_id": "snapshot-a"}],
    }
    agent_identity = {
        "source": {
            "repository_id": "repo",
            "git_revision": GIT_COMMIT,
            "git_tree": "c" * 40,
            "tree_state": tree_state,
            "dirty_overlay_sha256": None if tree_state == "clean" else "d" * 64,
        },
        "assets": [{"content_sha256": "e" * 64}],
        "contracts": {
            "structured_output": {"content_sha256": "f" * 64},
            "evidence_recipe": {"content_sha256": "0" * 64},
        },
        "dependencies": {"lock_sha256": "1" * 64},
        "model_policy": {"policy_sha256": "2" * 64},
    }
    provenance = {
        "schema_version": 2,
        "source_run_id": EVAL_RUN_ID,
        "agent_version_id": AGENT_VERSION_ID,
        "manifest_sha256": AGENT_MANIFEST_SHA256,
        "git": {
            **agent_identity["source"],
        },
        "agent_identity": agent_identity,
        "configuration_hashes": {
            "pipeline": "3" * 64,
            "evaluation_profile": "4" * 64,
            "grader_set": "5" * 64,
            "source_manifest": "6" * 64,
        },
        "benchmark": benchmark,
        "evidence": {"content_sha256": "7" * 64},
        "model": {"content_sha256": "8" * 64},
    }
    identity_seed = {
        "schema_version": 2,
        "lifecycle_state": "retained",
        "source_run_id": EVAL_RUN_ID,
        "source_run_spec_sha256": RUN_SPEC_SHA256,
        "agent_version_id": AGENT_VERSION_ID,
        "benchmark": {
            "key": BENCHMARK_KEY,
            "version": 7,
            "version_id": "benchmark-version-id",
            "source_state_sha256": benchmark["source_state_sha256"],
        },
        "source_eval_run_id": EVAL_RUN_ID,
        "agent_version_manifest_sha256": AGENT_MANIFEST_SHA256,
    }
    retained_eval_id = f"ret_{canonical_sha256(identity_seed)[:24]}"
    units["retained_eval_id"] = retained_eval_id
    artifacts = {
        "result.json": result,
        "units.json": units,
        "evidence-references.json": evidence,
        "agent-provenance.json": provenance,
    }
    manifest = {
        **identity_seed,
        "identity_seed": identity_seed,
        "created_at_utc": "2026-07-23T00:02:00+00:00",
        "artifacts": {name: _identity(payload) for name, payload in artifacts.items()},
        "source_provenance": {
            "git_revision": GIT_COMMIT,
            "tree_state": tree_state,
            "dirty_overlay_sha256": agent_identity["source"]["dirty_overlay_sha256"],
        },
        "pruned_categories": ["attempt_files", "performance"],
        "retained_eval_id": retained_eval_id,
    }
    retained = root / f"eval_results/retained/{BENCHMARK_KEY}/v7/{retained_eval_id}"
    retained.mkdir(parents=True)
    for name, payload in {**artifacts, "manifest.json": manifest}.items():
        (retained / name).write_bytes(_json_bytes(payload))
    shared_agent = root / f"eval_results/retained/agent_versions/{AGENT_VERSION_ID}"
    shared_agent.mkdir(parents=True)
    (shared_agent / "agent-provenance.json").write_bytes(
        _json_bytes(
            {
                key: provenance[key]
                for key in (
                    "schema_version",
                    "agent_version_id",
                    "manifest_sha256",
                    "git",
                    "agent_identity",
                )
            }
        )
    )
    return retained_eval_id


def test_cli_requires_explicit_publish_mode() -> None:
    parser = _parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["publish", "ret_" + "a" * 24])


def test_dry_run_is_storage_free_and_allocates_no_publication(tmp_path: Path) -> None:
    retained_eval_id = _retained_fixture(tmp_path)
    store = _MemoryStore()
    service = EvalPublicationService(tmp_path, store=store)

    preview = service.dry_run(retained_eval_id)

    assert preview["publication_id"] is None
    assert preview["publication_allocated"] is False
    assert preview["destination_parent"].endswith(
        f"benchmarks/{BENCHMARK_KEY}/v7/publications"
    )
    assert preview["counts"]["execution_states"] == {"completed": 1}
    assert store.operations == []


def test_publish_verifies_payloads_before_committing_manifest(tmp_path: Path) -> None:
    retained_eval_id = _retained_fixture(tmp_path)
    store = _MemoryStore()
    service = EvalPublicationService(tmp_path, store=store)

    first = service.publish(retained_eval_id, confirmed=True)
    second = service.publish(retained_eval_id, confirmed=True)

    assert first["publication_id"] != second["publication_id"]
    manifest_creates = [
        index
        for index, operation in enumerate(store.operations)
        if operation[0] == "create"
        and operation[1].endswith("publication-manifest.json")
    ]
    assert len(manifest_creates) == 2
    for manifest_index in manifest_creates:
        publication_prefix = store.operations[manifest_index][1].rsplit("/", 1)[0]
        payload_reads = [
            index
            for index, operation in enumerate(store.operations[:manifest_index])
            if operation[0] == "read"
            and operation[1].startswith(publication_prefix)
            and not operation[1].endswith("publication-manifest.json")
        ]
        assert len(payload_reads) == 4
        assert max(payload_reads) < manifest_index


def test_corrupt_payload_never_commits_manifest(tmp_path: Path) -> None:
    retained_eval_id = _retained_fixture(tmp_path)
    store = _MemoryStore(corrupt_payload_reads=True)
    service = EvalPublicationService(tmp_path, store=store)

    with pytest.raises(EvalPublicationError, match="artifact verification failed"):
        service.publish(retained_eval_id, confirmed=True)

    assert not any(name.endswith("publication-manifest.json") for name in store.blobs)


@pytest.mark.parametrize(
    ("execution_status", "tree_state", "message"),
    [
        ("failed", "clean", "Every canonical selected unit must complete"),
        ("completed", "dirty", "clean recorded agent-version surface"),
    ],
)
def test_publication_preflight_rejects_ineligible_retained_eval(
    tmp_path: Path,
    execution_status: str,
    tree_state: str,
    message: str,
) -> None:
    retained_eval_id = _retained_fixture(
        tmp_path,
        execution_status=execution_status,
        tree_state=tree_state,
    )

    with pytest.raises(EvalPublicationError, match=message):
        EvalPublicationService(tmp_path, store=_MemoryStore()).dry_run(retained_eval_id)
