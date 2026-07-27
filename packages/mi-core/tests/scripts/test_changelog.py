from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import changelog


CHANGELOG_TEMPLATE = """# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New feature

## [0.5.0] - 2026-03-17
### Fixed
- Previous fix

[Unreleased]: https://github.com/example/repo/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/example/repo/compare/v0.4.0...v0.5.0
"""


def write_changelog(path: Path) -> Path:
    path.write_text(CHANGELOG_TEMPLATE)
    return path


def test_update_changelog_rotates_unreleased_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog_path = write_changelog(tmp_path / "CHANGELOG.md")

    updated = changelog.update_changelog(
        "0.5.1",
        "0.5.0",
        changelog_file=changelog_path,
        repo_url="https://github.com/example/repo",
        release_date=date(2026, 3, 18),
    )

    assert updated is True
    content = changelog_path.read_text()
    assert "## [Unreleased]\n\n## [0.5.1] - 2026-03-18" in content
    assert (
        "[Unreleased]: https://github.com/example/repo/compare/v0.5.1...HEAD" in content
    )
    assert "[0.5.1]: https://github.com/example/repo/compare/v0.5.0...v0.5.1" in content
    assert capsys.readouterr().out.strip().endswith(f"Updated {changelog_path}")


def test_update_changelog_removes_duplicate_link_for_new_version(
    tmp_path: Path,
) -> None:
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        CHANGELOG_TEMPLATE
        + "[0.5.1]: https://github.com/example/repo/compare/v0.5.0...v0.5.1\n"
    )

    changelog.update_changelog(
        "0.5.1",
        "0.5.0",
        changelog_file=changelog_path,
        repo_url="https://github.com/example/repo",
        release_date=date(2026, 3, 18),
    )

    assert changelog_path.read_text().count("[0.5.1]:") == 1


def test_extract_changelog_returns_release_body(tmp_path: Path) -> None:
    changelog_path = write_changelog(tmp_path / "CHANGELOG.md")

    body = changelog.extract_changelog("0.5.0", changelog_file=changelog_path)

    assert (
        body
        == "### Fixed\n- Previous fix\n\n[Unreleased]: https://github.com/example/repo/compare/v0.5.0...HEAD\n[0.5.0]: https://github.com/example/repo/compare/v0.4.0...v0.5.0"
    )


def test_extract_changelog_errors_for_missing_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    changelog_path = write_changelog(tmp_path / "CHANGELOG.md")

    with pytest.raises(SystemExit):
        changelog.extract_changelog("9.9.9", changelog_file=changelog_path)

    assert "no changelog entry found for version 9.9.9" in capsys.readouterr().err
