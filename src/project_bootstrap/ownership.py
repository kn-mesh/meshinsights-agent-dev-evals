"""Resolve effective template ownership through longest-prefix matching."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath

from src.project_bootstrap.models import (
    OwnershipEntry,
    TemplateOwnershipManifest,
    _relative_template_path,
)


def resolve_ownership(
    relative_path: str,
    entries: Iterable[OwnershipEntry],
) -> OwnershipEntry | None:
    """Return the most-specific owner for one normalized repository path."""
    normalized = _relative_template_path(relative_path)
    path = PurePosixPath(normalized)
    matches = [
        entry
        for entry in entries
        if path == PurePosixPath(entry.path)
        or PurePosixPath(entry.path) in path.parents
    ]
    if not matches:
        return None
    return max(matches, key=lambda entry: len(PurePosixPath(entry.path).parts))


def unowned_paths(
    relative_paths: Iterable[str],
    manifest: TemplateOwnershipManifest,
) -> tuple[str, ...]:
    """Return sorted repository paths without an effective manifest owner."""
    return tuple(
        sorted(
            path
            for path in relative_paths
            if resolve_ownership(path, manifest.ownership) is None
        )
    )
