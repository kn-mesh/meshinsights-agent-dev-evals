"""Shared executor for repeated eval runs across units and runtimes."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import dataclass
import logging
import time
from typing import Generic, TypeVar

from src.experimental_core.evals.ai_metadata import ErrorActionType, RuntimeType


T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True, slots=True)
class RepeatedEvalExecutorConfig:
    """Configuration for repeated eval execution."""

    runtime: RuntimeType = "serial"
    max_workers: int = 1
    error_action: ErrorActionType = "continue"
    pending_heartbeat_seconds: float = 30.0
    unit_run_timeout_seconds: float | None = None
    stale_future_buffer_seconds: float = 60.0


@dataclass(frozen=True, slots=True)
class RepeatedEvalWorkItem(Generic[T]):
    """One repeated eval task for a unit and run index."""

    unit_id: str
    payload: T
    run_index: int


@dataclass(frozen=True, slots=True)
class RepeatedEvalRecord(Generic[T, R]):
    """Pair a work item with the result produced for that run."""

    work_item: RepeatedEvalWorkItem[T]
    result: R


class RepeatedEvalExecutor(Generic[T, R]):
    """Execute repeated eval work items with optional parallel runtimes."""

    def __init__(
        self,
        config: RepeatedEvalExecutorConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        """Store executor configuration and an optional logger."""

        self._config = config
        self._logger = logger or logging.getLogger(__name__)

    def run(
        self,
        items: Iterable[T],
        *,
        runs_per_unit: int,
        get_unit_id: Callable[[T], str],
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: Callable[
            [RepeatedEvalWorkItem[T], str, Exception | None],
            R,
        ],
        has_error: Callable[[R], bool],
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute repeated eval work and return deterministic run records."""

        self._validate_config(runs_per_unit=runs_per_unit)
        work_items = self._build_work_items(
            items=items,
            runs_per_unit=runs_per_unit,
            get_unit_id=get_unit_id,
        )
        total_work = len(work_items)

        if self._config.runtime == "serial":
            return self._run_serial(
                work_items,
                total_work=total_work,
                run_once=run_once,
                build_failure_result=build_failure_result,
                has_error=has_error,
            )

        return self._run_parallel(
            work_items,
            total_work=total_work,
            run_once=run_once,
            build_failure_result=build_failure_result,
            has_error=has_error,
        )

    def _validate_config(self, *, runs_per_unit: int) -> None:
        """Validate executor configuration before work starts."""

        if runs_per_unit < 1:
            raise ValueError("runs_per_unit must be at least 1.")
        if self._config.max_workers < 1:
            raise ValueError("max_workers must be at least 1.")
        if self._config.pending_heartbeat_seconds <= 0:
            raise ValueError("pending_heartbeat_seconds must be greater than 0.")
        if self._config.stale_future_buffer_seconds < 0:
            raise ValueError("stale_future_buffer_seconds must be non-negative.")
        if (
            self._config.unit_run_timeout_seconds is not None
            and self._config.unit_run_timeout_seconds <= 0
        ):
            raise ValueError("unit_run_timeout_seconds must be greater than 0 when set.")

    def _build_work_items(
        self,
        *,
        items: Iterable[T],
        runs_per_unit: int,
        get_unit_id: Callable[[T], str],
    ) -> tuple[RepeatedEvalWorkItem[T], ...]:
        """Expand units into per-run work items in deterministic order."""

        work_items: list[RepeatedEvalWorkItem[T]] = []
        for item in items:
            unit_id = get_unit_id(item)
            for run_index in range(1, runs_per_unit + 1):
                work_items.append(
                    RepeatedEvalWorkItem(
                        unit_id=unit_id,
                        payload=item,
                        run_index=run_index,
                    )
                )
        return tuple(work_items)

    def _run_serial(
        self,
        work_items: tuple[RepeatedEvalWorkItem[T], ...],
        *,
        total_work: int,
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: Callable[
            [RepeatedEvalWorkItem[T], str, Exception | None],
            R,
        ],
        has_error: Callable[[R], bool],
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute work items sequentially."""

        results: list[RepeatedEvalRecord[T, R]] = []
        for index, work_item in enumerate(work_items, 1):
            self._logger.info(
                "[%d/%d] Unit %s run %d",
                index,
                total_work,
                work_item.unit_id,
                work_item.run_index,
            )
            try:
                result = run_once(work_item)
            except Exception as exc:  # noqa: BLE001
                result = build_failure_result(work_item, str(exc), exc)

            results.append(RepeatedEvalRecord(work_item=work_item, result=result))
            if self._config.error_action == "stop" and has_error(result):
                self._logger.error(
                    "Stopping early due to error on unit %s run %d",
                    work_item.unit_id,
                    work_item.run_index,
                )
                break

        return tuple(results)

    def _run_parallel(
        self,
        work_items: tuple[RepeatedEvalWorkItem[T], ...],
        *,
        total_work: int,
        run_once: Callable[[RepeatedEvalWorkItem[T]], R],
        build_failure_result: Callable[
            [RepeatedEvalWorkItem[T], str, Exception | None],
            R,
        ],
        has_error: Callable[[R], bool],
    ) -> tuple[RepeatedEvalRecord[T, R], ...]:
        """Execute work items with thread or process pools."""

        executor_cls = (
            ProcessPoolExecutor
            if self._config.runtime == "process"
            else ThreadPoolExecutor
        )
        self._logger.info(
            "Running %d work items with %s executor (max_workers=%d)",
            total_work,
            self._config.runtime,
            self._config.max_workers,
        )

        results_by_index: dict[int, RepeatedEvalRecord[T, R]] = {}
        stopped = False
        should_wait_for_shutdown = True
        executor = executor_cls(max_workers=self._config.max_workers)
        try:
            pending_futures: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T]]] = {
                executor.submit(run_once, work_item): (index, work_item)
                for index, work_item in enumerate(work_items)
            }
            submitted_at = {future: time.monotonic() for future in pending_futures}
            running_started_at: dict[Future[R], float] = {}
            completed = 0

            while pending_futures:
                now = time.monotonic()
                self._record_running_futures_started(
                    pending_futures=pending_futures,
                    running_started_at=running_started_at,
                    now=now,
                )
                done, _ = wait(
                    pending_futures,
                    timeout=self._config.pending_heartbeat_seconds,
                    return_when=FIRST_COMPLETED,
                )
                now = time.monotonic()
                self._record_running_futures_started(
                    pending_futures=pending_futures,
                    running_started_at=running_started_at,
                    now=now,
                )

                stale_futures = self._collect_stale_futures(
                    pending_futures=pending_futures,
                    done=done,
                    running_started_at=running_started_at,
                    now=now,
                )
                if stale_futures:
                    completed = self._evict_stale_futures(
                        stale_futures=stale_futures,
                        pending_futures=pending_futures,
                        total_work=total_work,
                        completed=completed,
                        results_by_index=results_by_index,
                        build_failure_result=build_failure_result,
                        running_started_at=running_started_at,
                        now=now,
                    )
                    should_wait_for_shutdown = False

                if not done and not stale_futures:
                    self._log_pending_parallel_work(
                        pending_futures=pending_futures,
                        submitted_at=submitted_at,
                        completed=completed,
                        total_work=total_work,
                    )
                    continue

                for future in done:
                    index, work_item = pending_futures.pop(future)
                    running_started_at.pop(future, None)
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        result = build_failure_result(work_item, str(exc), exc)

                    completed += 1
                    status = "OK" if not has_error(result) else "FAIL"
                    self._logger.info(
                        "[%d/%d] Unit %s run %d - %s",
                        completed,
                        total_work,
                        work_item.unit_id,
                        work_item.run_index,
                        status,
                    )
                    results_by_index[index] = RepeatedEvalRecord(
                        work_item=work_item,
                        result=result,
                    )

                    if self._config.error_action == "stop" and has_error(result):
                        stopped = True
                        self._logger.error(
                            "Error on unit %s run %d - cancelling remaining work",
                            work_item.unit_id,
                            work_item.run_index,
                        )
                        should_wait_for_shutdown = False
                        self._logger.warning(
                            "Returning without waiting for already-running parallel work to finish."
                        )
                        for pending_future in pending_futures:
                            pending_future.cancel()
                        pending_futures.clear()
                        running_started_at.clear()
                        break

                if stopped:
                    break
        finally:
            executor.shutdown(
                wait=should_wait_for_shutdown,
                cancel_futures=not should_wait_for_shutdown,
            )

        return tuple(results_by_index[index] for index in sorted(results_by_index))

    def _record_running_futures_started(
        self,
        *,
        pending_futures: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T]]],
        running_started_at: dict[Future[R], float],
        now: float,
    ) -> None:
        """Record the first observed running timestamp for pending futures."""

        for future in pending_futures:
            if future.running() and future not in running_started_at:
                running_started_at[future] = now

    def _collect_stale_futures(
        self,
        *,
        pending_futures: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T]]],
        done: set[Future[R]],
        running_started_at: dict[Future[R], float],
        now: float,
    ) -> list[Future[R]]:
        """Return running futures that exceeded the per-run timeout."""

        if self._config.unit_run_timeout_seconds is None:
            return []

        stale_deadline_seconds = (
            self._config.unit_run_timeout_seconds
            + self._config.stale_future_buffer_seconds
        )
        stale_futures: list[Future[R]] = []
        for future in pending_futures:
            if future in done:
                continue
            running_since = running_started_at.get(future)
            if running_since is None:
                continue
            if now - running_since > stale_deadline_seconds:
                stale_futures.append(future)
        return stale_futures

    def _evict_stale_futures(
        self,
        *,
        stale_futures: list[Future[R]],
        pending_futures: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T]]],
        total_work: int,
        completed: int,
        results_by_index: dict[int, RepeatedEvalRecord[T, R]],
        build_failure_result: Callable[
            [RepeatedEvalWorkItem[T], str, Exception | None],
            R,
        ],
        running_started_at: dict[Future[R], float],
        now: float,
    ) -> int:
        """Cancel stale futures and store failure results for them."""

        if self._config.unit_run_timeout_seconds is None:
            return completed

        stale_deadline_seconds = (
            self._config.unit_run_timeout_seconds
            + self._config.stale_future_buffer_seconds
        )

        for stale_future in stale_futures:
            index, work_item = pending_futures.pop(stale_future)
            running_since = running_started_at.pop(stale_future, now)
            elapsed_seconds = now - running_since
            stale_future.cancel()
            completed += 1
            self._logger.warning(
                "[%d/%d] Unit %s run %d - STALE (elapsed %.1fs, deadline %.1fs) - evicting as timed out",
                completed,
                total_work,
                work_item.unit_id,
                work_item.run_index,
                elapsed_seconds,
                stale_deadline_seconds,
            )
            message = (
                f"Evicted as stale: elapsed {elapsed_seconds:.1f}s "
                f"(deadline {stale_deadline_seconds:.1f}s). "
                f"The worker likely hung beyond its "
                f"{self._config.unit_run_timeout_seconds:.1f}s timeout."
            )
            result = build_failure_result(work_item, message, None)
            results_by_index[index] = RepeatedEvalRecord(
                work_item=work_item,
                result=result,
            )

        return completed

    def _log_pending_parallel_work(
        self,
        *,
        pending_futures: dict[Future[R], tuple[int, RepeatedEvalWorkItem[T]]],
        submitted_at: dict[Future[R], float],
        completed: int,
        total_work: int,
    ) -> None:
        """Log a compact heartbeat while parallel eval work remains pending."""

        oldest_pending = sorted(
            (
                (
                    time.monotonic() - submitted_at.get(future, time.monotonic()),
                    work_item.unit_id,
                    work_item.run_index,
                )
                for future, (_, work_item) in pending_futures.items()
            ),
            reverse=True,
        )[:3]
        details = ", ".join(
            f"{unit_id} run {run_index} ({elapsed_seconds:.1f}s)"
            for elapsed_seconds, unit_id, run_index in oldest_pending
        )
        self._logger.info(
            "Still waiting on %d/%d runs after %d completions: %s",
            len(pending_futures),
            total_work,
            completed,
            details or "pending work remains",
        )
