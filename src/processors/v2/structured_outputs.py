"""Intermediate structured outputs for the progressive v2 investigation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OperatingPhase = Literal[
    "On",
    "Off",
    "Startup",
    "Shutdown",
    "Modulation",
    "Unclear",
]

InvestigationHypothesis = Literal[
    "Healthy operation",
    "Open failure",
    "Closed failure",
    "Unknown failure",
    "Sensor or installation issue",
    "Unclear",
]

InvestigationSkill = Literal[
    "open-failure-investigation",
    "closed-vs-shutdown",
    "modulation-vs-failure",
    "history-and-sensor-integrity",
]


class V2BaselineProfile(BaseModel):
    """Describe the unit-specific operating baseline visible in overview evidence."""

    model_config = ConfigDict(extra="forbid")

    on_state: str = Field(
        description="Typical elevated temperature relationship and delta, with dates or ranges."
    )
    off_state: str = Field(
        description="Typical low-temperature or shutdown relationship, or state that it is unclear."
    )
    recurring_patterns: str = Field(
        description="Recurring modulation, startup, shutdown, reversal, or connectivity patterns."
    )
    confidence: Literal["High", "Low"]


class V2AlarmObservation(BaseModel):
    """Describe what changed in the broader period around the FDE alarm."""

    model_config = ConfigDict(extra="forbid")

    operating_phase: OperatingPhase
    stabilized_regime: str = Field(
        description="Most recent meaningful regime, including dates, temperatures, and delta."
    )
    departure_from_baseline: str = Field(
        description="Specific difference from comparable historical behavior, or none."
    )
    approximate_onset: str = Field(
        description="Approximate timestamp or interval where the current change began, or unclear."
    )


class V2InvestigationHypothesis(BaseModel):
    """Store one candidate explanation without making the final classification."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: InvestigationHypothesis
    evidence: str = Field(
        description="Concise evidence for this explanation from the supplied overview."
    )


class V2ReferenceInterval(BaseModel):
    """Identify one useful source interval for a focused follow-up chart."""

    model_config = ConfigDict(extra="forbid")

    label: Literal[
        "On baseline",
        "Off baseline",
        "Prior shutdown",
        "Similar historical pattern",
        "Current alarm regime",
        "Possible sensor regime change",
    ]
    start: str = Field(description="Approximate ISO-8601 interval start.")
    end: str = Field(description="Approximate ISO-8601 interval end.")
    relevance: str = Field(description="Why this interval would resolve uncertainty.")


class V2InvestigationCaseBrief(BaseModel):
    """Orient a specialist agent without prematurely deciding the final result."""

    model_config = ConfigDict(extra="forbid")

    baseline: V2BaselineProfile
    alarm_observation: V2AlarmObservation
    leading_hypothesis: V2InvestigationHypothesis
    alternative_hypothesis: V2InvestigationHypothesis
    reference_intervals: list[V2ReferenceInterval] = Field(
        min_length=1,
        max_length=4,
        description="The most useful current and historical ranges for follow-up charts.",
    )
    unresolved_question: str = Field(
        description="The single most important uncertainty that focused evidence should resolve."
    )
    recommended_skill: InvestigationSkill
