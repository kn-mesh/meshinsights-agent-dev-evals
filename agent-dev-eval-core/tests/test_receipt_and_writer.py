"""Tests for structured output contracts and immutable result writing."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation import (
    StructuredOutputSpec,
    build_results_dir_for_pipeline,
    extract_structured_outputs,
    validate_metadata_identity,
    write_json_exclusive,
)


def test_pipeline_results_are_nested_under_one_outer_directory() -> None:
    assert build_results_dir_for_pipeline(
        base_results_dir=Path("eval_results"),
        yaml_path=Path("pipeline_configs/v1_3.ppln"),
    ) == Path("eval_results/v1_3")


def test_confidence_is_optional_when_configured() -> None:
    extraction = extract_structured_outputs(
        {"classification": {"value": "Failure"}},
        specs=(
            StructuredOutputSpec(
                name="classification",
                metadata_key="classification",
                confidence_path=("confidence",),
            ),
        ),
    )

    assert extraction.valid
    assert extraction.actual_values == {"classification": "Failure"}
    assert extraction.confidence_values == {}


def test_missing_required_output_and_identity_mismatch_are_diagnostic() -> None:
    extraction = extract_structured_outputs(
        {},
        specs=(
            StructuredOutputSpec(name="classification", metadata_key="classification"),
        ),
    )
    identity_errors = validate_metadata_identity(
        {"example_id": "actual"},
        expected={"example_id": "expected"},
    )

    assert extraction.errors == (
        "Missing or invalid required output 'classification'.",
    )
    assert "expected 'expected', got 'actual'" in identity_errors[0]


def test_result_writer_never_overwrites_existing_evidence(tmp_path) -> None:
    output_path = tmp_path / "eval.json"
    first = write_json_exclusive(output_path, {"run": 1})
    second = write_json_exclusive(output_path, {"run": 2})

    assert first == output_path
    assert second == tmp_path / "eval_1.json"
    assert json.loads(first.read_text(encoding="utf-8")) == {"run": 1}
    assert json.loads(second.read_text(encoding="utf-8")) == {"run": 2}
