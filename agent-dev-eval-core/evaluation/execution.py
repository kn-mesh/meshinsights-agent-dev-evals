"""Bounded repeated execution across serial, thread, and process runtimes."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass
import logging
import time
from typing import Generic, Literal, TypeVar


RuntimeType = Literal["serial", "threaded", "process"]
ErrorActionType = Literal["stop", "continue"]
T = TypeVar("T")
R = TypeVar("R")


class ExecutionCancelledError(RuntimeError):
    """A planned attempt was not started after stop-on-error was triggered."""


class EvaluationInterruptedError(KeyboardInterrupt):
    """Cooperative operator interruption after durable terminal callbacks."""


@dataclass(frozen=True, slots=True)
class RepeatedEvalExecutorConfig:
    """Configuration for bounded repeated execution."""

    runtime: RuntimeType = "serial"
    max_workers: int = 1
    error_action: ErrorActionType = "continue"
    pending_heartbeat_seconds: float = 30.0
    cancellation_grace_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.runtime not in {"serial", "threaded", "process"}:
            raise ValueError(f"Unsupported runtime: {self.runtime}.")
        if self.error_action not in {"stop", "continue"}:
            raise ValueError(f"Unsupported error_action: {self.error_action}.")
        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1.")
        if self.pending_heartbeat_seconds <= 0:
            raise ValueError("pending_heartbeat_seconds must be greater than 0.")
        if self.cancellation_grace_seconds < 0:
            raise ValueError("cancellation_grace_seconds must be non-negative.")


@dataclass(frozen=True, slots=True)
class RepeatedEvalWorkItem(Generic[T]):
    """One planned attempt for an arbitrary evaluation item."""

    item_id: str
    payload: T
    attempt_index: int


@dataclass(frozen=True, slots=True)
class RepeatedEvalRecord(Generic[T, R]):
    """One terminal result and its executor-observed duration."""

    work_item: RepeatedEvalWorkItem[T]
    result: R
    duration_seconds: float


FailureBuilder = Callable[[RepeatedEvalWorkItem[T], str, Exception | None, float], R]
TerminalCallback = Callable[[RepeatedEvalRecord[T, R]], None]


class RepeatedEvalExecutor(Generic[T, R]):
    """Execute every planned attempt and return deterministic terminal records."""

    def __init__(
        self,
        config: RepeatedEvalExecutorConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._logger = logger or logging.getLogger(__name__)

    def run(
        self,
        items: Iterable[T],
        *,
        attempts_per_item: int,
        get_item_id: Callable[[T], str],
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: FailureBuilder[T, R],
        has_error: Callable[[R], bool],
        on_completed: TerminalCallback[T, R] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute repeated work with bounded scheduling and complete accounting."""
        if attempts_per_item < 1:
            raise ValueError("attempts_per_item must be at least 1.")
        work_items = self._build_work_items(
            items,
            attempts_per_item=attempts_per_item,
            get_item_id=get_item_id,
        )
        return self.run_work_items(
            work_items,
            run_once=run_once,
            build_failure_result=build_failure_result,
            has_error=has_error,
            on_completed=on_completed,
            should_cancel=should_cancel,
        )

    def run_work_items(
        self,
        work_items: Iterable[RepeatedEvalWorkItem[T]],
        *,
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: FailureBuilder[T, R],
        has_error: Callable[[R], bool],
        on_completed: TerminalCallback[T, R] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute an explicit durable plan without rebuilding repetition slots."""
        planned = tuple(work_items)
        identities = [(item.item_id, item.attempt_index) for item in planned]
        if len(identities) != len(set(identities)):
            raise ValueError("Explicit evaluation work items must be unique.")
        if any(not item.item_id.strip() for item in planned):
            raise ValueError("Evaluation item ids must not be empty.")
        if any(item.attempt_index < 1 for item in planned):
            raise ValueError("Evaluation attempt indices must be at least 1.")
        if self._config.runtime == "serial":
            return self._run_serial(
                planned,
                run_once=run_once,
                build_failure_result=build_failure_result,
                has_error=has_error,
                on_completed=on_completed,
                should_cancel=should_cancel,
            )
        return self._run_parallel(
            planned,
            run_once=run_once,
            build_failure_result=build_failure_result,
            has_error=has_error,
            on_completed=on_completed,
            should_cancel=should_cancel,
        )

    @staticmethod
    def _build_work_items(
        items: Iterable[T],
        *,
        attempts_per_item: int,
        get_item_id: Callable[[T], str],
    ) -> tuple[RepeatedEvalWorkItem[T], ...]:
        work_items: list[RepeatedEvalWorkItem[T]] = []
        for item in items:
            item_id = get_item_id(item).strip()
            if not item_id:
                raise ValueError("Evaluation item ids must not be empty.")
            for attempt_index in range(1, attempts_per_item + 1):
                work_items.append(
                    RepeatedEvalWorkItem(
                        item_id=item_id,
                        payload=item,
                        attempt_index=attempt_index,
                    )
                )
        return tuple(work_items)

    def _run_serial(
        self,
        work_items: tuple[RepeatedEvalWorkItem[T], ...],
        *,
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: FailureBuilder[T, R],
        has_error: Callable[[R], bool],
        on_completed: TerminalCallback[T, R] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        records: list[RepeatedEvalRecord[T, R]] = []
        stopped = False
        for work_item in work_items:
            if should_cancel is not None and should_cancel():
                raise EvaluationInterruptedError(
                    "Evaluation interrupted before the next work item started."
                )
            if stopped:
                record = self._cancelled_record(work_item, build_failure_result)
                records.append(record)
                if on_completed is not None:
                    on_completed(record)
                continue
            started_at = time.monotonic()
            try:
                result = run_once(work_item)
            except Exception as exception:  # noqa: BLE001
                duration = time.monotonic() - started_at
                result = build_failure_result(
                    work_item,
                    str(exception),
                    exception,
                    duration,
                )
            duration = time.monotonic() - started_at
            record = RepeatedEvalRecord(
                work_item=work_item,
                result=result,
                duration_seconds=duration,
            )
            records.append(record)
            if on_completed is not None:
                on_completed(record)
            if should_cancel is not None and should_cancel():
                raise EvaluationInterruptedError(
                    "Evaluation interrupted after the active work item completed."
                )
            stopped = self._config.error_action == "stop" and has_error(result)
        return tuple(records)

    def _run_parallel(
        self,
        work_items: tuple[RepeatedEvalWorkItem[T], ...],
        *,
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: FailureBuilder[T, R],
        has_error: Callable[[R], bool],
        on_completed: TerminalCallback[T, R] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        executor_class = (
            ProcessPoolExecutor
            if self._config.runtime == "process"
            else ThreadPoolExecutor
        )
        queued = deque(enumerate(work_items))
        records: dict[int, RepeatedEvalRecord[T, R]] = {}
        pending: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T], float]] = {}
        stop_submitting = False
        cancellation_started_at: float | None = None
        executor = executor_class(max_workers=self._config.max_workers)
        interrupted = False
        try:
            if should_cancel is not None and should_cancel():
                raise EvaluationInterruptedError(
                    "Evaluation interrupted before work was submitted."
                )
            self._fill_pending(executor, queued, pending, run_once)
            while pending:
                if should_cancel is not None and should_cancel():
                    stop_submitting = True
                    if cancellation_started_at is None:
                        cancellation_started_at = time.monotonic()
                wait_timeout = self._config.pending_heartbeat_seconds
                if cancellation_started_at is not None:
                    grace_remaining = self._config.cancellation_grace_seconds - (
                        time.monotonic() - cancellation_started_at
                    )
                    if grace_remaining <= 0:
                        raise EvaluationInterruptedError(
                            "Evaluation interruption grace period expired."
                        )
                    wait_timeout = min(wait_timeout, grace_remaining)
                done, _ = wait(
                    pending,
                    timeout=wait_timeout,
                    return_when=FIRST_COMPLETED,
                )
                if not done:
                    self._logger.info(
                        "Waiting on %d running evaluation attempts; %d remain queued.",
                        len(pending),
                        len(queued),
                    )
                    continue
                for future in sorted(done, key=lambda item: pending[item][0]):
                    index, work_item, started_at = pending.pop(future)
                    duration = time.monotonic() - started_at
                    try:
                        result = future.result()
                    except Exception as exception:  # noqa: BLE001
                        result = build_failure_result(
                            work_item,
                            str(exception),
                            exception,
                            duration,
                        )
                    record = RepeatedEvalRecord(
                        work_item=work_item,
                        result=result,
                        duration_seconds=duration,
                    )
                    records[index] = record
                    if on_completed is not None:
                        on_completed(record)
                    if self._config.error_action == "stop" and has_error(result):
                        stop_submitting = True
                if should_cancel is not None and should_cancel():
                    stop_submitting = True
                    if cancellation_started_at is None:
                        cancellation_started_at = time.monotonic()
                if not stop_submitting:
                    self._fill_pending(executor, queued, pending, run_once)
            if cancellation_started_at is not None:
                raise EvaluationInterruptedError(
                    "Evaluation interrupted after active work completed."
                )
        except BaseException:
            interrupted = True
            raise
        finally:
            executor.shutdown(wait=not interrupted, cancel_futures=interrupted)
        for index, work_item in queued:
            record = self._cancelled_record(work_item, build_failure_result)
            records[index] = record
            if on_completed is not None:
                on_completed(record)
        return tuple(records[index] for index in sorted(records))

    def _fill_pending(
        self,
        executor: ThreadPoolExecutor | ProcessPoolExecutor,
        queued: deque[tuple[int, RepeatedEvalWorkItem[T]]],
        pending: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T], float]],
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
    ) -> None:
        while queued and len(pending) < self._config.max_workers:
            index, work_item = queued.popleft()
            started_at = time.monotonic()
            pending[executor.submit(run_once, work_item)] = (
                index,
                work_item,
                started_at,
            )

    @staticmethod
    def _cancelled_record(
        work_item: RepeatedEvalWorkItem[T],
        build_failure_result: FailureBuilder[T, R],
    ) -> RepeatedEvalRecord[T, R]:
        exception = ExecutionCancelledError(
            "Cancelled because an earlier attempt triggered stop-on-error."
        )
        return RepeatedEvalRecord(
            work_item=work_item,
            result=build_failure_result(work_item, str(exception), exception, 0.0),
            duration_seconds=0.0,
        )
