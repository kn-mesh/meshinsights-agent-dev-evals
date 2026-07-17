"""Core evaluation helpers for mi.core prototypes."""

# Shared utilities
from src.experimental_core.evals.ai_metadata import (
    ErrorActionType,
    RuntimeType,
    build_ai_metadata_extras,
)
from src.experimental_core.evals.rubric import JsonRubric, Rubric, RubricEntry
from src.experimental_core.evals.rubric_source import (
    LoadedRubric,
    RubricSource,
    filter_rubric_entries,
    list_rubric_files,
    load_rubric,
    load_rubric_entries,
    load_rubric_payload,
    resolve_rubric_display_name,
)

# CLI scaffolding
from src.experimental_core.evals.cli import (
    EvalArgParserBuilder,
    EvalWizardSelections,
    EvalWizardStepConfig,
    InteractiveEvalWizard,
    RuntimeProfileSpec,
    normalize_ai_reasoning_effort,
    prompt_free_text,
    prompt_optional_csv,
    prompt_positive_int,
    prompt_select_option,
    resolve_execution_profile,
)

# Pipeline evaluation
from src.experimental_core.evals.pipeline import (
    EvalAttempt,
    EvalResultsEnvelope,
    EvalResult,
    EvalSummaryBase,
    EvalSummaryBuilder,
    HasCorrectFlag,
    OrchestratedRunsReceipt,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalRecord,
    RepeatedEvalWorkItem,
    ReceiptExtractionResult,
    ReceiptFieldSpec,
    RunOutcome,
    RunRecord,
    UnitEvalResult,
    build_eval_results_path,
    build_eval_run_config,
    build_results_dir_for_pipeline,
    build_results_filename,
    extract_receipt_fields,
    extract_stage_metadata_fields,
    evaluate_outcome,
    evaluate_outcomes,
    normalize_filename_token,
    normalize_token,
    write_eval_results,
    write_eval_results_json,
)

__all__ = [
    # Shared - AI metadata
    "build_ai_metadata_extras",
    "ErrorActionType",
    "RuntimeType",
    # Shared - Rubric
    "JsonRubric",
    "Rubric",
    "RubricEntry",
    "LoadedRubric",
    "RubricSource",
    "filter_rubric_entries",
    "list_rubric_files",
    "load_rubric",
    "load_rubric_entries",
    "load_rubric_payload",
    "resolve_rubric_display_name",
    # Pipeline - Eval result primitives
    "EvalAttempt",
    "EvalResultsEnvelope",
    "EvalResult",
    "ReceiptExtractionResult",
    "ReceiptFieldSpec",
    "extract_receipt_fields",
    "extract_stage_metadata_fields",
    "evaluate_outcome",
    "evaluate_outcomes",
    # Pipeline - Eval summary
    "EvalSummaryBase",
    "EvalSummaryBuilder",
    "HasCorrectFlag",
    # Pipeline - Orchestrated runs
    "OrchestratedRunsReceipt",
    "RepeatedEvalExecutor",
    "RepeatedEvalExecutorConfig",
    "RepeatedEvalRecord",
    "RepeatedEvalWorkItem",
    "RunOutcome",
    "RunRecord",
    "UnitEvalResult",
    # Pipeline - Paths and tokens
    "build_eval_results_path",
    "build_eval_run_config",
    "build_results_dir_for_pipeline",
    "build_results_filename",
    "normalize_filename_token",
    "normalize_token",
    # Pipeline - Eval results output
    "write_eval_results",
    "write_eval_results_json",
    # CLI scaffolding
    "EvalArgParserBuilder",
    "EvalWizardSelections",
    "EvalWizardStepConfig",
    "InteractiveEvalWizard",
    "RuntimeProfileSpec",
    "normalize_ai_reasoning_effort",
    "prompt_free_text",
    "prompt_optional_csv",
    "prompt_positive_int",
    "prompt_select_option",
    "resolve_execution_profile",
]
