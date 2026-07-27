"""Tests for explicit deterministic grader behavior."""

import pytest

from evaluation import build_default_grader_registry


def test_exact_is_json_type_sensitive() -> None:
    grader = build_default_grader_registry().resolve("core.exact", 1)

    assert grader.grade(expected=1, actual=1, config={}).correct
    assert not grader.grade(expected=1, actual=1.0, config={}).correct


def test_string_normalization_records_effective_values() -> None:
    grader = build_default_grader_registry().resolve("core.normalized_string", 1)
    grade = grader.grade(
        expected=" Closed   Failure ",
        actual="closed failure",
        config={"trim": True, "collapse_whitespace": True, "casefold": True},
    )

    assert grade.correct
    assert grade.normalized_expected == "closed failure"
    assert grade.normalized_actual == "closed failure"


def test_numeric_tolerance_requires_explicit_tolerance() -> None:
    grader = build_default_grader_registry().resolve("core.numeric_tolerance", 1)

    assert grader.grade(expected=10.0, actual=10.1, config={"absolute": 0.1}).correct
    with pytest.raises(ValueError, match="requires absolute"):
        grader.grade(expected=1.0, actual=1.0, config={})
