"""Machine-enforced reusable/use-case dependency boundaries."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.project_bootstrap.models import TemplateOwnershipManifest
from src.project_bootstrap.ownership import resolve_ownership


ROOT = Path(__file__).resolve().parents[1]
REUSABLE_OWNERS = {"reusable_library", "reusable_workbench"}
REFERENCE_TERMS = (
    "spirax",
    "steam trap",
    "steam-trap",
    "v1_3",
    "phase-1-benchmark-3fb7f544",
    "misprx",
)


def _manifest() -> TemplateOwnershipManifest:
    return TemplateOwnershipManifest.model_validate_json(
        (ROOT / "workbench.template.json").read_text(encoding="utf-8")
    )


def _production_files(suffixes: set[str]) -> tuple[Path, ...]:
    manifest = _manifest()
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or path.suffix not in suffixes
            or any(
                part
                in {
                    ".git",
                    ".venv",
                    "node_modules",
                    "dist",
                    "build",
                    "__pycache__",
                    "tests",
                }
                for part in path.parts
            )
        ):
            continue
        relative = path.relative_to(ROOT).as_posix()
        ownership = resolve_ownership(relative, manifest.ownership)
        if ownership is not None and ownership.owner in REUSABLE_OWNERS:
            files.append(path)
    return tuple(sorted(files))


def test_reusable_python_does_not_import_use_case() -> None:
    violations: list[str] = []
    for path in _production_files({".py"}):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                modules = (alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            else:
                continue
            for module in modules:
                if module == "use_case" or module.startswith("use_case."):
                    violations.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}:{module}"
                    )
    assert violations == []


def test_reusable_typescript_does_not_import_use_case() -> None:
    violations: list[str] = []
    for path in _production_files({".ts", ".tsx"}):
        content = path.read_text(encoding="utf-8")
        if "@use-case/" in content or "use_case/" in content:
            violations.append(path.relative_to(ROOT).as_posix())
    assert violations == []


def test_reusable_production_contains_no_reference_identity() -> None:
    violations: dict[str, list[str]] = {}
    for path in _production_files(
        {".py", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml"}
    ):
        content = path.read_text(encoding="utf-8").lower()
        matches = [term for term in REFERENCE_TERMS if term in content]
        if matches:
            violations[path.relative_to(ROOT).as_posix()] = matches
    assert violations == {}


def test_manifest_has_one_reference_root_and_one_clear_root() -> None:
    payload = json.loads((ROOT / "workbench.template.json").read_text(encoding="utf-8"))
    reference_paths = [
        item["path"]
        for item in payload["ownership"]
        if item["owner"] == "reference_use_case"
    ]
    assert reference_paths == ["use_case"]
    assert payload["reference_reset"]["clear_directories"] == ["use_case"]
