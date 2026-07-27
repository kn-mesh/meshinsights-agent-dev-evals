from __future__ import annotations

from pathlib import Path

import typer

from mi.core.registry import (
    RegistryData,
    ensure_sys_path,
    find_project_root,
    load_pipeline_settings,
    load_registry,
    registry_path,
)


def _load_registry(project_root: Path, settings) -> RegistryData | None:
    return load_registry(registry_path(project_root, settings))


def register_list_command(app: typer.Typer) -> None:
    @app.command("list")
    def registry_list(
        section: str = typer.Option(
            "all",
            "--section",
            "-s",
            help="Registry section to list (e.g., retrievers, processors). Use 'all' for every section.",
        ),
        config: Path | None = typer.Option(
            None,
            "--config",
            "-c",
            help="Path to pyproject.toml containing meshinsights configuration.",
        ),
    ) -> None:
        """List components in the registry grouped by section."""
        try:
            settings, config_file = load_pipeline_settings(config)
        except FileNotFoundError as exc:
            typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1)

        project_root = find_project_root(config_file.parent)
        ensure_sys_path(project_root)
        registry = _load_registry(project_root, settings)
        if registry is None:
            typer.secho(
                "Registry not found. Run 'mi registry build' first.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)

        if section == "all":
            sections = [
                s for s in registry.components.keys() if registry.components.get(s)
            ]
        else:
            sections = [section]

        if not sections:
            typer.secho(
                "No components found in registry.", fg=typer.colors.BRIGHT_BLACK
            )
            raise typer.Exit(0)

        for sec in sections:
            records = registry.components.get(sec) or []
            if not records:
                continue
            typer.secho(f"[{sec}]", fg=typer.colors.BLUE)
            for record in records:
                typer.echo(f"  {record.name} ({record.import_path})")
