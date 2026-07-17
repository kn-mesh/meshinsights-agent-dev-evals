"""RootExecutor for main-thread function routing.

Enables worker threads and child processes to execute functions
on the main thread, essential for libraries that aren't thread-safe.
Supports decorator, context manager, and explicit API patterns.

See docs/utilities.md for usage patterns and best practices.
"""

from __future__ import annotations

import functools
import logging
import multiprocessing
import os
import pickle
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

_logger = logging.getLogger(__name__)


class ExecutionContext(Enum):
    """Identifies where code is executing relative to the root."""

    ROOT = auto()  # Main process, main thread
    CHILD_THREAD = auto()  # Main process, worker thread
    CHILD_PROCESS = auto()  # Child process (any thread)


@dataclass
class ExecutionRequest:
    """Request to execute a function on the root thread."""

    request_id: str
    func: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    response_queue: (
        queue.Queue[ExecutionResponse] | multiprocessing.Queue[ExecutionResponse]
    )


@dataclass
class ExecutionResponse:
    """Response from root thread execution."""

    request_id: str
    success: bool
    result: Any = None
    exception: BaseException | None = None


class RootExecutor:
    """Executes functions on the main process/main thread from workers.

    This class provides a mechanism for worker threads and child processes
    to delegate function execution back to the root context, which is
    essential for libraries that are not thread-safe or process-safe.

    The executor uses a dual-queue architecture:
    - Thread queue (queue.Queue) for requests from child threads
    - Process queue (multiprocessing.Queue) for requests from child processes

    A background pump thread processes incoming requests and dispatches
    responses back to the callers.

    Attributes:
        _root_process_id: PID of the main process (set at initialization)
        _root_thread_id: Thread ID of the main thread
        _thread_request_queue: Queue for requests from child threads
        _process_request_queue: Queue for requests from child processes
        _running: Flag indicating if the executor is active
        _pump_thread: Background thread that processes requests
    """

    def __init__(self) -> None:
        """Initialize the root executor (must be called from main thread)."""
        self._root_process_id: int | None = None
        self._root_thread_id: int | None = None

        # Thread-safe queues for different contexts
        self._thread_request_queue: queue.Queue[ExecutionRequest] = queue.Queue()
        self._process_request_queue: multiprocessing.Queue[ExecutionRequest] | None = (
            None
        )

        # Lifecycle management
        self._running = False
        self._pump_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

    def start(self) -> None:
        """Start the executor service (must be called from main thread).

        Raises:
            RuntimeError: If not called from the main thread or already running.
        """
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("RootExecutor.start() must be called from main thread")

        if self._running:
            raise RuntimeError("RootExecutor is already running")

        self._root_process_id = os.getpid()
        self._root_thread_id = threading.get_ident()
        self._process_request_queue = multiprocessing.Queue()
        self._running = True
        self._shutdown_event.clear()

        # Start the request pump in a daemon thread
        self._pump_thread = threading.Thread(
            target=self._request_pump,
            name="RootExecutor-Pump",
            daemon=True,
        )
        self._pump_thread.start()

        _logger.info(
            "RootExecutor started on pid=%d thread=%d",
            self._root_process_id,
            self._root_thread_id,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the executor service gracefully.

        Args:
            timeout: Maximum seconds to wait for pending requests.
        """
        if not self._running:
            return

        self._running = False
        self._shutdown_event.set()

        if self._pump_thread is not None:
            self._pump_thread.join(timeout=timeout)

        # Clean up multiprocessing queue
        if self._process_request_queue is not None:
            try:
                self._process_request_queue.close()
                self._process_request_queue.join_thread()
            except Exception:
                pass

        _logger.info("RootExecutor stopped")

    def __enter__(self) -> RootExecutor:
        """Context manager entry."""
        self.start()
        # Also set as global default
        global _root_executor
        _root_executor = self
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        global _root_executor
        self.stop()
        if _root_executor is self:
            _root_executor = None

    def get_context(self) -> ExecutionContext:
        """Determine the current execution context.

        Returns:
            ExecutionContext indicating if we're in root, child thread,
            or child process.
        """
        current_pid = os.getpid()
        current_thread = threading.get_ident()

        if current_pid != self._root_process_id:
            return ExecutionContext.CHILD_PROCESS
        elif current_thread != self._root_thread_id:
            return ExecutionContext.CHILD_THREAD
        else:
            return ExecutionContext.ROOT

    def run(
        self,
        func: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        """Execute a function, routing to root if necessary.

        If called from the root context (main process + main thread),
        the function is executed directly. Otherwise, the call is
        queued for execution on the root thread.

        Args:
            func: The function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The return value of the function.

        Raises:
            RuntimeError: If executor is not running.
            Exception: Any exception raised by the function is re-raised.
        """
        context = self.get_context()

        if context == ExecutionContext.ROOT:
            # Already on root - execute directly
            return func(*args, **kwargs)

        if not self._running:
            raise RuntimeError(
                "RootExecutor is not running. Call start() before using."
            )

        if context == ExecutionContext.CHILD_THREAD:
            return self._execute_from_thread(func, args, kwargs)
        else:  # CHILD_PROCESS
            return self._execute_from_process(func, args, kwargs)

    def _execute_from_thread(
        self,
        func: Callable[..., T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        """Handle execution request from a child thread."""
        request_id = str(uuid.uuid4())
        response_queue: queue.Queue[ExecutionResponse] = queue.Queue()

        request = ExecutionRequest(
            request_id=request_id,
            func=func,
            args=args,
            kwargs=kwargs,
            response_queue=response_queue,
        )

        self._thread_request_queue.put(request)

        # Block until response arrives
        response = response_queue.get()

        if not response.success:
            if response.exception is not None:
                raise response.exception
            raise RuntimeError(f"Request {request_id} failed without exception")
        return response.result

    def _execute_from_process(
        self,
        func: Callable[..., T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        """Handle execution request from a child process."""
        if self._process_request_queue is None:
            raise RuntimeError("Process request queue not initialized")

        request_id = str(uuid.uuid4())
        response_queue: multiprocessing.Queue[ExecutionResponse] = (
            multiprocessing.Queue()
        )

        # Validate picklability before sending
        try:
            pickle.dumps(func)
            pickle.dumps(args)
            pickle.dumps(kwargs)
        except (pickle.PicklingError, TypeError) as e:
            raise ValueError(
                f"Function or arguments are not picklable: {e}. "
                "Ensure the function is defined at module level and all "
                "arguments are serializable."
            ) from e

        request = ExecutionRequest(
            request_id=request_id,
            func=func,
            args=args,
            kwargs=kwargs,
            response_queue=response_queue,
        )

        self._process_request_queue.put(request)

        # Block until response arrives
        response = response_queue.get()

        if not response.success:
            if response.exception is not None:
                raise response.exception
            raise RuntimeError(f"Request {request_id} failed without exception")
        return response.result

    def _request_pump(self) -> None:
        """Background thread that processes incoming requests.

        This runs in the main process but NOT the main thread. It
        processes requests from both thread and process queues.
        """
        while not self._shutdown_event.is_set():
            self._process_pending_requests()
            time.sleep(0.001)  # Small sleep to prevent busy-waiting

        # Process any remaining requests before shutdown
        self._process_pending_requests()

    def _process_pending_requests(self) -> None:
        """Process all pending requests from both queues."""
        # Process thread requests
        while True:
            try:
                request = self._thread_request_queue.get_nowait()
                self._execute_request(request)
            except queue.Empty:
                break

        # Process process requests
        if self._process_request_queue is not None:
            while True:
                try:
                    request = self._process_request_queue.get_nowait()
                    self._execute_request(request)
                except queue.Empty:
                    break
                except Exception as e:
                    _logger.error("Error getting process request: %s", e)
                    break

    def _execute_request(self, request: ExecutionRequest) -> None:
        """Execute a single request and send the response."""
        try:
            result = request.func(*request.args, **request.kwargs)
            response = ExecutionResponse(
                request_id=request.request_id,
                success=True,
                result=result,
            )
        except BaseException as e:
            response = ExecutionResponse(
                request_id=request.request_id,
                success=False,
                exception=e,
            )

        try:
            request.response_queue.put(response)
        except Exception as e:
            _logger.error(
                "Failed to send response for request %s: %s",
                request.request_id,
                e,
            )


# Module-level singleton instance
_root_executor: RootExecutor | None = None


def get_executor() -> RootExecutor:
    """Get the global RootExecutor instance.

    Raises:
        RuntimeError: If no executor has been initialized.
    """
    if _root_executor is None:
        raise RuntimeError("No RootExecutor initialized. Call initialize() first.")
    return _root_executor


def initialize() -> RootExecutor:
    """Initialize and start the global RootExecutor.

    Must be called from the main thread before spawning workers.

    Returns:
        The initialized RootExecutor instance.

    Raises:
        RuntimeError: If not called from main thread.
    """
    global _root_executor
    if _root_executor is not None and _root_executor._running:
        return _root_executor

    _root_executor = RootExecutor()
    _root_executor.start()
    return _root_executor


def shutdown() -> None:
    """Stop and clean up the global RootExecutor."""
    global _root_executor
    if _root_executor is not None:
        _root_executor.stop()
        _root_executor = None


def run(func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Execute a function via the global RootExecutor.

    Convenience function that delegates to the global executor instance.
    If called from the root context, executes directly. Otherwise,
    queues the call for execution on the root thread.

    Args:
        func: The function to execute.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The return value of the function.

    Raises:
        RuntimeError: If no executor has been initialized.
    """
    return get_executor().run(func, *args, **kwargs)


def bound(
    func: Callable[P, T] | None = None,
    *,
    executor: RootExecutor | None = None,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to automatically route function calls through RootExecutor.

    Can be used with or without parentheses:

        @bound
        def my_function():
            ...

        @bound(executor=custom_executor)
        def my_function():
            ...

    When the decorated function is called from the root context (main process
    + main thread), it executes directly. When called from a worker thread
    or child process, the call is automatically routed to the root thread.

    Args:
        func: The function to wrap (when used without parentheses).
        executor: Optional specific executor instance to use. If not provided,
            uses the global executor.

    Returns:
        Wrapped function that routes through the executor.

    Raises:
        RuntimeError: If no executor is available when the function is called.
    """

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            exec_instance = executor or _root_executor
            if exec_instance is None:
                raise RuntimeError(
                    "No RootExecutor available. Initialize with initialize() "
                    "or pass an explicit executor."
                )
            return exec_instance.run(fn, *args, **kwargs)

        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
