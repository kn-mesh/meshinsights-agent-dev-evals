"""Explicit durable projections for retained evaluation artifacts."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


RETAINED_UNIT_FIELDS = (
    "example_id",
    "unit_id",
    "decision_timestamp",
    "source_snapshot_id",
    "label_schema_version_id",
    "run_index",
    "work_item_id",
    "metadata",
    "published_review_context",
    "raw_artifacts",
    "raw_captured_at",
    "raw_known_gaps",
    "raw_snapshot_content_sha256",
    "raw_source_kind",
    "raw_window_start",
    "raw_window_end",
    "benchmark_labels",
    "slice_keys",
    "agent_output",
    "evaluations",
    "complete_evaluation_correct",
    "contract_errors",
    "execution_status",
    "output_contract_status",
    "scoring_status",
    "failure_type",
    "error",
    "usage",
    "cost",
)


def project_retained_unit(unit: dict[str, Any]) -> dict[str, Any]:
    """Keep only the stable scientific and evidence contract for one unit."""
    return {
        key: deepcopy(unit[key])
        for key in RETAINED_UNIT_FIELDS
        if key in unit
    }


def project_retained_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove working-invocation identity from an aggregate retained result."""
    output = deepcopy(result)
    run = output.get("run")
    if isinstance(run, dict):
        run.pop("latest_invocation_id", None)
    return output
