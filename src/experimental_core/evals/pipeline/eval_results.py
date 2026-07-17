"""
Core evaluation helpers for comparing outcomes and computing metrics.

This module provides domain-agnostic primitives for evaluating pipeline outputs
against expected values and aggregating results into summary metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable, Iterable, Protocol, TypeVar

from src.experimental_core.evals.rubric import RubricEntry


T = TypeVar("T")


# =============================================================================
# Eval Result Primitives
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Result of comparing expected vs actual outcomes."""

    expected: str | None
    actual: str | None
    is_correct: bool | None
    error: str | None = None


def evaluate_outcome(
    expected: str | None,
    actual: str | None,
    *,
    comparator: Callable[[str, str], bool] | None = None,
) -> EvalResult:
    """Compare expected vs actual outcomes and return a structured result."""

    if not isinstance(expected, str) or not isinstance(actual, str):
        return EvalResult(expected=expected, actual=actual, is_correct=None)

    compare = comparator or (lambda left, right: left == right)
    try:
        result = compare(expected, actual)
    except Exception as exc:  # noqa: BLE001
        return EvalResult(expected=expected, actual=actual, is_correct=None, error=str(exc))

    return EvalResult(expected=expected, actual=actual, is_correct=result)


def evaluate_outcomes(
    entry: RubricEntry,
    actual_values: Mapping[str, str | None],
    *,
    comparator: Callable[[str, str], bool] | None = None,
) -> dict[str, EvalResult]:
    """Evaluate multiple named outcomes for a single rubric entry."""
    results: dict[str, EvalResult] = {}
    for name, expected in entry.expected_outcomes.items():
        actual = actual_values.get(name)
        results[name] = evaluate_outcome(expected, actual, comparator=comparator)
    for name, actual in actual_values.items():
        if name in entry.expected_outcomes:
            continue
        results[name] = EvalResult(
            expected=None,
            actual=actual,
            is_correct=False,
            error=f"Unexpected outcome key: {name}",
        )
    return results


# =============================================================================
# Eval Summary
# =============================================================================


class HasCorrectFlag(Protocol):
    """Protocol for results that expose a correctness flag."""

    @property
    def correct(self) -> bool | None:
        """Return True if correct, False if incorrect, None if unevaluated."""
        ...


@dataclass(frozen=True, slots=True)
class EvalSummaryBase:
    """Core evaluation metrics common across all projects."""

    total_runs: int
    successful_runs: int
    evaluated_runs: int
    correct_runs: int
    accuracy_total: float | None


class EvalSummaryBuilder:
    """Build evaluation summaries from result iterables."""

    @staticmethod
    def safe_accuracy(*, correct: int, total: int) -> float | None:
        """Return correct/total or None when total is zero."""

        if total <= 0:
            return None
        return correct / total

    @classmethod
    def compute_base_metrics(
        cls,
        results: Iterable[T],
        *,
        is_successful: Callable[[T], bool],
        get_correct: Callable[[T], bool | None],
    ) -> EvalSummaryBase:
        """Compute core metrics from any result iterable."""

        results_list = list(results)
        total_runs = len(results_list)
        successful_runs = sum(1 for r in results_list if is_successful(r))

        evaluated = [r for r in results_list if get_correct(r) is not None]
        evaluated_runs = len(evaluated)
        correct_runs = sum(1 for r in evaluated if get_correct(r) is True)
        accuracy_total = cls.safe_accuracy(correct=correct_runs, total=evaluated_runs)

        return EvalSummaryBase(
            total_runs=total_runs,
            successful_runs=successful_runs,
            evaluated_runs=evaluated_runs,
            correct_runs=correct_runs,
            accuracy_total=accuracy_total,
        )

    @classmethod
    def group_accuracy(
        cls,
        results: Iterable[T],
        *,
        key_fn: Callable[[T], str],
        get_correct: Callable[[T], bool | None],
    ) -> dict[str, float | None]:
        """Group results by a key function and compute per-group accuracy."""

        grouped: dict[str, dict[str, int]] = {}
        for result in results:
            if get_correct(result) is None:
                continue
            key = key_fn(result)
            bucket = grouped.setdefault(key, {"total": 0, "correct": 0})
            bucket["total"] += 1
            if get_correct(result) is True:
                bucket["correct"] += 1

        return {
            key: cls.safe_accuracy(correct=counts["correct"], total=counts["total"])
            for key, counts in grouped.items()
        }
