"""Reference-use-case tests for evaluation profiles and preflight."""

from pathlib import Path

import pytest
import yaml

from evaluation import build_default_grader_registry
from src.evals.evaluation_profile import (
    EvaluationProfile,
    evaluate_predicate,
    load_evaluation_profile,
)


def test_spirax_profile_is_versioned_and_hash_stable(tmp_path: Path) -> None:
    source = Path("evaluation_configs/spirax-failure-evaluation.eval.yaml")
    profile = load_evaluation_profile(source)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    reformatted = tmp_path / "profile.yaml"
    reformatted.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")

    assert profile.profile_id == "spirax-failure-evaluation"
    assert load_evaluation_profile(reformatted).content_sha256 == profile.content_sha256


def test_predicates_are_declarative_and_type_sensitive() -> None:
    context = {"benchmark": {"labels": {"count": 1, "active": True}}}

    assert evaluate_predicate(
        {"equals": {"path": ["benchmark", "labels", "count"], "value": 1}},
        context,
    )
    assert not evaluate_predicate(
        {"equals": {"path": ["benchmark", "labels", "count"], "value": 1.0}},
        context,
    )
    with pytest.raises(ValueError, match="Unsupported predicate"):
        evaluate_predicate({"python": "dangerous()"}, context)


def test_profile_rejects_unknown_fields_and_duplicate_keys() -> None:
    payload = yaml.safe_load(
        Path("evaluation_configs/spirax-failure-evaluation.eval.yaml").read_text(
            encoding="utf-8"
        )
    )
    payload["output_fields"].append(payload["output_fields"][0])

    with pytest.raises(ValueError, match="must be unique"):
        EvaluationProfile.model_validate(payload)


def test_default_grader_registry_resolves_profile_graders() -> None:
    profile = load_evaluation_profile(
        "evaluation_configs/spirax-failure-evaluation.eval.yaml"
    )
    registry = build_default_grader_registry()

    for field in profile.output_fields:
        if field.evaluation is not None:
            registry.resolve(field.evaluation.grader.id, field.evaluation.grader.version)
