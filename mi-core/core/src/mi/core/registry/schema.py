from __future__ import annotations

import inspect
import json
import logging
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, create_model

from mi.core.pipeline import PipelineConfig
from mi.core.registry.models import ComponentRecord, RegistryData
from mi.core.registry.utils import import_symbol

logger = logging.getLogger("meshinsights.registry")


@dataclass
class ComponentKeyConfig:
    """Configuration for how a component section maps to YAML keys."""

    key: str
    """The YAML key name (e.g., 'processor', 'metadata')."""

    default_for: str | None = None
    """If set, the base class name that gets a default value for the key.
    For example, 'PipelineMetadata' means that class won't require explicit key."""


class GenericComponentEntry(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "description": "A component entry specifying a component class and optional configuration."
        },
    )

    component: str = Field(
        ..., description="Name of the component class from the registry"
    )
    config: dict[str, Any] | None = Field(
        default=None, description="Component-specific configuration"
    )


class PipelineObjects(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Data object classes for process and action stages."
        },
    )

    process: str = Field(..., description="Process data object class name")
    action: str = Field(..., description="Action data object class name")


class RetrieveStage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Retrieval stage configuration. Fetches data from external sources and converts it to ProcessDataObject."
        },
    )

    hydrator: str = Field(..., description="Hydrator component name for this stage")
    retrievers: list[dict[str, Any]] = Field(
        ..., min_length=1, description="List of retriever components"
    )


class ProcessStage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Processing stage configuration. Transforms ProcessDataObject and converts it to ActionDataObject."
        },
    )

    hydrator: str = Field(..., description="Hydrator component name for this stage")
    processors: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of processor components. Each entry should have a 'processor' key with the component name, and optional config keys.",
    )


class ActionStage(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "description": "Action stage configuration. Executes final operations on ActionDataObject."
        },
    )

    hydrator: str = Field(..., description="Hydrator component name for this stage")
    actions: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of action components. Each entry should have an 'action' key with the component name, and optional config keys.",
    )


class PipelineDefinition(PipelineConfig):
    model_config = ConfigDict(extra="forbid")

    objects: PipelineObjects | None = Field(
        default=None,
        description="Data object classes (optional, will use defaults if not specified)",
    )

    retrieve: RetrieveStage = Field(...)
    process: ProcessStage = Field(...)
    action: ActionStage = Field(...)


@dataclass
class ComponentMetadata:
    record: ComponentRecord
    entry_model: type[BaseModel]
    config_type: type[BaseModel] | None
    list_entry_model: type[BaseModel] | None = None
    data_object_kind: str | None = None


def _extract_model(annotation: Any) -> type[BaseModel] | None:
    if annotation is None:
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        for arg in get_args(annotation):
            candidate = _extract_model(arg)
            if candidate is not None:
                return candidate
        return None
    if origin is None and isinstance(annotation, types.UnionType):
        for arg in get_args(annotation):
            candidate = _extract_model(arg)
            if candidate is not None:
                return candidate
    if origin is not None:
        args = get_args(annotation)
        if args:
            return _extract_model(args[0])
    return None


def load_component_class(import_path: str, root: Path) -> type[Any] | None:
    try:
        return import_symbol(import_path, root)
    except ImportError as exc:
        logger.warning(
            "Unable to import %s for schema generation: %s", import_path, exc
        )
        return None


def infer_component_config_type(component_cls: type[Any]) -> type[BaseModel] | None:
    try:
        signature = inspect.signature(component_cls.__init__)
    except (ValueError, TypeError):
        return None

    try:
        hints = get_type_hints(component_cls.__init__, include_extras=True)
    except Exception:
        hints = {}

    parameters = list(signature.parameters.items())[1:]
    for name, param in parameters:
        annotation = hints.get(name)
        candidate = _extract_model(annotation)
        if candidate is not None:
            return candidate
        if isinstance(param.default, BaseModel):
            return type(param.default)
    return None


