"""Tests for the generic explorer API and Spirax evidence projection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_eval_ui import create_app
from src.benchmarks.models import BenchmarkExample, SourceArtifact
from src.evidence.spirax import build_spirax_evidence_view


class _Backend:
    def list_runs(self) -> dict[str, Any]:
        return {"runs": [{"run_id": "run-1"}], "findings": []}

    def get_run(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id}

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
