from __future__ import annotations

from typing import Final

REGISTRY_VERSION: Final[str] = "1.0"
REGISTRY_FILE_NAME: Final[str] = "registry.json"
DEFAULT_SCAN_PATHS: Final[list[str]] = ["core/**", "examples/**"]
DEFAULT_EXCLUDE_PATHS: Final[list[str]] = [
    "**/__pycache__/**",
    "**/tests/**",
    "**/*.pyc",
]
COMPONENT_TYPES: Final[tuple[str, ...]] = (
    "retrievers",
    "processors",
    "actions",
    "retrieve_hydrators",
    "process_hydrators",
    "action_hydrators",
    "process_data_objects",
    "action_data_objects",
    "metadata_types",
)