class PipelineSchemaBuilder:
    def __init__(self, registry: RegistryData, project_root: Path) -> None:
        self.registry = registry
        self.project_root = project_root.resolve()
        self.component_models: dict[str, dict[str, ComponentMetadata]] = {
            "retrievers": {},
            "processors": {},
            "actions": {},
            "retrieve_hydrators": {},
            "process_hydrators": {},
            "action_hydrators": {},
            "process_data_objects": {},
            "action_data_objects": {},
            "metadata_types": {},
        }
        self._build_component_models()
        self.model = self._build_pipeline_model()

    def _build_component_models(self) -> None:
        from mi.core.registry.utils import ensure_sys_path

        ensure_sys_path(self.project_root)
        for section, records in self.registry.components.items():
            for record in records:
                component_cls = load_component_class(
                    record.import_path, self.project_root
                )

                # For metadata_types, the class itself is the config type
                # since it extends BaseModel/PipelineMetadata
                if section == "metadata_types" and component_cls is not None:
                    config_type = (
                        component_cls if issubclass(component_cls, BaseModel) else None
                    )
                else:
                    config_type = (
                        infer_component_config_type(component_cls)
                        if component_cls
                        else None
                    )
                entry_model = self._create_entry_model(section, record, config_type)

                component_key_configs: dict[str, ComponentKeyConfig] = {
                    "retrievers": ComponentKeyConfig(key="retriever"),
                    "processors": ComponentKeyConfig(key="processor"),
                    "actions": ComponentKeyConfig(key="action"),
                    "metadata_types": ComponentKeyConfig(
                        key="metadata", default_for="PipelineMetadata"
                    ),
                }
                key_config = component_key_configs.get(section)
                list_entry_model = None
                if key_config:
                    list_entry_model = self._create_list_entry_model(
                        section, key_config, record, config_type, component_cls
                    )

                self.component_models.setdefault(section, {})
                self.component_models[section][record.name] = ComponentMetadata(
                    record=record,
                    entry_model=entry_model,
                    config_type=config_type,
                    list_entry_model=list_entry_model,
                )

    def _create_entry_model(
        self,
        section: str,
        record: ComponentRecord,
        config_type: type[BaseModel] | None,
    ) -> type[BaseModel]:
        model_name = self._sanitize_name(f"{section}_{record.name}_Entry")
        literal_type = Literal[record.name]
        component_field = (
            literal_type,
            Field(
                default=record.name,
                description=f"Component: {record.name} ({record.import_path})",
            ),
        )
        if config_type is not None:
            config_field = (
                config_type | None,
                Field(default=None, description=f"Configuration for {record.name}"),
            )
        else:
            config_field = (
                dict[str, Any] | None,
                Field(
                    default=None,
                    description=f"Optional configuration for {record.name}",
                ),
            )
        return create_model(
            model_name,
            __base__=GenericComponentEntry,
            component=component_field,
            config=config_field,
        )

    def _create_list_entry_model(
        self,
        section: str,
        key_config: ComponentKeyConfig,
        record: ComponentRecord,
        config_type: type[BaseModel] | None,
        component_cls: type[Any] | None = None,
    ) -> type[BaseModel]:
        # Use cleaner names for metadata since it's a single object, not a list item
        if section == "metadata_types":
            model_name = self._sanitize_name(record.name)
        else:
            model_name = self._sanitize_name(f"{section}_{record.name}_ListEntry")
        literal_type = Literal[record.name]

        component_description = f"Component: {record.name}"
        if config_type is not None:
            json_schema_extra = getattr(
                config_type.model_config, "json_schema_extra", None
            )
            if json_schema_extra and isinstance(json_schema_extra, dict):
                config_desc = json_schema_extra.get("description")
                if config_desc:
                    component_description = config_desc
            if (
                component_description == f"Component: {record.name}"
                and config_type.__doc__
            ):
                component_description = config_type.__doc__.strip()
        if (
            component_description == f"Component: {record.name}"
            and component_cls
            and component_cls.__doc__
        ):
            component_description = component_cls.__doc__.strip()

        # Append filename information to description
        filename = Path(record.file_path).name
        component_description = f"{component_description} \n Added from {filename}"

        # Check if this component should have a default value for the key
        has_default = (
            key_config.default_for is not None and record.name == key_config.default_for
        )

        if has_default:
            component_field = (
                literal_type,
                Field(
                    default=record.name,
                    description=component_description,
                ),
            )
        else:
            component_field = (
                literal_type,
                Field(
                    ...,
                    description=component_description,
                ),
            )

        fields: dict[str, Any] = {key_config.key: component_field}

        if config_type is not None:
            for field_name, field_info in config_type.model_fields.items():
                field_kwargs: dict[str, Any] = {}

                if field_info.description:
                    field_kwargs["description"] = field_info.description

                if field_info.default is not ...:
                    field_kwargs["default"] = field_info.default
                    fields[field_name] = (field_info.annotation, Field(**field_kwargs))
                elif (
                    hasattr(field_info, "default_factory")
                    and field_info.default_factory is not None
                ):
                    field_kwargs["default_factory"] = field_info.default_factory
                    fields[field_name] = (field_info.annotation, Field(**field_kwargs))
                else:
                    if field_kwargs:
                        fields[field_name] = (
                            field_info.annotation,
                            Field(..., **field_kwargs),
                        )
                    else:
                        fields[field_name] = (field_info.annotation, Field(...))

        # Inherit the extra config setting from the original config_type if available
        if config_type is not None:
            # model_config is a dict/TypedDict, not an object - use .get() not getattr()
            original_extra = config_type.model_config.get("extra")
            if original_extra in ("allow", "ignore", "forbid"):
                model_config = ConfigDict(extra=original_extra)  # type: ignore[arg-type]
            else:
                model_config = ConfigDict(extra="forbid")
        else:
            model_config = ConfigDict(extra="forbid")

        return create_model(
            model_name,
            __config__=model_config,
            **fields,
        )

    def _sanitize_name(self, value: str) -> str:
        sanitized = "".join(ch if ch.isalnum() else "_" for ch in value)
        if sanitized and sanitized[0].isdigit():
            sanitized = f"Model_{sanitized}"
        return sanitized or "ComponentEntry"

    def _union_for(self, section: str) -> type[BaseModel]:
        models: list[type[BaseModel]] = []
        for metadata in self.component_models.get(section, {}).values():
            models.append(metadata.entry_model)
        if not models:
            return GenericComponentEntry
        union_type = models[0]
        for model in models[1:]:
            union_type = union_type | model
        return union_type

    def _list_union_for(self, section: str) -> type[BaseModel] | None:
        models: list[type[BaseModel]] = []
        for metadata in self.component_models.get(section, {}).values():
            if metadata.list_entry_model is not None:
                models.append(metadata.list_entry_model)
        if not models:
            return None
        union_type = models[0]
        for model in models[1:]:
            union_type = union_type | model
        return union_type

    def _literal_union_for(self, section: str) -> Any:
        names = tuple(self.component_models.get(section, {}).keys())
        if not names:
            return str
        if len(names) == 1:
            return Literal[names[0]]
        return Literal[names]

    def _build_pipeline_model(self) -> type[BaseModel]:
        process_object_literal = self._literal_union_for("process_data_objects")
        action_object_literal = self._literal_union_for("action_data_objects")
        retrieve_hydrator_literal = self._literal_union_for("retrieve_hydrators")
        process_hydrator_literal = self._literal_union_for("process_hydrators")
        action_hydrator_literal = self._literal_union_for("action_hydrators")

        retrievers_union = self._list_union_for("retrievers")
        processors_union = self._list_union_for("processors")
        actions_union = self._list_union_for("actions")
        metadata_union = self._list_union_for("metadata_types")

        return create_model(
            "MeshInsights Pipeline YAML",
            __base__=PipelineDefinition,
            objects=(
                create_model(
                    "ObjectsGroup",
                    __base__=PipelineObjects,
                    process=process_object_literal,
                    action=action_object_literal,
                )
                | None,
                Field(default=None),
            ),
            metadata=(
                (metadata_union | None if metadata_union else dict[str, Any] | None),
                Field(
                    default=None,
                    description="Pipeline metadata passed to all components. Defaults to PipelineMetadata if no 'metadata: ClassName' type is specified.",
                ),
            ),
            retrieve=create_model(
                "RetrieveStageModel",
                __base__=RetrieveStage,
                hydrator=(
                    retrieve_hydrator_literal,
                    Field(
                        ..., description="Hydrator component for the retrieval stage"
                    ),
                ),
                retrievers=(
                    (
                        list[retrievers_union]
                        if retrievers_union
                        else list[dict[str, Any]]
                    ),
                    Field(
                        ..., min_length=1, description="List of retriever components"
                    ),
                ),
            ),
            process=create_model(
                "ProcessStageModel",
                __base__=ProcessStage,
                hydrator=(
                    process_hydrator_literal,
                    Field(
                        ..., description="Hydrator component for the processing stage"
                    ),
                ),
                processors=(
                    (
                        list[processors_union]
                        if processors_union
                        else list[dict[str, Any]]
                    ),
                    Field(
                        ..., min_length=1, description="List of processor components"
                    ),
                ),
            ),
            action=create_model(
                "ActionStageModel",
                __base__=ActionStage,
                hydrator=(
                    action_hydrator_literal,
                    Field(..., description="Hydrator component for the action stage"),
                ),
                actions=(
                    (list[actions_union] if actions_union else list[dict[str, Any]]),
                    Field(..., min_length=1, description="List of action components"),
                ),
            ),
        )

    def component_config_type(self, section: str, name: str) -> type[BaseModel] | None:
        metadata = self.component_models.get(section, {}).get(name)
        if metadata is None:
            return None
        return metadata.config_type

    def json_schema(self) -> dict[str, Any]:
        return self.model.model_json_schema()


