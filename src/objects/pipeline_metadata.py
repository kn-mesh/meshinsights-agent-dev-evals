"""Typed runtime metadata for Pulse alarm decisions."""

from __future__ import annotations

from datetime import datetime

from mi.core.pipeline import PipelineMetadata


class PulseFailureAnalysisMetadata(PipelineMetadata):
    """Identify the installation and as-of decision timestamp for one run."""

    sensor_id: int
    decision_timestamp: datetime
