"""Reusable orchestration for running eval feedback on low-accuracy units."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from mi.core import PipelineConfig
from mi.core.pipeline import PipelineMetadata
from mi.core.pipeline_builder import PipelineBuilder
from mi.core.pipeline_orchestrator import OrchestratorConfig, PipelineOrchestrator
from mi.core.pipeline_receipt import PipelineReceipt

from src.experimental_core.ai_feedback_automation.eval_results_document import EvalResultsDocument
from src.experimental_core.evals.ai_metadata import (
    ErrorActionType,
    RuntimeType,
    build_ai_metadata_extras,
)
from src.experimental_core.evals.pipeline.pipeline_output import OrchestratedRunsReceipt


@dataclass(frozen=True, slots=True)
class EvalFeedbackOrchestratorConfig:
    """Configuration for extracting units and feedback from eval results."""

    accuracy_threshold: float
    results_key: str = "results"
    unit_id_key: str = "unit_id"
    context_metadata_key: str = "eval_context_json"
    receipt_feedback_key: str = "evaluation_feedback"


@dataclass(frozen=True, slots=True)
class EvalFeedbackRunResult:
    """Single feedback result from a pipeline run."""

    unit_id: str
    run_started_at: str
    ai_provider: str | None
    ai_model: str | None
    ai_reasoning_effort: str | None
    success: bool
    error: str | None
    feedback: dict[str, Any] | None
    unit_context: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EvalFeedbackReport:
    """Serializable report for an eval-feedback batch run."""

    source_eval_results: str
    accuracy_threshold: float
    selected_unit_ids: list[str]
    eval_run_config: dict[str, Any] | None
    eval_summary: dict[str, Any] | None
    pipeline_run_config: dict[str, Any]
    results: list[EvalFeedbackRunResult]

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary for this report."""

        return {
            "source_eval_results": self.source_eval_results,
            "accuracy_threshold": self.accuracy_threshold,
            "selected_unit_ids": list(self.selected_unit_ids),
            "eval_run_config": self.eval_run_config,
            "eval_summary": self.eval_summary,
            "pipeline_run_config": dict(self.pipeline_run_config),
            "results": [asdict(result) for result in self.results],
        }


