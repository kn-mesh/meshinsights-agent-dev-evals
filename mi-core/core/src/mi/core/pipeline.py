"""Pipeline execution engine for the Mesh Insights framework.

Coordinates the retrieve, process, and act stages, returning a
PipelineReceipt with timing, errors, and metadata for each stage.

See docs/pipeline-builder.md for usage examples.
"""

import logging
import time
from pathlib import Path
from typing import Generic, Literal, TypeVar
from uuid import uuid4

try:
    from rich.logging import RichHandler
except ImportError:  # pragma: no cover - optional dependency
    RichHandler = None  # type: ignore[misc,assignment]

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mi.core.utils.environment import bootstrap_environment
from mi.core.utils.telemetry import (
    bootstrap_telemetry,
    get_current_span,
    get_tracer,
    report_pipeline_error,
    set_span_error,
    ATTR_COMPONENT_LAYER,
)
from mi.core.objects import ActionDataObject, ProcessDataObject, RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt, StageReceipt
from mi.core.retrievers import BaseRetriever
from mi.core.actions import BaseAction
from mi.core.processors import BaseProcessor
from mi.core.hydrators import BaseHydrator

_tracer = get_tracer("pipeline")

PDO = TypeVar("PDO", bound=ProcessDataObject, default=ProcessDataObject)
ADO = TypeVar("ADO", bound=ActionDataObject, default=ActionDataObject)


def _record_stage_exception(stage_receipt: StageReceipt, error: Exception) -> None:
    """Attach a bounded exception chain and provider diagnostics to a receipt."""
    chain: list[dict[str, str | int]] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        entry: dict[str, str | int] = {
            "exception_type": type(current).__name__,
            "message": str(current),
        }
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int):
            entry["status_code"] = status_code
        request_id = getattr(current, "request_id", None)
        if isinstance(request_id, str) and request_id:
            entry["request_id"] = request_id
        chain.append(entry)
        current = current.__cause__ or current.__context__
    stage_receipt.set_metadata("error_details", {"exception_chain": chain})


