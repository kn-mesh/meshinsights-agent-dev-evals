"""Typed observations produced by one agent evaluation attempt."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None


class ExecutionStatus(StrEnum):
    """Terminal pipeline execution state for one planned attempt."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputContractStatus(StrEnum):
    """Whether a terminal execution produced a valid configured output."""

    VALID = "valid"
    INVALID = "invalid"
    NOT_PRODUCED = "not_produced"


class ScoringStatus(StrEnum):
    """Whether a contract-valid output was scored successfully."""

    SCORED = "scored"
    NOT_SCORED = "not_scored"
    GRADER_ERROR = "grader_error"
    NO_APPLICABLE_TARGETS = "no_applicable_targets"


class FailureType(StrEnum):
    """Normalized operational, contract, and scoring failure categories."""

    PROVIDER_ERROR = "provider_error"
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    PIPELINE_ERROR = "pipeline_error"
    RECEIPT_IDENTITY_ERROR = "receipt_identity_error"
    OUTPUT_MISSING = "output_missing"
    OUTPUT_MALFORMED = "output_malformed"
    OUTPUT_PARTIAL = "output_partial"
    GRADER_ERROR = "grader_error"
    EXECUTOR_ERROR = "executor_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FieldEvaluation:
    """One deterministic grade for an applicable benchmark target."""

    expected: JsonScalar
    actual: JsonScalar
    correct: bool
    grader_id: str
    grader_version: int
    grader_config: dict[str, Any] = field(default_factory=dict)
    normalized_expected: JsonScalar = None
    normalized_actual: JsonScalar = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EvalAttempt:
    """Complete terminal evidence for one planned agent attempt."""

    execution_status: ExecutionStatus
    output_contract_status: OutputContractStatus
    scoring_status: ScoringStatus
    actual_values: dict[str, JsonScalar] = field(default_factory=dict)
    evaluations: dict[str, FieldEvaluation] = field(default_factory=dict)
    confidence_values: dict[str, JsonScalar] = field(default_factory=dict)
    applicable_fields: tuple[str, ...] = ()
    contract_errors: tuple[str, ...] = ()
    complete_evaluation_correct: bool | None = None
    error: str | None = None
    failure_type: FailureType | None = None
    duration_seconds: float = 0.0
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject contradictory attempt states while retaining partial output."""
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative.")
        if any(duration < 0 for duration in self.stage_durations_seconds.values()):
            raise ValueError("stage durations must be non-negative.")
        if not set(self.confidence_values).issubset(self.actual_values):
            raise ValueError("Confidence values must correspond to extracted outputs.")
        if not set(self.evaluations).issubset(self.actual_values):
            raise ValueError("Evaluations must correspond to extracted outputs.")
        if self.execution_status is not ExecutionStatus.COMPLETED:
            if self.output_contract_status is not OutputContractStatus.NOT_PRODUCED:
                raise ValueError("Failed execution cannot report a produced output.")
            if self.scoring_status is not ScoringStatus.NOT_SCORED:
                raise ValueError("Failed execution cannot be scored.")
        if self.output_contract_status is not OutputContractStatus.VALID:
            if self.scoring_status is not ScoringStatus.NOT_SCORED:
                raise ValueError("Invalid output cannot be scored.")
            if self.evaluations or self.complete_evaluation_correct is not None:
                raise ValueError("Invalid output cannot contribute accuracy grades.")
        if self.scoring_status is ScoringStatus.SCORED:
            if not self.evaluations:
                raise ValueError("A scored attempt requires field evaluations.")
            expected_complete = all(
                evaluation.correct for evaluation in self.evaluations.values()
            )
            if self.complete_evaluation_correct is not expected_complete:
                raise ValueError(
                    "Complete correctness must equal all applicable field grades."
                )
        elif self.complete_evaluation_correct is not None:
            raise ValueError("Only scored attempts have complete correctness.")
        has_failure = self.failure_type is not None or self.error is not None
        healthy = (
            self.execution_status is ExecutionStatus.COMPLETED
            and self.output_contract_status is OutputContractStatus.VALID
            and self.scoring_status
            in {ScoringStatus.SCORED, ScoringStatus.NO_APPLICABLE_TARGETS}
        )
        if healthy and has_failure:
            raise ValueError("A healthy attempt cannot include failure details.")
        if not healthy and not has_failure:
            raise ValueError("An unhealthy attempt requires failure details.")

    @property
    def has_error(self) -> bool:
        """Return whether execution, output validation, or grading failed."""
        return not (
            self.execution_status is ExecutionStatus.COMPLETED
            and self.output_contract_status is OutputContractStatus.VALID
            and self.scoring_status
            in {ScoringStatus.SCORED, ScoringStatus.NO_APPLICABLE_TARGETS}
        )

    @property
    def contributes_to_accuracy(self) -> bool:
        return self.scoring_status is ScoringStatus.SCORED

    def get_artifact(self, name: str) -> Any | None:
        return self.artifacts.get(name)
