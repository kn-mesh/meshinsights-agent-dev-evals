"""Reusable Workbench tests for the explorer and injected evidence projection."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from agent_eval_ui import create_app
from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_eval_run_identity,
    build_work_item_id,
    canonical_sha256,
    eval_attempt_to_dict,
)
from workbench.apps.eval_explorer import (
    ProjectExplorerBackend,
    build_app,
)
from workbench.apps.evidence import UnconfiguredProjectEvidenceAdapter
from workbench.benchmarks.models import (
    BenchmarkExample,
    PublishedReviewContext,
    SourceArtifact,
)
from workbench.evals.run_store import LocalRunStore
from use_case.evidence.spirax import SpiraxEvidenceAdapter, build_spirax_evidence_view


class _Backend:
    def list_runs(self) -> dict[str, Any]:
        return {"runs": [{"run_id": "run-1"}], "findings": []}

    def get_run(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id}

    def get_performance(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "availability": "available"}

    def list_attempts(self, run_id: str, **query: Any) -> dict[str, Any]:
        return {"run_id": run_id, "query": query, "rows": []}

    def get_attempt(self, run_id: str, execution_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "execution_id": execution_id}

    def get_evidence(self, run_id: str, example_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "example_id": example_id, "verified": True}


def test_generic_app_delegates_routes_and_maps_missing_results() -> None:
    client = TestClient(create_app(backend=_Backend()))

    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/runs").json()["runs"][0]["run_id"] == "run-1"
    assert (
        client.get("/api/runs/run-1/performance").json()["availability"] == "available"
    )
    attempts = client.get(
        "/api/runs/run-1/attempts?state=incorrect&slice=site:north&limit=25"
    ).json()
    assert attempts["query"]["state"] == "incorrect"
    assert attempts["query"]["slice_key"] == "site:north"
    assert attempts["query"]["limit"] == 25
    assert (
        client.get("/api/runs/run-1/examples/example-1/evidence").json()["verified"]
        is True
    )
    assert client.get("/api/comparisons").status_code == 404


def test_unconfigured_evidence_adapter_fails_with_a_precise_message() -> None:
    adapter = UnconfiguredProjectEvidenceAdapter()

    with pytest.raises(RuntimeError, match="Use case not configured"):
        adapter.build_view(
            benchmark_key="benchmark",
            benchmark_version_id="version",
            version_number=1,
            example=BenchmarkExample.model_construct(),
        )


def test_static_app_serves_the_spa_without_shadowing_unknown_api(
    tmp_path: Path,
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("explorer", encoding="utf-8")
    client = TestClient(create_app(backend=_Backend(), static_dir=tmp_path))

    assert client.get("/attempts/run-1").text == "explorer"
    assert client.get("/api/not-a-route").status_code == 404


def test_project_run_catalog_includes_verified_accuracy_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "workbench.apps.eval_explorer.EvalLifecycleService.list_evals",
        lambda self: [
            {
                "run_id": "run-a",
                "result_status": "materialized",
                "lifecycle_state": "working",
                "accuracy": {
                    "complete_evaluation": {
                        "accuracy": 0.75,
                        "correct_runs": 3,
                        "evaluated_runs": 4,
                    },
                    "by_field": {},
                },
            }
        ],
    )

    payload = ProjectExplorerBackend(tmp_path).list_runs()

    assert payload["runs"][0]["accuracy"]["complete_evaluation"] == {
        "accuracy": 0.75,
        "correct_runs": 3,
        "evaluated_runs": 4,
    }


def test_spirax_projection_preserves_reviewer_evidence_semantics() -> None:
    decision = datetime(2026, 3, 17, 12, tzinfo=timezone.utc)
    example = BenchmarkExample(
        example_id="7|2026-03-17T12:00:00Z",
        unit_id="7",
        decision_timestamp=decision,
        approved_label_payload={"classification": "failed"},
        label_schema_version_id="schema-v1",
        example_metadata={"tag": "ST-007"},
        source_snapshot_id="snapshot-7",
        raw_snapshot_content_sha256="a" * 64,
        raw_source_kind="mongo",
        raw_captured_at=decision,
        raw_window_start=datetime(2026, 2, 17, 12, tzinfo=timezone.utc),
        raw_window_end=decision,
        raw_known_gaps=("two-hour outage",),
        published_review_context=PublishedReviewContext(),
        raw_artifacts=(
            SourceArtifact(
                artifact_kind="telemetry",
                object_key="snapshot/telemetry.parquet",
                content_type="application/parquet",
                byte_size=1,
                content_sha256="b" * 64,
            ),
        ),
    )
    payload = {
        "temperature_history": [
            {
                "timestamp": datetime(2026, 3, 17, 11, tzinfo=timezone.utc),
                "steam_temperature": 130,
                "condensate_temperature": 105,
                "front_mic": 0,
            }
        ],
        "selected_alarm": {
            "alarm_id": "selected",
            "detected_at": decision,
            "source_detected_at": decision,
        },
        "sensor_alarms": [
            {
                "alarm_id": "previous",
                "alarm_type": "FDE",
                "detected_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "resolved_at": None,
            }
        ],
        "window_start": datetime(2026, 2, 17, 12, tzinfo=timezone.utc),
        "window_end": decision,
        "decision_timestamp": decision,
        "lookback_days": 365,
        "known_gaps": ["two-hour outage"],
        "sensor_id": 7,
        "steam_trap_type": "Float",
        "source_snapshot_id": "snapshot-7",
        "source_snapshot_content_sha256": "a" * 64,
        "source_kind": "mongo",
    }

    view = build_spirax_evidence_view(example=example, payload=payload)

    point = view["evidence"]["telemetry"][0]
    assert point["temperature_delta"] == 25.0
    assert point["front_mic"] == 0.0
    assert view["evidence"]["alarm_markers"]["unresolved_fde_detected_times"]
    assert view["evidence"]["known_gaps"] == ["two-hour outage"]
    assert view["metadata"]["source_snapshot_id"] == "snapshot-7"
    assert view["window"]["cutoff_policy"] == "decision_timestamp"


class _EvidenceAdapter:
    def __init__(self) -> None:
        self.identity: dict[str, Any] | None = None

    def build_view(self, **identity: Any) -> dict[str, Any]:
        self.identity = identity
        return {
            "verified": True,
            "benchmark_key": identity["benchmark_key"],
            "benchmark_version_id": identity["benchmark_version_id"],
            "version_number": identity["version_number"],
            "example_id": identity["example"].example_id,
        }


class _FrozenEvidenceStore:
    def read_verified(self, artifact: SourceArtifact) -> bytes:
        if artifact.artifact_kind == "telemetry":
            stream = io.BytesIO()
            pd.DataFrame(
                [
                    {
                        "timestamp": "2025-12-31T23:30:00Z",
                        "steam_temperature": 120.0,
                        "condensate_temperature": 100.0,
                        "front_mic": 0.2,
                    }
                ]
            ).to_parquet(stream, index=False)
            return stream.getvalue()
        if artifact.artifact_kind == "alarms":
            return (
                json.dumps(
                    {
                        "kind": "selected_alarm",
                        "alarm": {
                            "_id": "alarm-a",
                            "sensorIdDec": "unit-a",
                            "detectedAt": "2025-12-31T23:45:00Z",
                            "alarmData": {"type": "FDE"},
                        },
                    }
                )
                + "\n"
            ).encode()
        raise AssertionError(f"Unexpected artifact: {artifact.artifact_kind}")


def _working_run(project_root: Path) -> tuple[Path, str, str]:
    run_spec = {"scope": {"example_ids": ["example-a"]}, "runs_per_example": 1}
    digest = canonical_sha256(run_spec)
    run_id, occurrence_seed = build_eval_run_identity(
        run_spec_sha256=digest,
        created_at_utc="2026-01-01T00:00:00+00:00",
        nonce="eval-explorer-test",
    )
    run_dir = project_root / ".workbench/evals" / "working" / "benchmark" / "v1" / run_id
    run_dir.mkdir(parents=True)
    work_item_id = build_work_item_id(
        run_id=run_id, item_id="example-a", attempt_index=1
    )
    manifest = {
        "schema_version": 2,
        "performance_schema_version": 1,
        "run_id": run_id,
        "eval_run_id": run_id,
        "run_spec_sha256": digest,
        "occurrence_seed": occurrence_seed,
        "run_spec": run_spec,
        "work_items": [
            {
                "example_id": "example-a",
                "repetition_index": 1,
                "work_item_id": work_item_id,
            }
        ],
        "eval_contract": {
            "schema_version": 2,
            "run": {
                "schema_version": 2,
                "run_id": run_id,
                "eval_run_id": run_id,
                "run_spec_sha256": digest,
                "dimensions": {
                    "benchmark": {
                        "key": "benchmark",
                        "version_id": "benchmark-version-1",
                        "version": 1,
                    }
                },
                "runs_per_example": 1,
            },
            "examples": [
                {
                    "example_id": "example-a",
                    "unit_id": "unit-a",
                    "decision_timestamp": "2026-01-01T00:00:00Z",
                    "source_snapshot_id": "snapshot-a",
                    "raw_snapshot_content_sha256": "a" * 64,
                    "raw_source_kind": "source-snapshot",
                    "raw_captured_at": "2026-01-01T00:00:00Z",
                    "raw_window_start": "2025-01-01T00:00:00Z",
                    "raw_window_end": "2026-01-01T00:00:00Z",
                    "raw_known_gaps": [],
                    "raw_artifacts": [
                        {
                            "artifact_kind": "telemetry",
                            "object_key": "snapshot-a/telemetry.parquet",
                            "content_type": "application/parquet",
                            "byte_size": 1,
                            "content_sha256": "b" * 64,
                        },
                        {
                            "artifact_kind": "alarms",
                            "object_key": "snapshot-a/alarms.jsonl",
                            "content_type": "application/x-ndjson",
                            "byte_size": 1,
                            "content_sha256": "c" * 64,
                        },
                    ],
                    "label_schema_version_id": "schema-v1",
                    "benchmark_labels": {"classification": "Healthy"},
                    "slice_keys": [],
                    "metadata": {"sensor_id": "7"},
                    "published_review_context": {
                        "reviewer_coverage": [
                            {
                                "review_event_id": "review-event-a",
                                "label_revision": 2,
                                "reviewer_user_id": "reviewer-user-a",
                                "reviewer_display_name": "Alex Labeler",
                                "reviewer_project_role": "domain_reviewer",
                                "submitted_at": "2026-01-01T00:00:00Z",
                                "is_selected_label_revision": True,
                            }
                        ],
                        "verification": {
                            "source": "operator_feedback",
                            "note": "Confirmed by customer.",
                            "recorded_at": "2026-01-02T00:00:00Z",
                            "source_content_sha256": "d" * 64,
                            "context_schema_key": ("spirax_customer_verification"),
                            "context_schema_version": "1",
                            "source_fields": {"failure_cause": "Trap failed closed"},
                        },
                    },
                }
            ],
            "output_fields": [
                {
                    "key": "classification",
                    "graded": True,
                    "benchmark_label_path": ["classification"],
                }
            ],
            "slice_keys": [],
        },
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    store = LocalRunStore(run_dir, run_id=run_id)
    attempt = EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.SCORED,
        actual_values={"classification": "Healthy"},
        evaluations={
            "classification": FieldEvaluation(
                expected="Healthy",
                actual="Healthy",
                correct=True,
                grader_id="core.exact",
                grader_version=1,
            )
        },
        applicable_fields=("classification",),
        complete_evaluation_correct=True,
        artifacts={"agent_output": {"classification": "Healthy"}},
    )
    execution_id = f"{work_item_id}.1"
    store.commit_attempt(
        {
            "schema_version": 1,
            "run_id": run_id,
            "work_item_id": work_item_id,
            "example_id": "example-a",
            "repetition_index": 1,
            "execution_id": execution_id,
            "generation": 1,
            "invocation_id": "inv_test",
            "attempt": eval_attempt_to_dict(attempt),
        }
    )
    store.commit_performance(
        {
            "schema_version": 1,
            "run_id": run_id,
            "work_item_id": work_item_id,
            "execution_id": execution_id,
            "generation": 1,
            "invocation_id": "inv_test",
            "started_at_utc": "2026-01-01T00:00:00+00:00",
            "completed_at_utc": "2026-01-01T00:00:12+00:00",
            "executor_duration_seconds": 12.0,
            "metrics": {
                "duration_seconds": 12.0,
                "stage_durations_seconds": {
                    "retrieve": 1.0,
                    "process": 10.0,
                    "act": 1.0,
                },
                "retry_telemetry": {
                    "availability": "partial",
                    "observed_model_requests": 1,
                    "observed_tool_calls": 0,
                    "observed_output_validation_attempts": 1,
                    "observed_transport_attempts": None,
                },
                "backend": {
                    "model_calls": [
                        {
                            "sequence": 1,
                            "duration_seconds": 9.5,
                            "status": "completed",
                            "timeout_seconds": 30.0,
                            "duration_exceeded_configured_timeout": False,
                            "transport_attempts_observed": None,
                        }
                    ]
                },
            },
        }
    )
    store.write_invocation_event(
        invocation_id="inv_test",
        event="completed",
        payload={"duration_seconds": 12.0, "selected_work_items": 1},
    )
    store.materialize_result(
        completed_at_utc="2026-01-01T00:00:12+00:00",
        latest_invocation_id="inv_test",
    )
    store.materialize_performance()
    return run_dir, run_id, execution_id


def test_project_backend_exposes_optional_correlated_performance(
    tmp_path: Path,
) -> None:
    run_dir, run_id, execution_id = _working_run(tmp_path)
    evidence_adapter = _EvidenceAdapter()
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=evidence_adapter,  # type: ignore[arg-type]
    )
    client = TestClient(create_app(backend=backend))

    performance = backend.get_performance(run_id)
    assert performance["availability"] == "available"
    assert performance["summary"]["stage_duration_seconds"]["process"]["median"] == 10.0
    assert performance["model_calls"]["slowest"][0]["example_id"] == "example-a"
    assert performance["model_calls"]["slowest"][0]["unit_id"] == "unit-a"
    assert (
        client.get(f"/api/runs/{run_id}/performance").json()["availability"]
        == "available"
    )
    attempt = backend.get_attempt(run_id, execution_id)
    assert "review" not in attempt
    assert attempt["performance"]["availability"] == "available"
    assert attempt["performance"]["metrics"]["duration_seconds"] == 12.0
    assert attempt["benchmark_context"]["availability"] == "available"
    assert attempt["benchmark_context"]["reviewer_coverage"][0]["review_event_id"] == (
        "review-event-a"
    )
    evidence = backend.get_evidence(run_id, "example-a")
    assert evidence == {
        "verified": True,
        "benchmark_key": "benchmark",
        "benchmark_version_id": "benchmark-version-1",
        "version_number": 1,
        "example_id": "example-a",
    }
    assert evidence_adapter.identity is not None
    retained_example = evidence_adapter.identity["example"]
    assert isinstance(retained_example, BenchmarkExample)
    assert retained_example.source_snapshot_id == "snapshot-a"
    assert [item.artifact_kind for item in retained_example.raw_artifacts] == [
        "telemetry",
        "alarms",
    ]

    shutil.rmtree(run_dir / "performance")

    assert backend.get_performance(run_id)["availability"] == "unavailable"
    missing_response = client.get(f"/api/runs/{run_id}/performance")
    assert missing_response.status_code == 200
    assert missing_response.json()["availability"] == "unavailable"
    attempt_without_performance = backend.get_attempt(run_id, execution_id)
    assert attempt_without_performance["row"]["example_id"] == "example-a"
    assert attempt_without_performance["performance"]["availability"] == "unavailable"
    assert backend.get_evidence(run_id, "example-a")["verified"] is True


def test_project_backend_exposes_retained_published_review_context(
    tmp_path: Path,
) -> None:
    _, run_id, execution_id = _working_run(tmp_path)
    backend = ProjectExplorerBackend(tmp_path)

    context = backend.get_attempt(run_id, execution_id)["benchmark_context"]

    assert context["availability"] == "available"
    assert context["reviewer_coverage"][0]["review_event_id"] == "review-event-a"
    assert context["reviewer_coverage"][0]["is_selected_label_revision"] is True
    assert context["verification"]["source"] == "operator_feedback"
    assert context["verification"]["source_fields"] == {
        "failure_cause": "Trap failed closed"
    }


def test_project_backend_reads_legacy_labeler_notes_for_context_and_evidence(
    tmp_path: Path,
) -> None:
    run_dir, run_id, execution_id = _working_run(tmp_path)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["eval_contract"]["examples"][0]["published_review_context"] = {
        "labeler_notes": [
            {
                "review_event_id": "legacy-review-a",
                "reviewer_display_name": "Alex Labeler",
                "reviewer_project_role": "domain_reviewer",
                "submitted_at": "2026-07-20T09:30:00Z",
                "explanation": "Legacy reviewer explanation.",
                "selected_for_publication": True,
            }
        ],
        "verification": None,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence_adapter = _EvidenceAdapter()
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=evidence_adapter,  # type: ignore[arg-type]
    )

    context = backend.get_attempt(run_id, execution_id)["benchmark_context"]
    evidence = backend.get_evidence(run_id, "example-a")

    assert context["reviewer_coverage"] == [
        {
            "review_event_id": "legacy-review-a",
            "label_revision": 1,
            "reviewer_user_id": "",
            "reviewer_display_name": "Alex Labeler",
            "reviewer_project_role": "domain_reviewer",
            "submitted_at": "2026-07-20T09:30:00Z",
            "is_selected_label_revision": True,
        }
    ]
    assert evidence["verified"] is True
    assert evidence_adapter.identity is not None
    retained_context = evidence_adapter.identity["example"].published_review_context
    assert retained_context.reviewer_coverage[0].review_event_id == "legacy-review-a"
    assert retained_context.reviewer_coverage[0].is_selected_label_revision is True


def test_project_backend_rejects_evidence_outside_retained_run_scope(
    tmp_path: Path,
) -> None:
    _, run_id, _ = _working_run(tmp_path)
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
    )

    with pytest.raises(FileNotFoundError, match="retained example"):
        backend.get_evidence(run_id, "example-not-in-run")


def test_project_backend_decodes_evidence_from_retained_manifest(
    tmp_path: Path,
) -> None:
    _, run_id, _ = _working_run(tmp_path)
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=SpiraxEvidenceAdapter(evidence_store=_FrozenEvidenceStore()),
    )

    evidence = backend.get_evidence(run_id, "example-a")

    assert evidence["example"]["example_id"] == "example-a"
    assert evidence["metadata"]["source_snapshot_id"] == "snapshot-a"
    assert evidence["evidence"]["telemetry"][0]["temperature_delta"] == 20.0
    assert evidence["evidence"]["selected_alarm"]["alarm_id"] == "alarm-a"


def test_project_backend_reuses_injected_evidence_adapter_factory(
    tmp_path: Path,
) -> None:
    _, run_id, _ = _working_run(tmp_path)
    evidence_adapter = _EvidenceAdapter()
    creations: list[Path] = []

    def create(
        project_root: Path,
        *,
        account_url: str | None = None,
        container: str | None = None,
    ) -> _EvidenceAdapter:
        del account_url, container
        creations.append(project_root)
        return evidence_adapter

    backend = ProjectExplorerBackend(tmp_path, evidence_adapter_factory=create)

    backend.get_evidence(run_id, "example-a")
    backend.get_evidence(run_id, "example-a")

    assert creations == [tmp_path.resolve()]


def test_project_backend_rejects_manifest_without_required_frozen_evidence(
    tmp_path: Path,
) -> None:
    run_dir, run_id, _ = _working_run(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["eval_contract"]["examples"][0].pop("raw_artifacts")
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="raw_artifacts"):
        backend.get_evidence(run_id, "example-a")


def test_build_app_bootstraps_dotenv_before_serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "workbench.apps.eval_explorer.bootstrap_environment",
        lambda: calls.append("bootstrapped"),
    )

    app = build_app(project_root=tmp_path)

    assert app.title == "Agent Workbench Eval Explorer"
    assert calls == ["bootstrapped"]


def test_spirax_evidence_adapter_factory_uses_project_blob_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "workbench.project.json").write_text(
        json.dumps(
            {
                "benchmark_studio": {
                    "storage_account_url": "https://evidence.blob.core.windows.net",
                    "storage_container": "source-snapshots",
                }
            }
        ),
        encoding="utf-8",
    )
    observed: dict[str, Any] = {}

    class _Store:
        def __init__(self, **kwargs: Any) -> None:
            observed.update(kwargs)

    monkeypatch.setattr("use_case.evidence.AzureBlobEvidenceStore", _Store)

    from use_case.evidence import create_project_evidence_adapter

    adapter = create_project_evidence_adapter(tmp_path)

    assert isinstance(adapter, SpiraxEvidenceAdapter)
    assert observed == {
        "account_url": "https://evidence.blob.core.windows.net",
        "container": "source-snapshots",
    }


def test_project_backend_pages_and_resolves_attempts_beyond_ten_thousand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = ProjectExplorerBackend(tmp_path)
    rows = [
        {
            "example_id": f"example-{index}",
            "unit_id": f"unit-{index}",
            "execution_id": f"execution-{index}",
            "execution_status": "completed",
            "output_contract_status": "valid",
            "scoring_status": "scored",
            "complete_evaluation_correct": True,
            "evaluations": {},
            "slice_keys": [],
            "review_status": "unavailable",
        }
        for index in range(10_001)
    ]
    monkeypatch.setattr(
        "workbench.apps.eval_explorer.all_inspection_rows", lambda run_dir: rows
    )
    monkeypatch.setattr(backend, "_run_dir", lambda run_id: tmp_path / run_id)
    monkeypatch.setattr(
        backend.lifecycle,
        "inspect",
        lambda run_id: {"run_id": run_id, "lifecycle_state": "working"},
    )
    monkeypatch.setattr(
        backend,
        "_benchmark_context",
        lambda run_dir, *, example_id: {
            "availability": "unavailable",
            "reason": "Synthetic pagination fixture.",
        },
    )

    page = backend.list_attempts(
        "run-large",
        state="all",
        search="",
        field=None,
        slice_key=None,
        offset=10_000,
        limit=100,
    )
    attempt = backend.get_attempt("run-large", "execution-10000")

    assert page["total"] == 10_001
    assert [row["execution_id"] for row in page["rows"]] == ["execution-10000"]
    assert attempt["row"]["example_id"] == "example-10000"


@pytest.mark.parametrize(
    "model_calls",
    [None, "invalid", {"slowest": None}, {"slowest": "invalid"}],
)
def test_project_backend_treats_malformed_performance_as_unavailable(
    tmp_path: Path, model_calls: Any
) -> None:
    run_dir, run_id, execution_id = _working_run(tmp_path)
    summary_path = run_dir / "performance" / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["model_calls"] = model_calls
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
    )
    client = TestClient(create_app(backend=backend))

    response = client.get(f"/api/runs/{run_id}/performance")

    assert response.status_code == 200
    assert response.json()["availability"] == "unavailable"
    assert backend.get_attempt(run_id, execution_id)["row"]["example_id"] == "example-a"
    assert backend.get_run(run_id)["run_id"] == run_id


def test_performance_summary_and_links_use_only_latest_generation(
    tmp_path: Path,
) -> None:
    run_dir, run_id, old_execution_id = _working_run(tmp_path)
    store = LocalRunStore(run_dir, run_id=run_id)
    durable = dict(store.read_attempt_records()[0])
    performance = dict(store.read_performance_records()[0])
    work_item_id = str(durable["work_item_id"])
    new_execution_id = f"{work_item_id}.2"
    durable.pop("record_sha256")
    durable.update(
        {
            "execution_id": new_execution_id,
            "generation": 2,
            "invocation_id": "inv_rerun",
        }
    )
    store.commit_attempt(durable)
    performance.pop("record_sha256")
    performance.update(
        {
            "execution_id": new_execution_id,
            "generation": 2,
            "invocation_id": "inv_rerun",
        }
    )
    performance["metrics"] = {
        **performance["metrics"],
        "backend": {
            "model_calls": [
                {
                    "sequence": 1,
                    "duration_seconds": 2.0,
                    "status": "completed",
                }
            ]
        },
    }
    store.commit_performance(performance)
    store.write_invocation_event(
        invocation_id="inv_rerun",
        event="completed",
        payload={"duration_seconds": 3.0, "selected_work_items": 1},
    )
    store.performance_attempt_path(work_item_id=work_item_id, generation=1).write_text(
        "not-json", encoding="utf-8"
    )
    store.materialize_result(
        completed_at_utc="2026-01-01T00:01:00+00:00",
        latest_invocation_id="inv_rerun",
    )
    store.materialize_performance()
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
    )

    summary = backend.get_performance(run_id)

    assert summary["availability"] == "available"
    assert summary["recorded_executions"] == 1
    assert summary["model_calls"]["slowest"][0]["execution_id"] == new_execution_id
    assert (
        backend.get_attempt(run_id, new_execution_id)["performance"]["availability"]
        == "available"
    )
    with pytest.raises(FileNotFoundError):
        backend.get_attempt(run_id, old_execution_id)