class PipelineMetadata(BaseModel):
    """Runtime metadata passed to all pipeline components.

    This model is threaded through retrievers, processors, actions, and hydrators
    so components can access execution-specific context (device IDs, tenant
    identifiers, feature flags, etc.). Extend this class to add strongly typed
    fields for your domain.

    Attributes:
        unit (str): Identifier for the unit being processed (e.g., device_id,
            tenant_id, or customer_id). This is the primary identifier for the
            pipeline execution context and is frequently used by retrievers to
            filter data.
        model_extra (dict[str, Any]): Additional metadata fields are permitted.
            Unknown keys are allowed and logged to help users define custom
            subclasses when stricter typing is required.

    Example:
        >>> metadata = PipelineMetadata(unit="device-123")
        >>> metadata.unit
        'device-123'
    """

    unit: str = Field(
        default="default", description="Identifier for the unit being processed"
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _warn_extra_fields(self) -> "PipelineMetadata":
        """Log a warning if extra fields are provided."""
        if self.model_extra:
            extra_keys = ", ".join(self.model_extra.keys())
            logger = logging.getLogger("meshinsights.pipeline")
            logger.warning(
                f"Unknown metadata fields will be ignored: {extra_keys}. "
                f"Define a custom PipelineMetadata subclass to use these fields."
            )
        return self


class PipelineConfig(BaseModel):
    """Configuration describing pipeline metadata and runtime behavior.

    Attributes:
        name (str): Identifier for the pipeline; used for logging namespaces.
        version (str): Semantic version displayed in receipts.
        logger (PipelineConfig.LoggerConfig): Nested logging configuration.
        error_action (Literal["stop", "continue", "skip"]): Determines how
            exceptions are handled.
        ephermeral_objects (bool | EphermeralObjectsConfig): Controls whether
            intermediate data objects should be discarded to reduce memory.
        environment (str | Literal["development"]): Environment label.

    Example:
        >>> PipelineConfig(name="demo").model_dump()["name"]
        'demo'
    """

    # ========== Metadata ==========
    name: str = Field(default="default_pipeline", description="Name of the pipeline")
    version: str = Field(default="0.0.1", description="Version of the pipeline")

    # ========== Top Level Config ==========
    class LoggerConfig(BaseModel):
        """Logger settings applied when the pipeline initializes a logger.

        Attributes:
            level (Literal["DEBUG", ...]): Logging verbosity.
            outfile (str | Path): Destination file relative to project root when
                no separators are included.
            format (str | None): Optional custom logging format string. Defaults to
                include timestamp, severity, logger name, and message.

        Example:
            >>> PipelineConfig.LoggerConfig(level="DEBUG").level
            'DEBUG'
        """

        level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
            default="INFO", description="Default logging level for the pipeline"
        )
        outfile: str | Path | None = Field(default=None, description="Log file path")
        format: str | None = Field(
            default="%(asctime)s %(levelname)s %(name)s %(message)s",
            description="Log message format",
        )

    class EphermeralObjectsConfig(BaseModel):
        """Flags determining whether to delete hydrated objects post-stage.

        Example:
            >>> PipelineConfig.EphermeralObjectsConfig(process=False).process
            False
        """

        process: bool = Field(
            default=True, description="Whether to delete process dataobject"
        )
        action: bool = Field(
            default=True, description="Whether to delete action dataobject"
        )

    logger: LoggerConfig = Field(
        default_factory=LoggerConfig,
        description="Logger configuration for the pipeline",
    )
    error_action: Literal["stop", "continue", "skip"] = Field(
        default="stop", description="Action to take on error"
    )
    ephermeral_objects: bool | EphermeralObjectsConfig = Field(
        default=True, description="Whether to delete ephermeral objects"
    )
    bootstrap_environment: bool = Field(
        default=True,
        description=(
            "When True, the pipeline will load a dotenv file (specified by "
            "the ``environment`` field) into ``os.environ`` before any "
            "pipeline stages or telemetry initialisation runs.  Set to "
            "False to skip automatic dotenv loading — useful when the "
            "host application manages its own environment setup."
        ),
    )
    bootstrap_otel: bool = Field(
        default=True,
        description=(
            "When True, the CLI (and bootstrap_telemetry()) will auto-detect "
            "and initialize Logfire or OTel SDK at startup. Set to False to "
            "prevent automatic telemetry initialization — useful when the "
            "host application manages its own TracerProvider."
        ),
    )
    environment: Path | Literal[".env"] = Field(
        default=".env",
        description="Path to the dotenv file loaded when bootstrap_environment is True.",
    )
    metadata: PipelineMetadata = Field(
        default_factory=PipelineMetadata,
        description="Runtime metadata passed to all pipeline components",
    )


