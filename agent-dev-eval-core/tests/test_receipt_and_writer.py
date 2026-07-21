"""Tests for schema-driven output extraction and immutable result writing."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation import (
    OutputFieldSpec,
    build_results_dir_for_pipeline,
    extract_output_fields,
    validate_metadata_identity,
    write_json_exclusive,
)


def test_pipeline_results_are_nested_under_one_outer_directory() -> None:
    assert build_results_dir_for_pipeline(
        base_results_dir=Path("eval_results"),
        yaml_path=Path("pipeline_configs/v1_3.ppln"),
    ) == Path("eval_results/v1_3")


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


def test_result_writer_never_overwrites_existing_evidence(tmp_path) -> None:
    output_path = tmp_path / "eval.json"
    first = write_json_exclusive(output_path, {"run": 1})
    second = write_json_exclusive(output_path, {"run": 2})

    assert first == output_path
    assert second == tmp_path / "eval_1.json"
    assert json.loads(first.read_text(encoding="utf-8")) == {"run": 1}
    assert json.loads(second.read_text(encoding="utf-8")) == {"run": 2}
