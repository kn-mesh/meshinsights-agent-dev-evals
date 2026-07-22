"""Tests for use-case-neutral eval explorer queries."""

from evaluation.explorer import AttemptQuery, query_attempt_rows


def _row(
    execution_id: str,
    *,
    correct: bool | None,
    scoring: str = "scored",
    review: str = "captured",
) -> dict[str, object]:
    return {
        "execution_id": execution_id,
        "example_id": f"example-{execution_id}",
        "unit_id": "trap-7",
        "complete_evaluation_correct": correct,
        "execution_status": "completed",
        "output_contract_status": "valid",
        "scoring_status": scoring,
        "review_status": review,
        "flaky": execution_id == "flaky",
        "fields": {"classification": {"correct": correct}},
        "slice_keys": ["site:north"],
        "benchmark_labels": {"classification": "failed"},
        "actual_outputs": {"classification": "failed" if correct else "normal"},
    }


def test_query_filters_searches_pages_and_builds_facets() -> None:
    rows = [
        _row("correct", correct=True),
        _row("incorrect", correct=False),
        _row("flaky", correct=None, scoring="unscored", review="unavailable"),
    ]

    result = query_attempt_rows(
        rows,
        AttemptQuery(
            state="incorrect",
            search="trap-7",
            field="classification",
            slice_key="site:north",
            limit=1,
        ),
    )

    assert result["matched"] == 1
    assert result["rows"][0]["execution_id"] == "incorrect"
    assert result["facets"]["states"] == {
        "all": 3,
        "correct": 1,
        "incorrect": 1,
        "invalid": 0,
        "failed": 0,
        "flaky": 1,
        "unscored": 1,
        "review-unavailable": 1,
    }
    assert result["facets"]["fields"] == ["classification"]
    assert result["facets"]["slices"] == ["site:north"]


def test_query_rejects_unbounded_page_size() -> None:
    try:
        AttemptQuery(limit=1_001)
    except ValueError as error:
        assert "between 1 and 1000" in str(error)
    else:
        raise AssertionError("Expected an invalid explorer page size to fail.")
