"""Strict extraction of required outputs from agent receipt metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class StructuredOutputSpec:
    """Describe one required output and its optional confidence field."""

    name: str
    metadata_key: str
    value_path: tuple[str, ...] = ("value",)
    confidence_path: tuple[str, ...] | None = None
    required: bool = True
    confidence_values: tuple[str, ...] = ("High", "Low")

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty.")
        if not self.metadata_key.strip():
            raise ValueError("metadata_key must not be empty.")
        if self.confidence_path is not None and not self.confidence_values:
            raise ValueError("confidence_values must not be empty when configured.")


@dataclass(frozen=True, slots=True)
class StructuredOutputExtraction:
    """Values, optional confidence, raw output, and contract errors."""

    actual_values: dict[str, str] = field(default_factory=dict)
    confidence_values: dict[str, str] = field(default_factory=dict)
    raw_outputs: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def extract_structured_outputs(
    metadata: Any,
    *,
    specs: Sequence[StructuredOutputSpec],
) -> StructuredOutputExtraction:
    """Extract outputs and report every required-contract violation."""
    errors = _validate_specs(specs)
    if not isinstance(metadata, Mapping):
        return StructuredOutputExtraction(
            errors=(*errors, "Stage metadata must be a mapping."),
        )

    actual_values: dict[str, str] = {}
    confidence_values: dict[str, str] = {}
    raw_outputs: dict[str, Any] = {}
    for spec in specs:
        raw_output = metadata.get(spec.metadata_key)
        if raw_output is not None:
            raw_outputs[spec.name] = raw_output
        actual = _read_non_empty_string(raw_output, spec.value_path)
        if actual is None:
            if spec.required:
                errors.append(f"Missing or invalid required output '{spec.name}'.")
            continue
        actual_values[spec.name] = actual

        if spec.confidence_path is None:
            continue
        confidence = _read_non_empty_string(raw_output, spec.confidence_path)
        if confidence is None:
            continue
        if confidence not in spec.confidence_values:
            supported = ", ".join(spec.confidence_values)
            errors.append(
                f"Output '{spec.name}' has unsupported confidence "
                f"'{confidence}'; expected one of: {supported}."
            )
            continue
        confidence_values[spec.name] = confidence

    return StructuredOutputExtraction(
        actual_values=actual_values,
        confidence_values=confidence_values,
        raw_outputs=raw_outputs,
        errors=tuple(errors),
    )


def validate_metadata_identity(
    metadata: Any,
    *,
    expected: Mapping[str, str | int],
) -> tuple[str, ...]:
    """Return receipt identity mismatches against one planned benchmark example."""
    if not isinstance(metadata, Mapping):
        return ("Stage metadata must be a mapping.",)
    errors: list[str] = []
    for name, expected_value in expected.items():
        actual_value = metadata.get(name)
        if actual_value != expected_value:
            errors.append(
                f"Receipt identity mismatch for '{name}': "
                f"expected {expected_value!r}, got {actual_value!r}."
            )
    return tuple(errors)


def _validate_specs(specs: Sequence[StructuredOutputSpec]) -> list[str]:
    names: set[str] = set()
    errors: list[str] = []
    for spec in specs:
        if spec.name in names:
            errors.append(f"Duplicate structured output name: '{spec.name}'.")
        names.add(spec.name)
    return errors


def _read_non_empty_string(value: Any, path: tuple[str, ...]) -> str | None:
    current = value
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    if not isinstance(current, str):
        return None
    normalized = current.strip()
    return normalized or None
