"""Hydrate retrieved Pulse evidence into the process object."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from mi.core.hydrators import BaseHydrator
from mi.core.objects import RetrieverDataObject
from mi.core.pipeline_receipt import PipelineReceipt
from mi.core.versioning import VersionAssetRole, VersionContractDeclaration

from use_case.objects.process_object import PulseFailureAnalysisProcessObject


class V1_3RetrieveToProcessHydrator(
    BaseHydrator[RetrieverDataObject, PulseFailureAnalysisProcessObject]
):
    """Validate and hydrate the v1_3 portable evidence package."""

    @classmethod
    def version_contracts(
        cls, config: Mapping[str, Any]
    ) -> Sequence[VersionContractDeclaration]:
        _ = config
        return (
            VersionContractDeclaration(
                role=VersionAssetRole.EVIDENCE_RECIPE,
                logical_name="pulse_evidence_hydration",
                value={
                    "decision_timestamp_semantics": "benchmark_example_decision_time",
                    "required_snapshot_hash": True,
                    "output": "PulseFailureAnalysisProcessObject",
                },
            ),
        )

    def hydrate(
        self,
        source: RetrieverDataObject,
        receipt: PipelineReceipt,
        *,
        metadata: Any = None,
    ) -> PulseFailureAnalysisProcessObject:
        """Convert retrieval output into the typed process-stage payload."""
        _ = metadata
        payload = source.azure_blob["pulse_alarm_temperature_history"]
        self._validate_payload(payload)
        decision_timestamp = payload.get(
            "decision_timestamp", payload.get("requested_end_date")
        )
        if not isinstance(decision_timestamp, datetime):
            raise ValueError("Retriever decision_timestamp must be a datetime.")
        selected_alarm = payload["selected_alarm"]
        if not isinstance(selected_alarm, dict) or not isinstance(
            selected_alarm.get("detected_at"), datetime
        ):
            raise ValueError("Retriever selected_alarm.detected_at must be a datetime.")
        process_object = (
            PulseFailureAnalysisProcessObject()
            .set_alarm_context(
                {
                    "example_id": payload["example_id"],
                    "benchmark_key": payload["benchmark_key"],
                    "benchmark_version_id": payload["benchmark_version_id"],
                    "benchmark_version_number": payload["benchmark_version_number"],
                    "source_snapshot_id": payload["source_snapshot_id"],
                    "unit": payload.get("unit", str(payload["sensor_id"])),
                    "sensor_id": payload["sensor_id"],
                    "decision_timestamp": decision_timestamp,
                    "selected_alarm": payload["selected_alarm"],
                    "window_start": payload["window_start"],
                    "window_end": payload["window_end"],
                    "lookback_days": payload["lookback_days"],
                }
            )
            .set_steam_trap_type(payload["steam_trap_type"])
            .set_temperature_history(payload["temperature_history"])
        )

        if receipt.retrieve_receipt is not None:
            receipt.retrieve_receipt.set_metadata("example_id", payload["example_id"])
            receipt.retrieve_receipt.set_metadata(
                "benchmark_key", payload["benchmark_key"]
            )
            receipt.retrieve_receipt.set_metadata(
                "benchmark_version_id", payload["benchmark_version_id"]
            )
            receipt.retrieve_receipt.set_metadata(
                "benchmark_version_number", payload["benchmark_version_number"]
            )
            receipt.retrieve_receipt.set_metadata(
                "source_snapshot_id", payload["source_snapshot_id"]
            )
            receipt.retrieve_receipt.set_metadata(
                "source_snapshot_content_sha256",
                payload["source_snapshot_content_sha256"],
            )
            receipt.retrieve_receipt.set_metadata(
                "unit", process_object.get_alarm_context()["unit"]
            )
            receipt.retrieve_receipt.set_metadata("sensor_id", payload["sensor_id"])
            receipt.retrieve_receipt.set_metadata(
                "decision_timestamp", decision_timestamp.isoformat()
            )
            receipt.retrieve_receipt.set_metadata(
                "selected_alarm_detected_at",
                payload["selected_alarm"]["detected_at"].isoformat(),
            )
            receipt.retrieve_receipt.set_metadata(
                "temperature_point_count", len(payload["temperature_history"])
            )
        return process_object

    def _validate_payload(self, payload: Any) -> None:
        """Ensure the retriever emitted the minimum evidence contract."""
        if not isinstance(payload, dict):
            raise ValueError("Pulse retrieval payload must be a mapping.")
        required = {
            "example_id",
            "benchmark_key",
            "benchmark_version_id",
            "benchmark_version_number",
            "source_snapshot_id",
            "source_snapshot_content_sha256",
            "sensor_id",
            "steam_trap_type",
            "selected_alarm",
            "window_start",
            "window_end",
            "lookback_days",
            "temperature_history",
        }
        missing = required - payload.keys()
        if missing:
            raise ValueError(
                f"Retriever payload is missing required keys: {', '.join(sorted(missing))}"
            )
        if "decision_timestamp" not in payload and "requested_end_date" not in payload:
            raise ValueError("Retriever payload is missing decision_timestamp.")
