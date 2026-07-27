"""Utility helpers for Mesh Insights core.

Exports schema utilities commonly used by retrievers.
"""
# ruff: noqa: F401

from .environment import bootstrap_environment
from .telemetry import (
    get_tracer,
    inject_context,
    extract_context,
    set_span_error,
    bootstrap_telemetry,
)

__all__: list[str] = [
    "bootstrap_environment",
    "get_tracer",
    "inject_context",
    "extract_context",
    "set_span_error",
    "bootstrap_telemetry",
]

try:
    import importlib.util

    if importlib.util.find_spec("pandas") is not None:
        from .typing import SchemaScalarType, apply_type_conversions, validate_schema

        __all__ += [
            "SchemaScalarType",
            "apply_type_conversions",
            "validate_schema",
        ]
except ImportError:
    pass
