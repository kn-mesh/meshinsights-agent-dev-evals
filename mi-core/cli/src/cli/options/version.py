from __future__ import annotations

from importlib import metadata

import typer

from ..ui.art import figlet_gradient
from ..ui.theme import get_console

PACKAGE_NAME = "meshinsights-cli"


def _print_banner() -> None:
    """Print the gradient MeshInsights figlet banner."""
    console = get_console()
    console.print()
    console.print(figlet_gradient("MeshInsights", font="slant"), highlight=False)


def print_version() -> int:
    console = get_console()
    try:
        current = metadata.version(PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        current = "dev"

    _print_banner()
    console.print(f"  [dim]version[/] [bold]{current}[/]")
    console.print()
    return 0


def register_version_option(app: typer.Typer) -> None:
    @app.callback(invoke_without_command=True)
    def _root(
        ctx: typer.Context,
        version: bool = typer.Option(
            False, "--version", help="Print the meshinsights CLI version and exit."
        ),
    ) -> None:
        if version:
            code = print_version()
            raise typer.Exit(code)
        if ctx.invoked_subcommand is None:
            # No command provided; show help like Typer default
            raise typer.Exit(0)
