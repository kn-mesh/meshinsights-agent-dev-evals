"""OpenTelemetry integration for mi-core.

Provides tracing helpers for pipeline components. OpenTelemetry API is a
required dependency; when no SDK is configured the API returns no-op
tracers automatically.

Architecture:
    - Separate TracerProvider with service.name=meshinsights-core (NOT set globally)
    - Tracer names: meshinsights.orchestrator, meshinsights.pipeline, etc.
    - Spans include attributes: component.layer=library
    - Reads trace context from global context (set by application) for unified traces
    - Exports spans independently with mi-core resource

Usage:
    from mi.core.utils.telemetry import get_tracer

    tracer = get_tracer("pipeline")
    with tracer.start_as_current_span("my.operation"):
        ...

See docs/utilities.md for telemetry configuration guidance.
"""

import logging
import os
from typing import Any

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Semantic conventions for mi-core spans
ATTR_COMPONENT_LAYER = "component.layer"
ATTR_COMPONENT_TYPE = "component.type"

logging.getLogger("opentelemetry.sdk.resources").setLevel(logging.CRITICAL)

_propagator = TraceContextTextMapPropagator()
_configured = False
_tracer_provider: Any = None
_bootstrapped = False


def _ensure_configured() -> None:
    """Ensure mi-core's library-local TracerProvider is configured.

    Uses OpenTelemetry SDK classes to create a separate provider with
    service.name=meshinsights-core. The SDK is imported lazily here
    because only the API package is a hard dependency — the SDK is
    provided by the application environment.
    """
    global _configured, _tracer_provider

    if _configured:
        return

    # Read OTLP endpoint from environment
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    try:
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logging.getLogger(__name__).debug(
            "OpenTelemetry SDK not installed; library-local TracerProvider disabled"
        )
        _configured = True
        return

    # Create resource for mi-core
    resource = Resource.create(
        {SERVICE_NAME: "meshinsights-core", SERVICE_VERSION: "0.5.2"},
    )

    # Configure tracing - DO NOT set globally, keep reference locally
    trace_provider = TracerProvider(resource=resource)

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # pyright: ignore[reportMissingImports]
                OTLPSpanExporter,
            )

            trace_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        except ImportError:
            logging.getLogger(__name__).warning(
                "OTLP trace exporter not available, traces will not be exported"
            )

    # Store provider reference locally - DO NOT call trace.set_tracer_provider()
    # This allows mi-core to have its own resource without overwriting application's provider
    _tracer_provider = trace_provider
    _configured = True


def get_tracer(
    component_name: str, *, use_library_resource: bool = False
) -> trace.Tracer:
    """Get a tracer for a mi-core component.

    By default uses the global TracerProvider (application's provider) so spans
    appear under the application's service. Set use_library_resource=True for
    mi-core internal components that should appear under
    service.name=meshinsights-core.

    Args:
        component_name: Component name (e.g., "pipeline", "orchestrator", "processor").
        use_library_resource: If True, use mi-core's TracerProvider with
            service.name=meshinsights-core. If False (default), use the global
            TracerProvider (application's).

    Returns:
        An OpenTelemetry tracer. Returns a no-op tracer when no SDK is configured.
    """
    tracer_name = f"meshinsights.{component_name}"

    if use_library_resource:
        _ensure_configured()
        if _tracer_provider is not None:
            return _tracer_provider.get_tracer(tracer_name)
        # SDK not available — fall through to global provider (API no-op)
    return trace.get_tracer_provider().get_tracer(tracer_name)


def get_current_span() -> trace.Span:
    """Get the current span from the active context."""
    return trace.get_current_span()


def set_span_error(span: trace.Span, exception: BaseException) -> None:
    """Record an exception on a span and set its status to ERROR.

    Centralizes the pattern of recording an exception and setting error
    status so callers don't need to import trace.Status / trace.StatusCode.

    Args:
        span: The span to mark as errored.
        exception: The exception to record.
    """
    span.record_exception(exception)
    span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


def bootstrap_telemetry() -> None:
    """Auto-detect and initialize application-level telemetry.

    Intended to be called once at application startup (e.g., by the CLI or an
    application entrypoint) — NOT by the library itself.

    Detection order:
        1. If ``logfire`` is installed (comes with the ``[ai]`` extra),
           call ``logfire.configure()``.  Logfire reads its own env vars
           (``LOGFIRE_TOKEN``, ``LOGFIRE_SEND_TO_LOGFIRE``, etc.) and sets
           the global TracerProvider.  When no token is present it still
           configures a local-only provider that instruments pydantic-ai
           and other integrations.
        2. Otherwise, if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set **and**
           the OpenTelemetry SDK is available, configure a basic global
           TracerProvider with OTLP export.
        3. If neither is available, no-op silently.

    This function is idempotent — subsequent calls are ignored.
    """
    global _bootstrapped

    if _bootstrapped:
        return
    _bootstrapped = True

    logger = logging.getLogger(__name__)

    # --- 1. Try Logfire (installed via [ai] extra) ---
    try:
        import logfire  # pyright: ignore[reportMissingImports]

        logfire.configure(
            send_to_logfire="if-token-present",
            console=False,
        )
        logger.debug("Telemetry bootstrapped via Logfire")
        return
    except ImportError:
        pass
    except Exception:
        logger.debug(
            "Logfire configure() failed, falling back to OTel SDK", exc_info=True
        )

    # --- 2. Fall back to plain OTel SDK with OTLP export ---
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.debug(
            "No OTEL_EXPORTER_OTLP_ENDPOINT set and Logfire unavailable; telemetry bootstrap skipped"
        )
        return

    try:
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME  # pyright: ignore[reportMissingImports]
        from opentelemetry.sdk.trace import TracerProvider  # pyright: ignore[reportMissingImports]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # pyright: ignore[reportMissingImports]
    except ImportError:
        logger.debug("OpenTelemetry SDK not installed; telemetry bootstrap skipped")
        return

    # Try HTTP exporter first (bundled with logfire / opentelemetry-exporter-otlp-proto-http),
    # fall back to gRPC exporter if available.
    exporter = None
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter as _HttpExporter,
        )  # pyright: ignore[reportMissingImports]

        exporter = _HttpExporter(endpoint=f"{endpoint}/v1/traces")
    except ImportError:
        pass

    if exporter is None:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # pyright: ignore[reportMissingImports]
                OTLPSpanExporter as _GrpcExporter,
            )

            exporter = _GrpcExporter(endpoint=endpoint, insecure=True)
        except ImportError:
            pass

    if exporter is None:
        logger.debug(
            "No OTLP exporter available (http or grpc); telemetry bootstrap skipped"
        )
        return

    resource = Resource.create({SERVICE_NAME: "meshinsights-pipeline"})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.debug("Telemetry bootstrapped via OTel SDK (OTLP endpoint: %s)", endpoint)


def inject_context() -> dict[str, str]:
    """Extract current trace context into a carrier dict for propagation.

    Use this to pass trace context to subprocesses or external services.

    Returns:
        Carrier containing traceparent header, or empty dict if no active trace.
    """
    carrier: dict[str, str] = {}
    _propagator.inject(carrier)
    return carrier


def extract_context(carrier: dict[str, str]) -> Any:
    """Restore trace context from a carrier dict.

    Use this in subprocesses to link spans back to the parent trace.

    Args:
        carrier: Dict containing traceparent header from inject_context().

    Returns:
        OpenTelemetry context object.
    """
    return _propagator.extract(carrier)
