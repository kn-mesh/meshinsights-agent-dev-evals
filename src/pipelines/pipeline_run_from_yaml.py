"""Run a unit/timestamp Pulse pipeline from YAML."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from mi.core.pipeline_builder import PipelineBuilder
from mi.core.pipeline_receipt import PipelineReceipt


def run_pipeline(
    yaml_path: str | Path,
    *,
    unit: str,
    sensor_id: int,
    decision_timestamp: str | datetime,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
    retrieval_snapshot_mode: str | None = None,
    retrieval_snapshot_dir: str | Path | None = None,
) -> PipelineReceipt:
    """Run one portable unit/timestamp example through a YAML pipeline."""
    source_path = Path(yaml_path).resolve()
    config = _load_pipeline_config(source_path)
    runtime_config = _apply_runtime_overrides(
        config,
        unit=unit,
        sensor_id=sensor_id,
        decision_timestamp=_parse_timestamp(decision_timestamp),
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        retrieval_snapshot_mode=retrieval_snapshot_mode,
        retrieval_snapshot_dir=retrieval_snapshot_dir,
    )
    return _execute_runtime_config(source_path, runtime_config)


def _load_pipeline_config(path: Path) -> dict[str, Any]:
    """Load and validate a pipeline YAML mapping."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Pipeline YAML must define a mapping at its root.")
    return payload


def _apply_runtime_overrides(
    pipeline_config: dict[str, Any],
    *,
    unit: str,
    sensor_id: int,
    decision_timestamp: datetime,
    ai_model: str | None,
    ai_reasoning_effort: str | None,
    retrieval_snapshot_mode: str | None,
    retrieval_snapshot_dir: str | Path | None,
) -> dict[str, Any]:
    """Build an ephemeral runtime config without mutating source YAML."""
    runtime = copy.deepcopy(pipeline_config)
    metadata_class = str(runtime.pop("metadata_class", "PulseFailureAnalysisMetadata"))
    runtime["metadata"] = {
        "metadata": metadata_class,
        "unit": _normalize_unit(unit),
        "sensor_id": sensor_id,
        "decision_timestamp": decision_timestamp.isoformat(),
    }

    for retriever in runtime.get("retrieve", {}).get("retrievers", []):
        if not isinstance(retriever, dict):
            continue
        if retriever.get("retriever") != "PulseAlarmTemperatureHistoryRetriever":
            continue
        if retrieval_snapshot_mode is not None:
            retriever["snapshot_mode"] = retrieval_snapshot_mode
        if retrieval_snapshot_dir is not None:
            retriever["snapshot_dir"] = str(Path(retrieval_snapshot_dir).resolve())

    normalized_model = _normalize_override(ai_model)
    normalized_effort = _normalize_override(ai_reasoning_effort)
    for processor in runtime.get("process", {}).get("processors", []):
        if not isinstance(processor, dict) or not _is_ai_processor(processor):
            continue
        if normalized_model is not None:
            processor["model"] = normalized_model
        if normalized_effort is not None:
            processor["reasoning_effort"] = normalized_effort
        elif normalized_model is not None:
            processor.pop("reasoning_effort", None)
    return runtime


def _execute_runtime_config(
    source_path: Path, runtime_config: dict[str, Any]
) -> PipelineReceipt:
    """Build and execute an ephemeral YAML configuration."""
    runtime_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ppln",
            prefix=f".{source_path.stem}.runtime.",
            dir=source_path.parent,
            encoding="utf-8",
            delete=False,
        ) as runtime_file:
            yaml.safe_dump(runtime_config, runtime_file, sort_keys=False)
            runtime_path = Path(runtime_file.name)
        return PipelineBuilder.from_yaml(runtime_path).build().run()
    finally:
        if runtime_path is not None:
            runtime_path.unlink(missing_ok=True)


def _parse_timestamp(value: str | datetime) -> datetime:
    """Parse an ISO decision timestamp and normalize aware values to naive UTC."""
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = value.strip()
        if len(normalized) == 10 and "T" not in normalized:
            parsed = datetime.fromisoformat(normalized).replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        else:
            parsed = datetime.fromisoformat(
                normalized[:-1] + "+00:00" if normalized.endswith("Z") else normalized
            )
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_unit(value: str) -> str:
    """Validate the non-empty unit identity."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("unit must not be empty.")
    return normalized


def _normalize_override(value: str | None) -> str | None:
    """Normalize a nullable CLI override."""
    if value is None:
        return None
    normalized = value.strip()
    return None if not normalized or normalized.lower() == "default" else normalized


def _is_ai_processor(processor: dict[str, Any]) -> bool:
    """Return whether a processor config represents an AI execution stage."""
    name = str(processor.get("processor", ""))
    return "Agent" in name or "AI" in name or "model" in processor


def _receipt_summary(receipt: PipelineReceipt) -> dict[str, Any]:
    """Create a compact JSON-safe CLI result."""
    return {
        "success": receipt.success,
        "pipeline_name": receipt.get_config("name"),
        "pipeline_version": receipt.get_config("version"),
        "retrieve_metadata": (
            receipt.retrieve_receipt.metadata if receipt.retrieve_receipt else {}
        ),
        "act_metadata": receipt.act_receipt.metadata if receipt.act_receipt else {},
        "process_error": (
            receipt.process_receipt.error if receipt.process_receipt else None
        ),
        "act_error": receipt.act_receipt.error if receipt.act_receipt else None,
    }


def _argument_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Run a Pulse agent for one unit at a decision timestamp."
    )
    parser.add_argument("yaml_path", type=Path)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--sensor-id", required=True, type=int)
    parser.add_argument("--decision-timestamp", required=True)
    parser.add_argument("--ai-model")
    parser.add_argument("--ai-reasoning-effort")
    parser.add_argument(
        "--retrieval-snapshot-mode", choices=["off", "use", "refresh", "strict"]
    )
    parser.add_argument("--retrieval-snapshot-dir", type=Path)
    return parser


def main() -> None:
    """Run the configured pipeline and print its durable receipt output."""
    args = _argument_parser().parse_args()
    receipt = run_pipeline(
        args.yaml_path,
        unit=args.unit,
        sensor_id=args.sensor_id,
        decision_timestamp=args.decision_timestamp,
        ai_model=args.ai_model,
        ai_reasoning_effort=args.ai_reasoning_effort,
        retrieval_snapshot_mode=args.retrieval_snapshot_mode,
        retrieval_snapshot_dir=args.retrieval_snapshot_dir,
    )
    print(json.dumps(_receipt_summary(receipt), indent=2))


if __name__ == "__main__":
    main()
