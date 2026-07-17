"""Pipeline evaluation helpers for orchestrated runs and output."""

from src.experimental_core.evals.pipeline.eval_results import (
    EvalResult,
    EvalSummaryBase,
    EvalSummaryBuilder,
    HasCorrectFlag,
    evaluate_outcome,
    evaluate_outcomes,
)
from src.experimental_core.evals.pipeline.pipeline_output import (
    EvalResultsEnvelope,
    OrchestratedRunsReceipt,
    RunOutcome,
    RunRecord,
    build_eval_results_path,
    build_eval_run_config,
    build_results_dir_for_pipeline,
    build_results_filename,
    normalize_filename_token,
    normalize_token,
    write_eval_results,
    write_eval_results_json,
)
from src.experimental_core.evals.pipeline.repeated_eval_executor import (
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalRecord,
    RepeatedEvalWorkItem,
)
from src.experimental_core.evals.pipeline.repeated_eval_models import (
    EvalAttempt,
    UnitEvalResult,
)
from src.experimental_core.evals.pipeline.receipt_extraction import (
    ReceiptExtractionResult,
    ReceiptFieldSpec,
    extract_receipt_fields,
    extract_stage_metadata_fields,
)

__all__ = [
    # Eval result primitives
    "EvalResult",
    "evaluate_outcome",
    "evaluate_outcomes",
    # Eval summary
    "EvalSummaryBase",
    "EvalSummaryBuilder",
    "HasCorrectFlag",
    # Orchestrated runs
    "OrchestratedRunsReceipt",
    "RunOutcome",
    "RunRecord",
    "EvalResultsEnvelope",
    "EvalAttempt",
    "UnitEvalResult",
    "ReceiptExtractionResult",
    "ReceiptFieldSpec",
    "extract_receipt_fields",
    "extract_stage_metadata_fields",
    "RepeatedEvalExecutor",
    "RepeatedEvalExecutorConfig",
    "RepeatedEvalRecord",
    "RepeatedEvalWorkItem",
    # Paths and tokens
    "build_eval_results_path",
    "build_eval_run_config",
    "build_results_dir_for_pipeline",
    "build_results_filename",
    "normalize_filename_token",
    "normalize_token",
    # Eval results output
    "write_eval_results",
    "write_eval_results_json",
]
