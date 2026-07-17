#!/usr/bin/env python3
"""Bump the unified version across all monorepo packages."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from changelog import update_changelog
except ImportError:  # pragma: no cover - used when imported as a package in tests
    from scripts.changelog import update_changelog

REPO_ROOT = Path(__file__).resolve().parent.parent

PYPROJECT_FILES = [
    REPO_ROOT / "core" / "pyproject.toml",
    REPO_ROOT / "cli" / "pyproject.toml",
]

TELEMETRY_FILE = REPO_ROOT / "core" / "src" / "mi" / "core" / "utils" / "telemetry.py"

VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
MI_CORE_DEP_RE = re.compile(r'("mi-core)==([^"]+)(")', re.MULTILINE)
SERVICE_VERSION_RE = re.compile(r'(SERVICE_VERSION:\s*")([^"]+)(")')


def display_path(path: Path) -> Path:
    """Return a readable path for log messages."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a semver string and ignore prerelease suffixes."""
    clean = re.match(r"(\d+\.\d+\.\d+)", version_str)
    if not clean:
        print(f"Error: cannot parse version '{version_str}'", file=sys.stderr)
        raise SystemExit(1)
    major, minor, patch = clean.group(1).split(".")
    return int(major), int(minor), int(patch)


def bump_version(major: int, minor: int, patch: int, bump_type: str) -> str:
    """Return the bumped version string."""
    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    if bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    print(f"Error: unknown bump type '{bump_type}'", file=sys.stderr)
    raise SystemExit(1)


def get_current_version() -> str:
    """Read the current version from core/pyproject.toml."""
    content = PYPROJECT_FILES[0].read_text()
    match = VERSION_RE.search(content)
    if not match:
        print("Error: could not find version in core/pyproject.toml", file=sys.stderr)
        raise SystemExit(1)
    return match.group(2)


def update_pyproject(path: Path, new_version: str) -> None:
    """Update the version field in a pyproject.toml file."""
    content = path.read_text()
    new_content = VERSION_RE.sub(rf"\g<1>{new_version}\3", content, count=1)
    new_content = MI_CORE_DEP_RE.sub(rf"\g<1>=={new_version}\3", new_content)

    if new_content != content:
        path.write_text(new_content)
        print(f"  Updated {display_path(path)}")


def update_telemetry(new_version: str) -> None:
    """Update the SERVICE_VERSION in telemetry.py."""
    if not TELEMETRY_FILE.exists():
        print(f"  Warning: {display_path(TELEMETRY_FILE)} not found, skipping")
        return

    content = TELEMETRY_FILE.read_text()
    new_content = SERVICE_VERSION_RE.sub(rf"\g<1>{new_version}\3", content)

    if new_content != content:
        TELEMETRY_FILE.write_text(new_content)
        print(f"  Updated {display_path(TELEMETRY_FILE)}")


def cmd_bump(bump_type: str) -> None:
    """Execute the bump subcommand."""
    current = get_current_version()
    major, minor, patch = parse_version(current)
    new_version = bump_version(major, minor, patch, bump_type)

    print(f"Bumping version: {current} -> {new_version} ({bump_type})")

    for pyproject in PYPROJECT_FILES:
        update_pyproject(pyproject, new_version)

    update_telemetry(new_version)
    update_changelog(new_version, prev_version=current)
    print(f"NEW_VERSION={new_version}")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage:\n  python scripts/bump_versions.py bump <patch|minor|major>",
            file=sys.stderr,
        )
        raise SystemExit(1)

    command = sys.argv[1]
    if command in ("patch", "minor", "major"):
        cmd_bump(command)
        return

    if command == "bump":
        if len(sys.argv) != 3 or sys.argv[2] not in ("patch", "minor", "major"):
            print(
                "Usage: python scripts/bump_versions.py bump <patch|minor|major>",
                file=sys.stderr,
            )
            raise SystemExit(1)
        cmd_bump(sys.argv[2])
        return

    print(f"Unknown command: {command}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
