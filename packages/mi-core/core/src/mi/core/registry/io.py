from __future__ import annotations

import json
import logging
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from mi.core.registry.constants import (
    DEFAULT_EXCLUDE_PATHS,
    DEFAULT_SCAN_PATHS,
    REGISTRY_FILE_NAME,
)
from mi.core.registry.models import PipelineSettings, RegistryData
from mi.core.registry.utils import locate_upwards

if TYPE_CHECKING:
    from mi.core.registry.schema import PipelineSchemaBuilder

logger = logging.getLogger("meshinsights.registry")


def load_pipeline_settings(
    config_path: Path | None = None,
    *,
    start: Path | None = None,
) -> tuple[PipelineSettings, Path]:
    base = (start or Path.cwd()).resolve()
    config_file = (
        Path(config_path).resolve()
        if config_path
        else locate_upwards("pyproject.toml", base)
    )
    if config_file is None:
        raise FileNotFoundError(
            "Unable to find pyproject.toml for pipeline configuration"
        )
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    with config_file.open("rb") as handle:
        data = tomllib.load(handle)

    raw_tool = data.get("tool", {})
    raw_config = raw_tool.get("meshinsights-pipeline", {})

    scan_paths = list(raw_config.get("scan_paths", DEFAULT_SCAN_PATHS))
    exclude_paths = list(raw_config.get("exclude_paths", DEFAULT_EXCLUDE_PATHS))
    auto_scan = bool(raw_config.get("auto_scan", True))
    registry_dir = str(raw_config.get("registry_dir", ".insights"))

    settings = PipelineSettings(
        scan_paths=scan_paths or DEFAULT_SCAN_PATHS.copy(),
        exclude_paths=exclude_paths or DEFAULT_EXCLUDE_PATHS.copy(),
        auto_scan=auto_scan,
        registry_dir=registry_dir or ".insights",
    )
    return settings, config_file


def ensure_registry_dir(root: Path, settings: PipelineSettings) -> Path:
    target = root / settings.registry_dir
    target.mkdir(parents=True, exist_ok=True)
    return target


def registry_path(root: Path, settings: PipelineSettings) -> Path:
    registry_dir = ensure_registry_dir(root, settings)
    return registry_dir / REGISTRY_FILE_NAME


def schema_path(root: Path, settings: PipelineSettings) -> Path:
    registry_dir = ensure_registry_dir(root, settings)
    schema_dir = registry_dir / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    return schema_dir / "pipeline_schema.json"


def load_registry(path: Path) -> RegistryData | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        logger.warning("Failed to decode registry at %s: %s", path, exc)
        return None
    return RegistryData.from_dict(data)


def save_registry(registry: RegistryData, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry.to_dict(), indent=2))


def prepare_registry_and_schema(
    project_root: Path,
    settings: PipelineSettings,
    config_file: Path,
    force_scan: bool,
) -> tuple[RegistryData, "PipelineSchemaBuilder"]:
    from mi.core.registry import (
        PipelineSchemaBuilder,
        RegistryScanner,
        collect_python_files,
        should_rebuild_registry,
        write_schema,
    )

    registry_file = registry_path(project_root, settings)
    existing = load_registry(registry_file)
    python_files = collect_python_files(project_root, settings)
    needs_scan = should_rebuild_registry(
        existing,
        project_root,
        settings,
        python_files,
        config_file=config_file,
        force=force_scan,
    )
    if needs_scan and not (settings.auto_scan or force_scan):
        raise RuntimeError(
            "Component registry is stale or missing and auto_scan is disabled. "
            "Run 'meshinsights-pipeline build-registry --force' to refresh."
        )
    if needs_scan:
        scanner = RegistryScanner(project_root, settings)
        registry = scanner.scan()
        save_registry(registry, registry_file)
        schema_builder = PipelineSchemaBuilder(registry, project_root)
        write_schema(schema_builder, schema_path(project_root, settings))
        return registry, schema_builder
    if existing is None:
        raise RuntimeError(
            "Component registry not found. Run 'meshinsights-pipeline build-registry' first."
        )
    schema_builder = PipelineSchemaBuilder(existing, project_root)
    schema_location = schema_path(project_root, settings)
    if not schema_location.exists():
        write_schema(schema_builder, schema_location)
    return existing, schema_builder
