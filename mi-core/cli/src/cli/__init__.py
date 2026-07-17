# ruff: noqa: F401
from __future__ import annotations

import click
import typer

from .auth import register_auth_command
from .init_project import register_init_command
from .options import register_version_option
from .registry import register_registry_commands
from .run_pipeline import register_run_command
from .self_update import register_update_command
from .ui import theme as _theme  # apply help overrides

DEVMODE = True

# ── App ─────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="meshinsights-pipeline",
    help="MeshInsights data pipeline CLI.",
    no_args_is_help=True,
)

register_version_option(app)
register_auth_command(app)
register_registry_commands(app)
register_run_command(app)
register_init_command(app)
register_update_command(app)


def main(argv: list[str] | None = None) -> int:
    try:
        app(standalone_mode=False, args=argv)
    except typer.Exit as exc:
        return exc.exit_code
    except (KeyboardInterrupt, click.Abort):
        typer.secho("\nOperation cancelled by user.", fg=typer.colors.RED, err=True)
        return 130
    except click.exceptions.UsageError:
        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            click.echo(ctx.get_help())
        return 0
    except Exception as exc:
        if DEVMODE:
            raise
        typer.secho(f"Unexpected error: {exc}", fg=typer.colors.RED, err=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
