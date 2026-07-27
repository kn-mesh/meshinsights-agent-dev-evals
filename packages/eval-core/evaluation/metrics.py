"""Accuracy, reliability, and performance aggregation primitives."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import mean, median

from evaluation.models import (
    EvalAttempt,
    ExecutionStatus,
    OutputContractStatus,
    ScoringStatus,
)


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


def build_reliability_summary(
    attempts: Iterable[EvalAttempt],
    *,
    planned_runs: int,
) -> dict[str, object]:
    """Summarize whether planned runs produced complete, valid agent outputs."""
    attempts_list = list(attempts)
    if planned_runs < len(attempts_list):
        raise ValueError("planned_runs cannot be smaller than recorded attempts.")
    execution_counts = Counter(
        attempt.execution_status.value for attempt in attempts_list
    )
    output_counts = Counter(
        attempt.output_contract_status.value for attempt in attempts_list
    )
    failure_counts = Counter(
        attempt.failure_type.value
        for attempt in attempts_list
        if attempt.failure_type is not None
    )
    return {
        "planned_runs": planned_runs,
        "recorded_runs": len(attempts_list),
        "execution_status_counts": dict(sorted(execution_counts.items())),
        "output_contract_status_counts": dict(sorted(output_counts.items())),
        "output_contract_validity_rate": (
            None
            if planned_runs == 0
            else output_counts[OutputContractStatus.VALID.value] / planned_runs
        ),
        "failures_by_type": dict(sorted(failure_counts.items())),
    }


def build_scoring_coverage(
    attempts: Iterable[EvalAttempt],
    *,
    planned_runs: int,
) -> dict[str, object]:
    attempts_list = list(attempts)
    status_counts = Counter(attempt.scoring_status.value for attempt in attempts_list)
    scored = status_counts[ScoringStatus.SCORED.value]
    valid_with_targets = sum(
        attempt.output_contract_status is OutputContractStatus.VALID
        and attempt.scoring_status is not ScoringStatus.NO_APPLICABLE_TARGETS
        for attempt in attempts_list
    )
    return {
        "status_counts": dict(sorted(status_counts.items())),
        "scored_runs": scored,
        "planned_runs": planned_runs,
        "coverage": None if planned_runs == 0 else scored / planned_runs,
        "grader_completion_rate": (
            None if valid_with_targets == 0 else scored / valid_with_targets
        ),
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
    successful = [
        attempt
        for attempt in attempts_list
        if attempt.execution_status is ExecutionStatus.COMPLETED
    ]
    failed = [
        attempt
        for attempt in attempts_list
        if attempt.execution_status is not ExecutionStatus.COMPLETED
    ]
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
            "p5": None,
            "p95": None,
        }
    return {
        "count": len(samples),
        "minimum": samples[0],
        "maximum": samples[-1],
        "mean": mean(samples),
        "median": median(samples),
        "p5": _percentile(samples, 0.05),
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
