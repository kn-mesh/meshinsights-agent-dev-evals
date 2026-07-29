"""Explorer contracts for permanent bulk deletion of working evals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from agent_eval_ui import create_app
from workbench.apps.eval_explorer import ProjectExplorerBackend


class _Lifecycle:
    def __init__(self, states: dict[str, str]) -> None:
        self.states = states
        self.deleted: list[str] = []

    def inspect(self, run_id: str) -> dict[str, str]:
        return {"run_id": run_id, "lifecycle_state": self.states[run_id]}

    def delete_working(self, run_id: str, *, confirmed: bool) -> dict[str, Any]:
        assert confirmed is True
        self.deleted.append(run_id)
        return {
            "entity_id": run_id,
            "files_deleted": 3,
            "bytes_deleted": 12,
        }


def _backend(lifecycle: _Lifecycle) -> ProjectExplorerBackend:
    backend = object.__new__(ProjectExplorerBackend)
    backend.project_root = Path.cwd()
    backend.lifecycle = lifecycle
    return backend


def test_bulk_delete_prevalidates_every_run_before_removing_files() -> None:
    lifecycle = _Lifecycle({"eval_working": "working", "ret_elevated": "retained"})

    with pytest.raises(ValueError, match="Only not elevated evals"):
        _backend(lifecycle).delete_runs(["eval_working", "ret_elevated"])

    assert lifecycle.deleted == []


def test_bulk_delete_deduplicates_ids_and_aggregates_removed_files() -> None:
    lifecycle = _Lifecycle({"eval_a": "working", "eval_b": "working"})

    result = _backend(lifecycle).delete_runs(["eval_a", "eval_a", "eval_b"])

    assert lifecycle.deleted == ["eval_a", "eval_b"]
    assert result["runs_deleted"] == 2
    assert result["files_deleted"] == 6
    assert result["bytes_deleted"] == 24
    assert result["recoverable"] is False


def test_delete_runs_api_requires_a_nonempty_selection() -> None:
    class Backend:
        def delete_runs(self, run_ids: list[str]) -> dict[str, Any]:
            return {"run_ids": run_ids}

    client = TestClient(create_app(backend=Backend()))  # type: ignore[arg-type]

    response = client.request("DELETE", "/api/runs", json={"run_ids": []})

    assert response.status_code == 422


def test_delete_runs_api_passes_exact_ids_to_backend() -> None:
    class Backend:
        def delete_runs(self, run_ids: list[str]) -> dict[str, Any]:
            return {"run_ids": run_ids}

    client = TestClient(create_app(backend=Backend()))  # type: ignore[arg-type]

    response = client.request(
        "DELETE",
        "/api/runs",
        json={"run_ids": ["eval_" + "a" * 24, "eval_" + "b" * 24]},
    )

    assert response.status_code == 200
    assert response.json()["run_ids"] == [
        "eval_" + "a" * 24,
        "eval_" + "b" * 24,
    ]
