"""Design-system theme, console singleton, and Typer help overrides.

Importing this module applies the help-formatting monkey-patch as a side effect.
"""

from __future__ import annotations

from collections import defaultdict
from importlib import resources
from pathlib import Path

import click
import typer
import typer.rich_utils
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.theme import Theme as RichTheme

# ---------------------------------------------------------------------------
# Colour palette (Tokyo Night)
# ---------------------------------------------------------------------------

PALETTE = {
    "primary": "#7AA2F7",  # tokyo-night blue
    "secondary": "#7DCFFF",  # light cyan
    "accent": "#7DCFFF",  # cyan accent
    "foreground": "#a9b1d6",  # tokyo-night fg
    "background": "#1A1B26",  # tokyo-night bg
    "surface": "#24283B",  # tokyo-night surface
    "panel": "#414868",  # tokyo-night panel
    "warning": "#E0AF68",  # tokyo-night warning
    "error": "#F7768E",  # tokyo-night error
    "success": "#9ECE6A",  # tokyo-night green
}

# ---------------------------------------------------------------------------
# Rich theme (for Console / print markup)
# ---------------------------------------------------------------------------

MI_RICH_THEME = RichTheme(
    {
        "info": f"bold {PALETTE['primary']}",
        "warn": f"bold {PALETTE['warning']}",
        "error": f"bold {PALETTE['error']}",
        "hint": f"dim {PALETTE['foreground']}",
        "success": f"bold {PALETTE['success']}",
    }
)

# ---------------------------------------------------------------------------
# Console singleton
# ---------------------------------------------------------------------------

_console: Console | None = None


def get_console() -> Console:
    """Return a themed :class:`rich.console.Console` singleton."""
    global _console
    if _console is None:
        _console = Console(theme=MI_RICH_THEME)
    return _console


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def print_banner(subtitle: str | None = None) -> None:
    """Print the gradient MeshInsights figlet banner."""
    from .art import figlet_gradient

    console = get_console()
    console.print()
    console.print(figlet_gradient("MeshInsights", font="slant"), highlight=False)
    if subtitle:
        console.print(f"  [dim]{subtitle}[/]")
    console.print()


# ---------------------------------------------------------------------------
# Typer / Rich help overrides (applied at import time)
# ---------------------------------------------------------------------------

typer.rich_utils.STYLE_OPTIONS_PANEL_BORDER = "dim"
typer.rich_utils.STYLE_COMMANDS_PANEL_BORDER = "dim"
typer.rich_utils.STYLE_OPTION = "bold blue"
typer.rich_utils.STYLE_SWITCH = "bold blue"
typer.rich_utils.STYLE_METAVAR = "dim"
typer.rich_utils.STYLE_COMMANDS_TABLE_FIRST_COLUMN = "bold blue"
typer.rich_utils.STYLE_HELPTEXT = ""
typer.rich_utils.STYLE_HELPTEXT_FIRST_LINE = ""
typer.rich_utils.STYLE_USAGE = "dim"
typer.rich_utils.STYLE_USAGE_COMMAND = "dim"
typer.rich_utils.OPTIONS_PANEL_TITLE = "Options"
typer.rich_utils.COMMANDS_PANEL_TITLE = "Commands"


def _clean_table() -> Table:
    """Borderless, headerless table for help rendering."""
    return Table(
        highlight=False,
        show_header=False,
        expand=False,
        box=None,
        padding=(0, 2),
        pad_edge=True,
    )


def _print_params(
    name: str,
    params: list[click.Parameter],
    ctx: click.Context,
    console: Console,
) -> None:
    """Render options/arguments as a clean indented table."""
    if not params:
        return
    console.print(f"  [bold]{name}[/]")
    table = _clean_table()
    for p in params:
        opt_text = ", ".join(list(p.opts) + list(p.secondary_opts))
        try:
            meta = p.make_metavar(ctx)  # type: ignore[arg-type]
        except TypeError:
            meta = p.make_metavar()  # type: ignore[call-arg]
        if meta != "BOOLEAN":
            opt_text += f"  [dim]{meta}[/]"
        help_text = getattr(p, "help", "") or ""
        table.add_row(
            Text.from_markup(f"    [bold blue]{opt_text}[/]"),
            Text.from_markup(f"[dim]{help_text}[/]"),
        )
    console.print(table)
    console.print()