def write_schema(builder: PipelineSchemaBuilder, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(builder.json_schema(), indent=2))
    _update_vscode_yaml_settings(builder.project_root, destination)


def _update_vscode_yaml_settings(project_root: Path, schema_location: Path) -> None:
    settings_dir = project_root / ".vscode"
    settings_path = settings_dir / "settings.json"
    settings_dir.mkdir(parents=True, exist_ok=True)

    current_raw = _load_vscode_settings(settings_path)
    existing_yaml = _normalize_yaml_schemas(current_raw.get("yaml.schemas"))
    existing_files = _normalize_files_associations(
        current_raw.get("files.associations")
    )
    files_assoc = existing_files.copy()

    try:
        schema_key = schema_location.relative_to(project_root).as_posix()
    except ValueError:
        schema_key = str(schema_location)

    new_yaml = existing_yaml.copy()
    for key, matches in list(new_yaml.items()):
        if key == schema_key:
            continue
        filtered = [match for match in matches if match != "*.ppln"]
        if filtered:
            new_yaml[key] = filtered
        else:
            del new_yaml[key]

    target_matches = new_yaml.get(schema_key, [])
    if "*.ppln" not in target_matches:
        target_matches.append("*.ppln")
    new_yaml[schema_key] = target_matches

    if files_assoc.get("*.ppln") != "yaml":
        files_assoc["*.ppln"] = "yaml"

    yaml_changed = new_yaml != existing_yaml
    files_changed = files_assoc != existing_files
    if not (yaml_changed or files_changed):
        return

    current_raw["yaml.schemas"] = {key: value for key, value in new_yaml.items()}
    current_raw["files.associations"] = files_assoc
    settings_path.write_text(json.dumps(current_raw, indent=4))


