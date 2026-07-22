"""Use-case-neutral query mechanics for human evaluation exploration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


AttemptState = Literal[
    "all",
    "correct",
    "incorrect",
    "invalid",
    "failed",
    "flaky",
    "unscored",
    "review-unavailable",
]


@dataclass(frozen=True, slots=True)
class AttemptQuery:
    """Bounded, composable filters over one run's compact attempt rows."""

    state: AttemptState = "all"
    search: str = ""
    field: str | None = None
    slice_key: str | None = None
    offset: int = 0
    limit: int = 100

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError("Attempt query offset must be non-negative.")
        if self.limit < 1 or self.limit > 1_000:
            raise ValueError("Attempt query limit must be between 1 and 1000.")


def query_attempt_rows(
    rows: list[dict[str, Any]], query: AttemptQuery
) -> dict[str, Any]:
    """Filter and page compact rows without use-case field assumptions."""
    selected = [row for row in rows if _matches(row, query)]
    page = selected[query.offset : query.offset + query.limit]
    return {
        "total": len(rows),
        "matched": len(selected),
        "offset": query.offset,
        "limit": query.limit,
        "rows": page,
        "facets": _facets(rows),
    }


def _matches(row: dict[str, Any], query: AttemptQuery) -> bool:
    if query.state == "correct" and row.get("complete_evaluation_correct") is not True:
        return False
    if (
        query.state == "incorrect"
        and row.get("complete_evaluation_correct") is not False
    ):
        return False
    if query.state == "invalid" and row.get("output_contract_status") != "invalid":
        return False
    if query.state == "failed" and row.get("execution_status") != "failed":
        return False
    if query.state == "flaky" and not row.get("flaky"):
        return False
    if query.state == "unscored" and row.get("scoring_status") == "scored":
        return False
    if (
        query.state == "review-unavailable"
        and row.get("review_status") != "unavailable"
    ):
        return False
    if query.field and query.field not in (row.get("fields") or {}):
        return False
    if query.slice_key and query.slice_key not in (row.get("slice_keys") or []):
        return False
    search = query.search.strip().casefold()
    if search and search not in _search_text(row):
        return False
    return True


def _search_text(row: dict[str, Any]) -> str:
    values = (
        row.get("example_id"),
        row.get("unit_id"),
        row.get("execution_id"),
        row.get("benchmark_labels"),
        row.get("actual_outputs"),
        row.get("failure_type"),
        row.get("error"),
    )
    return " ".join(str(value) for value in values if value is not None).casefold()


def _facets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = sorted(
        {str(field) for row in rows for field in (row.get("fields") or {}).keys()}
    )
    slices = sorted({str(key) for row in rows for key in (row.get("slice_keys") or [])})
    return {
        "states": {
            "all": len(rows),
            "correct": sum(
                row.get("complete_evaluation_correct") is True for row in rows
            ),
            "incorrect": sum(
                row.get("complete_evaluation_correct") is False for row in rows
            ),
            "invalid": sum(
                row.get("output_contract_status") == "invalid" for row in rows
            ),
            "failed": sum(row.get("execution_status") == "failed" for row in rows),
            "flaky": sum(bool(row.get("flaky")) for row in rows),
            "unscored": sum(row.get("scoring_status") != "scored" for row in rows),
            "review-unavailable": sum(
                row.get("review_status") == "unavailable" for row in rows
            ),
        },
        "fields": fields,
        "slices": slices,
    }
