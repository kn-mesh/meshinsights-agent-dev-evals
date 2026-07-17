"""Interactive step-by-step eval configuration wizard."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from src.experimental_core.evals.cli.models import (
    EvalWizardSelections,
    EvalWizardStepConfig,
    RuntimeProfileSpec,
)
from src.experimental_core.evals.cli.prompts import (
    prompt_optional_csv,
    prompt_positive_int,
    prompt_select_option,
)
from src.experimental_core.evals.cli.validators import (
    normalize_ai_reasoning_effort,
    resolve_execution_profile,
)


class InteractiveEvalWizard:
    """Drive the standard eval CLI wizard: pipeline, rubric, scope, runs, model, runtime."""

    def __init__(self, config: EvalWizardStepConfig) -> None:
        """Store repo-provided option sets for the wizard run."""
        self._config = config

    def run(self) -> EvalWizardSelections:
        """Walk all steps interactively and return the collected selections."""
        yaml_path = self._choose_pipeline_config()
        rubric_path = self._choose_rubric_file()
        unit_scope, unit_ids = self._choose_unit_scope()
        runs_per_unit = self._choose_runs_per_unit()
        ai_model = self._choose_ai_model()
        ai_reasoning_effort = self._choose_ai_reasoning_effort(ai_model)
        profile = self._choose_execution_profile()

        return EvalWizardSelections(
            yaml_path=yaml_path,
            rubric_path=rubric_path,
            unit_scope=unit_scope,
            unit_ids=unit_ids,
            runs_per_unit=runs_per_unit,
            ai_model=ai_model,
            ai_reasoning_effort=normalize_ai_reasoning_effort(ai_reasoning_effort),
            runtime=profile.runtime,
            max_workers=profile.max_workers,
        )

    def _choose_pipeline_config(self) -> Path:
        """Prompt the user to pick one pipeline config by filename."""
        label_to_path = self._build_label_to_path_map(self._config.pipeline_paths)
        selected = prompt_select_option(
            "1) Choose pipeline config:",
            list(label_to_path),
        )
        return label_to_path[selected]

    def _choose_rubric_file(self) -> Path:
        """Prompt the user to pick one rubric file by filename."""
        label_to_path = self._build_label_to_path_map(self._config.rubric_paths)
        selected = prompt_select_option(
            "2) Choose rubric file:",
            list(label_to_path),
        )
        return label_to_path[selected]

    def _choose_unit_scope(self) -> tuple[str, list[str] | None]:
        """Prompt for the unit scope, branching into a CSV prompt when configured."""
        scope = prompt_select_option(
            "3) Choose units scope:",
            list(self._config.unit_scope_options),
        )
        custom_label = self._config.custom_unit_ids_label
        if custom_label is not None and scope == custom_label:
            unit_ids = prompt_optional_csv(self._config.custom_unit_ids_prompt)
            if not unit_ids:
                raise ValueError(
                    f"{custom_label} selected, but no unit ids were provided."
                )
            return scope, unit_ids
        return scope, None

    def _choose_runs_per_unit(self) -> int:
        """Prompt for the number of repeated runs per unit."""
        return prompt_positive_int(
            "4) Number of runs per unit",
            default=self._config.default_runs_per_unit,
        )

    def _choose_ai_model(self) -> str | None:
        """Prompt for the AI model, returning None when the 'none' label is selected."""
        selected = prompt_select_option(
            "5) Choose model provider/model combination:",
            list(self._config.ai_model_options),
        )
        if selected == self._config.none_model_label:
            return None
        return selected

    def _choose_ai_reasoning_effort(self, ai_model: str | None) -> str | None:
        """Prompt for reasoning effort only when a model is selected."""
        if ai_model is None or not self._config.reasoning_effort_options:
            return None
        return prompt_select_option(
            "6) Choose reasoning effort:",
            list(self._config.reasoning_effort_options),
        )

    def _choose_execution_profile(self) -> RuntimeProfileSpec:
        """Prompt for and resolve the execution profile."""
        selected = prompt_select_option(
            "7) Choose execution profile:",
            list(self._config.execution_profile_options),
        )
        return resolve_execution_profile(selected, self._config.execution_profiles)

    def _build_label_to_path_map(self, paths: list[Path]) -> dict[str, Path]:
        """Build stable prompt labels that remain unique even for basename collisions."""

        labels = self._build_unique_path_labels(paths)
        return dict(zip(labels, paths, strict=True))

    def _build_unique_path_labels(self, paths: list[Path]) -> list[str]:
        """Return the shortest unique display label for each path."""

        labels = [path.name for path in paths]
        duplicate_names = {
            name for name, count in Counter(labels).items() if count > 1
        }
        if not duplicate_names:
            return labels

        resolved_labels: list[str] = []
        for path in paths:
            if path.name not in duplicate_names:
                resolved_labels.append(path.name)
                continue
            resolved_labels.append(self._build_unique_path_suffix(path, paths))
        return resolved_labels

    def _build_unique_path_suffix(self, target: Path, paths: list[Path]) -> str:
        """Return the shortest suffix string that uniquely identifies one path."""

        target_parts = target.parts
        for width in range(1, len(target_parts) + 1):
            candidate = "/".join(target_parts[-width:])
            if sum(1 for path in paths if "/".join(path.parts[-width:]) == candidate) == 1:
                return candidate
        return str(target)
