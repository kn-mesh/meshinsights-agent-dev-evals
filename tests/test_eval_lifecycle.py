"""Focused contracts for the supported working/retained eval lifecycle."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess

import pytest

from src.agent_versions.models import AgentVersionManifest
from src.eval_lifecycle.cli import _parser
from src.eval_lifecycle.service import EvalLifecycleError, EvalLifecycleService
from src.evals.inspection import find_run_directory


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def test_cli_exposes_only_supported_permanent_lifecycle_commands() -> None:
    parser = _parser()
    commands = next(
        action.choices
        for action in parser._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)
    )

    assert set(commands) == {"list", "inspect", "elevate", "verify", "delete"}


def test_inspection_resolves_new_working_and_legacy_run_layouts(
    tmp_path: Path,
) -> None:
    run_id = "eval_" + "a" * 24
    working = tmp_path / "working/benchmark/v1" / run_id
    working.mkdir(parents=True)
    (working / "manifest.json").write_text("{}\n", encoding="utf-8")

    assert find_run_directory(run_id, root=tmp_path) == working.resolve()

    legacy_id = "eval_" + "b" * 24
    legacy = tmp_path / "pipeline/benchmark/v1/runs" / legacy_id
    legacy.mkdir(parents=True)
    (legacy / "manifest.json").write_text("{}\n", encoding="utf-8")

    assert find_run_directory(legacy_id, root=tmp_path) == legacy.resolve()


def test_agent_patch_preserves_tracked_and_relevant_untracked_text(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "eval-lifecycle@example.com")
    _git(tmp_path, "config", "user.name", "Eval Lifecycle Test")
    tracked = tmp_path / "src/agent.py"
    tracked.parent.mkdir()
    tracked.write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "src/agent.py")
    _git(tmp_path, "commit", "-m", "base")
    revision = _git(tmp_path, "rev-parse", "HEAD")

    tracked_content = b"VALUE = 2\n"
    untracked_content = b"NEW_VALUE = 3\n"
    run_dir = tmp_path / "eval_results/working/benchmark/v1" / ("eval_" + "c" * 24)
    entries = []
    for relative, content in (
        ("src/agent.py", tracked_content),
        ("src/new_agent.py", untracked_content),
    ):
        digest = hashlib.sha256(content).hexdigest()
        object_path = run_dir / "objects/sha256" / digest[:2] / digest
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(content)
        entries.append(
            {
                "path": relative,
                "operation": "modify" if relative == "src/agent.py" else "add",
                "content_sha256": digest,
            }
        )
    manifest = AgentVersionManifest.build(
        {
            "source": {
                "git_revision": revision,
                "tree_state": "dirty",
                "dirty_overlay": {"entries": entries},
            }
        }
    )

    patch = EvalLifecycleService(tmp_path)._agent_patch(  # noqa: SLF001
        run_dir,
        candidate=manifest,
    )

    assert patch is not None
    assert "--- a/src/agent.py" in patch
    assert "+++ b/src/agent.py" in patch
    assert "-VALUE = 1" in patch
    assert "+VALUE = 2" in patch
    assert "--- /dev/null" in patch
    assert "+++ b/src/new_agent.py" in patch
    assert "+NEW_VALUE = 3" in patch


def test_clean_agent_has_no_patch(tmp_path: Path) -> None:
    manifest = AgentVersionManifest.build(
        {
            "source": {
                "git_revision": None,
                "tree_state": "clean",
                "dirty_overlay": None,
            }
        }
    )

    assert (
        EvalLifecycleService(tmp_path)._agent_patch(  # noqa: SLF001
            tmp_path,
            candidate=manifest,
        )
        is None
    )


def test_retained_delete_requires_exact_repeated_identity(tmp_path: Path) -> None:
    service = EvalLifecycleService(tmp_path)

    with pytest.raises(EvalLifecycleError, match="exact retained eval ID"):
        service.delete_retained(
            "ret_" + "a" * 24,
            confirmation="ret_" + "b" * 24,
        )
