"""Fluent builder for assembling Pipeline instances.

Provides a chainable API for adding retrievers, processors, actions,
and hydrators. Supports both programmatic construction and loading
from YAML configuration files.

See docs/pipeline-builder.md for the full API reference.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
import yaml

from mi.core.actions import BaseAction
from mi.core.hydrators import BaseHydrator
from mi.core.objects import ActionDataObject, ProcessDataObject, RetrieverDataObject
from mi.core.pipeline import Pipeline, PipelineConfig
from mi.core.processors import BaseProcessor
from mi.core.retrievers import BaseRetriever
from mi.core.utils.telemetry import get_current_span, get_tracer, ATTR_COMPONENT_LAYER

_tracer = get_tracer("pipeline_builder", use_library_resource=True)

if TYPE_CHECKING:
    from mi.core.registry import PipelineSchemaBuilder, RegistryData

PDO = TypeVar("PDO", bound=ProcessDataObject, default=ProcessDataObject)
ADO = TypeVar("ADO", bound=ActionDataObject, default=ActionDataObject)

_PDO = TypeVar("_PDO", bound=ProcessDataObject)
_ADO = TypeVar("_ADO", bound=ActionDataObject)


class PipelineBuilder(Generic[PDO, ADO]):
    """Fluent builder used to assemble pipelines stage-by-stage.

    The builder accumulates retrievers, processors, actions, and hydrators, and
    then produces a validated :class:`mi_core.pipeline.Pipeline` instance when
    :meth:`build` is called.

    Example:
        >>> from mi.core.pipeline import PipelineConfig
        >>> builder = PipelineBuilder().with_config(PipelineConfig(name="demo"))
        >>> isinstance(builder, PipelineBuilder)
        True
    """

    def __init__(self) -> None:
        """Initialize the builder with empty component collections.

        Example:
            >>> builder = PipelineBuilder()
            >>> builder._retrievers
            []
        """

        self._config: PipelineConfig | None = None
        self._logger: logging.Logger | None = None
        self._retrievers: list[BaseRetriever] = []
        self._retrieve_hydrator: BaseHydrator[RetrieverDataObject, PDO] | None = None
        self._processors: list[BaseProcessor[PDO]] = []
        self._process_hydrator: BaseHydrator[PDO, ADO] | None = None
        self._actions: list[BaseAction[ADO]] = []
        self._action_hydrator: BaseHydrator[ADO, None] | None = None

    def with_config(
        self,
        config: PipelineConfig,
        *,
        overwrite: bool = False,
    ) -> "PipelineBuilder[PDO, ADO]":
        """Attach or merge a pipeline configuration.

        Args:
            config (PipelineConfig): Configuration describing metadata, logging,
                and error handling strategies.
            overwrite (bool): When ``True``, replace any existing config
                wholesale. When ``False`` (default), merge only the fields that
                were explicitly set on ``config`` (``model_dump(exclude_unset=True)``),
                preserving previously provided values.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance for chaining.

        Example:
            >>> from mi.core.pipeline import PipelineConfig
            >>> base = PipelineConfig(name="doc", version="1.0.0")
            >>> builder = PipelineBuilder().with_config(base)
            >>> builder = builder.with_config(PipelineConfig(version="2.0.0"), overwrite=False)
            >>> builder._config.version
            '2.0.0'
        """

        if overwrite or self._config is None:
            self._config = config
        else:
            # Recreate a validated PipelineConfig to avoid nested models becoming plain dicts
            base_dump = self._config.model_dump()
            updates = config.model_dump(exclude_unset=True)
            merged = {**base_dump, **updates}
            self._config = PipelineConfig(**merged)
        return self

    def with_bootstraps(
        self,
        *,
        environment: bool = True,
        otel: bool = True,
    ) -> "PipelineBuilder[PDO, ADO]":
        """Enable or disable automatic bootstrap steps for the pipeline.

        Convenience method that sets ``bootstrap_environment`` and
        ``bootstrap_otel`` on the underlying :class:`PipelineConfig`.  A
        config is created automatically if one has not been attached yet.

        Args:
            environment: When ``True`` (default), the pipeline will load a
                ``.env`` file into ``os.environ`` before any stages or
                telemetry initialisation runs.
            otel: When ``True`` (default), telemetry (Logfire / OTel SDK) is
                auto-detected and initialised at pipeline startup.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance for chaining.

        Example:
            >>> builder = PipelineBuilder().with_bootstraps(environment=True, otel=False)
            >>> builder._config.bootstrap_environment
            True
            >>> builder._config.bootstrap_otel
            False
        """
        if self._config is None:
            self._config = PipelineConfig()
        self._config = self._config.model_copy(
            update={
                "bootstrap_environment": environment,
                "bootstrap_otel": otel,
            }
        )
        return self

    def with_logger(self, logger: logging.Logger) -> "PipelineBuilder[PDO, ADO]":
        """Provide a pre-configured logger to share across pipeline components.

        Args:
            logger (logging.Logger): Logger instance with handlers already
                attached.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> import logging
            >>> custom_logger = logging.getLogger("custom")
            >>> PipelineBuilder().with_logger(custom_logger)._logger is custom_logger
            True
        """

        self._logger = logger
        return self

    def with_objects(
        self,
        process_object: _PDO | type[_PDO],
        action_object: _ADO | type[_ADO],
    ) -> "PipelineBuilder[_PDO, _ADO]":
        """Override the default Process/Action data object types for type-checking.

        Args:
            process_object (_PDO | type[_PDO]): Concrete process data object
                class or instance.
            action_object (_ADO | type[_ADO]): Concrete action data object class
                or instance.

        Returns:
            PipelineBuilder[_PDO, _ADO]: The builder typed with the supplied
                objects to aid static analysis.

        Example:
            >>> from mi.core.objects import ProcessDataObject, ActionDataObject
            >>> builder = PipelineBuilder().with_objects(ProcessDataObject, ActionDataObject)
            >>> isinstance(builder, PipelineBuilder)
            True
        """

        self = cast("PipelineBuilder[_PDO, _ADO]", self)
        return cast("PipelineBuilder[_PDO, _ADO]", self)

    def add_retriever(self, retriever: BaseRetriever) -> "PipelineBuilder[PDO, ADO]":
        """Append a single retriever to the retrieve stage.

        Args:
            retriever (BaseRetriever): Concrete retriever instance.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
            >>> class InlineRetriever(BaseRetriever):
            ...     def __init__(self) -> None:
            ...         super().__init__(BaseRetrieverConfig(name="inline"))
            ...     def retrieve(self) -> list[int]:
            ...         return [1]
            >>> PipelineBuilder().add_retriever(InlineRetriever())._retrievers[0].name
            'inline'
        """

        self._retrievers.append(retriever)
        return self

    def add_retrievers(
        self, retrievers: list[BaseRetriever]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Extend the retrieve stage with multiple retrievers.

        Args:
            retrievers (list[BaseRetriever]): Concrete retriever instances to
                append in the provided order.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
            >>> class BulkRetriever(BaseRetriever):
            ...     def __init__(self, name: str) -> None:
            ...         super().__init__(BaseRetrieverConfig(name=name))
            ...     def retrieve(self) -> list[int]:
            ...         return [1]
            >>> builder = PipelineBuilder().add_retrievers([BulkRetriever("a"), BulkRetriever("b")])
            >>> len(builder._retrievers)
            2
        """

        self._retrievers.extend(retrievers)
        return self

    def with_retrieve_hydrator(
        self, hydrator: BaseHydrator[RetrieverDataObject, PDO]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Assign the hydrator that converts retriever output to process objects.

        Args:
            hydrator (BaseHydrator[RetrieverDataObject, PDO]): Hydrator that
                takes a :class:`RetrieverDataObject` and returns a process data
                object.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.hydrators import BaseHydrator
            >>> from mi.core.objects import RetrieverDataObject, ProcessDataObject
            >>> class DummyHydrator(BaseHydrator[RetrieverDataObject, ProcessDataObject]):
            ...     def hydrate(self, source: RetrieverDataObject, receipt):
            ...         return ProcessDataObject()
            >>> builder = PipelineBuilder().with_retrieve_hydrator(DummyHydrator())
            >>> builder._retrieve_hydrator.name
            'DummyHydrator'
        """

        self._retrieve_hydrator = hydrator
        return self

    def add_processor(
        self, processor: BaseProcessor[PDO]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Add a processor executed during the process stage.

        Args:
            processor (BaseProcessor[PDO]): Processor instance ready for
                invocation.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.objects import ProcessDataObject
            >>> from mi.core.processors import BaseProcessor
            >>> class NoOpProcessor(BaseProcessor[ProcessDataObject]):
            ...     def process(self, data_object: ProcessDataObject) -> None:
            ...         data_object.set_artifact("noop", True)
            >>> builder = PipelineBuilder().add_processor(NoOpProcessor())
            >>> builder._processors[0].name
            'NoOpProcessor'
        """

        self._processors.append(processor)
        return self

    def add_processors(
        self, processors: list[BaseProcessor[PDO]]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Append multiple processors in invocation order.

        Args:
            processors (list[BaseProcessor[PDO]]): Processor instances to add.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.objects import ProcessDataObject
            >>> from mi.core.processors import BaseProcessor
            >>> class P1(BaseProcessor[ProcessDataObject]):
            ...     def process(self, data_object: ProcessDataObject) -> None:
            ...         pass
            >>> class P2(P1):
            ...     pass
            >>> builder = PipelineBuilder().add_processors([P1(), P2()])
            >>> [proc.name for proc in builder._processors]
            ['P1', 'P2']
        """

        self._processors.extend(processors)
        return self

    def with_process_hydrator(
        self, hydrator: BaseHydrator[PDO, ADO]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Define the hydrator that converts process data into action data.

        Args:
            hydrator (BaseHydrator[PDO, ADO]): Hydrator bridging the process and
                action stages.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.hydrators import BaseHydrator
            >>> from mi.core.objects import ProcessDataObject, ActionDataObject
            >>> class ProcessToActionHydrator(BaseHydrator[ProcessDataObject, ActionDataObject]):
            ...     def hydrate(self, source: ProcessDataObject, receipt):
            ...         return ActionDataObject()
            >>> PipelineBuilder().with_process_hydrator(ProcessToActionHydrator())._process_hydrator.name
            'ProcessToActionHydrator'
        """

        self._process_hydrator = hydrator
        return self

    def add_action(self, action: BaseAction[ADO]) -> "PipelineBuilder[PDO, ADO]":
        """Register an action executed during the final act stage.

        Args:
            action (BaseAction[ADO]): Action instance.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.actions import BaseAction
            >>> from mi.core.objects import ActionDataObject
            >>> class PrintAction(BaseAction[ActionDataObject]):
            ...     def act(self, data_object: ActionDataObject) -> None:
            ...         pass
            >>> builder = PipelineBuilder().add_action(PrintAction(name="printer"))
            >>> builder._actions[0].name
            'printer'
        """

        self._actions.append(action)
        return self

    def add_actions(
        self, actions: list[BaseAction[ADO]]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Append multiple actions to the act stage in sequence.

        Args:
            actions (list[BaseAction[ADO]]): Action instances to append.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.actions import BaseAction
            >>> from mi.core.objects import ActionDataObject
            >>> class LogAction(BaseAction[ActionDataObject]):
            ...     def act(self, data_object: ActionDataObject) -> None:
            ...         pass
            >>> builder = PipelineBuilder().add_actions([LogAction(name="a"), LogAction(name="b")])
            >>> len(builder._actions)
            2
        """

        self._actions.extend(actions)
        return self

    def with_action_hydrator(
        self, hydrator: BaseHydrator[ADO, None]
    ) -> "PipelineBuilder[PDO, ADO]":
        """Set the hydrator responsible for final action cleanup.

        Args:
            hydrator (BaseHydrator[ADO, None]): Hydrator that runs after actions
                complete to finalize receipts or persist results.

        Returns:
            PipelineBuilder[PDO, ADO]: The builder instance.

        Example:
            >>> from mi.core.hydrators import BaseHydrator
            >>> from mi.core.objects import ActionDataObject
            >>> class FinalHydrator(BaseHydrator[ActionDataObject, None]):
            ...     def hydrate(self, source: ActionDataObject, receipt):
            ...         return None
            >>> PipelineBuilder().with_action_hydrator(FinalHydrator())._action_hydrator.name
            'FinalHydrator'
        """

        self._action_hydrator = hydrator
        return self

    def build(self) -> Pipeline[PDO, ADO]:
        """Validate collected components and construct a Pipeline instance.

        Returns:
            Pipeline[PDO, ADO]: Fully initialized pipeline ready for execution.

        Raises:
            ValueError: If any stage is missing required components.

        Example:
            >>> from mi.core.actions import BaseAction
            >>> from mi.core.hydrators import BaseHydrator
            >>> from mi.core.objects import (
            ...     ActionDataObject,
            ...     ProcessDataObject,
            ...     RetrieverDataObject,
            ... )
            >>> from mi.core.processors import BaseProcessor
            >>> from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
            >>> class DummyRetriever(BaseRetriever):
            ...     def __init__(self) -> None:
            ...         super().__init__(BaseRetrieverConfig(name="dummy"))
            ...     def retrieve(self) -> list[int]:
            ...         return []
            >>> class DummyHydrator(BaseHydrator[RetrieverDataObject, ProcessDataObject]):
            ...     def hydrate(self, source: RetrieverDataObject, receipt):
            ...         return ProcessDataObject()
            >>> class DummyProcessor(BaseProcessor[ProcessDataObject]):
            ...     def process(self, data_object: ProcessDataObject) -> None:
            ...         pass
            >>> class ProcToAction(BaseHydrator[ProcessDataObject, ActionDataObject]):
            ...     def hydrate(self, source: ProcessDataObject, receipt):
            ...         return ActionDataObject()
            >>> class DummyAction(BaseAction[ActionDataObject]):
            ...     def act(self, data_object: ActionDataObject) -> None:
            ...         pass
            >>> class FinalHydrator(BaseHydrator[ActionDataObject, None]):
            ...     def hydrate(self, source: ActionDataObject, receipt):
            ...         return None
            >>> pipeline = (
            ...     PipelineBuilder()
            ...     .add_retriever(DummyRetriever())
            ...     .with_retrieve_hydrator(DummyHydrator())
            ...     .add_processor(DummyProcessor())
            ...     .with_process_hydrator(ProcToAction())
            ...     .add_action(DummyAction())
            ...     .with_action_hydrator(FinalHydrator())
            ...     .build()
            ... )
            >>> isinstance(pipeline, Pipeline)
            True
        """

        if not self._retrievers:
            raise ValueError("At least one retriever is required")
        if self._retrieve_hydrator is None:
            raise ValueError("retrieve_hydrator is required")
        if not self._processors:
            raise ValueError("At least one processor is required")
        if self._process_hydrator is None:
            raise ValueError("process_hydrator is required")
        if not self._actions:
            raise ValueError("At least one action is required")
        if self._action_hydrator is None:
            raise ValueError("action_hydrator is required")

        pipeline = Pipeline[
            PDO, ADO
        ](
            retrievers=copy.deepcopy(self._retrievers),
            processors=copy.deepcopy(self._processors),
            actions=copy.deepcopy(self._actions),
            retrieve_hydrator=copy.deepcopy(self._retrieve_hydrator),
            process_hydrator=copy.deepcopy(self._process_hydrator),
            action_hydrator=copy.deepcopy(self._action_hydrator),
            config=copy.deepcopy(self._config) if self._config else None,
            logger=self._logger,  # Loggers are typically shared and reassigned in Pipeline.__init__
        )
        return pipeline

    @classmethod
    @_tracer.start_as_current_span("pipeline_builder.from_yaml")
    def from_yaml(
        cls,
        yaml_path: str | Path,
    ) -> "PipelineBuilder[PDO, ADO]":
        """Build a pipeline builder from a declarative YAML configuration.

        Args:
            yaml_path (str | Path): Path to the pipeline YAML file.

        Returns:
            PipelineBuilder[PDO, ADO]: Builder populated with the components
                declared in the YAML.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            ValueError: When the YAML content cannot be parsed or validated.

        Notes:
            This method loads the project registry, validates the YAML against
            the generated schema, and instantiates components defined in the
            registry (including resolving relative file paths).

        Example:
            >>> # Given a valid YAML file named 'pipeline.ppln' in the project root
            >>> # builder = PipelineBuilder.from_yaml('pipeline.ppln')  # doctest: +SKIP
        """

        current_span = get_current_span()
        current_span.set_attribute(ATTR_COMPONENT_LAYER, "library")

        from pydantic import ValidationError
        from mi.core.registry import find_project_root, load_pipeline_settings

        path = Path(yaml_path).resolve()
        current_span.set_attribute("pipeline.yaml_path", str(path))

        if not path.exists():
            raise FileNotFoundError(f"Pipeline YAML not found: {path}")

        settings, resolved_config = load_pipeline_settings(None, start=path.parent)
        project_root = find_project_root(path.parent)
        from mi.core.registry import prepare_registry_and_schema

        registry, schema_builder = prepare_registry_and_schema(
            project_root,
            settings,
            resolved_config,
            force_scan=True,
        )

        try:
            with path.open("r", encoding="utf-8") as handle:
                config_data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Failed to parse pipeline YAML: {exc}") from exc
        if not isinstance(config_data, dict):
            raise ValueError("Pipeline YAML must define a mapping at the root")

        try:
            parsed = schema_builder.model.model_validate(config_data)
        except ValidationError as exc:
            raise ValueError(f"Invalid pipeline configuration: {exc}") from exc

        return _build_builder_from_config(
            parsed,
            registry,
            schema_builder,
            project_root,
            yaml_file_path=path,
        )


def _resolve_relative_paths(config: Any, yaml_file_path: Path) -> Any:
    """Resolve relative file paths within a parsed configuration structure.

    Args:
        config (Any): Parsed YAML data (dict/list/primitives).
        yaml_file_path (Path): Absolute path to the YAML file being processed.

    Returns:
        Any: Structure with ``file_path`` entries rewritten to absolute paths.

    Notes:
        Recurses through nested lists/dicts and only rewrites ``file_path`` keys
        so other relative values remain untouched.

    Example:
        >>> from pathlib import Path
        >>> resolved = _resolve_relative_paths({"file_path": "data.csv"}, Path("/tmp/pipeline.ppln"))
        >>> resolved["file_path"].endswith("data.csv")
        True
    """

    if isinstance(config, dict):
        resolved = {}
        for key, value in config.items():
            if key == "file_path" and isinstance(value, str):
                path = Path(value)
                if not path.is_absolute():
                    resolved[key] = str((yaml_file_path.parent / path).resolve())
                else:
                    resolved[key] = value
            else:
                resolved[key] = _resolve_relative_paths(value, yaml_file_path)
        return resolved
    elif isinstance(config, list):
        return [_resolve_relative_paths(item, yaml_file_path) for item in config]
    else:
        return config


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    """Normalize registry entries (dicts or pydantic models) to dictionaries.

    Args:
        entry (Any): Component entry loaded from YAML or schema builder.

    Returns:
        dict[str, Any]: Raw dictionary form of the entry.

    Raises:
        TypeError: If the entry type cannot be converted.

    Example:
        >>> _entry_to_dict({"retriever": "csv"}) == {"retriever": "csv"}
        True
    """

    if isinstance(entry, dict):
        return entry
    model_dump = getattr(entry, "model_dump", None)
    if callable(model_dump):
        return model_dump()  # pyright: ignore[reportReturnType]
    raise TypeError(f"Unsupported entry type: {type(entry)!r}")


def _build_builder_from_config(
    parsed_config: Any,
    registry: "RegistryData",
    schema_builder: "PipelineSchemaBuilder",
    project_root: Path,
    *,
    yaml_file_path: Path | None = None,
) -> "PipelineBuilder[_PDO, _ADO]":
    """Construct a builder by instantiating components declared in parsed YAML.

    Args:
        parsed_config (Any): Validated pipeline configuration model.
        registry (RegistryData): Registry describing available components.
        schema_builder (PipelineSchemaBuilder): Builder used to infer config types.
        project_root (Path): Root of the mesh insights project.
        yaml_file_path (Path | None): Optional path used to resolve relative
            component file references.

    Returns:
        PipelineBuilder[_PDO, _ADO]: Builder populated with the YAML contents.

    Notes:
        Uses the registry to look up classes by name, instantiates config models
        when provided, and preserves ordering across stages.

    Example:
        >>> # Typically invoked internally via PipelineBuilder.from_yaml
        >>> # builder = _build_builder_from_config(parsed, registry, schema_builder, Path('.'))  # doctest: +SKIP
    """

    builder = PipelineBuilder()

    from mi.core.registry import (
        build_registry_index,
        get_record,
        instantiate_component,
        load_data_object_type,
        load_metadata_type,
    )

    registry_index = build_registry_index(registry)

    # Handle metadata with type specification
    metadata = None
    if hasattr(parsed_config, "metadata") and parsed_config.metadata is not None:
        metadata_dict = _entry_to_dict(parsed_config.metadata)
        metadata_type_name = metadata_dict.pop("metadata", None)

        if metadata_type_name:
            # Load custom metadata type from registry
            metadata_class = load_metadata_type(
                metadata_type_name,
                registry_index,
                project_root,
            )
            config_type = schema_builder.component_config_type(
                "metadata_types", metadata_type_name
            )
            if config_type is not None and metadata_dict:
                metadata = metadata_class(**config_type(**metadata_dict).model_dump())
            elif metadata_dict:
                metadata = metadata_class(**metadata_dict)
            else:
                metadata = metadata_class(unit_id="default")
        else:
            # Fall back to base PipelineMetadata
            from mi.core.pipeline import PipelineMetadata

            if metadata_dict:
                metadata = PipelineMetadata(**metadata_dict)

    pipeline_config_values = {
        field_name: getattr(parsed_config, field_name)
        for field_name in PipelineConfig.model_fields.keys()
        if hasattr(parsed_config, field_name) and field_name != "metadata"
    }
    # Only set metadata if provided; otherwise let PipelineConfig use its default_factory
    if metadata is not None:
        pipeline_config_values["metadata"] = metadata
    pipeline_config = PipelineConfig(**pipeline_config_values)
    builder.with_config(pipeline_config)

    if parsed_config.objects is not None:
        process_obj = load_data_object_type(
            "process_data_objects",
            parsed_config.objects.process,
            registry_index,
            project_root,
            expected_cls=ProcessDataObject,
        )
        action_obj = load_data_object_type(
            "action_data_objects",
            parsed_config.objects.action,
            registry_index,
            project_root,
            expected_cls=ActionDataObject,
        )
        builder = builder.with_objects(process_obj, action_obj)
    else:
        builder = builder.with_objects(ProcessDataObject, ActionDataObject)
        builder = cast("PipelineBuilder[_PDO, _ADO]", builder)

    retrieve_stage = parsed_config.retrieve
    process_stage = parsed_config.process
    action_stage = parsed_config.action

    for entry in retrieve_stage.retrievers:
        entry_dict = _entry_to_dict(entry)
        component_name = entry_dict.get("retriever")
        if not component_name:
            raise ValueError(
                "Retriever entry must have 'retriever' key with component name"
            )
        record = get_record("retrievers", component_name, registry_index)
        config_type = schema_builder.component_config_type("retrievers", record.name)
        config_value = {k: v for k, v in entry_dict.items() if k != "retriever"}
        if yaml_file_path and config_value and config_type is not None:
            config_value = _resolve_relative_paths(config_value, yaml_file_path)
        instance = instantiate_component(
            record,
            project_root,
            config_value if config_value else None,
            config_type=config_type,
        )
        builder.add_retriever(instance)

    retrieve_record = get_record(
        "retrieve_hydrators",
        retrieve_stage.hydrator,
        registry_index,
    )
    retrieve_config_type = schema_builder.component_config_type(
        "retrieve_hydrators", retrieve_record.name
    )
    builder.with_retrieve_hydrator(
        instantiate_component(
            retrieve_record,
            project_root,
            None,
            config_type=retrieve_config_type,
        )
    )

    for entry in process_stage.processors:
        entry_dict = _entry_to_dict(entry)
        component_name = entry_dict.get("processor")
        if not component_name:
            raise ValueError(
                "Processor entry must have 'processor' key with component name"
            )
        record = get_record("processors", component_name, registry_index)
        config_type = schema_builder.component_config_type("processors", record.name)
        config_value = {k: v for k, v in entry_dict.items() if k != "processor"}
        if yaml_file_path and config_value and config_type is not None:
            config_value = _resolve_relative_paths(config_value, yaml_file_path)
        builder.add_processor(
            instantiate_component(
                record,
                project_root,
                config_value if config_value else None,
                config_type=config_type,
            )
        )

    process_hydrator_record = get_record(
        "process_hydrators",
        process_stage.hydrator,
        registry_index,
    )
    process_config_type = schema_builder.component_config_type(
        "process_hydrators", process_hydrator_record.name
    )
    builder.with_process_hydrator(
        instantiate_component(
            process_hydrator_record,
            project_root,
            None,
            config_type=process_config_type,
        )
    )

    for entry in action_stage.actions:
        entry_dict = _entry_to_dict(entry)
        component_name = entry_dict.get("action")
        if not component_name:
            raise ValueError("Action entry must have 'action' key with component name")
        record = get_record("actions", component_name, registry_index)
        config_type = schema_builder.component_config_type("actions", record.name)
        config_value = {k: v for k, v in entry_dict.items() if k != "action"}
        if yaml_file_path and config_value and config_type is not None:
            config_value = _resolve_relative_paths(config_value, yaml_file_path)
        builder.add_action(
            instantiate_component(
                record,
                project_root,
                config_value if config_value else None,
                config_type=config_type,
            )
        )

    action_hydrator_record = get_record(
        "action_hydrators",
        action_stage.hydrator,
        registry_index,
    )
    action_config_type = schema_builder.component_config_type(
        "action_hydrators", action_hydrator_record.name
    )
    builder.with_action_hydrator(
        instantiate_component(
            action_hydrator_record,
            project_root,
            None,
            config_type=action_config_type,
        )
    )

    return builder
