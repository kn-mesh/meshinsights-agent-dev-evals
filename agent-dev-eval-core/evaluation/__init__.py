"""Reusable, use-case-neutral agent evaluation primitives."""

from evaluation.execution import (
    ErrorActionType,
    ExecutionCancelledError,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalRecord,
    RepeatedEvalWorkItem,
    RuntimeType,
)
from evaluation.metrics import (
    MetricCounts,
    build_confidence_accuracy,
    build_performance_summary,
    build_reliability_summary,
    group_metric_counts,
    metric_counts,
)
from evaluation.models import (
    AttemptStatus,
    EvalAttempt,
    FailureType,
    LabelEvaluation,
)
from evaluation.receipt_extraction import (
    StructuredOutputExtraction,
    StructuredOutputSpec,
    extract_structured_outputs,
    validate_metadata_identity,
)
from evaluation.result_writer import (
    build_results_dir_for_pipeline,
    normalize_filename_token,
    write_json_exclusive,
)

__all__ = [
    "AttemptStatus",
    "ErrorActionType",
    "EvalAttempt",
    "ExecutionCancelledError",
    "FailureType",
    "LabelEvaluation",
    "MetricCounts",
    "RepeatedEvalExecutor",
    "RepeatedEvalExecutorConfig",
    "RepeatedEvalRecord",
    "RepeatedEvalWorkItem",
    "RuntimeType",
    "StructuredOutputExtraction",
    "StructuredOutputSpec",
    "build_performance_summary",
    "build_confidence_accuracy",
    "build_reliability_summary",
    "build_results_dir_for_pipeline",
    "extract_structured_outputs",
    "group_metric_counts",
    "metric_counts",
    "normalize_filename_token",
    "validate_metadata_identity",
    "write_json_exclusive",
]