def _print_commands(
    name: str,
    commands: list[click.Command],
    console: Console,
) -> None:
    """Render commands as a clean indented table."""
    if not commands:
        return
    console.print(f"  [bold]{name}[/]")
    table = _clean_table()
    table.add_column(style="bold blue", no_wrap=True)
    table.add_column(justify="left", no_wrap=True)
    for cmd in commands:
        table.add_row(
            Text(f"    {cmd.name or ''}"),
            Text.from_markup(f"[dim]{cmd.get_short_help_str(limit=60)}[/]"),
        )
    console.print(table)
    console.print()


def _custom_rich_format_help(
    *,
    obj: click.Command | click.Group,
    ctx: click.Context,
    markup_mode: str,  # needed for monkey-patching
) -> None:
    """MI-styled help: gradient banner for root, clean tables for all."""
    if ctx.parent is None:
        print_banner(subtitle=obj.get_short_help_str(limit=80) if obj.help else None)
    else:
        con = get_console()
        con.print()
        if obj.help:
            con.print(f"  [dim]{obj.get_short_help_str(limit=80)}[/]")
            con.print()

    console = typer.rich_utils._get_rich_console()

    # Group params by panel
    panels_opts: defaultdict[str, list[click.Parameter]] = defaultdict(list)
    for param in obj.get_params(ctx):
        if getattr(param, "hidden", False):
            continue
        panel = getattr(param, typer.rich_utils._RICH_HELP_PANEL_NAME, None) or (
            typer.rich_utils.ARGUMENTS_PANEL_TITLE
            if isinstance(param, click.Argument)
            else typer.rich_utils.OPTIONS_PANEL_TITLE
        )
        panels_opts[panel].append(param)

    for panel_name, params in panels_opts.items():
        _print_params(panel_name, params, ctx, console)

    # Commands (for groups)
    if isinstance(obj, click.Group):
        panels_cmds: defaultdict[str, list[click.Command]] = defaultdict(list)
        for cmd_name in obj.list_commands(ctx):
            cmd = obj.get_command(ctx, cmd_name)
            if cmd and not cmd.hidden:
                panel = (
                    getattr(cmd, typer.rich_utils._RICH_HELP_PANEL_NAME, None)
                    or typer.rich_utils.COMMANDS_PANEL_TITLE
                )
                panels_cmds[panel].append(cmd)
        for panel_name, cmds in panels_cmds.items():
            _print_commands(panel_name, cmds, console)


typer.rich_utils.rich_format_help = _custom_rich_format_help  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Textual theme + CSS (for the pipeline monitor TUI)
# ---------------------------------------------------------------------------

try:
    from textual.theme import Theme as TextualTheme

    PIPELINE_THEME: TextualTheme | None = TextualTheme(
        name="mi-pipeline",
        primary=PALETTE["primary"],
        secondary=PALETTE["secondary"],
        accent=PALETTE["accent"],
        foreground=PALETTE["foreground"],
        background=PALETTE["background"],
        surface=PALETTE["surface"],
        panel=PALETTE["panel"],
        warning=PALETTE["warning"],
        error=PALETTE["error"],
        success=PALETTE["primary"],
        dark=True,
        variables={"button-color-foreground": PALETTE["surface"]},
    )
except ImportError:
    PIPELINE_THEME = None


def _load_monitor_css() -> str:
    """Load monitor.css from the package directory."""
    css_path = Path(__file__).parent / "monitor.css"
    if css_path.is_file():
        return css_path.read_text()
    # Fallback for installed packages using importlib.resources
    ref = resources.files(__package__) / "monitor.css"  # type: ignore[arg-type]
    return ref.read_text()  # type: ignore[union-attr]


MONITOR_CSS: str = _load_monitor_css()
