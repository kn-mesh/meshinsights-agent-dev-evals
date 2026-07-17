"""Shared models for repeated eval attempts and aggregated unit results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.experimental_core.evals.pipeline.eval_results import EvalResult
from src.experimental_core.evals.rubric import RubricEntry


@dataclass(frozen=True, slots=True)
class EvalAttempt:
    """Result of one eval attempt for a single unit."""

    actual_values: dict[str, str | None]
    evals: dict[str, EvalResult]
    success: bool
    error: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_error(self) -> bool:
        """Return whether the attempt ended in an error."""

        return self.error is not None

    def get_actual_value(self, name: str) -> str | None:
        """Return one named actual outcome value."""

        return self.actual_values.get(name)

    def get_artifact(self, name: str) -> Any | None:
        """Return one named raw artifact captured during the attempt."""

        return self.artifacts.get(name)

    def get_eval(self, name: str) -> EvalResult | None:
        """Return one named comparison result."""

        return self.evals.get(name)


@dataclass(frozen=True, slots=True)
class UnitEvalResult:
    """Aggregated eval attempts and rubric context for one unit."""

    entry: RubricEntry
    attempts: tuple[EvalAttempt, ...]
    unit_accuracy: float | None = None

    @property
    def unit_id(self) -> str:
        """Return the unit identifier."""

        return self.entry.unit_id

    @property
    def expected_outcomes(self) -> dict[str, str]:
        """Return the expected rubric outcomes."""

        return self.entry.expected_outcomes

    @property
    def metadata(self) -> dict[str, Any]:
        """Return rubric metadata for the unit."""

        return self.entry.metadata

    @property
    def run_count(self) -> int:
        """Return the number of recorded attempts."""

        return len(self.attempts)

    def get_expected_outcome(self, name: str) -> str | None:
        """Return one named expected outcome."""

        return self.entry.expected_outcomes.get(name)
