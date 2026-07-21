"""Contract tests for reusable repeated evaluation execution."""

from __future__ import annotations

import threading

import pytest

from evaluation import (
    ExecutionCancelledError,
    EvaluationInterruptedError,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalWorkItem,
)


def _failure_result(
    work_item: RepeatedEvalWorkItem[str],
    message: str,
    exception: Exception | None,
    duration_seconds: float,
) -> str:
    _ = work_item, message, duration_seconds
    return "cancelled" if isinstance(exception, ExecutionCancelledError) else "failed"


def test_serial_stop_returns_terminal_record_for_every_planned_attempt() -> None:
    executor = RepeatedEvalExecutor[str, str](
        RepeatedEvalExecutorConfig(runtime="serial", error_action="stop")
    )

    def run_once(work_item: RepeatedEvalWorkItem[str]) -> str:
        if work_item.item_id == "b":
            raise RuntimeError("provider unavailable")
        return "ok"

    records = executor.run(
        ["a", "b", "c"],
        attempts_per_item=1,
        get_item_id=lambda item: item,
        run_once=run_once,
        build_failure_result=_failure_result,
        has_error=lambda result: result != "ok",
    )

    assert [record.work_item.item_id for record in records] == ["a", "b", "c"]
    assert [record.result for record in records] == ["ok", "failed", "cancelled"]


def test_threaded_execution_preserves_planned_order() -> None:
    executor = RepeatedEvalExecutor[str, str](
        RepeatedEvalExecutorConfig(runtime="threaded", max_workers=2)
    )
    records = executor.run(
        ["a", "b"],
        attempts_per_item=2,
        get_item_id=lambda item: item,
        run_once=lambda work_item: f"{work_item.item_id}-{work_item.attempt_index}",
        build_failure_result=_failure_result,
        has_error=lambda result: result in {"failed", "cancelled"},
    )

    assert [record.result for record in records] == ["a-1", "a-2", "b-1", "b-2"]


def test_explicit_work_items_emit_terminal_callbacks() -> None:
    executor = RepeatedEvalExecutor[str, str](
        RepeatedEvalExecutorConfig(runtime="serial")
    )
    completed: list[str] = []
    records = executor.run_work_items(
        [RepeatedEvalWorkItem(item_id="a", payload="payload", attempt_index=3)],
        run_once=lambda work_item: f"{work_item.item_id}-{work_item.attempt_index}",
        build_failure_result=_failure_result,
        has_error=lambda result: result != "a-3",
        on_completed=lambda record: completed.append(record.result),
    )

    assert [record.result for record in records] == ["a-3"]
    assert completed == ["a-3"]


def test_cooperative_cancellation_stops_before_unsubmitted_serial_work() -> None:
    executor = RepeatedEvalExecutor[str, str](
        RepeatedEvalExecutorConfig(runtime="serial")
    )
    completed: list[str] = []

    with pytest.raises(EvaluationInterruptedError):
        executor.run(
            ["a", "b"],
            attempts_per_item=1,
            get_item_id=lambda item: item,
            run_once=lambda work_item: work_item.item_id,
            build_failure_result=_failure_result,
            has_error=lambda result: result != "a",
            on_completed=lambda record: completed.append(record.result),
            should_cancel=lambda: completed == ["a"],
        )

    assert completed == ["a"]


def test_threaded_cancellation_does_not_submit_queued_work() -> None:
    executor = RepeatedEvalExecutor[str, str](
        RepeatedEvalExecutorConfig(runtime="threaded", max_workers=1)
    )
    cancelled = threading.Event()
    executed: list[str] = []

    def run_once(work_item: RepeatedEvalWorkItem[str]) -> str:
        executed.append(work_item.item_id)
        cancelled.set()
        return work_item.item_id

    with pytest.raises(EvaluationInterruptedError):
        executor.run(
            ["a", "b"],
            attempts_per_item=1,
            get_item_id=lambda item: item,
            run_once=run_once,
            build_failure_result=_failure_result,
            has_error=lambda result: False,
            should_cancel=cancelled.is_set,
        )

    assert executed == ["a"]


def test_executor_configuration_rejects_invalid_runtime() -> None:
    try:
        RepeatedEvalExecutorConfig(runtime="invalid")  # type: ignore[arg-type]
    except ValueError as exception:
        assert "Unsupported runtime" in str(exception)
    else:
        raise AssertionError("Invalid runtime was accepted.")
