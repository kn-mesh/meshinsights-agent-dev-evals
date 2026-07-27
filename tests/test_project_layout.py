"""Tests for the fixed Agent Workbench project-layout convention."""

from pathlib import Path

import pytest

from src.project_layout import (
    USE_CASE_DIRECTORIES,
    USE_CASE_ROOT,
    project_path,
)


def test_use_case_layout_is_fixed_and_has_no_overlapping_duplicates() -> None:
    assert USE_CASE_ROOT == "use_case"
    assert len(USE_CASE_DIRECTORIES) == len(set(USE_CASE_DIRECTORIES))
    assert all(path.startswith(f"{USE_CASE_ROOT}/") for path in USE_CASE_DIRECTORIES)


def test_project_path_resolves_inside_the_project_root(tmp_path: Path) -> None:
    assert project_path(tmp_path, "use_case/docs") == (
        tmp_path / "use_case/docs"
    ).resolve()

    with pytest.raises(ValueError, match="normalized and relative"):
        project_path(tmp_path, "../outside")
