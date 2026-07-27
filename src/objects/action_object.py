"""Typed action object for the Pulse alarm failure-analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from mi.core.objects import ActionDataObject


@dataclass
class PulseFailureAnalysisActionObject(ActionDataObject):
    """Store the portable final decision emitted by the process stage."""

    def set_pipeline_result(
        self, value: dict[str, Any]
    ) -> "PulseFailureAnalysisActionObject":
        """Store the final pipeline decision payload."""
        self.set_decision("pipeline_result", value)
        return self

    def get_pipeline_result(self) -> dict[str, Any]:
        """Return the final pipeline decision payload."""
        return cast(dict[str, Any], self.get_decision("pipeline_result"))
