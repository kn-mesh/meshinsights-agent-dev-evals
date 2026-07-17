"""Finalize the portable decision on the action-stage receipt."""

from __future__ import annotations

from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.pipeline_receipt import PipelineReceipt

from src.objects.action_object import PulseFailureAnalysisActionObject


class V1_3FinalizeActionHydrator(BaseHydrator[PulseFailureAnalysisActionObject, None]):
    """Write the final v1_3 outcome to durable receipt metadata."""

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
            for key, value in source.get_pipeline_result().items():
                receipt.act_receipt.set_metadata(key, value)
