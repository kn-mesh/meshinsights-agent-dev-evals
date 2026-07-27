from __future__ import annotations

import logging
from pathlib import Path

import typer

from mi.core.registry import (
    PipelineSchemaBuilder,
    RegistryScanner,
    collect_python_files,
    ensure_sys_path,
    find_project_root,
    find_project_venv,
    load_pipeline_settings,
    load_registry,
    registry_path,
    schema_path,
    should_rebuild_registry,
    save_registry,
    write_schema,
)
from .list import register_list_command


def build_registry_command(*, force: bool = False, config: Path | None = None) -> int:
    try:
        settings, config_file = load_pipeline_settings(config)
    except FileNotFoundError as exc:
        typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
        return 1

    project_root = find_project_root(config_file.parent)
    venv_path = find_project_venv(project_root)
    if venv_path is not None:
        typer.secho(
            f"Detected project virtual environment: {venv_path}", fg=typer.colors.BLUE
        )
    else:
        logging.debug("No project virtual environment detected in %s", project_root)
    ensure_sys_path(project_root)

    registry_file = registry_path(project_root, settings)
    existing_registry = load_registry(registry_file)
    python_files = collect_python_files(project_root, settings)

    needs_rebuild = should_rebuild_registry(
        existing_registry,
        project_root,
        settings,
        python_files,
        config_file=config_file,
        force=force,
    )

    if not needs_rebuild and existing_registry is not None:
        typer.secho(
            f"Registry already up to date at {registry_file}", fg=typer.colors.BLUE
        )
        return 0

    # Route registry scanner logs to typer
    registry_logger = logging.getLogger("meshinsights.registry")

    def emit_to_typer(record: logging.LogRecord) -> None:
        """Emit log record to typer with appropriate styling."""
        msg = record.getMessage()
        if record.levelno >= logging.ERROR:
            typer.secho(msg, fg=typer.colors.RED, err=True)
        elif record.levelno >= logging.WARNING:
            typer.secho(msg, fg=typer.colors.YELLOW, err=True)
        elif record.levelno >= logging.INFO:
            typer.secho(msg, fg=typer.colors.BLUE)
        else:  # DEBUG
            typer.secho(msg, fg=typer.colors.BRIGHT_BLACK)

    typer_handler = logging.Handler()
    typer_handler.emit = emit_to_typer
    registry_logger.addHandler(typer_handler)
    registry_logger.setLevel(logging.INFO)
    registry_logger.propagate = True

    scanner = RegistryScanner(project_root, settings)
    registry = scanner.scan()
    save_registry(registry, registry_file)

    schema_builder = PipelineSchemaBuilder(registry, project_root)
    write_schema(schema_builder, schema_path(project_root, settings))
    typer.secho(
        f"Registry rebuilt with {len(registry.all_records())} components",
        fg=typer.colors.BLUE,
    )
    registry_logger.removeHandler(typer_handler)
    registry_logger.propagate = True

    return 0


def register_registry_commands(app: typer.Typer) -> None:
    registry_app = typer.Typer(help="Manage the component registry.")

    @registry_app.callback(invoke_without_command=True)
    def _registry_root(ctx: typer.Context) -> None:
        if ctx.invoked_subcommand is None:
            typer.echo(ctx.get_help())
            raise typer.Exit(0)

    @registry_app.command("build")
    def registry_build(
        force: bool = typer.Option(
            False,
            "--force",
            "-f",
            help="Force rebuild even if registry appears up to date.",
        ),
        config: Path | None = typer.Option(
            None,
            "--config",
            "-c",
            help="Path to pyproject.toml containing meshinsights configuration.",
        ),
    ) -> None:
        """Scan the project and rebuild the component registry."""
        code = build_registry_command(force=force, config=config)
        raise typer.Exit(code)

    register_list_command(registry_app)
    app.add_typer(registry_app, name="registry")
