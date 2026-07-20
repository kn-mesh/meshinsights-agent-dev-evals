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


@dataclass(frozen=True, slots=True)
class RepeatedEvalExecutorConfig:
    """Configuration for bounded repeated execution."""

    runtime: RuntimeType = "serial"
    max_workers: int = 1
    error_action: ErrorActionType = "continue"
    pending_heartbeat_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.runtime not in {"serial", "threaded", "process"}:
            raise ValueError(f"Unsupported runtime: {self.runtime}.")
        if self.error_action not in {"stop", "continue"}:
            raise ValueError(f"Unsupported error_action: {self.error_action}.")
        if self.max_workers < 1:
            raise ValueError("max_workers must be at least 1.")
        if self.pending_heartbeat_seconds <= 0:
            raise ValueError("pending_heartbeat_seconds must be greater than 0.")


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
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute repeated work with bounded scheduling and complete accounting."""
        if attempts_per_item < 1:
            raise ValueError("attempts_per_item must be at least 1.")
        work_items = self._build_work_items(
            items,
            attempts_per_item=attempts_per_item,
            get_item_id=get_item_id,
        )
        if self._config.runtime == "serial":
            return self._run_serial(
                work_items,
                run_once=run_once,
                build_failure_result=build_failure_result,
                has_error=has_error,
            )
        return self._run_parallel(
            work_items,
            run_once=run_once,
            build_failure_result=build_failure_result,
            has_error=has_error,
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
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        records: list[RepeatedEvalRecord[T, R]] = []
        stopped = False
        for work_item in work_items:
            if stopped:
                records.append(self._cancelled_record(work_item, build_failure_result))
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
            records.append(
                RepeatedEvalRecord(
                    work_item=work_item,
                    result=result,
                    duration_seconds=duration,
                )
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

        with executor_class(max_workers=self._config.max_workers) as executor:
            self._fill_pending(executor, queued, pending, run_once)
            while pending:
                done, _ = wait(
                    pending,
                    timeout=self._config.pending_heartbeat_seconds,
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
                    records[index] = RepeatedEvalRecord(
                        work_item=work_item,
                        result=result,
                        duration_seconds=duration,
                    )
                    if self._config.error_action == "stop" and has_error(result):
                        stop_submitting = True
                if not stop_submitting:
                    self._fill_pending(executor, queued, pending, run_once)

        for index, work_item in queued:
            records[index] = self._cancelled_record(work_item, build_failure_result)
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
