"""Tests for the append-only local evaluation run store."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import (
    build_eval_run_identity,
    build_work_item_id,
    canonical_sha256,
)
from workbench.evals.run_store import LocalRunStore, RunStoreIntegrityError


def _manifest() -> dict[str, object]:
    run_spec = {"benchmark": "v1", "model": "provider:model"}
    digest = canonical_sha256(run_spec)
    run_id, occurrence_seed = build_eval_run_identity(
        run_spec_sha256=digest,
        created_at_utc="2026-01-01T00:00:00+00:00",
        nonce="run-store-test",
    )
    work_item_id = build_work_item_id(
        run_id=run_id, item_id="example-a", attempt_index=1
    )
    return {
        "schema_version": 2,
        "performance_schema_version": 1,
        "coordinator_scope": "local_single_host",
        "run_id": run_id,
        "eval_run_id": run_id,
        "run_spec_sha256": digest,
        "occurrence_seed": occurrence_seed,
        "run_spec": run_spec,
        "work_items": [
            {
                "work_item_id": work_item_id,
                "example_id": "example-a",
                "repetition_index": 1,
            }
        ],
        "created_at_utc": "2026-01-01T00:00:00+00:00",
    }


def _attempt_record(
    manifest: dict[str, object], *, status: str = "completed"
) -> dict[str, object]:
    work_item = manifest["work_items"][0]  # type: ignore[index]
    work_item_id = work_item["work_item_id"]  # type: ignore[index]
    healthy = status == "completed"
    return {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "work_item_id": work_item_id,
        "example_id": "example-a",
        "repetition_index": 1,
        "execution_id": f"{work_item_id}.1",
        "generation": 1,
        "invocation_id": "inv_a",
        "attempt": {
            "execution_status": "completed" if healthy else "failed",
            "output_contract_status": "valid" if healthy else "not_produced",
            "scoring_status": "scored" if healthy else "not_scored",
            "failure_type": None if healthy else "provider_error",
        },
    }


def test_store_selects_missing_then_never_reselects_completed(tmp_path: Path) -> None:
    manifest = _manifest()
    store = LocalRunStore(
        tmp_path / str(manifest["run_id"]), run_id=str(manifest["run_id"])
    )
    store.initialize(manifest)  # type: ignore[arg-type]

    assert len(store.select_work_items(mode="missing")) == 1
    store.commit_attempt(_attempt_record(manifest))  # type: ignore[arg-type]
    assert store.select_work_items(mode="missing") == ()
    assert store.select_work_items(mode="failed") == ()
    assert store.state_counts() == {
        "missing": 0,
        "completed": 1,
        "failed": 0,
        "cancelled": 0,
    }


def test_store_rejects_conflicting_immutable_generation(tmp_path: Path) -> None:
    manifest = _manifest()
    store = LocalRunStore(
        tmp_path / str(manifest["run_id"]), run_id=str(manifest["run_id"])
    )
    store.initialize(manifest)  # type: ignore[arg-type]
    record = _attempt_record(manifest, status="failed")
    store.commit_attempt(record)  # type: ignore[arg-type]
    conflicting = dict(record)
    conflicting["invocation_id"] = "inv_conflict"

    with pytest.raises(RunStoreIntegrityError, match="Conflicting immutable"):
        store.commit_attempt(conflicting)  # type: ignore[arg-type]


def test_manifest_validates_full_spec_hash(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["run_spec_sha256"] = canonical_sha256({"different": True})
    store = LocalRunStore(
        tmp_path / str(manifest["run_id"]), run_id=str(manifest["run_id"])
    )
    store.initialize(manifest)  # type: ignore[arg-type]

    with pytest.raises(RunStoreIntegrityError, match="identity is invalid"):
        store.read_manifest()


def test_manifest_rejects_removed_schema_v1_contract(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["schema_version"] = 1
    store = LocalRunStore(
        tmp_path / str(manifest["run_id"]), run_id=str(manifest["run_id"])
    )
    store.initialize(manifest)  # type: ignore[arg-type]

    with pytest.raises(RunStoreIntegrityError, match="identity is invalid"):
        store.read_manifest()


def test_store_allows_only_one_local_coordinator(tmp_path: Path) -> None:
    manifest = _manifest()
    run_dir = tmp_path / str(manifest["run_id"])
    first = LocalRunStore(run_dir, run_id=str(manifest["run_id"]))
    second = LocalRunStore(run_dir, run_id=str(manifest["run_id"]))
    first.initialize(manifest)  # type: ignore[arg-type]

    with first.coordinator_lock(invocation_id="inv_first"):
        with pytest.raises(RuntimeError, match="already active"):
            with second.coordinator_lock(invocation_id="inv_second"):
                pass


def test_execution_wall_time_excludes_no_op_and_includes_terminal_work(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    store = LocalRunStore(
        tmp_path / str(manifest["run_id"]), run_id=str(manifest["run_id"])
    )
    store.initialize(manifest)  # type: ignore[arg-type]
    store.write_invocation_event(
        invocation_id="inv_work",
        event="completed",
        payload={"duration_seconds": 2.5, "selected_work_items": 1},
    )
    store.write_invocation_event(
        invocation_id="inv_noop",
        event="completed",
        payload={"duration_seconds": 10.0, "selected_work_items": 0},
    )
    store.write_invocation_event(
        invocation_id="inv_interrupted",
        event="interrupted",
        payload={"duration_seconds": 0.5, "selected_work_items": 1},
    )

    assert store.execution_invocation_wall_time_seconds() == 3.0
