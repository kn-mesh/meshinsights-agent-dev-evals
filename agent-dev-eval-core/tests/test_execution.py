"""Contract tests for reusable repeated evaluation execution."""

from __future__ import annotations

from evaluation import (
    ExecutionCancelledError,
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


def test_executor_configuration_rejects_invalid_runtime() -> None:
    try:
        RepeatedEvalExecutorConfig(runtime="invalid")  # type: ignore[arg-type]
    except ValueError as exception:
        assert "Unsupported runtime" in str(exception)
    else:
        raise AssertionError("Invalid runtime was accepted.")
