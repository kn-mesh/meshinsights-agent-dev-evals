"""No-op action used when the durable output is recorded on the receipt."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mi.core.actions import BaseAction
from mi.core.versioning import VersionAssetRole, VersionContractDeclaration

from use_case.objects.action_object import PulseFailureAnalysisActionObject


class NoOpAction(BaseAction[PulseFailureAnalysisActionObject]):
    """Consume a finalized decision without an external side effect."""

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        _ = config
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.ACTION_POLICY,
                logical_name="no_external_side_effect",
                value={
                    "action": "NoOpAction",
                    "external_side_effect": False,
                    "durable_output": "act_receipt.metadata.agent_output",
                },
            ),
        )

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
