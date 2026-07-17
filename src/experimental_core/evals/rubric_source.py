"""Shared helpers for loading and selecting rubric entries."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from src.experimental_core.evals.rubric import (
    RubricEntry,
    RubricPayload,
    parse_rubric_entries,
)

RubricSource: TypeAlias = str | Path | RubricPayload
FilterValue: TypeAlias = object | Sequence[object]


@dataclass(frozen=True, slots=True)
class LoadedRubric:
    """Carry the resolved rubric source, payload, and validated entries."""

    source: RubricSource
    display_name: str
    source_path: Path | None
    payload: RubricPayload
    entries: tuple[RubricEntry, ...]

    def list_unit_ids(self) -> list[str]:
        """Return the loaded unit ids in rubric order."""

        return [entry.unit_id for entry in self.entries]


def load_rubric_payload(source: RubricSource) -> RubricPayload:
    """Load one rubric payload from a file path or inline mapping."""

    if isinstance(source, dict):
        payload = source
    else:
        rubric_path = Path(source).resolve()
        if not rubric_path.exists():
            raise FileNotFoundError(f"Rubric file not found: {rubric_path}")
        rubric_text = rubric_path.read_text(encoding="utf-8")
        if not rubric_text.strip():
            raise ValueError(f"Rubric file is empty: {rubric_path}")
        try:
            payload = json.loads(rubric_text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Rubric file contains invalid JSON: {rubric_path} "
                f"(line {exc.lineno}, column {exc.colno})"
            ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Rubric payload must be a JSON object.")
    return payload


def load_rubric_entries(source: RubricSource) -> list[RubricEntry]:
    """Load and validate rubric entries from one source."""

    payload = load_rubric_payload(source)
    return parse_rubric_entries(
        payload,
        source_name=_describe_rubric_source(source),
    )


def load_rubric(source: RubricSource) -> LoadedRubric:
    """Load one rubric source into a reusable shared container."""

    payload = load_rubric_payload(source)
    return LoadedRubric(
        source=source,
        display_name=resolve_rubric_display_name(source),
        source_path=_resolve_rubric_source_path(source),
        payload=payload,
        entries=tuple(
            parse_rubric_entries(
                payload,
                source_name=_describe_rubric_source(source),
            )
        ),
    )


def list_rubric_files(rubrics_dir: Path) -> list[Path]:
    """Return the rubric JSON files in one directory in sorted order."""

    if not rubrics_dir.exists():
        return []
    return sorted(path for path in rubrics_dir.glob("*.json") if path.is_file())


def resolve_rubric_display_name(source: RubricSource) -> str:
    """Return a stable display token for one rubric source."""

    if isinstance(source, dict):
        return "inline_rubric"

    stem = Path(source).stem.strip()
    if not stem:
        raise ValueError("Rubric file name must include a non-empty stem.")
    return stem


def filter_rubric_entries(
    entries: Sequence[RubricEntry],
    *,
    unit_ids: Sequence[str] | None = None,
    expected_outcomes: Mapping[str, FilterValue] | None = None,
    metadata_filters: Mapping[str, FilterValue] | None = None,
    require_known_unit_ids: bool = True,
) -> list[RubricEntry]:
    """Filter rubric entries by unit id, expected outcomes, and metadata."""

    filtered_entries = list(entries)

    if unit_ids is not None:
        requested_unit_ids = [unit_id.strip() for unit_id in unit_ids if unit_id.strip()]
        known_unit_ids = {entry.unit_id for entry in entries}
        if require_known_unit_ids:
            missing_unit_ids = sorted(
                unit_id for unit_id in requested_unit_ids if unit_id not in known_unit_ids
            )
            if missing_unit_ids:
                missing_text = ", ".join(missing_unit_ids)
                raise ValueError(
                    f"Requested unit ids were not found in the rubric: {missing_text}"
                )

        requested_unit_id_set = set(requested_unit_ids)
        filtered_entries = [
            entry for entry in filtered_entries if entry.unit_id in requested_unit_id_set
        ]

    if expected_outcomes:
        filtered_entries = [
            entry
            for entry in filtered_entries
            if _mapping_matches_filters(entry.expected_outcomes, expected_outcomes)
        ]

    if metadata_filters:
        filtered_entries = [
            entry
            for entry in filtered_entries
            if _mapping_matches_filters(entry.metadata, metadata_filters)
        ]

    return filtered_entries


def _describe_rubric_source(source: RubricSource) -> str:
    """Return a readable source description for validation errors."""

    if isinstance(source, dict):
        return "<inline_rubric>"
    return str(Path(source).resolve())


def _resolve_rubric_source_path(source: RubricSource) -> Path | None:
    """Return the resolved source path when the rubric is file-backed."""

    if isinstance(source, dict):
        return None
    return Path(source).resolve()


def _mapping_matches_filters(
    values: Mapping[str, Any],
    filters: Mapping[str, FilterValue],
) -> bool:
    """Return whether one mapping satisfies all requested field filters."""

    for field_name, expected_value in filters.items():
        actual_value = values.get(field_name)
        allowed_values = _normalize_filter_values(expected_value)
        if not any(
            _normalize_comparable_value(actual_value)
            == _normalize_comparable_value(candidate)
            for candidate in allowed_values
        ):
            return False
    return True


def _normalize_filter_values(value: FilterValue) -> tuple[object, ...]:
    """Normalize one filter value into a comparable tuple."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return (value,)


def _normalize_comparable_value(value: object) -> object:
    """Normalize one value before generic equality comparison."""

    if isinstance(value, str):
        return value.strip()
    return value
