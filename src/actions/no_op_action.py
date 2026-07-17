"""No-op action used when the durable output is recorded on the receipt."""

from __future__ import annotations

from typing import Any

from mi.core.actions import BaseAction

from src.objects.action_object import PulseFailureAnalysisActionObject


class NoOpAction(BaseAction[PulseFailureAnalysisActionObject]):
    """Consume a finalized decision without an external side effect."""

    def __init__(self) -> None:
        """Initialize the no-op action with a stable name."""
        super().__init__(name="no_op_action")

    def act(
        self,
        data_object: PulseFailureAnalysisActionObject,
        *,
        metadata: Any = None,
    ) -> None:
        """Leave the finalized action payload unchanged."""
        _ = data_object
        _ = metadata
