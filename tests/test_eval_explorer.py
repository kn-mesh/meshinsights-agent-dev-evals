"""Tests for the generic explorer API and Spirax evidence projection."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from fastapi.testclient import TestClient

from agent_eval_ui import create_app
from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_run_identity,
    build_work_item_id,
    eval_attempt_to_dict,
)
from src.apps.eval_explorer import ProjectExplorerBackend
from src.benchmarks.models import BenchmarkExample, SourceArtifact
from src.evals.run_store import LocalRunStore
from src.evidence.spirax import build_spirax_evidence_view


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

    def list_comparisons(self) -> dict[str, Any]:
        return {"comparisons": []}

    def get_comparison(self, comparison_id: str) -> dict[str, Any]:
        raise FileNotFoundError(comparison_id)


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
    assert client.get("/api/comparisons/missing").status_code == 404


def test_static_app_serves_the_spa_without_shadowing_unknown_api(
    tmp_path: Path,
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("explorer", encoding="utf-8")
    client = TestClient(create_app(backend=_Backend(), static_dir=tmp_path))

    assert client.get("/attempts/run-1").text == "explorer"
    assert client.get("/api/not-a-route").status_code == 404


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
    def build_view(self, **identity: Any) -> dict[str, Any]:
        return {"verified": True, **identity}


def _schema_v1_run(project_root: Path) -> tuple[Path, str, str]:
    run_spec = {"scope": {"example_ids": ["example-a"]}, "runs_per_example": 1}
    run_id, digest = build_run_identity(run_spec)
    run_dir = (
        project_root
        / "eval_results"
        / "pipeline"
        / "benchmark"
        / "v1"
        / "runs"
        / run_id
    )
    run_dir.mkdir(parents=True)
    work_item_id = build_work_item_id(
        run_id=run_id, item_id="example-a", attempt_index=1
    )
    manifest = {
        "schema_version": 1,
        "performance_schema_version": 1,
        "run_id": run_id,
        "run_spec_sha256": digest,
        "run_spec": run_spec,
        "work_items": [
            {
                "example_id": "example-a",
                "repetition_index": 1,
                "work_item_id": work_item_id,
            }
        ],
        "eval_contract": {
            "schema_version": 1,
            "run": {
                "schema_version": 1,
                "run_id": run_id,
                "run_spec_sha256": digest,
                "benchmark_key": "benchmark",
                "benchmark_version_number": 1,
                "runs_per_example": 1,
            },
            "examples": [
                {
                    "example_id": "example-a",
                    "unit_id": "unit-a",
                    "decision_timestamp": "2026-01-01T00:00:00Z",
                    "benchmark_labels": {"classification": "Healthy"},
                    "slice_keys": [],
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
    run_dir, run_id, execution_id = _schema_v1_run(tmp_path)
    backend = ProjectExplorerBackend(
        tmp_path,
        evidence_adapter=_EvidenceAdapter(),  # type: ignore[arg-type]
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
    assert attempt["performance"]["availability"] == "available"
    assert attempt["performance"]["metrics"]["duration_seconds"] == 12.0
    assert backend.get_evidence(run_id, "example-a")["verified"] is True

    shutil.rmtree(run_dir / "performance")

    assert backend.get_performance(run_id)["availability"] == "unavailable"
    missing_response = client.get(f"/api/runs/{run_id}/performance")
    assert missing_response.status_code == 200
    assert missing_response.json()["availability"] == "unavailable"
    attempt_without_performance = backend.get_attempt(run_id, execution_id)
    assert attempt_without_performance["row"]["example_id"] == "example-a"
    assert attempt_without_performance["performance"]["availability"] == "unavailable"
    assert backend.get_evidence(run_id, "example-a")["verified"] is True
