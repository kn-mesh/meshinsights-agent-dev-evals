"""Resolved reproducibility specifications for evaluation runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any, Iterable

from evaluation import canonical_sha256


_SOURCE_GLOBS = (
    "src/**/*.py",
    "use_case/**/*.py",
    "use_case/**/*.ppln",
    "use_case/**/*.yaml",
    "agent-dev-eval-core/evaluation/*.py",
    "mi-core/core/src/mi/**/*.py",
)
_SOURCE_FILES = (
    "model_catalog.py",
    "model_pricing.yaml",
    "models.yaml",
    "pyproject.toml",
    "uv.lock",
)


def repository_root(start: Path | None = None) -> Path:
    """Resolve the repository root without making Git a hard dependency."""
    base = (start or Path.cwd()).resolve()
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=base,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return base
    return Path(result.stdout.strip()).resolve()


def build_source_manifest(
    *,
    root: Path,
    required_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    """Hash conservative execution-relevant source content, including dirty files."""
    root = root.resolve()
    paths: set[Path] = set()
    for pattern in _SOURCE_GLOBS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    for relative in _SOURCE_FILES:
        path = root / relative
        if path.is_file():
            paths.add(path)
    for raw_path in required_paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        if not path.is_file():
            raise ValueError(f"Execution-relevant source file does not exist: {path}")
        paths.add(path.resolve())

    entries = []
    for path in sorted(paths):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError(
                f"Execution-relevant file is outside the repository: {path}"
            ) from error
        content = path.read_bytes()
        entries.append(
            {
                "path": relative,
                "byte_size": len(content),
                "content_sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "files": entries,
    }
    manifest["content_sha256"] = canonical_sha256(manifest)
    manifest.update(_git_identity(root))
    return manifest


def _git_identity(root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {"git_revision": None, "source_tree_state": "unavailable"}
    return {
        "git_revision": revision or None,
        "source_tree_state": "dirty" if status.strip() else "clean",
    }
