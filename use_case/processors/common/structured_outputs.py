"""Shared structured output models for Pulse failure-analysis AI processors."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ClassificationResult(BaseModel):
    """Store the top-level healthy-versus-failure decision."""

    value: Literal["Healthy", "Failure"] = Field(
        description='Issue classification for the steam trap: output "Healthy" or "Failure".'
    )
    confidence: Literal["High", "Low"] = Field(
        description='Confidence for the issue classification: output "High" when the operating phase and baseline are clear and the main alternative explanation can be ruled out; otherwise output "Low".'
    )
    explanation: str = Field(
        description="1-2 sentences citing the specific temperature evidence and the operating phase for the issue classification. Name the historical baseline used for comparison, and prefer dates, temperatures, and patterns rather than referring to specific charts."
    )


class RootCauseResult(BaseModel):
    """Store the detailed failure root-cause decision."""

    value: Literal["Open Failure", "Closed Failure", "Unknown", "N/A"] = Field(
        description='Root cause classification: output "Open Failure", "Closed Failure", "Unknown", or "N/A". Output "N/A" when the issue classification is "Healthy".'
    )
    confidence: Literal["High", "Low"] = Field(
        description='Confidence for the root cause classification: output "High" when the direction of change is clear, otherwise output "Low". If open vs closed cannot be justified, prefer root cause "Unknown" rather than guessing.'
    )
    explanation: str = Field(
        description='1-2 sentences citing which side changed and the trajectory evidence for the root cause classification. If the value is "Unknown", explain why open vs closed cannot be determined. If the issue classification is "Healthy", provide only "N/A". Prefer dates, temperatures, and patterns rather than referring to specific charts.'
    )


class PulseFailureAnalysisResult(BaseModel):
    """Store the shared structured AI result for Pulse failure analysis."""

    classification: ClassificationResult = Field(
        description="Top-level issue classification output containing the value, confidence, and explanation for whether the steam trap is Healthy or Failure."
    )
    root_cause: RootCauseResult = Field(
        description="Root cause classification output containing the value, confidence, and explanation for Open Failure, Closed Failure, Unknown, or N/A."
    )

    @model_validator(mode="after")
    def validate_classification_root_cause_consistency(self) -> Self:
        """Reject root causes that contradict the top-level classification."""
        is_healthy = self.classification.value == "Healthy"
        is_not_applicable = self.root_cause.value == "N/A"
        if is_healthy != is_not_applicable:
            raise ValueError(
                'Healthy classifications require root cause "N/A", and Failure '
                "classifications require a failure root cause."
            )
        return self
