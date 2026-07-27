"""Reference-use-case checks that must be cleared during project bootstrap."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_reference_ai_processor_needs_no_static_f_string_suppression() -> None:
    processor = (
        ROOT
        / "use_case/processors/v1_3/v1_3_alarm_classification_ai_workflow_processor.py"
    ).read_text(encoding="utf-8")

    assert "# ruff: noqa: F541" not in processor
