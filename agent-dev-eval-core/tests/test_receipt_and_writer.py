"""Tests for schema-driven output extraction and immutable result writing."""

from __future__ import annotations

from evaluation import (
    OutputFieldSpec,
    extract_output_fields,
    validate_metadata_identity,
)


def test_nested_scalar_and_optional_confidence_are_observed() -> None:
    extraction = extract_output_fields(
        {"agent_output": {"classification": {"value": "Failure"}}},
        specs=(
            OutputFieldSpec(
                name="classification",
                value_path=("agent_output", "classification", "value"),
                value_type="string",
                confidence_path=("agent_output", "classification", "confidence"),
                confidence_values=("High", "Low"),
            ),
        ),
    )

    assert extraction.observations["classification"].valid
    assert extraction.actual_values == {"classification": "Failure"}
    assert extraction.confidence_values == {}


def test_missing_output_type_error_and_identity_mismatch_are_diagnostic() -> None:
    extraction = extract_output_fields(
        {"agent_output": {"score": "not-a-number"}},
        specs=(
            OutputFieldSpec(
                name="classification",
                value_path=("agent_output", "classification"),
                value_type="string",
            ),
            OutputFieldSpec(
                name="score",
                value_path=("agent_output", "score"),
                value_type="number",
            ),
        ),
    )
    identity_errors = validate_metadata_identity(
        {"example_id": "actual"},
        expected={"example_id": "expected"},
    )

    assert not extraction.observations["classification"].present
    assert "must be number" in extraction.observations["score"].errors[0]
    assert "expected 'expected', got 'actual'" in identity_errors[0]
