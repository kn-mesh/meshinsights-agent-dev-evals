from __future__ import annotations

import ast
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterator

from mi.core.registry.constants import COMPONENT_TYPES, REGISTRY_VERSION
from mi.core.registry.models import ComponentRecord, PipelineSettings, RegistryData
from mi.core.registry.validation import collect_python_files, compute_component_hash
from mi.core.registry.utils import (
    iso_timestamp,
    find_project_venv,
    ensure_sys_path,
    _get_venv_site_packages,
)

DATA_OBJECT_SECTION_MAP = {
    "ProcessDataObject": "process_data_objects",
    "ActionDataObject": "action_data_objects",
    "PipelineMetadata": "metadata_types",
}

HYDRATOR_SECTIONS = ("retrieve_hydrators", "process_hydrators", "action_hydrators")

DEFAULT_SECTION_BASES = {
    "retrievers": "BaseRetriever",
    "processors": "BaseProcessor",
    "actions": "BaseAction",
    "retrieve_hydrators": "BaseHydrator",
    "process_hydrators": "BaseHydrator",
    "action_hydrators": "BaseHydrator",
    "process_data_objects": "ProcessDataObject",
    "action_data_objects": "ActionDataObject",
    "metadata_types": "PipelineMetadata",
}


@dataclass
class ComponentMatch:
    category: str
    type_args: list[str] = field(default_factory=list)