class EvalFeedbackOrchestrator:
    """Run a feedback pipeline for units selected from an eval results document."""

    def __init__(self, *, builder: PipelineBuilder, config: EvalFeedbackOrchestratorConfig) -> None:
        """Initialize the orchestrator with injected dependencies."""

        self._builder = builder
        self._config = config

    def select_units(self, *, document: EvalResultsDocument) -> list[str]:
        """Return unit ids whose accuracy falls below the configured threshold."""

        unit_accuracy = document.read_accuracy_by_unit_id()
        selected = [
            unit_id
            for unit_id, accuracy in unit_accuracy.items()
            if accuracy is not None and accuracy < self._config.accuracy_threshold
        ]
        return sorted(selected)

    def build_unit_contexts(
        self,
        *,
        document: EvalResultsDocument,
        selected_unit_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Build per-unit eval context payloads for downstream feedback processors."""

        unit_accuracy = document.read_accuracy_by_unit_id()
        run_config = document.read_run_config()
        source_run_config = run_config if isinstance(run_config, dict) else None

        contexts: dict[str, dict[str, Any]] = {}
        for unit_id in selected_unit_ids:
            unit_results = document.filter_results_for_unit(
                unit_id=unit_id,
                unit_id_key=self._config.unit_id_key,
                results_key=self._config.results_key,
            )
            contexts[unit_id] = {
                "unit_id": unit_id,
                "accuracy": unit_accuracy.get(unit_id),
                "threshold": self._config.accuracy_threshold,
                "source_run_config": source_run_config,
                "results": unit_results,
            }
        return contexts

    def run(
        self,
        *,
        document: EvalResultsDocument,
        runtime: RuntimeType,
        max_workers: int,
        error_action: ErrorActionType,
        ai_provider: str | None = None,
        ai_model: str | None = None,
        ai_reasoning_effort: str | None = None,
        pipeline_yaml_path: str | None = None,
    ) -> EvalFeedbackReport:
        """Execute feedback pipelines and return a collected report."""

        selected_unit_ids = self.select_units(document=document)
        unit_contexts = self.build_unit_contexts(document=document, selected_unit_ids=selected_unit_ids)
        run_started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if not selected_unit_ids:
            return self._build_report(
                document=document,
                results=[],
                selected_unit_ids=selected_unit_ids,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
                run_started_at=run_started_at,
                pipeline_yaml_path=pipeline_yaml_path,
            )

        orchestrator = self._build_orchestrator(
            runtime=runtime,
            max_workers=max_workers,
            error_action=error_action,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_reasoning_effort=ai_reasoning_effort,
            unit_contexts=unit_contexts,
        )

        batch_results = orchestrator.run(selected_unit_ids)
        receipt = OrchestratedRunsReceipt.from_orchestrator_results(
            batch_results,
            metadata={"run.started_at": run_started_at},
        )

        parsed = [
            self._parse_result(
                unit_id=record.run_id,
                receipt=record.outcome.receipt,
                error=record.outcome.error,
                run_started_at=run_started_at,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
                unit_context=unit_contexts.get(record.run_id, {}),
            )
            for record in receipt.list_runs()
        ]

        return self._build_report(
            document=document,
            results=parsed,
            selected_unit_ids=selected_unit_ids,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_reasoning_effort=ai_reasoning_effort,
            run_started_at=run_started_at,
            pipeline_yaml_path=pipeline_yaml_path,
        )

    def _build_orchestrator(
        self,
        *,
        runtime: RuntimeType,
        max_workers: int,
        error_action: ErrorActionType,
        ai_provider: str | None,
        ai_model: str | None,
        ai_reasoning_effort: str | None,
        unit_contexts: dict[str, dict[str, Any]],
    ) -> PipelineOrchestrator[str]:
        """Build a pipeline orchestrator configured for feedback runs."""

        extras = build_ai_metadata_extras(
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_reasoning_effort=ai_reasoning_effort,
        )

        def adapter(unit_id: str) -> PipelineConfig:
            """Convert a unit id into pipeline config for this run."""

            context = unit_contexts.get(unit_id, {})
            model_extra = dict(extras)
            model_extra[self._config.context_metadata_key] = json.dumps(context)
            return PipelineConfig(metadata=PipelineMetadata(unit=unit_id, **model_extra))

        return (
            PipelineOrchestrator[str]()
            .with_builder(self._builder)
            .with_adapter(adapter)
            .with_config(
                OrchestratorConfig(
                    runtime=runtime,
                    error_action=error_action,
                    max_workers=max_workers,
                ),
                overwrite=True,
            )
        )

    def _parse_result(
        self,
        *,
        unit_id: str,
        receipt: PipelineReceipt | None,
        error: Exception | None,
        run_started_at: str,
        ai_provider: str | None,
        ai_model: str | None,
        ai_reasoning_effort: str | None,
        unit_context: dict[str, Any],
    ) -> EvalFeedbackRunResult:
        """Normalize a pipeline receipt into a feedback run result."""

        if error is not None or receipt is None:
            return EvalFeedbackRunResult(
                unit_id=unit_id,
                run_started_at=run_started_at,
                ai_provider=ai_provider,
                ai_model=ai_model,
                ai_reasoning_effort=ai_reasoning_effort,
                success=False,
                error=str(error) if error is not None else "Missing receipt",
                feedback=None,
                unit_context=unit_context,
            )

        error_text = None
        if receipt.act_receipt is not None and receipt.act_receipt.error:
            error_text = receipt.act_receipt.error
        elif receipt.process_receipt is not None and receipt.process_receipt.error:
            error_text = receipt.process_receipt.error
        elif receipt.retrieve_receipt is not None and receipt.retrieve_receipt.error:
            error_text = receipt.retrieve_receipt.error

        metadata = receipt.act_receipt.metadata if receipt.act_receipt is not None else {}
        feedback = metadata.get(self._config.receipt_feedback_key)
        return EvalFeedbackRunResult(
            unit_id=unit_id,
            run_started_at=run_started_at,
            ai_provider=ai_provider,
            ai_model=ai_model,
            ai_reasoning_effort=ai_reasoning_effort,
            success=receipt.success,
            error=error_text,
            feedback=feedback if isinstance(feedback, dict) else None,
            unit_context=unit_context,
        )

    def _build_report(
        self,
        *,
        document: EvalResultsDocument,
        results: list[EvalFeedbackRunResult],
        selected_unit_ids: list[str],
        ai_provider: str | None,
        ai_model: str | None,
        ai_reasoning_effort: str | None,
        run_started_at: str,
        pipeline_yaml_path: str | None,
    ) -> EvalFeedbackReport:
        """Build a serializable report from a run."""

        completed_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        source = str(document.source_path) if document.source_path is not None else "n/a"
        pipeline_run_config: dict[str, Any] = {
            "yaml_path": pipeline_yaml_path,
            "ai_provider": ai_provider,
            "ai_model": ai_model,
            "ai_reasoning_effort": ai_reasoning_effort,
            "run_started_at": run_started_at,
            "completed_at_utc": completed_at,
        }

        return EvalFeedbackReport(
            source_eval_results=source,
            accuracy_threshold=self._config.accuracy_threshold,
            selected_unit_ids=list(selected_unit_ids),
            eval_run_config=document.read_run_config(),
            eval_summary=document.read_summary(),
            pipeline_run_config=pipeline_run_config,
            results=list(results),
        )
