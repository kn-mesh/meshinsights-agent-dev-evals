"""Fluent builder for the standard eval argparse parser."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Self


class EvalArgParserBuilder:
    """Build the common eval CLI parser with per-group opt-in methods."""

    def __init__(self, description: str) -> None:
        """Initialize an empty argparse parser with the given description."""
        self._parser = argparse.ArgumentParser(description=description)

    def add_yaml_path(self, *, required: bool = False) -> Self:
        """Add the positional pipeline YAML path argument."""
        self._parser.add_argument(
            "yaml_path",
            nargs=None if required else "?",
            type=Path,
            help=(
                "Pipeline YAML config (e.g. pipeline_configs/v1_0.ppln). "
                "Omit when using --interactive."
            ),
        )
        return self

    def add_rubric_file(self, default: Path) -> Self:
        """Add the --rubric-file argument with the given default path."""
        self._parser.add_argument(
            "--rubric-file",
            type=Path,
            default=default,
            help="Rubric JSON file.",
        )
        return self

    def add_ai_model(self) -> Self:
        """Add the optional --ai-model override."""
        self._parser.add_argument(
            "--ai-model",
            type=str,
            help="Optional AI model override (provider:model).",
        )
        return self

    def add_ai_reasoning_effort(self, choices: Sequence[str]) -> Self:
        """Add the optional --ai-reasoning-effort argument with explicit choices."""
        self._parser.add_argument(
            "--ai-reasoning-effort",
            choices=list(choices),
            help=(
                "Optional reasoning effort override. "
                "Use 'default' to omit the override."
            ),
        )
        return self

    def add_units_and_classifications(self, classification_help: str) -> Self:
        """Add the --units and --classifications scope filters."""
        self._parser.add_argument(
            "--units",
            nargs="*",
            type=str,
            help="Subset of unit IDs to evaluate (default: all).",
        )
        self._parser.add_argument(
            "--classifications",
            nargs="*",
            type=str,
            help=classification_help,
        )
        return self

    def add_runs_per_unit(self, default: int = 1) -> Self:
        """Add the --runs-per-unit argument with the given default."""
        self._parser.add_argument(
            "--runs-per-unit",
            type=int,
            default=default,
            help=(
                "Number of identical pipeline runs per unit for reliability "
                f"(default: {default})."
            ),
        )
        return self

    def add_runtime(self, default: str = "threaded", default_workers: int = 4) -> Self:
        """Add the --runtime and --max-workers arguments."""
        self._parser.add_argument(
            "--runtime",
            choices=["serial", "threaded", "process"],
            default=default,
            help=f"Execution model: serial, threaded, or process (default: {default}).",
        )
        self._parser.add_argument(
            "--max-workers",
            type=int,
            default=default_workers,
            help=(
                "Max parallel workers for threaded/process runtime "
                f"(default: {default_workers})."
            ),
        )
        return self

    def add_execution_profile(
        self, profiles: Sequence[str], help_text: str
    ) -> Self:
        """Add the --execution-profile named-profile override argument."""
        self._parser.add_argument(
            "--execution-profile",
            choices=list(profiles),
            help=help_text,
        )
        return self

    def add_error_action(self) -> Self:
        """Add the --error-action stop-or-continue argument."""
        self._parser.add_argument(
            "--error-action",
            choices=["stop", "continue"],
            default="continue",
            help="Stop on first error or continue (default: continue).",
        )
        return self

    def add_interactive_flag(self) -> Self:
        """Add the --interactive wizard toggle."""
        self._parser.add_argument(
            "--interactive",
            action="store_true",
            help="Prompt step-by-step for eval settings.",
        )
        return self

    def build(self) -> argparse.ArgumentParser:
        """Return the configured argparse parser for further repo-specific additions."""
        return self._parser
