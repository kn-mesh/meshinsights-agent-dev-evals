"""Cross-cutting utilities for the Mesh Insights framework.

Provides thread-safe caching with singleflight semantics and a
RootExecutor for routing function calls to the main thread when
working with non-thread-safe libraries.

See docs/utilities.md for usage examples and API reference.
"""
# ruff: noqa: F401

from .cache_adapter import (
    cache,
    cached_method,
    resolved_path_key,
    resolved_path_key_from_args,
)
from .root_executor import (
    ExecutionContext,
    RootExecutor,
    bound,
    get_executor,
    initialize,
    run,
    shutdown,
)

# Module-level access for convenience
from . import root_executor

__all__ = [
    # Cache utilities
    "cache",
    "cached_method",
    "resolved_path_key",
    "resolved_path_key_from_args",
    # Root executor
    "ExecutionContext",
    "RootExecutor",
    "bound",
    "get_executor",
    "initialize",
    "run",
    "shutdown",
    "root_executor",
]
