"""
Pipeline output helpers for collecting run results and writing output files.

Provides domain-agnostic collection of batch pipeline results from
PipelineOrchestrator, plus utilities for file naming and JSON output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence, TypeVar
from uuid import uuid4

from mi.core.pipeline_receipt import PipelineReceipt


T = TypeVar("T")


# =============================================================================
# Orchestrated Runs Receipt
# =============================================================================


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Outcome of a single pipeline run."""

    receipt: PipelineReceipt | None = None
    error: Exception | None = None

    @property
    def success(self) -> bool:
        """Return True if the run completed without error and the receipt succeeded."""

        return self.error is None and self.receipt is not None and self.receipt.success


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Record a single run outcome and its metadata."""

    run_id: str
    outcome: RunOutcome
    metadata: dict[str, Any]


@dataclass
class OrchestratedRunsReceipt:
    """Collect multiple pipeline run outcomes with batch recording support."""

    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    _runs: list[RunRecord] = field(default_factory=list, repr=False)

    @classmethod
    def from_orchestrator_results(
        cls,
        results: dict[T, PipelineReceipt],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "OrchestratedRunsReceipt":
        """Create a receipt from PipelineOrchestrator.run() output."""

        receipt = cls()
        receipt.record_batch(results=results, metadata=metadata)
        return receipt

    def record_batch(
        self,
        *,
        results: dict[Any, PipelineReceipt],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a batch of pipeline results from PipelineOrchestrator.run()."""

        base_metadata = metadata or {}
        for run_id, receipt in results.items():
            run_metadata = dict(base_metadata)
            run_metadata["eval.unit_id"] = run_id
            outcome = RunOutcome(receipt=receipt)
            self._runs.append(RunRecord(run_id=str(run_id), outcome=outcome, metadata=run_metadata))

    def record_run(
        self,
        *,
        run_id: str,
        outcome: RunOutcome,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a single pipeline outcome and associated metadata."""

        self._runs.append(RunRecord(run_id=run_id, outcome=outcome, metadata=metadata or {}))

    def list_runs(self) -> tuple[RunRecord, ...]:
        """Return recorded runs in insertion order."""

        return tuple(self._runs)


# =============================================================================
# Output Helpers
# =============================================================================


@dataclass(frozen=True, slots=True)
class EvalResultsEnvelope:
    """Stable top-level eval results payload shared across repos."""

    summary: dict[str, Any]
    run_config: dict[str, Any]
    selected_unit_ids: list[str]
    results: list[dict[str, Any]]

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary for this eval payload."""

        return {
            "summary": self.summary,
            "run_config": self.run_config,
            "selected_unit_ids": list(self.selected_unit_ids),
            "results": self.results,
        }


def normalize_filename_token(value: str | None) -> str:
    """Normalize a value into a filesystem-safe filename token."""

    token = (value or "default").strip()
    token = token.replace("/", "_")
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", token)
    token = token.strip("._-")
    return token or "default"


def normalize_token(value: str, *, separator: str = "_", uppercase: bool = False, fallback: str = "UNKNOWN") -> str:
    """Normalize a string into a safe token with configurable separator."""

    normalized = re.sub(r"[^A-Za-z0-9]+", separator, value.strip())
    normalized = re.sub(rf"{re.escape(separator)}+", separator, normalized).strip(separator)
    result = normalized or fallback
    return result.upper() if uppercase else result


def build_results_filename(
    *,
    ai_provider: str | None,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
    eval_scope: str,
    runs_per_unit: int,
    timestamp_utc: str,
) -> str:
    """Build an eval results filename using a standard naming convention."""

    provider = normalize_filename_token(ai_provider)
    model = normalize_filename_token(ai_model)
    effort = normalize_filename_token(ai_reasoning_effort)
    scope = normalize_filename_token(eval_scope)
    rpu = max(0, int(runs_per_unit))
    return f"{provider}_{model}_{effort}_{scope}_{rpu}runsPerUnit_{timestamp_utc}.json"


def build_results_dir_for_pipeline(*, base_results_dir: Path, yaml_path: Path) -> Path:
    """Return the output directory name scoped to a pipeline config file."""

    pipeline_token = normalize_filename_token(yaml_path.stem)
    return base_results_dir.parent / f"{base_results_dir.name}_{pipeline_token}"


def build_eval_results_path(
    *,
    base_results_dir: Path,
    yaml_path: Path,
    filename: str,
    subdirs: Sequence[str | Path] = (),
) -> Path:
    """Return the full output path for one eval results JSON file."""

    output_dir = build_results_dir_for_pipeline(
        base_results_dir=base_results_dir,
        yaml_path=yaml_path,
    )
    for part in subdirs:
        output_dir /= Path(part)
    return output_dir / filename


def build_eval_run_config(
    *,
    yaml_path: str | Path,
    rubric_file: str | Path | None,
    units: str | None,
    unit_id: str | None = None,
    runs_per_unit: int,
    runtime: str,
    max_workers: int,
    error_action: str | None = None,
    ai_provider: str | None = None,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
    completed_at_utc: str | None = None,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard `run_config` payload for one eval invocation."""

    payload: dict[str, Any] = {
        "yaml_path": str(yaml_path),
        "rubric_file": None if rubric_file is None else str(rubric_file),
        "units": units,
        "unit_id": unit_id,
        "runs_per_unit": runs_per_unit,
        "runtime": runtime,
        "max_workers": max_workers,
        "error_action": error_action,
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_reasoning_effort": ai_reasoning_effort,
        "completed_at_utc": completed_at_utc,
    }
    if extra_fields:
        payload.update(dict(extra_fields))
    return payload


def write_eval_results(
    *,
    envelope: EvalResultsEnvelope,
    output_path: Path,
) -> Path:
    """Write one eval results envelope to disk and return the written path."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(envelope.to_json_dict(), indent=2),
        encoding="utf-8",
    )
    return output_path


def write_eval_results_json(
    *,
    summary: dict[str, Any],
    run_config: dict[str, Any],
    selected_unit_ids: list[str] | None = None,
    selected_location_ids: list[str] | None = None,
    results: list[dict[str, Any]],
    output_dir: Path,
    filename: str,
) -> Path:
    """Write an eval results JSON payload to disk and return the path.

    `selected_location_ids` remains accepted as a legacy alias during migration.
    """

    resolved_unit_ids = (
        list(selected_unit_ids)
        if selected_unit_ids is not None
        else list(selected_location_ids or [])
    )
    envelope = EvalResultsEnvelope(
        summary=summary,
        run_config=run_config,
        selected_unit_ids=resolved_unit_ids,
        results=results,
    )
    return write_eval_results(
        envelope=envelope,
        output_path=output_dir / filename,
    )
