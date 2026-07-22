"""Prevent removed eval-schema contracts from returning to active guidance."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "EvalRunbook.md",
    *sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")),
)
REMOVED_CONTRACTS = (
    "run_config",
    "summary.performance",
    "summary.retries",
    "results[].runs[].fields",
)


@pytest.mark.parametrize("path", OPERATOR_DOCUMENTS, ids=lambda path: path.name)
def test_active_operator_document_uses_only_schema_v1_contracts(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    found = [contract for contract in REMOVED_CONTRACTS if contract in content]
    assert not found, f"{path.relative_to(ROOT)} contains removed contracts: {found}"


def test_eval_skills_cover_current_artifact_boundaries() -> None:
    run_skill = (
        ROOT / ".agents" / "skills" / "run-use-case-evals" / "SKILL.md"
    ).read_text(encoding="utf-8")
    analysis_skill = (
        ROOT / ".agents" / "skills" / "eval-results-analysis" / "SKILL.md"
    ).read_text(encoding="utf-8")

    for required in ("`run`", "`run.dimensions`", "`performance/summary.json`"):
        assert required in run_skill
    for required in (
        "LocalRunStore.evaluation_rows()",
        "`agent_output`",
        "`evaluations`",
        "`performance/summary.json`",
        "`capture_failed`",
    ):
        assert required in analysis_skill


def test_runbook_explicit_eval_flags_match_current_cli_help() -> None:
    runbook = (ROOT / "EvalRunbook.md").read_text(encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "src.evals.eval_orchestration", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    required_flags = (
        "--evaluation-profile",
        "--project-key",
        "--azure-postgres-host",
        "--azure-postgres-database",
        "--azure-postgres-user",
        "--azure-storage-account-url",
        "--azure-storage-container",
        "--benchmark-key",
        "--benchmark-version",
        "--all-examples",
        "--example-ids",
        "--ai-model",
        "--ai-reasoning-effort",
        "--runs-per-example",
        "--runtime",
        "--max-workers",
        "--error-action",
        "--review-capture",
    )
    for flag in required_flags:
        assert flag in runbook
        assert flag in completed.stdout