class ImportTracker:
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}

    def feed(self, node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            self._handle_import(node)
        elif isinstance(node, ast.ImportFrom):
            self._handle_import_from(node)

    def _handle_import(self, node: ast.Import) -> None:
        for alias in node.names:
            target = alias.name
            name = alias.asname or target.split(".")[0]
            self.aliases[name] = target

    def _handle_import_from(self, node: ast.ImportFrom) -> None:
        module = (node.module or "").lstrip(".")
        for alias in node.names:
            qualified = ".".join(part for part in (module, alias.name) if part)
            name = alias.asname or alias.name
            self.aliases[name] = qualified

    def resolve(self, identifier: str) -> str:
        parts = identifier.split(".")
        if not parts:
            return identifier
        first = parts[0]
        resolved = self.aliases.get(first, first)
        if len(parts) == 1:
            return resolved
        return ".".join([resolved, *parts[1:]])


class RegistryScanner:
    def __init__(self, root: Path, settings: PipelineSettings) -> None:
        self.root = root.resolve()
        # Ensure the project root and its venv site-packages are on sys.path before any imports.
        ensure_sys_path(self.root)
        self.settings = settings
        self.logger = logging.getLogger("meshinsights.registry")
        self.data_object_types: dict[str, str] = {
            "ProcessDataObject": "process",
            "core.objects.process_data_object.ProcessDataObject": "process",
            "mi.core.objects.process_data_object.ProcessDataObject": "process",
            "mi.core.objects.ProcessDataObject": "process",
            "ActionDataObject": "action",
            "core.objects.action_data_object.ActionDataObject": "action",
            "mi.core.objects.action_data_object.ActionDataObject": "action",
            "mi.core.objects.ActionDataObject": "action",
            "RetrieverDataObject": "retriever",
            "core.objects.retriever_data_object.RetrieverDataObject": "retriever",
            "mi.core.objects.retriever_data_object.RetrieverDataObject": "retriever",
            "mi.core.objects.RetrieverDataObject": "retriever",
        }

    def scan(self) -> RegistryData:
        files = collect_python_files(self.root, self.settings)
        # Also scan mi package from installed packages (e.g., in venv)
        mi_files = self._find_mi_core_files()
        files.extend(mi_files)
        components: dict[str, list[ComponentRecord]] = {
            section: [] for section in COMPONENT_TYPES
        }
        hydrator_candidates: list[tuple[ComponentRecord, list[str]]] = []
        name_counts: dict[tuple[str, str], int] = {}

        for file_path in files:
            for match, record in self._scan_file(file_path, name_counts):
                if match.category in ("process_data_objects", "action_data_objects"):
                    self._register_data_object(record, match.category)
                    components[match.category].append(record)
                elif match.category == "hydrators":
                    hydrator_candidates.append((record, match.type_args))
                else:
                    components[match.category].append(record)

        self._assign_hydrators(hydrator_candidates, components)

        defaults: dict[str, str | None] = {
            section: DEFAULT_SECTION_BASES.get(section) for section in COMPONENT_TYPES
        }
        for section, records in components.items():
            records.sort(key=lambda item: item.name)

        return RegistryData(
            version=REGISTRY_VERSION,
            last_scan=iso_timestamp(),
            components=components,
            defaults=defaults,
        )

    def _scan_file(
        self,
        file_path: Path,
        name_counts: dict[tuple[str, str], int],
    ) -> Iterator[tuple[ComponentMatch, ComponentRecord]]:
        try:
            source = file_path.read_text()
            tree = ast.parse(source)
        except (OSError, SyntaxError) as exc:
            self.logger.warning("Skipping %s due to parse error: %s", file_path, exc)
            return

        tracker = ImportTracker()
        for node in ast.iter_child_nodes(tree):
            tracker.feed(node)

        # Handle files inside and outside project root
        # Check if this is a site-packages file (even if inside project root)
        parts = list(file_path.parts)

        # Check if this file is in site-packages
        is_site_packages = "site-packages" in parts

        if is_site_packages:
            # File is from site-packages, extract module name from after site-packages
            rel_path = str(file_path.resolve())
            try:
                site_packages_idx = next(
                    i for i, p in enumerate(parts) if p == "site-packages"
                )
                # Get parts after site-packages, remove .py extension
                module_parts = list(parts[site_packages_idx + 1 :])
                if module_parts and module_parts[-1].endswith(".py"):
                    module_parts[-1] = module_parts[-1][:-3]  # Remove .py extension
            except (StopIteration, ValueError):
                # Fallback: use filename without extension
                module_parts = [file_path.stem]
        else:
            # File is in project, use relative path
            try:
                rel_path = file_path.relative_to(self.root).as_posix()
                module_path = file_path.relative_to(self.root).with_suffix("")
                module_parts = list(module_path.parts)
            except ValueError:
                # File is outside project root, use absolute path
                rel_path = str(file_path.resolve())
                # Fallback: use filename without extension
                module_parts = [file_path.stem]

        if module_parts and module_parts[-1] == "__init__":
            module_parts = module_parts[:-1]
        module_name = ".".join(module_parts)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            match = self._match_component(node, tracker)
            if match is None:
                continue
            unique_name = self._unique_name(match.category, node.name, name_counts)
            import_path = f"{module_name}.{node.name}" if module_name else node.name
            component_hash = compute_component_hash(node.name, rel_path, node.lineno)
            record = ComponentRecord(
                name=unique_name,
                import_path=import_path,
                file_path=rel_path,
                hash=component_hash,
            )
            yield match, record

    def _match_component(
        self,
        node: ast.ClassDef,
        tracker: ImportTracker,
    ) -> ComponentMatch | None:
        # Check if the class name itself matches data objects or PipelineMetadata
        if node.name in DATA_OBJECT_SECTION_MAP:
            return ComponentMatch(DATA_OBJECT_SECTION_MAP[node.name])
        if node.name == "PipelineMetadata":
            return ComponentMatch("metadata_types")

        # Check base classes
        for base in node.bases:
            identifier = self._base_identifier(base)
            if not identifier:
                continue
            resolved = tracker.resolve(identifier)
            candidate = resolved.split(".")[-1]
            if candidate == "BaseRetriever":
                return ComponentMatch("retrievers")
            if candidate == "BaseProcessor":
                return ComponentMatch("processors")
            if candidate == "BaseAction":
                return ComponentMatch("actions")
            if candidate == "PipelineMetadata":
                return ComponentMatch("metadata_types")
            if candidate in DATA_OBJECT_SECTION_MAP:
                return ComponentMatch(DATA_OBJECT_SECTION_MAP[candidate])
            if candidate == "BaseHydrator":
                args = self._extract_type_args(base, tracker)
                return ComponentMatch("hydrators", args)
        return None

    def _base_identifier(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = self._base_identifier(node.value)
            if parent:
                return f"{parent}.{node.attr}"
            return node.attr
        if isinstance(node, ast.Subscript):
            return self._base_identifier(node.value)
        if isinstance(node, ast.Call):
            return self._base_identifier(node.func)
        return None

    def _extract_type_args(
        self,
        node: ast.expr,
        tracker: ImportTracker,
    ) -> list[str]:
        if not isinstance(node, ast.Subscript):
            return []
        raw = node.slice
        elements: list[ast.expr]
        if isinstance(raw, ast.Tuple):
            elements = list(raw.elts)
        else:
            elements = [raw]
        results: list[str] = []
        for element in elements:
            ident = self._annotation_identifier(element, tracker)
            if ident is not None:
                results.append(ident)
        return results

    def _annotation_identifier(
        self, node: ast.expr, tracker: ImportTracker
    ) -> str | None:
        if isinstance(node, ast.Constant) and node.value is None:
            return "None"
        identifier = self._base_identifier(node)
        if identifier is None:
            return None
        return tracker.resolve(identifier)

    def _register_data_object(self, record: ComponentRecord, section: str) -> None:
        kind = "process" if section == "process_data_objects" else "action"
        self.data_object_types[record.import_path] = kind
        self.data_object_types[record.class_name] = kind

    def _assign_hydrators(
        self,
        candidates: list[tuple[ComponentRecord, list[str]]],
        components: dict[str, list[ComponentRecord]],
    ) -> None:
        for record, args in candidates:
            section = self._categorize_hydrator(args)
            if section is None:
                self.logger.warning(
                    "Unable to determine hydrator type for %s with args %s",
                    record.import_path,
                    args,
                )
                continue
            components[section].append(record)

    def _categorize_hydrator(self, args: list[str]) -> str | None:
        if len(args) < 2:
            return None
        source_type = self._data_kind_from_name(args[0])
        target_type = self._data_kind_from_name(args[1])
        if source_type == "retriever" and target_type == "process":
            return "retrieve_hydrators"
        if source_type == "process" and target_type == "action":
            return "process_hydrators"
        if source_type == "action" and target_type in ("none", None):
            return "action_hydrators"
        return None

    def _data_kind_from_name(self, name: str | None) -> str | None:
        if name is None:
            return None
        simplified = name.split(".")[-1]
        if simplified in ("None", "NoneType"):
            return "none"
        if simplified == "RetrieverDataObject":
            return "retriever"
        if simplified in ("ProcessDataObject", "ActionDataObject"):
            return "process" if simplified == "ProcessDataObject" else "action"
        return self.data_object_types.get(name) or self.data_object_types.get(
            simplified
        )

    def _unique_name(
        self,
        component_type: str,
        class_name: str,
        counters: dict[tuple[str, str], int],
    ) -> str:
        key = (component_type, class_name)
        current = counters.get(key, 0)
        counters[key] = current + 1
        if current == 0:
            return class_name
        return f"{class_name}@{current}"

    def _find_mi_core_files(self) -> list[Path]:
        """Find mi package Python files from installed packages (e.g., in venv).

        Scans the mi package and its subpackages (mi.core, mi.ai, mi.utilities)
        for pipeline components like processors, retrievers, actions, and hydrators.
        """
        mi_files: list[Path] = []

        # Try to find venv and check for mi in site-packages
        venv_path = find_project_venv(self.root)
        if venv_path is None:
            self.logger.debug(
                "No venv found, skipping mi package scan from installed packages"
            )
            return mi_files

        # Get site-packages path
        site_packages = _get_venv_site_packages(venv_path)
        if site_packages is None:
            return mi_files

        # Check if mi package is installed in site-packages
        mi_path = site_packages / "mi"
        if not mi_path.exists():
            self.logger.debug(
                "mi package not found in site-packages: %s", site_packages
            )
            return mi_files
        if not mi_path.is_dir():
            return mi_files

        # Collect all Python files from mi and its subpackages
        self.logger.debug("Scanning mi package from installed location: %s", mi_path)
        for py_file in mi_path.rglob("*.py"):
            # Skip __pycache__ and test files
            if "__pycache__" in str(py_file) or "test" in py_file.name.lower():
                continue
            mi_files.append(py_file.resolve())

        return mi_files
