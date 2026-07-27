"""Reusable CLI checks for fail-closed hosted identity validation."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest

from workbench.evals import eval_orchestration


ROOT = Path(__file__).resolve().parents[2]


def test_eval_cli_rejects_identity_mismatch_before_catalog_or_run_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = json.loads((ROOT / "workbench.project.json").read_text())
    studio = project["benchmark_studio"]
    benchmark = project["benchmarks"]["default"]
    called = False
    before = {
        path.relative_to(ROOT / ".workbench/evals")
        for path in (ROOT / ".workbench/evals").rglob("*")
    }

    def fail_if_called(**_: Any) -> Any:
        nonlocal called
        called = True
        raise AssertionError("benchmark catalog access must follow identity validation")

    monkeypatch.setattr(eval_orchestration, "bootstrap_environment", lambda: None)
    monkeypatch.setattr(
        eval_orchestration,
        "AzurePostgresBenchmarkRepository",
        fail_if_called,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "eval-orchestration",
            "use_case/pipeline_configs/v1_3.ppln",
            "--evaluation-profile",
            "use_case/evaluation_configs/spirax-failure-evaluation.eval.yaml",
            "--project-key",
            studio["project_key"],
            "--azure-postgres-host",
            studio["postgres_host"],
            "--azure-postgres-database",
            studio["postgres_database"],
            "--azure-postgres-user",
            "operator@example.com",
            "--azure-storage-account-url",
            "https://other.blob.core.windows.net",
            "--azure-storage-container",
            studio["storage_container"],
            "--benchmark-key",
            benchmark["key"],
            "--benchmark-version",
            benchmark["version"],
            "--all-examples",
            "--ai-model",
            project["model_catalog"]["default_model"],
            "--ai-reasoning-effort",
            "medium",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        eval_orchestration.main()

    after = {
        path.relative_to(ROOT / ".workbench/evals")
        for path in (ROOT / ".workbench/evals").rglob("*")
    }
    assert raised.value.code == 2
    assert called is False
    assert after == before
