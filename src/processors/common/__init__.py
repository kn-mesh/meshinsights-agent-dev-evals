"""Shared processor contracts for Pulse failure analysis."""

from src.processors.common.structured_outputs import PulseFailureAnalysisResult
from src.processors.common.temperature_window_analysis import (
    TemperatureWindowAnalyzer,
    TemperatureWindowSummary,
)

__all__ = [
    "PulseFailureAnalysisResult",
    "TemperatureWindowAnalyzer",
    "TemperatureWindowSummary",
]
