from __future__ import annotations

import logging
from pathlib import Path

import typer

from mi.core import PipelineBuilder
from mi.core.registry import load_pipeline_settings
from mi.core.registry.utils import ensure_sys_path, find_project_root, find_project_venv


def run_pipeline_command(yaml: Path) -> int:
    yaml_path = Path(yaml).resolve()
    if not yaml_path.exists():
        typer.secho(
            f"Pipeline YAML not found: {yaml_path}", fg=typer.colors.RED, err=True
        )
        return 1

    try:
        try:
            _, config_file = load_pipeline_settings(None, start=yaml_path.parent)
        except FileNotFoundError as exc:
            typer.secho(
                f"Failed to locate pipeline configuration: {exc}",
                fg=typer.colors.RED,
                err=True,
            )
            return 1

        project_root = find_project_root(config_file.parent)
        venv_path = find_project_venv(project_root)
        if venv_path is not None:
            logging.info("Detected project virtual environment: %s", venv_path)
        else:
            logging.debug("No project virtual environment detected in %s", project_root)

        ensure_sys_path(project_root)

        typer.secho(f"Loading pipeline from: {yaml_path}", fg=typer.colors.BLUE)
        builder = PipelineBuilder.from_yaml(yaml_path)

        typer.secho("Building pipeline...", fg=typer.colors.BLUE)
        pipeline = builder.build()

        typer.secho("Running pipeline...", fg=typer.colors.BLUE)
        receipt = pipeline.run()

        if receipt.success:
            typer.secho(
                "Pipeline execution completed successfully", fg=typer.colors.BLUE
            )
            typer.echo(
                f"Total execution time: {receipt.total_execution_time_seconds:.2f} seconds"
            )
            return 0
        else:
            typer.secho("Pipeline execution failed", fg=typer.colors.RED, err=True)
            return 1
    except Exception as exc:
        logging.exception("Failed to run pipeline: %s", exc)
        return 1


def register_run_command(app: typer.Typer) -> None:
    @app.command("run")
    def run_pipeline(
        yaml: Path = typer.Argument(..., help="Pipeline YAML file to run."),
    ) -> None:
        """Run a pipeline from a YAML configuration file."""
        code = run_pipeline_command(yaml)
        raise typer.Exit(code)
