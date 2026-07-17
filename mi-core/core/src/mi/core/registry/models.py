from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mi.core.registry.constants import (
    COMPONENT_TYPES,
    DEFAULT_EXCLUDE_PATHS,
    DEFAULT_SCAN_PATHS,
    REGISTRY_VERSION,
)
from mi.core.registry.utils import iso_timestamp


@dataclass
class PipelineSettings:
    scan_paths: list[str] = field(default_factory=lambda: DEFAULT_SCAN_PATHS.copy())
    exclude_paths: list[str] = field(
        default_factory=lambda: DEFAULT_EXCLUDE_PATHS.copy()
    )
    auto_scan: bool = True
    registry_dir: str = ".insights"


@dataclass
class ComponentRecord:
    name: str
    import_path: str
    file_path: str
    hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "import_path": self.import_path,
            "file_path": self.file_path,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ComponentRecord":
        return cls(
            name=data["name"],
            import_path=data["import_path"],
            file_path=data["file_path"],
            hash=data["hash"],
        )

    @property
    def class_name(self) -> str:
        return self.import_path.rsplit(".", 1)[-1]


@dataclass
class RegistryData:
    version: str
    last_scan: str
    components: dict[str, list[ComponentRecord]]
    defaults: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": self.version,
            "last_scan": self.last_scan,
            "defaults": self.defaults,
        }
        for section in COMPONENT_TYPES:
            payload[section] = [
                record.to_dict() for record in self.components.get(section, [])
            ]
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegistryData":
        components: dict[str, list[ComponentRecord]] = {}
        for section in COMPONENT_TYPES:
            section_data = data.get(section, [])
            components[section] = [
                ComponentRecord.from_dict(entry) for entry in section_data
            ]
        defaults = data.get("defaults", {})
        return cls(
            version=data.get("version", REGISTRY_VERSION),
            last_scan=data.get("last_scan", iso_timestamp()),
            components=components,
            defaults=defaults,
        )

    def all_records(self) -> list[ComponentRecord]:
        results: list[ComponentRecord] = []
        for section in COMPONENT_TYPES:
            results.extend(self.components.get(section, []))
        return results
