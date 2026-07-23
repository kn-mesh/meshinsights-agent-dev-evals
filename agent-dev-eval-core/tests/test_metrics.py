"""Tests for independent accuracy, reliability, coverage, and performance."""

from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FailureType,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_confidence_accuracy,
    build_performance_summary,
    build_reliability_summary,
    build_scoring_coverage,
    metric_counts,
)


def _scored_attempt(
    *, correct: bool, duration: float, confidence: str | None = None
) -> EvalAttempt:
    actual = "Failure" if correct else "Healthy"
    return EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.SCORED,
        actual_values={"classification": actual},
        evaluations={
            "classification": FieldEvaluation(
                expected="Failure",
                actual=actual,
                correct=correct,
                grader_id="core.exact",
                grader_version=1,
            )
        },
        confidence_values=(
            {"classification": confidence} if confidence is not None else {}
        ),
        applicable_fields=("classification",),
        complete_evaluation_correct=correct,
        duration_seconds=duration,
        stage_durations_seconds={"process": duration / 2},
    )


def _failed_attempt(*, duration: float, failure_type: FailureType) -> EvalAttempt:
    return EvalAttempt(
        execution_status=ExecutionStatus.FAILED,
        output_contract_status=OutputContractStatus.NOT_PRODUCED,
        scoring_status=ScoringStatus.NOT_SCORED,
        error=failure_type.value,
        failure_type=failure_type,
        duration_seconds=duration,
        stage_durations_seconds={"process": max(0.0, duration - 1)},
    )


def test_failure_reduces_coverage_without_entering_accuracy() -> None:
    successful = _scored_attempt(correct=True, duration=2.0)
    failed = _failed_attempt(duration=4.0, failure_type=FailureType.PROVIDER_ERROR)

    reliability = build_reliability_summary([successful, failed], planned_runs=2)
    coverage = build_scoring_coverage([successful, failed], planned_runs=2)
    accuracy = metric_counts(
        evaluation.correct
        for attempt in (successful, failed)
        for evaluation in attempt.evaluations.values()
    )

    assert reliability["output_contract_validity_rate"] == 0.5
    assert reliability["failures_by_type"] == {"provider_error": 1}
    assert coverage["coverage"] == 0.5
    assert accuracy.accuracy == 1.0
    assert accuracy.evaluated_runs == 1


def test_performance_reports_completed_failed_and_stage_latency() -> None:
    successful = _scored_attempt(correct=False, duration=2.0)
    failed = _failed_attempt(duration=4.0, failure_type=FailureType.TIMEOUT)

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
        "p5": 2.1,
        "p95": 3.9,
    }
    assert performance["stage_duration_seconds"]["process"]["mean"] == 2.0


def test_confidence_accuracy_is_optional_and_reports_coverage() -> None:
    with_confidence = _scored_attempt(correct=True, duration=1.0, confidence="High")
    without_confidence = _scored_attempt(correct=False, duration=1.0)

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
