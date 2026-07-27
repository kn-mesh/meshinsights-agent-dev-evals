"""Tests for reusable ``mi init`` template choices."""

from cli.init_project import PIPELINE_TEMPLATES


def test_init_template_choices_have_no_reference_use_case() -> None:
    serialized = " ".join(
        f"{template.key} {template.label} {template.repo} {template.ref}"
        for template in PIPELINE_TEMPLATES
    ).lower()

    assert "spirax" not in serialized
    assert "reference_spirax" not in serialized
