"""Shared helpers for extracting eval fields from pipeline receipt metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from mi.core.pipeline_receipt import PipelineReceipt


@dataclass(frozen=True, slots=True)
class ReceiptFieldSpec:
    """Describe one field to extract from stage metadata."""

    output_name: str
    metadata_key: str
    value_path: tuple[str, ...] = ()
    artifact_group: str | None = None
    artifact_name: str | None = None

    def __post_init__(self) -> None:
        """Validate the field spec shape."""

        if not self.output_name.strip():
            raise ValueError("output_name must not be empty.")
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty.")
        if self.artifact_name is not None and self.artifact_group is None:
            raise ValueError(
                "artifact_name requires artifact_group so the raw value has a parent artifact key."
            )


@dataclass(frozen=True, slots=True)
class ReceiptExtractionResult:
    """Structured result of extracting eval fields from one stage receipt."""

    stage_name: str
    stage_metadata: dict[str, Any] = field(default_factory=dict)
    actual_values: dict[str, str | None] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def get_actual_value(self, name: str) -> str | None:
        """Return one extracted actual value."""

        return self.actual_values.get(name)

    def get_artifact(self, name: str) -> Any | None:
        """Return one extracted artifact."""

        return self.artifacts.get(name)


def extract_receipt_fields(
    receipt: PipelineReceipt,
    *,
    field_specs: Sequence[ReceiptFieldSpec],
    stage_name: str = "act",
) -> ReceiptExtractionResult:
    """Extract configured fields from one pipeline receipt stage."""

    stage_receipt = receipt.get_stage_receipt(stage_name)
    return extract_stage_metadata_fields(
        stage_receipt.metadata if stage_receipt is not None else {},
        field_specs=field_specs,
        stage_name=stage_name,
    )


def extract_stage_metadata_fields(
    metadata: Any,
    *,
    field_specs: Sequence[ReceiptFieldSpec],
    stage_name: str = "act",
) -> ReceiptExtractionResult:
    """Extract configured fields from raw stage metadata."""

    stage_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    actual_values: dict[str, str | None] = {}
    artifacts: dict[str, Any] = {}

    for spec in field_specs:
        raw_value = stage_metadata.get(spec.metadata_key)
        extracted = _extract_string_value(raw_value, value_path=spec.value_path)
        if extracted is not None:
            actual_values[spec.output_name] = extracted

        if spec.artifact_group is not None and raw_value is not None:
            artifact_name = spec.artifact_name or spec.metadata_key
            grouped = artifacts.setdefault(spec.artifact_group, {})
            if isinstance(grouped, dict):
                grouped[artifact_name] = raw_value

    return ReceiptExtractionResult(
        stage_name=stage_name,
        stage_metadata=stage_metadata,
        actual_values=actual_values,
        artifacts=artifacts,
    )


def _extract_string_value(value: Any, *, value_path: tuple[str, ...]) -> str | None:
    """Read one stripped string value from a nested mapping path."""

    current = value
    for path_part in value_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(path_part)

    if not isinstance(current, str):
        return None

    stripped = current.strip()
    return stripped or None
