"""Tests for Azure Container App benchmark retrieval."""

from __future__ import annotations

import base64
import json
import zlib
from datetime import datetime, timezone
from typing import Any

from src.benchmarks.azure_container_app_repository import (
    AzureContainerAppBenchmarkRepository,
    _decode_remote_payload,
)


def _artifact(kind: str, suffix: str, checksum: str) -> dict[str, Any]:
    return {
        "artifact_kind": kind,
        "object_key": f"snapshot/{suffix}",
        "content_type": "application/octet-stream",
        "byte_size": 1,
        "content_sha256": checksum * 64,
    }


def test_repository_lists_and_loads_hosted_phase_1_benchmark() -> None:
    calls: list[dict[str, Any]] = []

    def run_query(query: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        _ = query
        calls.append(parameters)
        base = {
            "project_key": "spirax-pulse",
            "benchmark_key": "phase-1-benchmark-3fb7f544",
            "benchmark_name": "Phase 1 Benchmark",
            "benchmark_version_id": "phase-1-version-id",
            "version_number": 1,
            "published_at": datetime(2026, 7, 17, tzinfo=timezone.utc).isoformat(),
            "source_state_sha256": "d" * 64,
        }
        if "benchmark_key" not in parameters:
            return [{**base, "example_count": 70}]
        return [
            {
                **base,
                "eval_label_fields": ["classification", "root_cause"],
                "example_id": "7|2026-03-17T12:00:00",
                "unit_id": "7",
                "decision_timestamp": "2026-03-17T12:00:00+00:00",
                "approved_label_payload": {
                    "classification": "Failure",
                    "root_cause": "Closed Failure",
                    "internal_note": "ignored",
                },
                "example_metadata": {"sensor_id": "7"},
                "source_snapshot_id": "snapshot-id",
                "raw_snapshot_content_sha256": "c" * 64,
                "raw_source_kind": "mongo",
                "raw_captured_at": "2026-03-18T00:00:00+00:00",
                "raw_window_start": "2025-03-17T12:00:00+00:00",
                "raw_window_end": "2026-03-17T12:00:00+00:00",
                "raw_known_gaps": [],
                "raw_artifacts": [
                    _artifact("telemetry", "telemetry.parquet", "a"),
                    _artifact("alarms", "alarms.jsonl", "b"),
                ],
            }
        ]

    repository = AzureContainerAppBenchmarkRepository(
        project_key="spirax-pulse",
        resource_group="rg-misprx-dv",
        container_app="label-benchmark",
        query_runner=run_query,
    )

    versions = repository.list_published_versions()
    benchmark = repository.load_published_version(
        benchmark_key="phase-1-benchmark-3fb7f544"
    )

    assert versions[0].benchmark_name == "Phase 1 Benchmark"
    assert versions[0].example_count == 70
    assert benchmark.examples[0].approved_labels == {
        "classification": "Failure",
        "root_cause": "Closed Failure",
    }
    assert calls == [
        {"project_key": "spirax-pulse"},
        {
            "project_key": "spirax-pulse",
            "benchmark_key": "phase-1-benchmark-3fb7f544",
            "version_number": None,
        },
    ]


def test_remote_payload_decoder_ignores_terminal_formatting() -> None:
    compressed = zlib.compress(json.dumps([{"example_count": 70}]).encode("utf-8"))
    encoded = base64.b64encode(compressed).decode("ascii")
    output = (
        "\x1b[93mConnected\x1b[0m\r\n"
        f"__MI_BENCHMARK_PAYLOAD_BEGIN__{encoded}\r\n"
        "__MI_BENCHMARK_PAYLOAD_END__\r\nDisconnected"
    )

    assert _decode_remote_payload(output) == [{"example_count": 70}]
