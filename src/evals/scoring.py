"""Schema-driven output validation and deterministic scoring."""

from __future__ import annotations

from typing import Any

from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FailureType,
    FieldEvaluation,
    GraderRegistry,
    OutputContractStatus,
    OutputFieldSpec,
    ScoringStatus,
    extract_output_fields,
    read_path,
    validate_metadata_identity,
)

from src.benchmarks import BenchmarkExample
from src.evals.evaluation_profile import (
    EvaluationProfile,
    evaluation_context,
    field_is_applicable,
    field_is_required,
)


def score_receipt_metadata(
    *,
    metadata: Any,
    expected_identity: dict[str, str | int],
    example: BenchmarkExample,
    profile: EvaluationProfile,
    grader_registry: GraderRegistry,
    duration_seconds: float,
    stage_durations_seconds: dict[str, float],
    attempt_metadata: dict[str, Any],
) -> EvalAttempt:
    """Validate and score a successful pipeline's act-stage metadata."""
    identity_errors = validate_metadata_identity(metadata, expected=expected_identity)
    specs = tuple(
        OutputFieldSpec(
            name=field.key,
            value_path=field.actual.receipt_metadata_path,
            value_type=field.actual.type,
            confidence_path=(
                field.confidence.receipt_metadata_path
                if field.confidence is not None
                else None
            ),
            confidence_values=(
                field.confidence.values if field.confidence is not None else ()
            ),
        )
        for field in profile.output_fields
    )
    extraction = extract_output_fields(metadata, specs=specs)
    actual_values = extraction.actual_values
    context = evaluation_context(example=example, agent_outputs=actual_values)
    applicable_fields = tuple(
        field.key
        for field in profile.output_fields
        if field_is_applicable(field, context)
    )
    contract_errors = list(identity_errors)
    missing_fields: list[str] = []
    malformed_fields: list[str] = []
    for field in profile.output_fields:
        if field.key not in applicable_fields:
            continue
        observation = extraction.observations[field.key]
        if not observation.present:
            if field_is_required(field, context):
                missing_fields.append(field.key)
                contract_errors.append(f"Missing required output '{field.key}'.")
            continue
        if not observation.valid:
            malformed_fields.append(field.key)
            contract_errors.extend(observation.errors)

    artifacts = {
        "agent_output": (
            metadata.get("agent_output") if isinstance(metadata, dict) else None
        ),
        "output_observations": {
            name: {
                "present": observation.present,
                "valid": observation.valid,
                "raw_value": observation.raw_value,
                "errors": list(observation.errors),
            }
            for name, observation in extraction.observations.items()
        },
    }
    if contract_errors:
        if identity_errors:
            failure_type = FailureType.RECEIPT_IDENTITY_ERROR
        elif missing_fields and actual_values:
            failure_type = FailureType.OUTPUT_PARTIAL
        elif missing_fields:
            failure_type = FailureType.OUTPUT_MISSING
        elif malformed_fields and actual_values:
            failure_type = FailureType.OUTPUT_PARTIAL
        else:
            failure_type = FailureType.OUTPUT_MALFORMED
        return EvalAttempt(
            execution_status=ExecutionStatus.COMPLETED,
            output_contract_status=OutputContractStatus.INVALID,
            scoring_status=ScoringStatus.NOT_SCORED,
            actual_values=actual_values,
            confidence_values=extraction.confidence_values,
            applicable_fields=applicable_fields,
            contract_errors=tuple(contract_errors),
            error="; ".join(contract_errors),
            failure_type=failure_type,
            duration_seconds=duration_seconds,
            stage_durations_seconds=stage_durations_seconds,
            artifacts=artifacts,
            metadata=attempt_metadata,
        )

    evaluations: dict[str, FieldEvaluation] = {}
    try:
        for field in profile.output_fields:
            if field.key not in applicable_fields or field.evaluation is None:
                continue
            if field.key not in actual_values:
                # Optional graded fields contribute only when the agent emits them.
                continue
            expected_found, expected = read_path(
                example.approved_label_payload,
                field.evaluation.benchmark_label_path,
            )
            if not expected_found:
                raise ValueError(
                    f"Benchmark target for {field.key!r} was not found at scoring."
                )
            actual = actual_values[field.key]
            grader_config = field.evaluation.grader
            grader = grader_registry.resolve(grader_config.id, grader_config.version)
            grade = grader.grade(
                expected=expected,
                actual=actual,
                config=grader_config.config,
            )
            evaluations[field.key] = FieldEvaluation(
                expected=grade.expected,
                actual=grade.actual,
                correct=grade.correct,
                grader_id=grader.grader_id,
                grader_version=grader.grader_version,
                grader_config=grader_config.config,
                normalized_expected=grade.normalized_expected,
                normalized_actual=grade.normalized_actual,
                details=grade.details,
            )
    except Exception as error:  # deterministic grader boundary
        return EvalAttempt(
            execution_status=ExecutionStatus.COMPLETED,
            output_contract_status=OutputContractStatus.VALID,
            scoring_status=ScoringStatus.GRADER_ERROR,
            actual_values=actual_values,
            confidence_values=extraction.confidence_values,
            applicable_fields=applicable_fields,
            error=f"Deterministic grading failed: {error}",
            failure_type=FailureType.GRADER_ERROR,
            duration_seconds=duration_seconds,
            stage_durations_seconds=stage_durations_seconds,
            artifacts=artifacts,
            metadata=attempt_metadata,
        )

    if not evaluations:
        return EvalAttempt(
            execution_status=ExecutionStatus.COMPLETED,
            output_contract_status=OutputContractStatus.VALID,
            scoring_status=ScoringStatus.NO_APPLICABLE_TARGETS,
            actual_values=actual_values,
            confidence_values=extraction.confidence_values,
            applicable_fields=applicable_fields,
            duration_seconds=duration_seconds,
            stage_durations_seconds=stage_durations_seconds,
            artifacts=artifacts,
            metadata=attempt_metadata,
        )

    complete_correct = all(evaluation.correct for evaluation in evaluations.values())
    return EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.SCORED,
        actual_values=actual_values,
        evaluations=evaluations,
        confidence_values=extraction.confidence_values,
        applicable_fields=applicable_fields,
        complete_evaluation_correct=complete_correct,
        duration_seconds=duration_seconds,
        stage_durations_seconds=stage_durations_seconds,
        artifacts=artifacts,
        metadata=attempt_metadata,
    )
