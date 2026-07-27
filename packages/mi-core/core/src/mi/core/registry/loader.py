from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mi.core.registry.constants import COMPONENT_TYPES
from mi.core.registry.models import ComponentRecord, RegistryData
from mi.core.registry.utils import import_symbol


def build_registry_index(
    registry: RegistryData,
) -> dict[str, dict[str, ComponentRecord]]:
    index: dict[str, dict[str, ComponentRecord]] = {
        section: {} for section in COMPONENT_TYPES
    }
    for section, records in registry.components.items():
        index.setdefault(section, {})
        for record in records:
            index[section][record.name] = record
    return index


def get_record(
    section: str,
    name: str,
    index: dict[str, dict[str, ComponentRecord]],
) -> ComponentRecord:
    record = index.get(section, {}).get(name)
    if record is None:
        raise ValueError(
            f"Component '{name}' not found in registry section '{section}'"
        )
    return record


def load_data_object_type(
    section: str,
    component_name: str,
    index: dict[str, dict[str, ComponentRecord]],
    project_root: Path,
    *,
    expected_cls: type[Any],
) -> type[Any]:
    record = get_record(section, component_name, index)
    cls = import_symbol(record.import_path, project_root)
    if not issubclass(cls, expected_cls):
        raise ValueError(
            f"Component '{record.name}' does not implement {expected_cls.__name__}"
        )
    return cls


def load_metadata_type(
    component_name: str,
    index: dict[str, dict[str, ComponentRecord]],
    project_root: Path,
) -> type[Any]:
    """Load a metadata type class from the registry.

    Args:
        component_name: Name of the metadata type class in the registry.
        index: Registry index built from build_registry_index().
        project_root: Root path of the project.

    Returns:
        The metadata type class.

    Raises:
        ValueError: If the component is not found or doesn't inherit from PipelineMetadata.
    """
    from mi.core.pipeline import PipelineMetadata

    record = get_record("metadata_types", component_name, index)
    cls = import_symbol(record.import_path, project_root)
    if not issubclass(cls, PipelineMetadata):
        raise ValueError(
            f"Component '{record.name}' does not inherit from PipelineMetadata"
        )
    return cls


def instantiate_component(
    record: ComponentRecord,
    project_root: Path,
    config_value: Any = None,
    *,
    config_type: type[Any] | None = None,
) -> Any:
    component_cls = import_symbol(record.import_path, project_root)
    if config_type is not None:
        if config_value is None:
            return component_cls(config_type())
        if isinstance(config_value, config_type):
            return component_cls(config_value)
        if isinstance(config_value, BaseModel):
            return component_cls(config_type(**config_value.model_dump()))
        if isinstance(config_value, dict):
            return component_cls(config_type(**config_value))
        return component_cls(config_value)
    if config_value is None:
        return component_cls()
    if isinstance(config_value, BaseModel):
        payload = config_value.model_dump()
        return component_cls(**payload)
    if isinstance(config_value, dict):
        return component_cls(**config_value)
    return component_cls(config_value)
