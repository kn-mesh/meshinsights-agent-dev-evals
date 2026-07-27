"""Schema-driven JSON scalar extraction from pipeline receipt metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from evaluation.models import JsonScalar


ScalarType = Literal["string", "integer", "number", "boolean", "null"]


@dataclass(frozen=True, slots=True)
class OutputFieldSpec:
    name: str
    value_path: tuple[str, ...]
    value_type: ScalarType
    confidence_path: tuple[str, ...] | None = None
    confidence_values: tuple[JsonScalar, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.value_path:
            raise ValueError("Output fields require a name and non-empty value path.")
        if self.confidence_path is not None and not self.confidence_values:
            raise ValueError("Configured confidence paths require allowed values.")


@dataclass(frozen=True, slots=True)
class OutputFieldObservation:
    name: str
    present: bool
    valid: bool
    value: JsonScalar = None
    raw_value: Any = None
    confidence: JsonScalar = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StructuredOutputExtraction:
    observations: dict[str, OutputFieldObservation] = field(default_factory=dict)

    @property
    def actual_values(self) -> dict[str, JsonScalar]:
        return {
            name: observation.value
            for name, observation in self.observations.items()
            if observation.present and observation.valid
        }

    @property
    def confidence_values(self) -> dict[str, JsonScalar]:
        return {
            name: observation.confidence
            for name, observation in self.observations.items()
            if observation.confidence is not None
        }


def extract_output_fields(
    metadata: Any,
    *,
    specs: Sequence[OutputFieldSpec],
) -> StructuredOutputExtraction:
    """Observe every configured output without deciding requiredness."""
    names = [spec.name for spec in specs]
    if len(names) != len(set(names)):
        raise ValueError("Output field names must be unique.")
    observations: dict[str, OutputFieldObservation] = {}
    for spec in specs:
        found, raw_value = read_path(metadata, spec.value_path)
        if not found:
            observations[spec.name] = OutputFieldObservation(
                name=spec.name,
                present=False,
                valid=False,
            )
            continue
        errors: list[str] = []
        if not _matches_scalar_type(raw_value, spec.value_type):
            errors.append(
                f"Output '{spec.name}' must be {spec.value_type}; "
                f"received {type(raw_value).__name__}."
            )
        confidence: JsonScalar = None
        if spec.confidence_path is not None:
            confidence_found, raw_confidence = read_path(metadata, spec.confidence_path)
            if confidence_found:
                if not _is_json_scalar(raw_confidence):
                    errors.append(f"Output '{spec.name}' confidence must be scalar.")
                elif raw_confidence not in spec.confidence_values:
                    errors.append(
                        f"Output '{spec.name}' has unsupported confidence "
                        f"{raw_confidence!r}."
                    )
                else:
                    confidence = raw_confidence
        observations[spec.name] = OutputFieldObservation(
            name=spec.name,
            present=True,
            valid=not errors,
            value=raw_value if not errors else None,
            raw_value=raw_value,
            confidence=confidence,
            errors=tuple(errors),
        )
    return StructuredOutputExtraction(observations=observations)


def validate_metadata_identity(
    metadata: Any,
    *,
    expected: Mapping[str, str | int],
) -> tuple[str, ...]:
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


def read_path(value: Any, path: Sequence[str]) -> tuple[bool, Any]:
    current = value
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _is_json_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _matches_scalar_type(value: Any, value_type: ScalarType) -> bool:
    if value_type == "null":
        return value is None
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, str)
