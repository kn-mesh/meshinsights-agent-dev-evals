"""Finalize the portable decision on the action-stage receipt."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt
from mi.core.versioning import VersionAssetRole, VersionContractDeclaration

from src.objects.action_object import PulseFailureAnalysisActionObject


class V1_3FinalizeActionHydrator(BaseHydrator[PulseFailureAnalysisActionObject, None]):
    """Write the final v1_3 outcome to durable receipt metadata."""

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        _ = config
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.OUTPUT_SCHEMA,
                logical_name="act_receipt_agent_output",
                value={
                    "receipt_stage": "act",
                    "output_path": "agent_output",
                    "identity_fields": [
                        "example_id",
                        "benchmark_key",
                        "benchmark_version_id",
                        "benchmark_version_number",
                        "source_snapshot_id",
                    ],
                },
            ),
        )

    def hydrate(
        self,
        source: PulseFailureAnalysisActionObject,
        receipt: PipelineReceipt,
        *,
        metadata: Any = None,
    ) -> None:
        """Record every portable decision field on the act receipt."""
        _ = metadata
        if receipt.act_receipt is not None:
            payload = source.get_pipeline_result()
            for key, value in payload["identity"].items():
                receipt.act_receipt.set_metadata(key, value)
            receipt.act_receipt.set_metadata("agent_output", payload["agent_output"])
            receipt.act_receipt.set_metadata("agent_context", payload["agent_context"])
            receipt.act_receipt.set_metadata(
                "execution_telemetry", payload.get("execution_telemetry", {})
            )
