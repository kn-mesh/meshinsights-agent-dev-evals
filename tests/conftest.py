"""Project test isolation from the developer's ambient Git worktree."""

from __future__ import annotations

import pytest

import src.agent_versions.resolver as agent_version_resolver


@pytest.fixture(autouse=True)
def isolate_agent_version_runtime_git_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep general tests independent of unrelated live worktree changes.

    Tests that exercise runtime-surface capture can override this injected
    boundary explicitly. Pipeline and declared asset dirtiness still uses real
    Git bytes and remains covered by dedicated repository fixtures.
    """
    monkeypatch.setattr(
        agent_version_resolver,
        "_dirty_runtime_paths",
        lambda root: (),
    )
