"""Structured outputs shared by Pulse failure-analysis agents."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClassificationResult(BaseModel):
    """Represent the top-level healthy-versus-failure decision."""

    model_config = ConfigDict(extra="forbid")

    value: Literal["Healthy", "Failure"] = Field(
        description="Health classification for the steam trap at the decision point."
    )
    confidence: Literal["High", "Low"] = Field(
        description="High only when the phase and baseline are clear and the main alternative is reasonably excluded."
    )
    explanation: str = Field(
        min_length=1,
        description="One or two sentences citing concrete historical and alarm-adjacent temperature evidence.",
    )


class RootCauseResult(BaseModel):
    """Represent the detailed failure root-cause decision."""

    model_config = ConfigDict(extra="forbid")

    value: Literal["Open Failure", "Closed Failure", "Unknown", "N/A"] = Field(
        description="Failure mechanism, Unknown when direction is ambiguous, or N/A for Healthy."
    )
    confidence: Literal["High", "Low"] = Field(
        description="High only when the direction of change is clear."
    )
    explanation: str = Field(
        min_length=1,
        description="One or two sentences identifying which side departed first, or N/A for Healthy.",
    )


class PulseFailureAnalysisResult(BaseModel):
    """Represent one validated steam-trap health decision."""

    model_config = ConfigDict(extra="forbid")

    classification: ClassificationResult
    root_cause: RootCauseResult

    @model_validator(mode="after")
    def validate_root_cause_consistency(self) -> "PulseFailureAnalysisResult":
        """Require N/A only for healthy decisions and a failure cause otherwise."""
        healthy = self.classification.value == "Healthy"
        root_cause_is_na = self.root_cause.value == "N/A"
        if healthy != root_cause_is_na:
            raise ValueError(
                "Healthy decisions require root cause N/A; failures require a failure cause."
            )
        if healthy and self.root_cause.explanation.strip() != "N/A":
            raise ValueError("Healthy decisions require root cause explanation N/A.")
        return self
