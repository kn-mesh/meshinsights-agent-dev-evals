"""Accuracy, reliability, and performance aggregation primitives."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import mean, median
from typing import TypeVar

from evaluation.models import AttemptStatus, EvalAttempt


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class MetricCounts:
    """Count-bearing accuracy metric with an explicit empty value."""

    correct_runs: int
    evaluated_runs: int
    accuracy: float | None

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "accuracy": self.accuracy,
            "correct_runs": self.correct_runs,
            "evaluated_runs": self.evaluated_runs,
        }


def metric_counts(correctness: Iterable[bool]) -> MetricCounts:
    """Return validated correct/evaluated counts for boolean observations."""
    flags = list(correctness)
    correct = sum(flag is True for flag in flags)
    evaluated = len(flags)
    return MetricCounts(
        correct_runs=correct,
        evaluated_runs=evaluated,
        accuracy=None if evaluated == 0 else correct / evaluated,
    )


def group_metric_counts(
    observations: Iterable[T],
    *,
    key_fn: Callable[[T], str],
    correct_fn: Callable[[T], bool],
    expected_keys: Iterable[str] = (),
) -> dict[str, MetricCounts]:
    """Group observations deterministically and retain explicitly empty groups."""
    grouped: dict[str, list[bool]] = {key: [] for key in expected_keys}
    for observation in observations:
        grouped.setdefault(key_fn(observation), []).append(correct_fn(observation))
    return {key: metric_counts(grouped[key]) for key in sorted(grouped)}


def build_confidence_accuracy(
    attempts: Iterable[EvalAttempt],
    *,
    label_name: str,
    confidence_levels: Iterable[str] = ("High", "Low"),
    expected_values: Iterable[str] = (),
) -> dict[str, object]:
    """Build optional-confidence coverage and accuracy by expected label value."""
    attempts_list = list(attempts)
    levels = tuple(dict.fromkeys(confidence_levels))
    if not levels:
        raise ValueError("confidence_levels must not be empty.")
    evaluated = [
        attempt for attempt in attempts_list if label_name in attempt.evaluations
    ]
    with_confidence = [
        attempt
        for attempt in evaluated
        if attempt.confidence_values.get(label_name) in levels
    ]
    all_counts = group_metric_counts(
        with_confidence,
        key_fn=lambda attempt: attempt.confidence_values[label_name],
        correct_fn=lambda attempt: attempt.evaluations[label_name].is_correct,
        expected_keys=levels,
    )
    grouped: dict[str, dict[str, MetricCounts]] = {
        expected: group_metric_counts(
            (
                attempt
                for attempt in with_confidence
                if attempt.evaluations[label_name].expected == expected
            ),
            key_fn=lambda attempt: attempt.confidence_values[label_name],
            correct_fn=lambda attempt: attempt.evaluations[label_name].is_correct,
            expected_keys=levels,
        )
        for expected in sorted(
            set(expected_values)
            | {attempt.evaluations[label_name].expected for attempt in evaluated}
        )
    }
    return {
        "confidence_coverage": {
            "outputs_with_confidence": len(with_confidence),
            "evaluated_outputs": len(evaluated),
            "coverage": (
                None if not evaluated else len(with_confidence) / len(evaluated)
            ),
        },
        "all": {name: counts.to_dict() for name, counts in all_counts.items()},
        "by_expected_value": {
            expected: {
                name: counts.to_dict() for name, counts in confidence_counts.items()
            }
            for expected, confidence_counts in grouped.items()
        },
    }


def build_reliability_summary(
    attempts: Iterable[EvalAttempt],
    *,
    planned_runs: int,
) -> dict[str, object]:
    """Summarize whether planned runs produced complete, valid agent outputs."""
    attempts_list = list(attempts)
    if planned_runs < len(attempts_list):
        raise ValueError("planned_runs cannot be smaller than recorded attempts.")
    successful = sum(attempt.success for attempt in attempts_list)
    failed = sum(attempt.status is AttemptStatus.FAILED for attempt in attempts_list)
    cancelled = sum(
        attempt.status is AttemptStatus.CANCELLED for attempt in attempts_list
    )
    failure_counts = Counter(
        attempt.failure_type.value
        for attempt in attempts_list
        if attempt.failure_type is not None
    )
    return {
        "planned_runs": planned_runs,
        "recorded_runs": len(attempts_list),
        "successful_runs": successful,
        "failed_runs": failed,
        "cancelled_runs": cancelled,
        "reliability": None if planned_runs == 0 else successful / planned_runs,
        "failures_by_type": dict(sorted(failure_counts.items())),
    }


def build_performance_summary(
    attempts: Iterable[EvalAttempt],
    *,
    evaluation_wall_time_seconds: float,
) -> dict[str, object]:
    """Summarize wall time, throughput, run latency, and available stage latency."""
    if evaluation_wall_time_seconds < 0:
        raise ValueError("evaluation_wall_time_seconds must be non-negative.")
    attempts_list = list(attempts)
    successful = [attempt for attempt in attempts_list if attempt.success]
    failed = [attempt for attempt in attempts_list if not attempt.success]
    stage_names = sorted(
        {
            stage
            for attempt in attempts_list
            for stage in attempt.stage_durations_seconds
        }
    )
    throughput = (
        None
        if evaluation_wall_time_seconds == 0
        else len(attempts_list) / evaluation_wall_time_seconds * 60
    )
    return {
        "evaluation_wall_time_seconds": evaluation_wall_time_seconds,
        "throughput_runs_per_minute": throughput,
        "run_duration_seconds": _duration_stats(
            attempt.duration_seconds for attempt in attempts_list
        ),
        "successful_run_duration_seconds": _duration_stats(
            attempt.duration_seconds for attempt in successful
        ),
        "failed_run_duration_seconds": _duration_stats(
            attempt.duration_seconds for attempt in failed
        ),
        "stage_duration_seconds": {
            stage: _duration_stats(
                attempt.stage_durations_seconds[stage]
                for attempt in attempts_list
                if stage in attempt.stage_durations_seconds
            )
            for stage in stage_names
        },
    }


def _duration_stats(values: Iterable[float]) -> dict[str, int | float | None]:
    samples = sorted(values)
    if not samples:
        return {
            "count": 0,
            "minimum": None,
            "maximum": None,
            "mean": None,
            "median": None,
            "p95": None,
        }
    return {
        "count": len(samples),
        "minimum": samples[0],
        "maximum": samples[-1],
        "mean": mean(samples),
        "median": median(samples),
        "p95": _percentile(samples, 0.95),
    }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = position - lower_index
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )
