"""
Utilities for reading and querying eval results JSON payloads.

This module intentionally avoids domain-specific assumptions about what a "unit"
means, but it enforces the core convention for where per-unit accuracy lives.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


JsonKeyPath = tuple[str, ...]
ACCURACY_BY_UNIT_ID_PATH: JsonKeyPath = ("summary", "accuracy_by_unit_id")


@dataclass(frozen=True, slots=True)
class EvalResultsDocument:
    """Lightweight accessor for an eval results JSON payload."""

    payload: dict[str, Any]
    source_path: Path | None = None

    @classmethod
    def from_json_file(cls, path: Path) -> "EvalResultsDocument":
        """Load an eval results JSON document from disk."""

        if not path.exists():
            raise FileNotFoundError(f"Eval results file not found: {path}")
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Eval results payload must be a JSON object")
        return cls(payload=parsed, source_path=path)

    def read_dict(self, path: JsonKeyPath) -> dict[str, Any] | None:
        """Return a nested dict at the provided key path."""

        current: Any = self.payload
        for key in path:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current if isinstance(current, dict) else None

    def read_list(self, path: JsonKeyPath) -> list[Any]:
        """Return a nested list at the provided key path."""

        current: Any = self.payload
        for key in path:
            if not isinstance(current, dict):
                return []
            current = current.get(key)
        return current if isinstance(current, list) else []

    def read_accuracy_by_unit_id(self) -> dict[str, float | None]:
        """Read the per-unit accuracy map from `summary.accuracy_by_unit_id`."""

        mapping = self.read_dict(ACCURACY_BY_UNIT_ID_PATH)
        if mapping is None:
            return {}

        parsed: dict[str, float | None] = {}
        for key, value in mapping.items():
            unit_id = str(key)
            parsed[unit_id] = value if isinstance(value, (int, float)) else None
        return parsed

    def read_run_config(self, *, key: str = "run_config") -> dict[str, Any] | None:
        """Return the `run_config` dictionary from the payload when present."""

        run_config = self.payload.get(key)
        return run_config if isinstance(run_config, dict) else None

    def read_summary(self, *, key: str = "summary") -> dict[str, Any] | None:
        """Return the `summary` dictionary from the payload when present."""

        summary = self.payload.get(key)
        return summary if isinstance(summary, dict) else None

    def list_results(self, *, results_key: str = "results") -> list[dict[str, Any]]:
        """Return the list of per-run result objects from the payload."""

        raw = self.payload.get(results_key)
        if not isinstance(raw, list):
            return []
        return [entry for entry in raw if isinstance(entry, dict)]

    def filter_results_for_unit(
        self,
        *,
        unit_id: str,
        unit_id_key: str = "unit_id",
        results_key: str = "results",
    ) -> list[dict[str, Any]]:
        """Return result objects whose unit id matches the provided unit id."""

        return [entry for entry in self.list_results(results_key=results_key) if entry.get(unit_id_key) == unit_id]

    @staticmethod
    def safe_unit_ids(values: Iterable[Any]) -> list[str]:
        """Normalize an iterable into a list of non-empty unit id strings."""

        unit_ids: list[str] = []
        for value in values:
            if not isinstance(value, str):
                continue
            token = value.strip()
            if token:
                unit_ids.append(token)
        return unit_ids
