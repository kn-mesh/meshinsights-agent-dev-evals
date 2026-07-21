"""Reusable, use-case-neutral agent evaluation primitives."""

from evaluation.execution import (
    ErrorActionType,
    EvaluationInterruptedError,
    ExecutionCancelledError,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalRecord,
    RepeatedEvalWorkItem,
    RuntimeType,
)
from evaluation.graders import (
    DeterministicGrader,
    FieldGrade,
    GraderRegistry,
    build_default_grader_registry,
)
from evaluation.identity import (
    build_comparison_identity,
    build_run_identity,
    build_work_item_id,
    canonical_json_bytes,
    canonical_sha256,
)
from evaluation.metrics import (
    MetricCounts,
    build_confidence_accuracy,
    build_performance_summary,
    build_reliability_summary,
    build_scoring_coverage,
    group_metric_counts,
    metric_counts,
)
from evaluation.models import (
    EvalAttempt,
    ExecutionStatus,
    FailureType,
    FieldEvaluation,
    JsonScalar,
    OutputContractStatus,
    ScoringStatus,
)
from evaluation.receipt_extraction import (
    OutputFieldObservation,
    OutputFieldSpec,
    StructuredOutputExtraction,
    extract_output_fields,
    read_path,
    validate_metadata_identity,
)
from evaluation.result_writer import (
    build_results_dir_for_pipeline,
    normalize_filename_token,
    write_json_exclusive,
)
from evaluation.serialization import eval_attempt_from_dict, eval_attempt_to_dict

__all__ = [
    "DeterministicGrader",
    "ErrorActionType",
    "EvaluationInterruptedError",
    "EvalAttempt",
    "ExecutionCancelledError",
    "ExecutionStatus",
    "FailureType",
    "FieldEvaluation",
    "FieldGrade",
    "GraderRegistry",
    "JsonScalar",
    "MetricCounts",
    "OutputContractStatus",
    "OutputFieldObservation",
    "OutputFieldSpec",
    "RepeatedEvalExecutor",
    "RepeatedEvalExecutorConfig",
    "RepeatedEvalRecord",
    "RepeatedEvalWorkItem",
    "RuntimeType",
    "ScoringStatus",
    "StructuredOutputExtraction",
    "build_confidence_accuracy",
    "build_comparison_identity",
    "build_default_grader_registry",
    "build_performance_summary",
    "build_run_identity",
    "build_reliability_summary",
    "build_results_dir_for_pipeline",
    "build_scoring_coverage",
    "build_work_item_id",
    "canonical_json_bytes",
    "canonical_sha256",
    "eval_attempt_from_dict",
    "eval_attempt_to_dict",
    "extract_output_fields",
    "group_metric_counts",
    "metric_counts",
    "normalize_filename_token",
    "read_path",
    "validate_metadata_identity",
    "write_json_exclusive",
]
