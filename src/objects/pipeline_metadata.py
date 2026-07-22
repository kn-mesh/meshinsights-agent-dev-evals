"""Typed runtime metadata for one frozen benchmark example."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mi.core.pipeline import PipelineMetadata


class BenchmarkExamplePipelineMetadata(PipelineMetadata):
    """Carry the exact published benchmark example and raw artifact manifest."""

    example_id: str
    decision_timestamp: datetime
    benchmark_key: str
    benchmark_version_id: str
    benchmark_version_number: int
    source_snapshot_id: str
    source_snapshot_content_sha256: str
    source_kind: str
    raw_captured_at: datetime
    raw_window_start: datetime | None = None
    raw_window_end: datetime | None = None
    raw_known_gaps: list[Any]
    raw_artifacts: list[dict[str, Any]]
    example_metadata: dict[str, Any]
    review_capture: bool = False
