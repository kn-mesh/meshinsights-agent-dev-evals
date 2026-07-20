"""Tests for independent reliability and performance aggregation."""

from __future__ import annotations

from evaluation import (
    AttemptStatus,
    EvalAttempt,
    FailureType,
    LabelEvaluation,
    build_confidence_accuracy,
    build_performance_summary,
    build_reliability_summary,
    metric_counts,
)


def _successful_attempt(
    *, correct: bool, duration: float, confidence: str | None = None
) -> EvalAttempt:
    actual = "Failure" if correct else "Healthy"
    return EvalAttempt(
        status=AttemptStatus.SUCCEEDED,
        actual_values={"classification": actual},
        evaluations={
            "classification": LabelEvaluation(
                expected="Failure",
                actual=actual,
                is_correct=correct,
            )
        },
        confidence_values=(
            {"classification": confidence} if confidence is not None else {}
        ),
        duration_seconds=duration,
        stage_durations_seconds={"process": duration / 2},
    )


def test_failure_reduces_reliability_without_entering_accuracy() -> None:
    successful = _successful_attempt(correct=True, duration=2.0)
    failed = EvalAttempt(
        status=AttemptStatus.FAILED,
        error="provider unavailable",
        failure_type=FailureType.PROVIDER_ERROR,
        duration_seconds=4.0,
    )

    reliability = build_reliability_summary([successful, failed], planned_runs=2)
    accuracy = metric_counts(
        evaluation.is_correct
        for attempt in (successful, failed)
        for evaluation in attempt.evaluations.values()
    )

    assert reliability["reliability"] == 0.5
    assert reliability["failures_by_type"] == {"provider_error": 1}
    assert accuracy.accuracy == 1.0
    assert accuracy.evaluated_runs == 1


def test_performance_reports_success_failure_and_stage_latency() -> None:
    successful = _successful_attempt(correct=False, duration=2.0)
    failed = EvalAttempt(
        status=AttemptStatus.FAILED,
        error="timeout",
        failure_type=FailureType.TIMEOUT,
        duration_seconds=4.0,
        stage_durations_seconds={"process": 3.0},
    )

    performance = build_performance_summary(
        [successful, failed],
        evaluation_wall_time_seconds=5.0,
    )

    assert performance["throughput_runs_per_minute"] == 24.0
    assert performance["run_duration_seconds"] == {
        "count": 2,
        "minimum": 2.0,
        "maximum": 4.0,
        "mean": 3.0,
        "median": 3.0,
        "p95": 3.9,
    }
    assert performance["stage_duration_seconds"]["process"]["mean"] == 2.0


def test_confidence_accuracy_is_optional_and_reports_coverage() -> None:
    with_confidence = _successful_attempt(
        correct=True,
        duration=1.0,
        confidence="High",
    )
    without_confidence = _successful_attempt(correct=False, duration=1.0)

    confidence = build_confidence_accuracy(
        [with_confidence, without_confidence],
        label_name="classification",
        expected_values=("Failure",),
    )

    assert confidence["confidence_coverage"] == {
        "outputs_with_confidence": 1,
        "evaluated_outputs": 2,
        "coverage": 0.5,
    }
    assert confidence["all"]["High"] == {
        "accuracy": 1.0,
        "correct_runs": 1,
        "evaluated_runs": 1,
    }
    assert confidence["all"]["Low"]["accuracy"] is None
