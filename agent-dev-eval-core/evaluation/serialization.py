"""JSON serialization for immutable evaluation attempts."""

from __future__ import annotations

from typing import Any

from evaluation.models import (
    EvalAttempt,
    ExecutionStatus,
    FailureType,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
)


def field_evaluation_to_dict(value: FieldEvaluation) -> dict[str, Any]:
    return {
        "expected": value.expected,
        "actual": value.actual,
        "correct": value.correct,
        "grader_id": value.grader_id,
        "grader_version": value.grader_version,
        "grader_config": value.grader_config,
        "normalized_expected": value.normalized_expected,
        "normalized_actual": value.normalized_actual,
        "details": value.details,
    }


def field_evaluation_from_dict(payload: dict[str, Any]) -> FieldEvaluation:
    return FieldEvaluation(
        expected=payload.get("expected"),
        actual=payload.get("actual"),
        correct=bool(payload["correct"]),
        grader_id=str(payload["grader_id"]),
        grader_version=int(payload["grader_version"]),
        grader_config=dict(payload.get("grader_config", {})),
        normalized_expected=payload.get("normalized_expected"),
        normalized_actual=payload.get("normalized_actual"),
        details=dict(payload.get("details", {})),
    )


def eval_attempt_to_dict(value: EvalAttempt) -> dict[str, Any]:
    """Convert one typed terminal attempt to JSON-compatible evidence."""
    return {
        "execution_status": value.execution_status.value,
        "output_contract_status": value.output_contract_status.value,
        "scoring_status": value.scoring_status.value,
        "actual_values": value.actual_values,
        "evaluations": {
            name: field_evaluation_to_dict(evaluation)
            for name, evaluation in sorted(value.evaluations.items())
        },
        "confidence_values": value.confidence_values,
        "applicable_fields": list(value.applicable_fields),
        "contract_errors": list(value.contract_errors),
        "complete_evaluation_correct": value.complete_evaluation_correct,
        "error": value.error,
        "failure_type": value.failure_type.value if value.failure_type else None,
        "duration_seconds": value.duration_seconds,
        "stage_durations_seconds": value.stage_durations_seconds,
        "artifacts": value.artifacts,
        "metadata": value.metadata,
    }


def eval_attempt_from_dict(payload: dict[str, Any]) -> EvalAttempt:
    """Restore one typed terminal attempt from persisted evidence."""
    raw_failure = payload.get("failure_type")
    return EvalAttempt(
        execution_status=ExecutionStatus(payload["execution_status"]),
        output_contract_status=OutputContractStatus(payload["output_contract_status"]),
        scoring_status=ScoringStatus(payload["scoring_status"]),
        actual_values=dict(payload.get("actual_values", {})),
        evaluations={
            name: field_evaluation_from_dict(evaluation)
            for name, evaluation in dict(payload.get("evaluations", {})).items()
        },
        confidence_values=dict(payload.get("confidence_values", {})),
        applicable_fields=tuple(payload.get("applicable_fields", ())),
        contract_errors=tuple(payload.get("contract_errors", ())),
        complete_evaluation_correct=payload.get("complete_evaluation_correct"),
        error=payload.get("error"),
        failure_type=FailureType(raw_failure) if raw_failure is not None else None,
        duration_seconds=float(payload.get("duration_seconds", 0.0)),
        stage_durations_seconds={
            str(name): float(duration)
            for name, duration in dict(
                payload.get("stage_durations_seconds", {})
            ).items()
        },
        artifacts=dict(payload.get("artifacts", {})),
        metadata=dict(payload.get("metadata", {})),
    )
