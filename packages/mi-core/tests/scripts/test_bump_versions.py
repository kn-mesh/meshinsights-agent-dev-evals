from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import bump_versions
from scripts import changelog


def make_repo(tmp_path: Path) -> dict[str, Path]:
    core_pyproject = tmp_path / "core" / "pyproject.toml"
    cli_pyproject = tmp_path / "cli" / "pyproject.toml"
    telemetry = tmp_path / "core" / "src" / "mi" / "core" / "utils" / "telemetry.py"
    changelog_file = tmp_path / "CHANGELOG.md"

    core_pyproject.parent.mkdir(parents=True)
    cli_pyproject.parent.mkdir(parents=True)
    telemetry.parent.mkdir(parents=True)

    core_pyproject.write_text('[project]\nname = "mi-core"\nversion = "0.5.0"\n')
    cli_pyproject.write_text(
        '[project]\nname = "meshinsights-cli"\nversion = "0.5.0"\ndependencies = [\n    "mi-core==0.5.0",\n]\n'
    )
    telemetry.write_text('resource = {SERVICE_VERSION: "0.5.0"}\n')
    changelog_file.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- Something new\n\n"
        "## [0.5.0] - 2026-03-17\n### Fixed\n- Something old\n\n"
        "[Unreleased]: https://github.com/example/repo/compare/v0.5.0...HEAD\n"
        "[0.5.0]: https://github.com/example/repo/compare/v0.4.0...v0.5.0\n"
    )

    return {
        "core": core_pyproject,
        "cli": cli_pyproject,
        "telemetry": telemetry,
        "changelog": changelog_file,
    }


def patch_repo(monkeypatch: pytest.MonkeyPatch, files: dict[str, Path]) -> None:
    repo_root = files["changelog"].parent
    monkeypatch.setattr(bump_versions, "REPO_ROOT", repo_root)
    monkeypatch.setattr(bump_versions, "PYPROJECT_FILES", [files["core"], files["cli"]])
    monkeypatch.setattr(bump_versions, "TELEMETRY_FILE", files["telemetry"])


def test_cmd_bump_updates_versions_and_changelog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = make_repo(tmp_path)
    patch_repo(monkeypatch, files)

    def fake_update(new_version: str, prev_version: str) -> bool:
        return changelog.update_changelog(
            new_version,
            prev_version,
            changelog_file=files["changelog"],
            repo_url="https://github.com/example/repo",
            release_date=date(2026, 3, 18),
        )

    monkeypatch.setattr(bump_versions, "update_changelog", fake_update)

    bump_versions.cmd_bump("patch")

    assert 'version = "0.5.1"' in files["core"].read_text()
    assert 'version = "0.5.1"' in files["cli"].read_text()
    assert "mi-core==0.5.1" in files["cli"].read_text()
    assert 'SERVICE_VERSION: "0.5.1"' in files["telemetry"].read_text()
    assert "## [0.5.1] - 2026-03-18" in files["changelog"].read_text()
    assert "NEW_VERSION=0.5.1" in capsys.readouterr().out


def test_parse_version_accepts_prerelease_suffix() -> None:
    assert bump_versions.parse_version("0.5.0a") == (0, 5, 0)


def test_parse_version_rejects_invalid_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        bump_versions.parse_version("bogus")

    assert "cannot parse version 'bogus'" in capsys.readouterr().err


def test_main_requires_known_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(bump_versions.sys, "argv", ["bump_versions.py", "changelog"])

    with pytest.raises(SystemExit):
        bump_versions.main()

    assert "Unknown command: changelog" in capsys.readouterr().err
