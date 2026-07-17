"""Thread-safe TTL cache with singleflight semantics.

Prevents duplicate work when multiple threads request the same
uncached value simultaneously. Supports custom key functions
and per-namespace isolation.

See docs/utilities.md for caching examples and configuration.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock
from typing import Any, Callable, Hashable, MutableMapping, ParamSpec, TypeVar, overload

from cachetools import TTLCache
from cachetools.keys import hashkey

from mi.core.utils.telemetry import get_current_span, get_tracer, ATTR_COMPONENT_LAYER

_tracer = get_tracer("cache", use_library_resource=True)

P = ParamSpec("P")
T = TypeVar("T")

_logger = logging.getLogger(__name__)

DEFAULT_MAXSIZE = 256
DEFAULT_TTL_SECONDS = 300.0
_MISS = object()

# Shared cache/lock and in-flight map
_SHARED_CACHE: MutableMapping[Hashable, Any] = TTLCache(
    maxsize=DEFAULT_MAXSIZE,
    ttl=DEFAULT_TTL_SECONDS,
    timer=time.monotonic,
)
_SHARED_LOCK = RLock()
_IN_FLIGHT: dict[Hashable, "_Flight"] = {}


@dataclass
class _Flight:
    event: Event
    error: BaseException | None = None


def resolved_path_key(path: str | Path, *extra: Hashable) -> Hashable:
    """Build a deterministic cache key from a path and extra dimensions.

    Paths are expanded and resolved so cache entries remain stable even when
    relative inputs differ.
    """
    return hashkey(str(Path(path).expanduser().resolve()), *extra)


def resolved_path_key_from_args(path_index: int = 0) -> Callable[..., Hashable]:
    """Factory to build a key_fn that normalizes a path argument without a lambda.

    Useful when wrapping functions with ``@cache``/``@cached_method`` so that
    filesystem paths are always cached by their absolute location.
    """

    def _builder(*args: Any, **kwargs: Any) -> Hashable:
        try:
            path = args[path_index]
        except IndexError as exc:
            raise ValueError("Path argument missing for cache key") from exc

        extras = args[:path_index] + args[path_index + 1 :]
        kwargs_items = tuple(sorted(kwargs.items()))
        return resolved_path_key(path, *extras, *kwargs_items)

    return _builder


def _build_key(
    namespace: str, key_fn: Callable[..., Hashable] | None
) -> Callable[..., Hashable]:
    if key_fn is None:

        def build(*args: Any, **kwargs: Any) -> Hashable:
            return hashkey(namespace, *args, **kwargs)

    else:

        def build(*args: Any, **kwargs: Any) -> Hashable:
            return hashkey(namespace, key_fn(*args, **kwargs))

    return build


def _try_get(key: Hashable) -> Any | object:
    try:
        return _SHARED_CACHE[key]
    except KeyError:
        return _MISS


@_tracer.start_as_current_span("cache.lookup")
def _singleflight_call(
    key: Hashable,
    namespace: str,
    log_misses: bool,
    loader: Callable[[], T],
) -> T:
    current_span = get_current_span()
    current_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
    current_span.set_attribute("cache.namespace", namespace)
    # Only use string representation if key is not a simple type
    key_str = str(key)[:100]  # Limit to 100 chars
    current_span.set_attribute("cache.key", key_str)

    with _SHARED_LOCK:
        cached = _try_get(key)
        if cached is not _MISS:
            _logger.debug("cache_hit namespace=%s key=%s", namespace, key)
            current_span.set_attribute("cache.hit", True)
            current_span.set_attribute("cache.is_inflight", False)
            current_span.add_event(
                "cache.hit", {"namespace": namespace, "key": key_str}
            )
            return cached  # type: ignore[return-value]
        flight = _IN_FLIGHT.get(key)
        if flight:
            wait_event = flight.event
            _logger.debug("cache_join namespace=%s key=%s", namespace, key)
            current_span.set_attribute("cache.hit", False)
            current_span.set_attribute("cache.is_inflight", True)
        else:
            flight = _Flight(event=Event())
            _IN_FLIGHT[key] = flight
            _logger.debug("cache_inflight_start namespace=%s key=%s", namespace, key)
            current_span.set_attribute("cache.hit", False)
            current_span.set_attribute("cache.is_inflight", False)
            current_span.add_event(
                "cache.miss", {"namespace": namespace, "key": key_str}
            )
            wait_event = None

    if wait_event:
        with _tracer.start_as_current_span("cache.wait") as wait_span:
            wait_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
            _logger.debug("cache_wait namespace=%s key=%s", namespace, key)
            wait_event.wait()
            with _SHARED_LOCK:
                if flight.error:
                    wait_span.record_exception(flight.error)
                    raise flight.error
                cached = _try_get(key)
                if cached is _MISS:
                    raise RuntimeError(
                        "Cache fill missing after singleflight completion"
                    )
                return cached  # type: ignore[return-value]

    if log_misses:
        _logger.debug("cache_miss namespace=%s key=%s", namespace, key)

    with _tracer.start_as_current_span("cache.fill") as fill_span:
        fill_span.set_attribute(ATTR_COMPONENT_LAYER, "library")
        try:
            _logger.debug("cache_fill_start namespace=%s key=%s", namespace, key)
            value = loader()
            fill_span.set_attribute("cache.fill_success", True)
        except BaseException as exc:
            with _SHARED_LOCK:
                flight.error = exc
                flight.event.set()
                _IN_FLIGHT.pop(key, None)
            _logger.debug(
                "cache_fill_error namespace=%s key=%s exc=%s", namespace, key, exc
            )
            fill_span.set_attribute("cache.fill_success", False)
            fill_span.record_exception(exc)
            raise

        with _SHARED_LOCK:
            _SHARED_CACHE[key] = value
            flight.event.set()
            _IN_FLIGHT.pop(key, None)
            _logger.debug("cache_fill_done namespace=%s key=%s", namespace, key)
            return value


@overload
def cache(
    func: Callable[P, T],
    *,
    key_fn: Callable[..., Hashable] | None = ...,
    namespace: str | None = ...,
    log_misses: bool = ...,
) -> Callable[P, T]: ...


@overload
def cache(
    func: None = ...,
    *,
    key_fn: Callable[..., Hashable] | None = ...,
    namespace: str | None = ...,
    log_misses: bool = ...,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def cache(
    func: Callable[P, T] | None = None,
    *,
    key_fn: Callable[..., Hashable] | None = None,
    namespace: str | None = None,
    log_misses: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]] | Callable[P, T]:
    """Decorator for functions using the shared TTL cache with singleflight.

    The wrapped function will:
    - Build a cache key from ``namespace`` and the provided ``key_fn`` (or args)
    - Return cached values when available
    - Coordinate concurrent callers to the same key so only one loader runs

    Attach ``.cache_clear()`` to the wrapped function to flush the shared cache.
    """

    def wrapper(target: Callable[P, T]) -> Callable[P, T]:
        key_builder = _build_key(namespace or target.__qualname__, key_fn)

        def wrapped(*args: P.args, **kwargs: P.kwargs) -> T:
            key = key_builder(*args, **kwargs)
            return _singleflight_call(
                key=key,
                namespace=namespace or target.__qualname__,
                log_misses=log_misses,
                loader=lambda: target(*args, **kwargs),
            )

        setattr(wrapped, "cache_clear", _SHARED_CACHE.clear)
        return wrapped

    if func is not None:
        return wrapper(func)
    return wrapper


def cached_method(
    *,
    key_fn: Callable[..., Hashable] | None = None,
    namespace: str | None = None,
    log_misses: bool = False,
) -> Callable[[Callable[P, T]], Callable[..., T]]:
    """Decorator for methods using the shared TTL cache with singleflight.

    Behaves like :func:`cache` but includes ``self`` in the cache key, making it
    suitable for instance methods where per-instance memoization is desired.
    """

    def decorator(target: Callable[P, T]) -> Callable[..., T]:
        key_builder = _build_key(namespace or target.__qualname__, key_fn)

        def wrapped(self: Any, *args: P.args, **kwargs: P.kwargs) -> T:
            key = key_builder(self, *args, **kwargs)
            return _singleflight_call(
                key=key,
                namespace=namespace or target.__qualname__,
                log_misses=log_misses,
                loader=lambda: target(self, *args, **kwargs),  # pyright: ignore[reportCallIssue]
            )

        setattr(wrapped, "cache_clear", _SHARED_CACHE.clear)
        return wrapped

    return decorator