def _normalize_yaml_schemas(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, list[str]] = {}
    for key, value in raw.items():
        normalized[str(key)] = _ensure_string_list(value)
    return normalized


def _normalize_files_associations(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            normalized[str(key)] = value
        else:
            normalized[str(key)] = str(value)
    return normalized


def _ensure_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(entry) for entry in value]
    if value is None:
        return []
    return [str(value)]


def _load_vscode_settings(settings_path: Path) -> dict[str, Any]:
    if not settings_path.exists():
        return {}
    try:
        raw_text = settings_path.read_text()
    except OSError as exc:
        logger.warning("Unable to read VS Code settings at %s: %s", settings_path, exc)
        return {}
    try:
        cleaned = _strip_json_comments(raw_text)
        parsed = json.loads(cleaned) if cleaned.strip() else {}
    except json.JSONDecodeError as exc:
        logger.warning("Unable to parse VS Code settings at %s: %s", settings_path, exc)
        return {}
    if isinstance(parsed, dict):
        return parsed
    logger.warning("VS Code settings at %s are not a JSON object", settings_path)
    return {}


def _strip_json_comments(source: str) -> str:
    result: list[str] = []
    in_string = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    quote_char = ""
    i = 0
    length = len(source)

    while i < length:
        char = source[i]
        next_char = source[i + 1] if i + 1 < length else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
                result.append(char)
            i += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
            i += 1
            continue

        if char in ('"', "'"):
            in_string = True
            quote_char = char
            result.append(char)
            i += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            i += 2
            continue

        if char == "/" and next_char == "*":
            in_block_comment = True
            i += 2
            continue

        result.append(char)
        i += 1

    return "".join(result)
