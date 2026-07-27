"""Orchestrator for running pipelines at scale.

Processes multiple items in parallel using serial, threaded,
or process-based runtimes. Each item gets its own pipeline
instance and PipelineReceipt.

See docs/orchestrator.md for configuration and usage examples.
"""

from __future__ import annotations

import atexit
import copy
from concurrent.futures import (
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
import os
from typing import Callable, Iterable, TypeVar, Generic, Any, Literal, cast

from opentelemetry import context as otel_context, trace
from opentelemetry.trace import Span
from pydantic import BaseModel, Field

from mi.core.pipeline import Pipeline, PipelineConfig
from mi.core.pipeline_builder import PipelineBuilder
from mi.core.pipeline_receipt import PipelineReceipt
from mi.core.utils.environment import bootstrap_environment
from mi.core.utils.telemetry import (
    bootstrap_telemetry,
    get_current_span,
    get_tracer,
    set_span_error,
    inject_context,
    extract_context,
    ATTR_COMPONENT_LAYER,
)

# Application-provided hook called in spawned subprocesses to reconfigure
# telemetry (the global TracerProvider is NOT inherited across process
# boundaries with the 'spawn' start method).  Set via
# ``set_subprocess_telemetry_hook()`` before calling ``orchestrator.run()``.
_subprocess_telemetry_hook: Callable[[], None] | None = None


def set_subprocess_telemetry_hook(hook: Callable[[], None]) -> None:
    """Register a callback to reconfigure telemetry in spawned subprocesses.

    The hook is invoked once per subprocess before any pipeline runs. Use it
    to re-initialise the application's TracerProvider/LoggerProvider so that
    spans and logs are exported from worker processes.
    """
    global _subprocess_telemetry_hook
    _subprocess_telemetry_hook = hook


_tracer = get_tracer("orchestrator")

# Process-local storage for reusable process spans
# Key: PID, Value: tuple of (span, trace context)
_process_spans: dict[int, tuple[Span, Any]] = {}

# Thread span storage for reusable thread spans within a single orchestrator run
# Key: (trace_id, thread_id), Value: (span, thread_number)
# Using trace_id ensures fresh spans per orchestrator.run invocation
_thread_spans: dict[tuple[str, int], tuple[Span, int]] = {}
_next_thread_number = 0
_thread_span_lock = __import__("threading").Lock()


T = TypeVar("T", bound=Any, default=Any)
_U = TypeVar("_U", bound=Any, default=Any)


class OrchestratorConfig(BaseModel):
    """Configuration for the pipeline orchestrator.

    Attributes:
        name: Friendly identifier used for logging and receipts.
        runtime: Execution model used when running pipelines.
        error_action: Behavior when a pipeline run fails.
        max_workers: Maximum number of workers to use for threaded or process runtimes.
    """

    name: str = Field(
        default="pipeline_orchestrator", description="Name for this orchestrator"
    )
    runtime: Literal["serial", "threaded", "process"] = Field(
        default="serial",
        description="Execution model to use when running pipelines",
    )
    error_action: Literal["stop", "continue"] = Field(
        default="stop",
        description="Behavior when a pipeline run fails",
    )

    max_workers: int = Field(
        default=1,
        description="Maximum number of workers to use for threaded or process runtimes",
    )


class PipelineOrchestrator(Generic[T]):
    """Orchestrates running a pipeline builder across an iterable.

    Configure with a :class:`PipelineBuilder` and an adapter that converts each
    item into :class:`PipelineConfig`; then call :meth:`run` to execute with the
    selected runtime.
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        """Initialize the orchestrator.

        Args:
            config: Optional configuration for runtime behavior. Defaults to a
                new :class:`OrchestratorConfig` when omitted.
        """

        self._config = config
        self._builder: PipelineBuilder | None = None
        self._adapter: Callable[[T], PipelineConfig] | None = None

    def with_config(
        self,
        config: OrchestratorConfig,
        *,
        overwrite: bool = False,
    ) -> "PipelineOrchestrator[T]":
        """Attach or merge an orchestrator configuration.

        Args:
            config: Configuration to apply.
            overwrite: When ``True``, replace any existing configuration;
                otherwise merge set fields into the current config.

        Returns:
            PipelineOrchestrator[T]: The orchestrator for fluent chaining.
        """

        if overwrite or self._config is None:
            self._config = config
        else:
            updates = config.model_dump(exclude_unset=True)
            self._config = self._config.model_copy(update=updates)
        return self

    def with_builder(self, builder: PipelineBuilder) -> "PipelineOrchestrator[T]":
        """Assign the pipeline builder template used for all runs.

        Args:
            builder: A preconfigured :class:`PipelineBuilder` instance used to
                construct pipelines per item.

        Returns:
            PipelineOrchestrator[T]: The orchestrator for fluent chaining.
        """

        self._builder = builder
        return self

    def with_adapter(
        self,
        adapter: Callable[[T], PipelineConfig],
    ) -> "PipelineOrchestrator[T]":
        """Provide a function that maps each item to a PipelineConfig.

        Args:
            adapter: Callable that transforms each unit into a
                :class:`PipelineConfig`.

        Returns:
            PipelineOrchestrator[T]: The orchestrator for fluent chaining.
        """

        self._adapter = adapter
        return self

    def with_unit(self, unit: _U | type[_U]) -> "PipelineOrchestrator[_U]":
        """Type-narrow the orchestrator's input unit for type-checking.

        Args:
            unit: Example instance or type used purely for static analysis.

        Returns:
            PipelineOrchestrator[_U]: The orchestrator typed to the provided
                unit.
        """

        self = cast("PipelineOrchestrator[_U]", self)
        return cast("PipelineOrchestrator[_U]", self)

    @_tracer.start_as_current_span("orchestrator.run")
    def run(self, items: Iterable[T]) -> dict[T, PipelineReceipt]:
        """Run pipelines for each item according to the configured runtime.

        Args:
            items: Iterable of units to process. Each unit is converted to a
                :class:`PipelineConfig` via ``adapter`` and executed with the
                configured builder.

        Returns:
            dict[T, PipelineReceipt]: Mapping of each item to its pipeline
            receipt.

        Raises:
            ValueError: When required builder/adapter are missing or the runtime
                is unsupported.
            Exception: Propagated from pipeline execution when
                ``error_action`` is set to ``"stop"``.

        Notes:
            The returned mapping preserves the input ``items`` ordering when
            using the serial runtime; parallel runtimes may complete out of
            order but are keyed by item.
        """
        config = self._get_config()
        self._ensure_builder_and_adapter()

        # Convert to list to get count for tracing (iterables may be single-use)
        items_list = list(items)

        current_span = get_current_span()
        current_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
        current_span.set_attribute("orchestrator.name", config.name)
        current_span.set_attribute("orchestrator.runtime", config.runtime)
        current_span.set_attribute("orchestrator.error_action", config.error_action)
        current_span.set_attribute("orchestrator.item_count", len(items_list))

        if config.runtime == "serial":
            return self._run_serial(items_list)
        if config.runtime == "threaded":
            return self._run_threaded(
                items_list,
                max_workers=config.max_workers,
                error_action=config.error_action,
            )
        if config.runtime == "process":
            return self._run_process(
                items_list,
                max_workers=config.max_workers,
                error_action=config.error_action,
            )
        raise ValueError(f"Unsupported runtime: {config.runtime}")

    def _run_serial(self, items: Iterable[T]) -> dict[T, PipelineReceipt]:
        receipts: dict[T, PipelineReceipt] = {}

        for item in items:
            receipts[item] = self._run_pipeline_for_item(item)

        return receipts

    def _run_threaded(
        self,
        items: Iterable[T],
        *,
        max_workers: int,
        error_action: Literal["stop", "continue"],
    ) -> dict[T, PipelineReceipt]:
        receipts: dict[T, PipelineReceipt] = {}

        # Capture current trace context to propagate to worker threads
        parent_context = otel_context.get_current()

        # Get trace ID for this run to track which thread spans to end
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        trace_id = (
            format(span_context.trace_id, "032x")
            if span_context.is_valid
            else "no-trace"
        )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item: dict[Future[PipelineReceipt], T] = {
                executor.submit(
                    self._run_pipeline_in_thread, item, parent_context, trace_id
                ): item
                for item in items
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    receipts[item] = future.result()
                except Exception:
                    if error_action == "stop":
                        executor.shutdown(cancel_futures=True)
                        raise

        # End all thread spans for this trace and clean up
        _end_thread_spans_for_trace(trace_id)

        return receipts

    def _run_process(
        self,
        items: Iterable[T],
        *,
        max_workers: int,
        error_action: Literal["stop", "continue"],
    ) -> dict[T, PipelineReceipt]:
        if (
            self._builder is None or self._adapter is None
        ):  # Defensive check for static analyzers
            raise ValueError(
                "Builder and adapter must be set before running pipelines."
            )

        receipts: dict[T, PipelineReceipt] = {}

        # Extract current trace context to propagate to subprocesses
        trace_carrier = inject_context()

        # Determine whether subprocesses should bootstrap environment / telemetry.
        # The builder's config (if set) carries the bootstrap flags.
        _bootstrap_env = True
        _bootstrap_otel = True
        _environment = ".env"
        if self._builder is not None and self._builder._config is not None:
            _bootstrap_env = self._builder._config.bootstrap_environment
            _bootstrap_otel = self._builder._config.bootstrap_otel
            _environment = str(self._builder._config.environment)

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_item: dict[Future[PipelineReceipt], T] = {
                executor.submit(
                    _run_pipeline_in_subprocess,
                    self._builder,
                    self._adapter,
                    item,
                    trace_carrier,
                    _bootstrap_env,
                    _bootstrap_otel,
                    _environment,
                ): item
                for item in items
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    receipts[item] = future.result()
                except Exception:
                    if error_action == "stop":
                        executor.shutdown(cancel_futures=True)
                        raise

        return receipts

    def _run_pipeline_for_item(self, item: T) -> PipelineReceipt:
        """Run pipeline for an item in serial mode (no thread/process pool)."""
        if (
            self._builder is None or self._adapter is None
        ):  # Defensive check for static analyzers
            raise ValueError(
                "Builder and adapter must be set before running pipelines."
            )

        # Include item in span name so each pipeline is a distinct operation in Jaeger
        span_name = f"pipeline[{item}]"
        with _tracer.start_as_current_span(span_name) as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("orchestrator.item", str(item))

            item_config = self._adapter(item)
            temp_builder = copy.deepcopy(self._builder)
            temp_builder.with_config(item_config, overwrite=False)
            pipeline: Pipeline = temp_builder.build()

            try:
                receipt = pipeline.run()
                span.set_attribute("pipeline.success", receipt.success)
                return receipt
            except Exception as e:
                set_span_error(span, e)
                raise

    def _run_pipeline_in_thread(
        self, item: T, parent_context: Any, trace_id: str
    ) -> PipelineReceipt:
        """Run pipeline for an item in a thread pool with numbered thread spans."""

        if (
            self._builder is None or self._adapter is None
        ):  # Defensive check for static analyzers
            raise ValueError(
                "Builder and adapter must be set before running pipelines."
            )

        # Attach parent trace context to this thread
        token = otel_context.attach(parent_context)
        try:
            # Get or create thread span for this trace+thread combination
            thread_span = _get_or_create_thread_span(trace_id)

            tracer = get_tracer("orchestrator")

            # Make the thread span current for this item's execution
            with trace.use_span(thread_span, end_on_exit=False):
                # Create pipeline span as child of thread.pool span
                span_name = f"pipeline[{item}]"
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                    span.set_attribute("orchestrator.item", str(item))

                    item_config = self._adapter(item)
                    temp_builder = copy.deepcopy(self._builder)
                    temp_builder.with_config(item_config, overwrite=False)
                    pipeline: Pipeline = temp_builder.build()

                    try:
                        receipt = pipeline.run()
                        span.set_attribute("pipeline.success", receipt.success)
                        return receipt
                    except Exception as e:
                        set_span_error(span, e)
                        raise
        finally:
            # Detach context when done
            otel_context.detach(token)

    def _get_config(self) -> OrchestratorConfig:
        if self._config is None:
            self._config = OrchestratorConfig()

        if self._config.max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        return self._config

    def _ensure_builder_and_adapter(self) -> None:
        if self._builder is None:
            raise ValueError("Pipeline builder is not set. Call with_builder() first.")
        if self._adapter is None:
            raise ValueError("Adapter is not set. Call with_adapter() first.")


def _get_or_create_thread_span(trace_id: str) -> Span:
    """Get or create a reusable thread span for the current thread within a trace.

    Thread spans are created once per thread per orchestrator run and reused
    for all items processed by that thread. They are numbered sequentially
    (thread.pool[0], thread.pool[1], etc.) and ended when the orchestrator
    run completes.

    Args:
        trace_id: The trace ID for the current orchestrator run.

    Returns:
        Span: The thread span to use as parent for pipeline spans.
    """
    import threading

    global _next_thread_number

    thread_id = threading.get_ident()
    cache_key = (trace_id, thread_id)

    if cache_key not in _thread_spans:
        with _thread_span_lock:
            # Double-check after acquiring lock
            if cache_key not in _thread_spans:
                thread_number = _next_thread_number
                _next_thread_number += 1

                # Get tracer and create span as child of current context
                tracer = get_tracer("orchestrator")
                span = tracer.start_span(f"thread.pool[{thread_number}]")
                span.set_attribute(ATTR_COMPONENT_LAYER, "library")
                span.set_attribute("thread.number", thread_number)

                _thread_spans[cache_key] = (span, thread_number)

    return _thread_spans[cache_key][0]


def _end_thread_spans_for_trace(trace_id: str) -> None:
    """End all thread spans for a given trace and remove them from cache.

    Called when an orchestrator run completes to properly end all thread spans.

    Args:
        trace_id: The trace ID for the completed orchestrator run.
    """
    with _thread_span_lock:
        keys_to_remove = [key for key in _thread_spans if key[0] == trace_id]
        for key in keys_to_remove:
            span, _ = _thread_spans.pop(key)
            span.end()


def _get_or_create_process_span(trace_carrier: dict[str, str]) -> Span:
    """Get or create a reusable process span for the current process.

    The span is created once per process and reused for all items processed
    by that process. It is automatically closed when the process exits.

    Args:
        trace_carrier: Serialized trace context from parent process.

    Returns:
        Span: The process span that should be made current using trace.use_span().
    """
    pid = os.getpid()

    if pid not in _process_spans:
        # Restore trace context from parent process (links traces across services)
        # Note: The global TracerProvider is inherited from the parent process
        ctx = extract_context(trace_carrier)

        # Get a fresh tracer after SDK is configured
        tracer = get_tracer("orchestrator")

        # Create the process span (not as current span, we'll activate it per item)
        span = tracer.start_span(f"process.pool[{pid}]", context=ctx)
        _process_spans[pid] = (span, ctx)

        # Register cleanup to end span when process exits
        def _cleanup_process_span() -> None:
            if pid in _process_spans:
                span_to_end, _ = _process_spans[pid]
                span_to_end.end()
                del _process_spans[pid]

        atexit.register(_cleanup_process_span)

    return _process_spans[pid][0]


def _run_pipeline_in_subprocess(
    builder: PipelineBuilder,
    adapter: Callable[[Any], PipelineConfig],
    item: Any,
    trace_carrier: dict[str, str],
    bootstrap_env: bool = True,
    bootstrap_otel: bool = True,
    environment: str = ".env",
) -> PipelineReceipt:
    """Module-level helper so ProcessPoolExecutor can pickle the target.

    Args:
        builder: Pipeline builder template to clone for the item.
        adapter: Function mapping an item to a :class:`PipelineConfig`.
        item: Unit to convert into pipeline configuration.
        trace_carrier: Serialized trace context from parent process.
        bootstrap_env: Whether to load a dotenv file in this subprocess.
        bootstrap_otel: Whether to auto-bootstrap telemetry in this subprocess.
            When ``False``, automatic initialisation is skipped (the application's
            custom hook, if registered, is still honoured).
        environment: Path to the dotenv file (forwarded from PipelineConfig).

    Returns:
        PipelineReceipt: Receipt emitted by the executed pipeline.
    """
    # Bootstrap environment FIRST so that env vars (LOGFIRE_TOKEN,
    # OTEL_EXPORTER_OTLP_ENDPOINT, etc.) are available before telemetry.
    if bootstrap_env:
        bootstrap_environment(environment)

    # Reconfigure telemetry in this subprocess — the global TracerProvider is
    # NOT inherited across process boundaries with the 'spawn' start method.
    # Prefer the application's custom hook when registered; otherwise fall back
    # to bootstrap_telemetry() which re-detects Logfire / OTel env vars.
    if _subprocess_telemetry_hook is not None:
        _subprocess_telemetry_hook()
    elif bootstrap_otel:
        bootstrap_telemetry()

    # Get or create the reusable process span for this process
    process_span = _get_or_create_process_span(trace_carrier)

    # Make the process span current for this item's execution
    with trace.use_span(process_span):
        tracer = get_tracer("orchestrator")
        # Include item in span name so each pipeline is a distinct operation in Jaeger
        span_name = f"pipeline[{item}]"
        with tracer.start_as_current_span(span_name) as span:
            span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            span.set_attribute("orchestrator.item", str(item))

            item_config = adapter(item)
            temp_builder = copy.deepcopy(builder)
            temp_builder.with_config(item_config, overwrite=False)
            pipeline: Pipeline = temp_builder.build()

            try:
                receipt = pipeline.run()
                span.set_attribute("pipeline.success", receipt.success)
                return receipt
            except Exception as e:
                set_span_error(span, e)
                raise
