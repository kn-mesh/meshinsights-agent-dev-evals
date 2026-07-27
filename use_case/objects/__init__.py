"""Domain object exports for the Pulse failure-analysis pipeline."""

from use_case.objects.action_object import PulseFailureAnalysisActionObject
from use_case.objects.process_object import PulseFailureAnalysisProcessObject

__all__ = [
    "PulseFailureAnalysisActionObject",
    "PulseFailureAnalysisProcessObject",
]
