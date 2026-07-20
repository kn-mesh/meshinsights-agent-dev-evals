"""Typed observations produced by one agent evaluation attempt."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AttemptStatus(StrEnum):
    """Terminal execution status for one planned attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureType(StrEnum):
    """Normalized operational failure categories."""

    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    PIPELINE_ERROR = "pipeline_error"
    RECEIPT_CONTRACT_ERROR = "receipt_contract_error"
    EXECUTOR_ERROR = "executor_error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LabelEvaluation:
    """Comparison of one expected label with a contract-valid actual label."""

    expected: str
    actual: str
    is_correct: bool


@dataclass(frozen=True, slots=True)
class EvalAttempt:
    """Complete terminal evidence for one planned agent attempt."""

    status: AttemptStatus
    actual_values: dict[str, str] = field(default_factory=dict)
    evaluations: dict[str, LabelEvaluation] = field(default_factory=dict)
    confidence_values: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    failure_type: FailureType | None = None
    duration_seconds: float = 0.0
    stage_durations_seconds: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject contradictory terminal states and invalid durations."""
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative.")
        if any(duration < 0 for duration in self.stage_durations_seconds.values()):
            raise ValueError("stage durations must be non-negative.")
        if self.status is AttemptStatus.SUCCEEDED:
            if self.error is not None or self.failure_type is not None:
                raise ValueError("A successful attempt cannot include failure details.")
            if set(self.actual_values) != set(self.evaluations):
                raise ValueError(
                    "Successful attempts must evaluate every actual required label."
                )
            for name, evaluation in self.evaluations.items():
                if evaluation.actual != self.actual_values[name]:
                    raise ValueError(
                        f"Evaluation actual value does not match output '{name}'."
                    )
        else:
            if self.error is None or self.failure_type is None:
                raise ValueError("A failed attempt requires error and failure_type.")
            if self.evaluations:
                raise ValueError(
                    "Failed attempts cannot contribute label evaluations to accuracy."
                )
        if not set(self.confidence_values).issubset(self.actual_values):
            raise ValueError("Confidence values must correspond to actual labels.")

    @property
    def success(self) -> bool:
        """Return whether the complete required output contract was valid."""
        return self.status is AttemptStatus.SUCCEEDED

    @property
    def has_error(self) -> bool:
        """Return whether execution did not produce a contract-valid output."""
        return not self.success

    def get_artifact(self, name: str) -> Any | None:
        """Return a named attempt artifact when present."""
        return self.artifacts.get(name)