class Pipeline(Generic[PDO, ADO]):
    """Runtime coordinator that executes the retrieve, process, and act stages.

    The pipeline enforces stage ordering, ensures each component shares a logger
    namespace, and records structured telemetry via :class:`PipelineReceipt`.
    Most users construct pipelines through :class:`PipelineBuilder` rather than
    calling this constructor directly.

    Example:
        >>> from mi.core.pipeline import PipelineConfig
        >>> # Instances would normally come from PipelineBuilder
        >>> # pipeline = Pipeline(... )  # doctest: +SKIP
    """

    # ========== Pipeline Metadata ==========
    config: PipelineConfig
    logger: logging.Logger
    receipt: PipelineReceipt

    # ========== Retrieval Stage ==========
    retrievers: list[BaseRetriever]
    retrieve_hydrator: BaseHydrator[RetrieverDataObject, PDO]

    # ========== Processing Stage ==========
    processors: list[BaseProcessor[PDO]]
    process_hydrator: BaseHydrator[PDO, ADO]

    # ========== Action Stage ==========
    actions: list[BaseAction[ADO]]
    action_hydrator: BaseHydrator[ADO, None]

    def __init__(
        self,
        retrievers: list[BaseRetriever],
        processors: list[BaseProcessor[PDO]],
        actions: list[BaseAction[ADO]],
        retrieve_hydrator: BaseHydrator[RetrieverDataObject, PDO],
        process_hydrator: BaseHydrator[PDO, ADO],
        action_hydrator: BaseHydrator[ADO, None],
        config: PipelineConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """Create a pipeline with the supplied stage components.

        Args:
            retrievers (list[BaseRetriever]): Ordered list of retrievers that
                fetch raw data.
            processors (list[BaseProcessor[PDO]]): Ordered processors that
                mutate :class:`ProcessDataObject` instances.
            actions (list[BaseAction[ADO]]): Actions executed during the act
                stage.
            retrieve_hydrator (BaseHydrator[RetrieverDataObject, PDO]): Hydrator
                bridging retrieval output to process objects.
            process_hydrator (BaseHydrator[PDO, ADO]): Hydrator bridging process
                output to action objects.
            action_hydrator (BaseHydrator[ADO, None]): Final hydrator invoked
                after actions finish.
            config (PipelineConfig | None): Optional pipeline configuration.
                Defaults to :class:`PipelineConfig`.
            logger (logging.Logger | None): Pre-configured logger. When absent,
                a logger is created using ``config.logger`` values.

        Example:
            >>> # The constructor is typically invoked by PipelineBuilder
            >>> # pipeline = Pipeline([...])  # doctest: +SKIP
        """

        self.retrievers = retrievers
        self.processors = processors
        self.actions = actions
        self.retrieve_hydrator = retrieve_hydrator
        self.process_hydrator = process_hydrator
        self.action_hydrator = action_hydrator
        self.config = config or PipelineConfig()

        # Set up logger from config if not provided
        if logger is not None:
            self.logger = logger
        else:
            self.logger = logging.getLogger(self.config.name)
            # Configure logger if it hasn't been configured yet
            if not self.logger.handlers:
                # Prevent logs from bubbling to root (avoids duplicate console output)
                self.logger.propagate = False
                self.logger.setLevel(
                    getattr(logging, self.config.logger.level.upper(), logging.INFO)
                )
                formatter = (
                    logging.Formatter(self.config.logger.format)
                    if self.config.logger.format
                    else None
                )

                # Add console handler (prefer RichHandler for colorized output)
                if RichHandler is not None:
                    console_handler: logging.Handler = RichHandler(
                        markup=True,
                        rich_tracebacks=False,
                        show_time=True,
                        show_level=True,
                        show_path=False,
                    )
                else:
                    console_handler = logging.StreamHandler()
                    if formatter:
                        console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)

                # If outfile is not set, default to "<name>.log"
                outfile = self.config.logger.outfile or f"{self.config.name}.log"
                log_path = self._resolve_log_path(outfile)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.FileHandler(log_path)
                if formatter:
                    file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

        # Receipt will be created fresh for each run() call
        self.receipt = self._create_receipt()

        # Set up shared logger context for all components
        self._setup_component_loggers()

    def _setup_component_loggers(self) -> None:
        """Set up child loggers for all pipeline components to share context.

        Components inherit the pipeline logger namespace so log levels,
        handlers, and formatting remain consistent across stages.

        Example:
            >>> # Typically called internally after initialization
            >>> # pipeline._setup_component_loggers()  # doctest: +SKIP
        """
        # Set up retrievers
        for retriever in self.retrievers:
            retriever.logger = self.logger.getChild(retriever.logger.name)  # pyright: ignore[reportAttributeAccessIssue]

        # Set up processors
        for processor in self.processors:
            processor.logger = self.logger.getChild(processor.logger.name)

        # Set up actions
        for action in self.actions:
            action.logger = self.logger.getChild(action.logger.name)

        # Set up hydrators
        self.retrieve_hydrator.logger = self.logger.getChild(
            self.retrieve_hydrator.logger.name
        )
        self.process_hydrator.logger = self.logger.getChild(
            self.process_hydrator.logger.name
        )
        self.action_hydrator.logger = self.logger.getChild(
            self.action_hydrator.logger.name
        )

    def _resolve_log_path(self, outfile: str | Path) -> Path:
        """Resolve a log file destination relative to the project root.

        Args:
            outfile (str | Path): Path or filename defined in the config.

        Returns:
            Path: Absolute path where log records should be written.

        Example:
            >>> pipeline = object.__new__(Pipeline)  # doctest: +SKIP
            >>> pipeline._resolve_log_path("pipeline.log").name  # doctest: +SKIP
            'pipeline.log'
        """

        from mi.core.registry.utils import find_project_root

        outfile_path = Path(outfile)

        # If it's just a filename (no path separators), put it in .insights/logs/
        if "/" not in str(outfile_path) and "\\" not in str(outfile_path):
            project_root = find_project_root()
            log_dir = project_root / ".insights" / "logs"
            return log_dir / outfile_path

        # If it has a path, use it as-is (absolute or relative to current working directory)
        return Path(outfile_path).resolve()

    def _create_receipt(self) -> PipelineReceipt:
        """Create a new pipeline receipt for a run.

        Returns:
            PipelineReceipt: A new receipt instance with unique pipeline_id and config values.

        Notes:
            Copies key configuration values onto the receipt so serialized
            receipts are self-describing when viewed outside the runtime.

        Example:
            >>> # Typically called internally by run()
            >>> # receipt = pipeline._create_receipt()  # doctest: +SKIP
        """
        receipt = PipelineReceipt(pipeline_id=str(uuid4()))
        receipt.set_config("name", self.config.name)
        receipt.set_config("version", self.config.version)
        receipt.set_config("unit", self.config.metadata.unit)
        receipt.set_config("environment", self.config.environment)
        receipt.set_config("error_action", self.config.error_action)
        self.receipt = receipt
        return receipt

    @_tracer.start_as_current_span("pipeline.run")
    def run(self) -> PipelineReceipt:
        """Execute all pipeline stages sequentially.

        Returns:
            PipelineReceipt: Structured record describing the run.

        Raises:
            Exception: Re-raises the first exception when ``error_action`` is
                set to ``"stop"``.

        Notes:
            Exceptions are logged and recorded on the receipt even when the
            pipeline continues.

        Example:
            >>> # Typically triggered via PipelineBuilder
            >>> # receipt = pipeline.run()  # doctest: +SKIP
        """

        # --- Bootstrap environment before anything else ---
        # Environment variables must be available before telemetry reads
        # LOGFIRE_TOKEN, OTEL_EXPORTER_OTLP_ENDPOINT, etc.
        if self.config.bootstrap_environment:
            bootstrap_environment(self.config.environment)
        if self.config.bootstrap_otel:
            bootstrap_telemetry()

        current_span = get_current_span()
        current_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
        current_span.set_attribute("pipeline.name", self.config.name)
        current_span.set_attribute("pipeline.unit", self.config.metadata.unit)
        current_span.set_attribute("pipeline.version", self.config.version)
        current_span.set_attribute("pipeline.error_action", self.config.error_action)

        # Create a new receipt for this run to ensure atomicity
        self._create_receipt()

        overall_start = time.time()

        try:
            # Stage 1: Retrieve
            temp_retrieve_data = self._stage_retrieve()
            with _tracer.start_as_current_span(self.retrieve_hydrator.name) as h_span:
                h_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                h_span.set_attribute("hydrator.name", self.retrieve_hydrator.name)
                temp_process_data = self.retrieve_hydrator.hydrate(
                    temp_retrieve_data, self.receipt, metadata=self.config.metadata
                )
            del temp_retrieve_data

            # Stage 2: Process
            temp_process_data = self._stage_process(temp_process_data)
            with _tracer.start_as_current_span(self.process_hydrator.name) as h_span:
                h_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                h_span.set_attribute("hydrator.name", self.process_hydrator.name)
                temp_action_data = self.process_hydrator.hydrate(
                    temp_process_data, self.receipt, metadata=self.config.metadata
                )
            del temp_process_data

            # Stage 3: Act
            temp_action_data = self._stage_act(temp_action_data)
            with _tracer.start_as_current_span(self.action_hydrator.name) as h_span:
                h_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                h_span.set_attribute("hydrator.name", self.action_hydrator.name)
                self.action_hydrator.hydrate(
                    temp_action_data, self.receipt, metadata=self.config.metadata
                )
            del temp_action_data

            self.receipt.success = True
            current_span.set_attribute("pipeline.success", True)

        except Exception as e:
            set_span_error(current_span, e)
            report_pipeline_error(
                e,
                pipeline_name=self.config.name,
                pipeline_unit=self.config.metadata.unit,
                stage="pipeline",
            )
            self.logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            self.receipt.success = False
            current_span.set_attribute("pipeline.success", False)
            if self.config.error_action == "stop":
                raise

        finally:
            self.receipt.total_execution_time_seconds = time.time() - overall_start
            current_span.set_attribute(
                "pipeline.duration_seconds", self.receipt.total_execution_time_seconds
            )

        return self.receipt

    def _stage_retrieve(self) -> RetrieverDataObject:
        """Execute all retrievers and capture the retrieve stage receipt.

        Returns:
            RetrieverDataObject: Aggregated retrieval results grouped by adapter
                and scope.

        Raises:
            Exception: Propagates retriever or hydrator errors when the pipeline
                is configured to stop on failure.

        Notes:
            Always writes a :class:`StageReceipt` to ``receipt.retrieve_receipt``
            with timing and any captured metadata.

        Example:
            >>> # Internal helper used by run(); not typically called directly.
            >>> # pipeline._stage_retrieve()  # doctest: +SKIP
        """
        with _tracer.start_as_current_span("pipeline.stage.retrieve") as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("stage.name", "retrieve")
            span.set_attribute("retriever.count", len(self.retrievers))

            stage_start = time.time()
            stage_receipt = StageReceipt(
                stage_name="retrieve",
                success=False,
                execution_time_seconds=0.0,
            )

            retrieve_data = RetrieverDataObject()

            try:
                self.logger.info(
                    f"Starting retrieve stage: {len(self.retrievers)} retrievers"
                )

                for retriever in self.retrievers:
                    with _tracer.start_as_current_span(retriever.name) as r_span:
                        r_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                        r_span.set_attribute("retriever.name", retriever.name)
                        r_span.set_attribute("retriever.scope", retriever.scope)
                        self.logger.debug(f"Running retriever: {retriever.name}")
                        retrieve_data[retriever.name][retriever.scope] = (
                            retriever.retrieve(metadata=self.config.metadata)
                        )

                stage_receipt.success = True
                stage_receipt.set_metadata(
                    "retriever_name", [r.name for r in self.retrievers]
                )
                span.set_attribute("retriever.names", [r.name for r in self.retrievers])

                self.logger.info("Retrieve stage completed")

            except Exception as e:
                set_span_error(span, e)
                report_pipeline_error(
                    e,
                    pipeline_name=self.config.name,
                    pipeline_unit=self.config.metadata.unit,
                    stage="retrieve",
                )
                self.logger.error(f"Retrieve stage failed: {e}", exc_info=True)
                stage_receipt.error = str(e)
                _record_stage_exception(stage_receipt, e)
                stage_receipt.success = False
                if self.config.error_action == "stop":
                    raise

            finally:
                stage_receipt.execution_time_seconds = time.time() - stage_start
                span.set_attribute(
                    "stage.duration_seconds", stage_receipt.execution_time_seconds
                )
                self.receipt.retrieve_receipt = stage_receipt

            return retrieve_data

    def _stage_process(
        self,
        process_data: PDO,
    ) -> PDO:
        """Run the process stage using the configured processors.

        Args:
            process_data (PDO): Input process data object.

        Returns:
            PDO: Mutated process data object for later hydrators or actions.

        Notes:
            Writes a :class:`StageReceipt` to ``receipt.process_receipt`` even
            when an exception is raised.

        Example:
            >>> # Internal helper invoked by run()
            >>> # pipeline._stage_process(ProcessDataObject())  # doctest: +SKIP
        """
        with _tracer.start_as_current_span("pipeline.stage.process") as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("stage.name", "process")
            span.set_attribute("processor.count", len(self.processors))

            stage_start = time.time()
            stage_receipt = StageReceipt(
                stage_name="process",
                success=False,
                execution_time_seconds=0.0,
            )

            try:
                self.logger.info(
                    f"Starting process stage: {len(self.processors)} processors"
                )

                for processor in self.processors:
                    with _tracer.start_as_current_span(processor.name) as p_span:
                        p_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                        p_span.set_attribute("processor.name", processor.name)
                        self.logger.debug(f"Running processor: {processor.name}")
                        processor(process_data, metadata=self.config.metadata)

                stage_receipt.success = True
                stage_receipt.set_metadata("processor_count", len(self.processors))
                stage_receipt.set_metadata(
                    "processor_names", [p.name for p in self.processors]
                )
                span.set_attribute("processor.names", [p.name for p in self.processors])

                self.logger.info("Process stage completed")

            except Exception as e:
                set_span_error(span, e)
                report_pipeline_error(
                    e,
                    pipeline_name=self.config.name,
                    pipeline_unit=self.config.metadata.unit,
                    stage="process",
                )
                self.logger.error(f"Process stage failed: {e}", exc_info=True)
                stage_receipt.error = str(e)
                _record_stage_exception(stage_receipt, e)
                stage_receipt.success = False
                if self.config.error_action == "stop":
                    raise

            finally:
                execution_telemetry = process_data.get_execution_telemetry()
                if execution_telemetry is not None:
                    stage_receipt.set_metadata(
                        "execution_telemetry", execution_telemetry
                    )
                execution_review = process_data.get_execution_review()
                if execution_review is not None:
                    stage_receipt.set_metadata("execution_review", execution_review)
                stage_receipt.execution_time_seconds = time.time() - stage_start
                span.set_attribute(
                    "stage.duration_seconds", stage_receipt.execution_time_seconds
                )
                self.receipt.process_receipt = stage_receipt

            return process_data

    def _stage_act(
        self,
        action_data: ADO,
    ) -> ADO:
        """Execute actions and populate the act stage receipt.

        Args:
            action_data (ADO): Input action data object.

        Returns:
            ADO: The same action data object after all actions run.

        Notes:
            Writes a :class:`StageReceipt` to ``receipt.act_receipt`` capturing
            timing, action names, and errors if they occur.

        Example:
            >>> # Internal helper invoked by run()
            >>> # pipeline._stage_act(ActionDataObject())  # doctest: +SKIP
        """
        with _tracer.start_as_current_span("pipeline.stage.act") as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("stage.name", "act")
            span.set_attribute("action.count", len(self.actions))

            stage_start = time.time()
            stage_receipt = StageReceipt(
                stage_name="act",
                success=False,
                execution_time_seconds=0.0,
            )

            try:
                self.logger.info(f"Starting act stage: {len(self.actions)} actions")

                for action in self.actions:
                    with _tracer.start_as_current_span(action.name) as a_span:
                        a_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                        a_span.set_attribute("action.name", action.name)
                        self.logger.debug(f"Running action: {action.name}")
                        action.act(action_data, metadata=self.config.metadata)

                stage_receipt.success = True
                stage_receipt.set_metadata(
                    "action_name", [a.name for a in self.actions]
                )
                span.set_attribute("action.names", [a.name for a in self.actions])

                self.logger.info("Act stage completed")

            except Exception as e:
                set_span_error(span, e)
                report_pipeline_error(
                    e,
                    pipeline_name=self.config.name,
                    pipeline_unit=self.config.metadata.unit,
                    stage="act",
                )
                self.logger.error(f"Act stage failed: {e}", exc_info=True)
                stage_receipt.error = str(e)
                _record_stage_exception(stage_receipt, e)
                stage_receipt.success = False
                if self.config.error_action == "stop":
                    raise

            finally:
                stage_receipt.execution_time_seconds = time.time() - stage_start
                span.set_attribute(
                    "stage.duration_seconds", stage_receipt.execution_time_seconds
                )
                self.receipt.act_receipt = stage_receipt

            return action_data
