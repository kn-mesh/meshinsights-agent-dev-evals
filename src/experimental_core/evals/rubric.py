"""
Core rubric abstractions for evaluation datasets.

Provides a standard protocol for loading and accessing expected outcomes
and unit metadata from rubric files.

Standard JSON schema:
{
  "units": [
    {
      "unit_id": "UNIT_001",
      "expected_outcomes": {"classification": "Failed", "confidence": "High"},
      "metadata": {"location_name": "Building A"}
    }
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


RubricPayload = dict[str, Any]


@dataclass(frozen=True, slots=True)
class RubricEntry:
    """A single entry in a rubric representing a unit of work."""

    unit_id: str
    expected_outcomes: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_outcome(self, name: str) -> str | None:
        """Return a single expected outcome by name, or None if not present."""
        return self.expected_outcomes.get(name)

    @property
    def outcome_names(self) -> list[str]:
        """Return the list of available outcome keys."""
        return list(self.expected_outcomes.keys())


@runtime_checkable
class Rubric(Protocol):
    """Protocol for rubric implementations."""

    def list_entries(self) -> list[RubricEntry]:
        """Return all entries in the rubric."""
        ...

    def get_entry(self, unit_id: str) -> RubricEntry | None:
        """Return a specific entry by unit_id, or None if not found."""
        ...

    def list_unit_ids(self) -> list[str]:
        """Return a list of all unit_ids in the rubric."""
        ...


class JsonRubric:
    """Standard implementation for JSON-based rubrics.

    Expects the standardized rubric JSON schema with fixed keys:
    `units`, `unit_id`, `expected_outcomes`, and optional `metadata`.
    """

    def __init__(self, path: Path) -> None:
        """Initialize and load the JSON rubric.

        Raises:
            FileNotFoundError: If the rubric file does not exist.
            ValueError: If the JSON does not conform to the expected schema.
        """
        self._path = path
        self._entries: dict[str, RubricEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load, validate, and parse the JSON file."""
        if not self._path.exists():
            raise FileNotFoundError(f"Rubric file not found: {self._path}")

        data = json.loads(self._path.read_text(encoding="utf-8"))
        parsed_entries = parse_rubric_entries(
            data,
            source_name=str(self._path),
        )
        self._entries = {entry.unit_id: entry for entry in parsed_entries}

    def list_entries(self) -> list[RubricEntry]:
        """Return all entries in insertion order."""
        return list(self._entries.values())

    def get_entry(self, unit_id: str) -> RubricEntry | None:
        """Return a specific entry by unit_id."""
        return self._entries.get(unit_id)

    def list_unit_ids(self) -> list[str]:
        """Return all unit identifiers."""
        return list(self._entries.keys())


def parse_rubric_entries(
    payload: RubricPayload,
    *,
    source_name: str,
) -> list[RubricEntry]:
    """Validate one rubric payload and return normalized entries."""

    if not isinstance(payload, dict):
        raise ValueError("Rubric payload must be a JSON object.")

    if "units" not in payload:
        raise ValueError(
            f"Rubric missing required top-level key 'units': {source_name}"
        )

    units = payload["units"]
    if not isinstance(units, list):
        raise ValueError(
            f"'units' must be a list, got {type(units).__name__}: {source_name}"
        )
    if not units:
        raise ValueError(f"Rubric payload does not contain any units: {source_name}")

    parsed_entries: list[RubricEntry] = []
    seen_unit_ids: set[str] = set()
    for index, item in enumerate(units):
        if not isinstance(item, dict):
            raise ValueError(
                f"Entry at index {index} must be an object: {source_name}"
            )

        unit_id = item.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            raise ValueError(
                f"Entry at index {index} has invalid 'unit_id' "
                f"(must be non-empty string): {source_name}"
            )

        outcomes = item.get("expected_outcomes")
        if not isinstance(outcomes, dict):
            raise ValueError(
                f"Entry at index {index} 'expected_outcomes' must be a dict, "
                f"got {type(outcomes).__name__}: {source_name}"
            )
        if not outcomes:
            raise ValueError(
                f"Entry at index {index} 'expected_outcomes' must not be empty: {source_name}"
            )

        normalized_outcomes: dict[str, str] = {}
        for key, value in outcomes.items():
            if not isinstance(value, str):
                raise ValueError(
                    f"Entry at index {index} expected_outcomes['{key}'] must be a string, "
                    f"got {type(value).__name__}: {source_name}"
                )
            normalized_outcomes[key] = value.strip()

        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(
                f"Entry at index {index} 'metadata' must be a dict, "
                f"got {type(metadata).__name__}: {source_name}"
            )

        normalized_unit_id = unit_id.strip()
        if normalized_unit_id in seen_unit_ids:
            raise ValueError(
                f"Duplicate 'unit_id' found: '{normalized_unit_id}' at index {index}: {source_name}"
            )
        seen_unit_ids.add(normalized_unit_id)

        parsed_entries.append(
            RubricEntry(
                unit_id=normalized_unit_id,
                expected_outcomes=normalized_outcomes,
                metadata=metadata,
            )
        )

    return parsed_entries
