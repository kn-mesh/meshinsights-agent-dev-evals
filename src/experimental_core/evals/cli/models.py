"""Typed dataclasses shared by the eval CLI scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.experimental_core.evals.ai_metadata import RuntimeType


@dataclass(frozen=True, slots=True)
class RuntimeProfileSpec:
    """One named execution profile resolved to runtime settings."""

    runtime: RuntimeType
    max_workers: int


@dataclass(frozen=True, slots=True)
class EvalWizardStepConfig:
    """Repo-provided option sets that drive the interactive eval wizard."""

    pipeline_paths: list[Path]
    rubric_paths: list[Path]
    unit_scope_options: tuple[str, ...]
    ai_model_options: tuple[str, ...]
    reasoning_effort_options: tuple[str, ...]
    execution_profile_options: tuple[str, ...]
    execution_profiles: dict[str, RuntimeProfileSpec]
    custom_unit_ids_label: str | None = None
    none_model_label: str = "none"
    default_runs_per_unit: int = 1
    custom_unit_ids_prompt: str = (
        "Enter comma-separated unit ids (example: 250003825, 250003969): "
    )

    def __post_init__(self) -> None:
        """Validate that option sets and the profiles dict are consistent."""
        if not self.pipeline_paths:
            raise ValueError("pipeline_paths must not be empty.")
        if not self.rubric_paths:
            raise ValueError("rubric_paths must not be empty.")
        if not self.unit_scope_options:
            raise ValueError("unit_scope_options must not be empty.")
        if not self.ai_model_options:
            raise ValueError("ai_model_options must not be empty.")
        if not self.execution_profile_options:
            raise ValueError("execution_profile_options must not be empty.")
        missing = [
            name
            for name in self.execution_profile_options
            if name not in self.execution_profiles
        ]
        if missing:
            raise ValueError(
                "execution_profile_options references unknown profiles: "
                f"{', '.join(missing)}"
            )


@dataclass(frozen=True, slots=True)
class EvalWizardSelections:
    """Structured result returned by one interactive wizard run."""

    yaml_path: Path
    rubric_path: Path
    unit_scope: str
    runs_per_unit: int
    ai_model: str | None
    ai_reasoning_effort: str | None
    runtime: RuntimeType
    max_workers: int
    unit_ids: list[str] | None = None
