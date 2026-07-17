#!/usr/bin/env python3
"""Update and extract changelog entries."""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"
REPO_URL = "https://github.com/Mesh-Systems-Eng/mesh.insights.core"


def display_path(path: Path) -> Path:
    """Return a readable path for log messages."""
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path


def today_utc() -> date:
    """Return today's UTC date."""
    return datetime.now(timezone.utc).date()


def update_changelog(
    new_version: str,
    prev_version: str,
    *,
    changelog_file: Path = CHANGELOG_FILE,
    repo_url: str = REPO_URL,
    release_date: date | None = None,
) -> bool:
    """Rename [Unreleased] to a release entry and refresh link refs."""
    if not changelog_file.exists():
        print(f"  Warning: {display_path(changelog_file)} not found, skipping")
        return False

    content = changelog_file.read_text()
    stamp = (release_date or today_utc()).strftime("%Y-%m-%d")

    unreleased_header_re = re.compile(r"^## \[Unreleased\].*$", re.MULTILINE)
    if not unreleased_header_re.search(content):
        print("  Warning: no [Unreleased] section found in CHANGELOG.md, skipping")
        return False

    new_header = f"## [Unreleased]\n\n## [{new_version}] - {stamp}"
    new_content = unreleased_header_re.sub(new_header, content, count=1)

    existing_version_link_re = re.compile(
        rf"^\[{re.escape(new_version)}\]: .+\n?", re.MULTILINE
    )
    new_content = existing_version_link_re.sub("", new_content)

    unreleased_link_re = re.compile(r"^\[Unreleased\]: .+$", re.MULTILINE)
    new_links = (
        f"[Unreleased]: {repo_url}/compare/v{new_version}...HEAD\n"
        f"[{new_version}]: {repo_url}/compare/v{prev_version}...v{new_version}"
    )
    new_content = unreleased_link_re.sub(new_links, new_content, count=1)

    if new_content == content:
        return False

    changelog_file.write_text(new_content)
    print(f"  Updated {display_path(changelog_file)}")
    return True


def extract_changelog(version: str, *, changelog_file: Path = CHANGELOG_FILE) -> str:
    """Extract the body for a specific release version."""
    if not changelog_file.exists():
        print(f"Error: {display_path(changelog_file)} not found", file=sys.stderr)
        raise SystemExit(1)

    content = changelog_file.read_text()
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        print(f"Error: no changelog entry found for version {version}", file=sys.stderr)
        raise SystemExit(1)

    return match.group(1).strip()


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage:\n"
            "  python scripts/changelog.py update <new_version> <prev_version>\n"
            "  python scripts/changelog.py extract <version>",
            file=sys.stderr,
        )
        raise SystemExit(1)

    command = sys.argv[1]
    if command == "update":
        if len(sys.argv) != 4:
            print(
                "Usage: python scripts/changelog.py update <new_version> <prev_version>",
                file=sys.stderr,
            )
            raise SystemExit(1)
        update_changelog(sys.argv[2], sys.argv[3])
        return

    if command == "extract":
        if len(sys.argv) != 3:
            print(
                "Usage: python scripts/changelog.py extract <version>", file=sys.stderr
            )
            raise SystemExit(1)
        print(extract_changelog(sys.argv[2]))
        return

    print(f"Unknown command: {command}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
