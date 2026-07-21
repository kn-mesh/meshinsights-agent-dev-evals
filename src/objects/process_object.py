"""Typed process object for the Pulse alarm failure-analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from mi.core.objects import ProcessDataObject


@dataclass
class PulseFailureAnalysisProcessObject(ProcessDataObject):
    """Store alarm context, telemetry, evidence artifacts, and the agent result."""

    _chart_key_prefix: str = field(default="temperature_chart_", init=False, repr=False)

    def set_alarm_context(
        self, value: dict[str, Any]
    ) -> "PulseFailureAnalysisProcessObject":
        """Store the selected alarm and decision-point context."""
        self.normalized_data["alarm_context"] = value
        return self

    def get_alarm_context(self) -> dict[str, Any]:
        """Return the selected alarm and decision-point context."""
        return cast(dict[str, Any], self.get_dataset("alarm_context"))

    def set_steam_trap_type(
        self, value: str | None
    ) -> "PulseFailureAnalysisProcessObject":
        """Store the steam-trap installation type."""
        self.normalized_data["steam_trap_type"] = value
        return self

    def get_steam_trap_type(self) -> str | None:
        """Return the steam-trap installation type."""
        return cast(str | None, self.get_dataset("steam_trap_type"))

    def set_temperature_history(
        self, value: list[dict[str, Any]]
    ) -> "PulseFailureAnalysisProcessObject":
        """Store normalized temperature telemetry."""
        self.normalized_data["temperature_history"] = value
        return self

    def get_temperature_history(self) -> list[dict[str, Any]]:
        """Return normalized temperature telemetry."""
        return cast(list[dict[str, Any]], self.get_dataset("temperature_history"))

    def set_temperature_chart(
        self, window_days: int, base64_png: str
    ) -> "PulseFailureAnalysisProcessObject":
        """Store one rendered temperature chart."""
        self.set_artifact(f"{self._chart_key_prefix}{window_days}d_base64", base64_png)
        return self

    def get_temperature_chart(self, window_days: int) -> str | None:
        """Return one rendered temperature chart when present."""
        value = self.get_artifact(f"{self._chart_key_prefix}{window_days}d_base64")
        return value if isinstance(value, str) else None

    def set_investigation_case_brief(
        self, value: dict[str, Any]
    ) -> "PulseFailureAnalysisProcessObject":
        """Store the stable first-pass case brief used by investigative agents."""
        self.set_artifact("investigation_case_brief", value)
        return self

    def get_investigation_case_brief(self) -> dict[str, Any] | None:
        """Return the first-pass case brief when present."""
        value = self.get_artifact("investigation_case_brief")
        return value if isinstance(value, dict) else None

    def add_investigation_evidence(
        self, value: dict[str, Any]
    ) -> "PulseFailureAnalysisProcessObject":
        """Record one focused chart request completed by the investigation agent."""
        existing = self.get_artifact("investigation_evidence")
        evidence = list(existing) if isinstance(existing, list) else []
        evidence.append(value)
        self.set_artifact("investigation_evidence", evidence)
        return self

    def get_investigation_evidence(self) -> list[dict[str, Any]]:
        """Return focused evidence records produced during investigation."""
        value = self.get_artifact("investigation_evidence")
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    def set_ai_result(
        self, value: dict[str, Any]
    ) -> "PulseFailureAnalysisProcessObject":
        """Store the stable, serializable agent decision artifact."""
        self.set_artifact("ai_classification", value)
        return self

    def get_ai_result(self) -> dict[str, Any] | None:
        """Return the stable agent decision artifact when present."""
        value = self.get_artifact("ai_classification")
        return value if isinstance(value, dict) else None

    def get_ai_usage(self) -> dict[str, Any] | None:
        """Aggregate processor-attached backend usage without guessing omissions."""
        processors = {
            key: value
            for key, value in sorted(self.artifacts.items())
            if key.endswith("_usage") and isinstance(value, dict)
        }
        if not processors:
            return None
        totals = {
            name: sum(
                int(usage.get(name, 0))
                for usage in processors.values()
                if isinstance(usage.get(name), int)
            )
            for name in (
                "requests",
                "input_tokens",
                "output_tokens",
                "cached_input_tokens",
                "reasoning_tokens",
                "tool_calls",
                "output_validation_attempts",
            )
        }
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
        return {
            "availability": "available",
            "source": "mi.ai.processor_artifacts",
            "processors": processors,
            **totals,
        }

    def get_ai_retry_telemetry(self) -> dict[str, Any]:
        """Expose observed request/tool/output activity and explicit gaps."""
        usage = self.get_ai_usage()
        if usage is None:
            return {
                "availability": "unavailable",
                "reason": "No mi.ai usage artifact was produced.",
            }
        return {
            "availability": "partial",
            "observed_model_requests": usage["requests"],
            "observed_tool_calls": usage["tool_calls"],
            "observed_output_validation_attempts": usage["output_validation_attempts"],
            "observed_transport_attempts": None,
            "reason": (
                "Model requests, tool calls, and direct-workflow output attempts "
                "are observed; the backend transport does not yet expose HTTP "
                "retry-attempt counts."
            ),
        }

    def get_execution_telemetry(self) -> dict[str, Any] | None:
        """Expose bounded observations for the durable process-stage receipt."""
        usage = self.get_ai_usage()
        retry_telemetry = self.get_ai_retry_telemetry()
        if usage is None and retry_telemetry.get("availability") == "unavailable":
            return None
        return {
            "usage": usage,
            "retry_telemetry": retry_telemetry,
        }
