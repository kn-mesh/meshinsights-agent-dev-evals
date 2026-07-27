from __future__ import annotations

import ast
import fnmatch
import hashlib
import logging
from datetime import datetime
from pathlib import Path

from mi.core.registry.constants import REGISTRY_VERSION
from mi.core.registry.models import ComponentRecord, PipelineSettings, RegistryData
from mi.core.registry.utils import (
    parse_timestamp,
    find_project_venv,
    _get_venv_site_packages,
)

logger = logging.getLogger("meshinsights.registry")


def compute_component_hash(class_name: str, rel_path: str, line_number: int) -> str:
    payload = f"{class_name}:{rel_path}:{line_number}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def collect_python_files(root: Path, settings: PipelineSettings) -> list[Path]:
    discovered: set[Path] = set()
    for pattern in settings.scan_paths:
        for path in root.glob(pattern):
            if path.is_file() and path.suffix == ".py":
                rel = path.relative_to(root)
                rel_str = str(rel).replace("\\", "/")  # Normalize path separators
                if any(
                    fnmatch.fnmatch(rel_str, exclude)
                    for exclude in settings.exclude_paths
                ):
                    continue
                discovered.add(path.resolve())
    return sorted(discovered)


def collect_installed_mi_core_files(root: Path) -> list[Path]:
    """
    Gather mi package Python files from an installed package (e.g., venv site-packages).
    Used to decide whether the registry is stale when components are loaded from installed mi package.
    """
    venv_path = find_project_venv(root)
    if venv_path is None:
        return []
    site_packages = _get_venv_site_packages(venv_path)
    if site_packages is None:
        return []

    mi_path = site_packages / "mi"
    if not mi_path.exists() or not mi_path.is_dir():
        return []

    discovered: list[Path] = []
    for py_file in mi_path.rglob("*.py"):
        # Skip cache and tests to mirror scanner behavior
        if "__pycache__" in py_file.parts or "test" in py_file.name.lower():
            continue
        discovered.append(py_file.resolve())
    return discovered


def files_modified_after(files: list[Path], reference: datetime | None) -> bool:
    if reference is None:
        return True
    ref_ts = reference.timestamp()
    for file_path in files:
        try:
            if file_path.stat().st_mtime > ref_ts:
                return True
        except FileNotFoundError:
            return True
    return False


def _class_lines_for_file(path: Path) -> dict[str, int]:
    try:
        source = path.read_text()
        tree = ast.parse(source)
    except (OSError, SyntaxError) as exc:
        logger.warning("Unable to parse %s while validating registry: %s", path, exc)
        return {}
    mapping: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            mapping[node.name] = node.lineno
    return mapping


def has_hash_mismatch(registry: RegistryData, root: Path) -> bool:
    by_file: dict[str, list[ComponentRecord]] = {}
    for record in registry.all_records():
        by_file.setdefault(record.file_path, []).append(record)
    for rel_path, entries in by_file.items():
        absolute = (root / rel_path).resolve()
        if not absolute.exists():
            return True
        class_lines = _class_lines_for_file(absolute)
        if not class_lines:
            return True
        for record in entries:
            actual_line = class_lines.get(record.class_name)
            if actual_line is None:
                return True
            recalculated = compute_component_hash(
                record.class_name, record.file_path, actual_line
            )
            if recalculated != record.hash:
                return True
    return False


def should_rebuild_registry(
    registry: RegistryData | None,
    root: Path,
    settings: PipelineSettings,
    python_files: list[Path],
    *,
    config_file: Path | None = None,
    force: bool = False,
) -> bool:
    # Include installed mi package files when determining staleness, since the scanner
    # adds those components to the registry when available.
    python_files = python_files + collect_installed_mi_core_files(root)
    if force:
        return True
    if registry is None:
        return True
    if registry.version != REGISTRY_VERSION:
        return True
    last_scan_at = parse_timestamp(registry.last_scan)
    if files_modified_after(python_files, last_scan_at):
        return True
    if config_file is not None:
        try:
            config_mtime = config_file.stat().st_mtime
        except FileNotFoundError:
            return True
        if last_scan_at is None or config_mtime > last_scan_at.timestamp():
            return True
    if has_hash_mismatch(registry, root):
        return True
    return False
