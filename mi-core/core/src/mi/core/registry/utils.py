from __future__ import annotations

import importlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mi.core.registry.constants import REGISTRY_VERSION

__all__ = [
    "REGISTRY_VERSION",
    "_now_utc",
    "iso_timestamp",
    "parse_timestamp",
    "locate_upwards",
    "find_project_root",
    "ensure_sys_path",
    "import_symbol",
    "find_project_venv",
]


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc).replace(microsecond=0)


def iso_timestamp(dt: datetime | None = None) -> str:
    current = dt or _now_utc()
    return current.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        cleaned = value.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def locate_upwards(name: str, start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        target = candidate / name
        if target.exists():
            return target
    return None


def _is_valid_venv_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    if (path / "pyvenv.cfg").exists():
        return True
    activate = (
        path / ("Scripts" if platform.system() == "Windows" else "bin") / "activate"
    )
    return activate.exists()


def find_project_root(start: Path | None = None) -> Path:
    """
    Find the most appropriate project root starting from `start` (or cwd).

    Preference order:
    1) First ancestor containing .insights
    2) First ancestor containing a venv directory
    3) Topmost ancestor containing pyproject.toml
    4) Fallback to the starting directory

    TODO: consider richer multi-workspace heuristics (e.g., dedicated root markers).
    """

    base = (start or Path.cwd()).resolve()
    candidates = (base, *base.parents)
    topmost_pyproject: Path | None = None

    for candidate in candidates:
        if (candidate / "pyproject.toml").exists():
            topmost_pyproject = candidate
        if (candidate / ".insights").exists():
            return candidate
        for venv_name in (".venv", "venv", "env"):
            if _is_valid_venv_dir(candidate / venv_name):
                return candidate

    if topmost_pyproject is not None:
        return topmost_pyproject
    return base


def find_project_venv(start: Path) -> Path | None:
    """Search upward from start for the nearest virtual environment directory."""
    current = start.resolve()
    for candidate in (current, *current.parents):
        for venv_name in (".venv", "venv", "env"):
            venv_path = candidate / venv_name
            if _is_valid_venv_dir(venv_path):
                return venv_path
    return None


def _get_venv_site_packages(venv_path: Path) -> Path | None:
    venv_path = venv_path.resolve()
    python_versions: list[str] = []

    # Prefer the version recorded in the venv itself, fall back to the running interpreter.
    pyvenv_cfg = venv_path / "pyvenv.cfg"
    if pyvenv_cfg.exists():
        for line in pyvenv_cfg.read_text().splitlines():
            if line.startswith(("version_info", "version")):
                _, _, raw = line.partition("=")
                raw = raw.strip()
                if raw:
                    parts = raw.split(".")
                    if len(parts) >= 2:
                        python_versions.append(f"{parts[0]}.{parts[1]}")
                        break
    python_versions.append(f"{sys.version_info.major}.{sys.version_info.minor}")

    lib_dirs = ["Lib"] if platform.system() == "Windows" else ["lib", "lib64"]

    # First try explicit versioned paths
    for version in python_versions:
        for lib_dir in lib_dirs:
            candidate = venv_path / lib_dir / f"python{version}" / "site-packages"
            if candidate.exists():
                return candidate

    # Fallback: pick the first site-packages directory we can find
    for lib_dir in lib_dirs:
        for candidate in (venv_path / lib_dir).glob("python*/site-packages"):
            if candidate.exists():
                return candidate

    return None


def ensure_sys_path(root: Path) -> None:
    root_str = str(root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    # Try to find and add the project's virtual environment
    venv_path = find_project_venv(root)
    if venv_path is not None:
        site_packages = _get_venv_site_packages(venv_path)
        if site_packages is not None:
            site_packages_str = str(site_packages.resolve())
            if site_packages_str not in sys.path:
                # Insert after project root but before other paths
                try:
                    root_index = sys.path.index(root_str)
                    sys.path.insert(root_index + 1, site_packages_str)
                except ValueError:
                    # Root not in path (shouldn't happen, but be safe)
                    sys.path.insert(1, site_packages_str)


def import_symbol(import_path: str, root: Path) -> Any:
    ensure_sys_path(root)
    module_name, _, attr = import_path.rpartition(".")
    if not module_name:
        raise ImportError(f"Invalid import path: {import_path}")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ImportError(f"Unable to load {import_path}") from exc
