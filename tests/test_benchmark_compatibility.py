"""Tests for use-case-neutral benchmark and pipeline compatibility preflight."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.benchmarks.compatibility import preflight_pipeline_benchmark_contract
from src.benchmarks.models import (
    BenchmarkExample,
    BenchmarkVersion,
    PublishedLabelSchema,
    PublishedReviewContext,
    SourceArtifact,
)
from src.evals.eval_orchestration import _select_examples
from src.evals.evaluation_profile import load_evaluation_profile
from src.pipelines.pipeline_run_from_yaml import _apply_runtime_overrides
from src.project_bootstrap.models import ProjectContract


def _published() -> tuple[BenchmarkVersion, BenchmarkExample]:
    schema = {
        "schema_key": "pump-decision-label",
        "version": "v1",
        "fields": [{"key": "classification", "values": ["normal", "fault"]}],
    }
    digest = hashlib.sha256(
        json.dumps(
            schema,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    example = BenchmarkExample(
        example_id="pump-A|2026-07-01T12:00:00Z",
        unit_id="pump-A",
        decision_timestamp=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        approved_label_payload={"classification": "fault"},
        label_schema_version_id="pump-schema-v1",
        example_metadata={"site": "north"},
        source_snapshot_id="snapshot-pump-A",
        raw_snapshot_content_sha256="a" * 64,
        raw_source_kind="historian",
        raw_captured_at=datetime(2026, 7, 1, 13, tzinfo=timezone.utc),
        raw_window_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
        raw_window_end=datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
        published_review_context=PublishedReviewContext(),
        raw_artifacts=(
            SourceArtifact(
                artifact_kind="vibration-spectrum",
                object_key="snapshot/vibration.arrow",
                content_type="application/vnd.apache.arrow.file",
                byte_size=42,
                content_sha256="b" * 64,
            ),
        ),
    )
    benchmark = BenchmarkVersion(
        project_key="acme-pumps",
        benchmark_key="pump-failures",
        benchmark_name="Pump Failures",
        benchmark_version_id="pump-version-id",
        version_number=3,
        published_at=datetime(2026, 7, 2, tzinfo=timezone.utc),
        source_state_sha256="c" * 64,
        published_contract_schema_version=2,
        eval_label_field_hints=("classification",),
        label_schemas=(
            PublishedLabelSchema(
                schema_version_id="pump-schema-v1",
                schema_key="pump-decision-label",
                version="v1",
                schema=schema,
                content_sha256=digest,
            ),
        ),
        examples=(example,),
    )
    return benchmark, example


def _project_contract(*, label_fields: list[str] | None = None) -> ProjectContract:
    return ProjectContract.model_validate(
        {
            "schema_version": 1,
            "created_at_utc": "2026-07-02T00:00:00Z",
            "template": {"source": "fixture", "revision": "abc123"},
            "project": {
                "key": "acme-pump-workbench",
                "name": "Acme Pump Workbench",
                "distribution_name": "acme-pump-agent",
                "use_case_key": "pump-failure",
                "description": "Pump failure fixture",
            },
            "benchmark_studio": {
                "project_key": "acme-pumps",
                "access_mode": "direct_read_only",
                "postgres_host": "benchmark.postgres.database.azure.com",
                "postgres_database": "benchmark_studio",
                "storage_account_url": "https://benchmark.blob.core.windows.net",
                "storage_container": "source-snapshots",
            },
            "benchmarks": {
                "default": {"key": "pump-failures", "version": "3"},
                "published": [
                    {
                        "key": "pump-failures",
                        "version": "3",
                        "published_contract_schema_version": 2,
                        "label_fields": label_fields or ["classification"],
                        "evidence_recipe_id": "pump-evidence@v3",
                        "source_snapshot_contract": "arrow-sha256-v1",
                    }
                ],
            },
            "model_catalog": {
                "default_model": "azure:test",
                "models": [{"id": "azure:test", "api": "openai_responses"}],
            },
            "paths": {},
        }
    )


def _pipeline_contract(**overrides: Any) -> dict[str, Any]:
    contract = {
        "published_contract_schema_version": 2,
        "evidence_recipe_id": "pump-evidence@v3",
        "source_snapshot_contract": "arrow-sha256-v1",
        "required_artifact_kinds": ["vibration-spectrum"],
    }
    contract.update(overrides)
    return {"benchmark_contract": contract}


def test_non_spirax_example_preflights_without_sensor_or_known_artifact_names() -> None:
    benchmark, example = _published()
    source = _pipeline_contract()

    resolved = preflight_pipeline_benchmark_contract(
        pipeline_config=source,
        benchmark=benchmark,
        examples=(example,),
        start_path=Path("pipeline_configs/example.ppln"),
        project_contract=_project_contract(),
    )
    runtime = _apply_runtime_overrides(
        source,
        benchmark=benchmark,
        example=example,
        ai_model=None,
        ai_reasoning_effort=None,
    )

    assert resolved.required_artifact_kinds == ("vibration-spectrum",)
    assert runtime["metadata"]["unit"] == "pump-A"
    assert runtime["metadata"]["example_metadata"] == {"site": "north"}
    assert "sensor_id" not in runtime["metadata"]
    assert "benchmark_contract" not in runtime

    selected = _select_examples(
        benchmark.examples,
        profile=load_evaluation_profile(
            Path("evaluation_configs/spirax-failure-evaluation.eval.yaml")
        ),
        example_ids=None,
        unit_ids=["pump-A"],
        label_filters={"classification": ["fault"]},
        slice_keys=None,
    )
    assert [item.example_id for item in selected] == [example.example_id]


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"published_contract_schema_version": 3},
            "schema versions do not match",
        ),
        ({"evidence_recipe_id": "wrong"}, "evidence_recipe_id"),
        ({"source_snapshot_contract": "wrong"}, "source_snapshot_contract"),
        ({"required_artifact_kinds": ["missing-kind"]}, "missing pipeline artifact"),
    ],
)
def test_preflight_rejects_pipeline_contract_mismatches(
    override: dict[str, Any], message: str
) -> None:
    benchmark, example = _published()

    with pytest.raises(ValueError, match=message):
        preflight_pipeline_benchmark_contract(
            pipeline_config=_pipeline_contract(**override),
            benchmark=benchmark,
            examples=(example,),
            start_path=Path("pipeline_configs/example.ppln"),
            project_contract=_project_contract(),
        )


def test_preflight_rejects_project_catalog_and_label_field_mismatches() -> None:
    benchmark, example = _published()
    wrong_version = benchmark.model_copy(update={"version_number": 4})
    with pytest.raises(ValueError, match="not configured"):
        preflight_pipeline_benchmark_contract(
            pipeline_config=_pipeline_contract(),
            benchmark=wrong_version,
            examples=(example,),
            start_path=Path("pipeline_configs/example.ppln"),
            project_contract=_project_contract(),
        )

    with pytest.raises(ValueError, match="missing configured evaluation fields"):
        preflight_pipeline_benchmark_contract(
            pipeline_config=_pipeline_contract(),
            benchmark=benchmark,
            examples=(example,),
            start_path=Path("pipeline_configs/example.ppln"),
            project_contract=_project_contract(label_fields=["root_cause"]),
        )


def test_benchmark_example_rejects_generic_snapshot_invariant_violations() -> None:
    _, example = _published()
    artifact = example.raw_artifacts[0]
    with pytest.raises(ValueError, match="no raw artifacts"):
        BenchmarkExample.model_validate({**example.model_dump(), "raw_artifacts": []})
    with pytest.raises(ValueError, match="duplicate raw artifact kinds"):
        BenchmarkExample.model_validate(
            {**example.model_dump(), "raw_artifacts": [artifact, artifact]}
        )
    with pytest.raises(ValueError, match="extends beyond"):
        BenchmarkExample.model_validate(
            {
                **example.model_dump(),
                "raw_window_end": datetime(2026, 7, 1, 12, 0, 1, tzinfo=timezone.utc),
            }
        )
