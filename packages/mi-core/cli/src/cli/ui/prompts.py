"""Styled CLI prompts: text input, confirm, and spinner."""

from __future__ import annotations

import concurrent.futures
from typing import Callable, TypeVar

from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt

T = TypeVar("T")

# ── Shared glyphs ───────────────────────────────────────────────────────

GLYPH_ARROW = "\u00bb"  # >>  (pipeline flow arrow)
GLYPH_CHECK = "\u2714"  # checkmark
GLYPH_CROSS = "\u2718"  # cross


# ── Text input ──────────────────────────────────────────────────────────


def ask_text(
    label: str,
    *,
    placeholder: str = "",
    default: str | None = None,
    required: bool = False,
    console: Console | None = None,
) -> str:
    """Prompt for free-text input with styled arrow prefix."""
    con = console or Console()
    effective_default = default or (placeholder if placeholder else None)
    while True:
        hint = f" [dim]({placeholder})[/]" if placeholder and not default else ""
        answer = Prompt.ask(
            f"  [bright_blue]{GLYPH_ARROW}[/] {label}{hint}",
            console=con,
            default=effective_default or "",
        )
        if required and not answer.strip():
            con.print(
                f"    [bright_red]{GLYPH_CROSS}[/] [red]This field is required[/]"
            )
            continue
        return answer.strip()


# ── Yes / No ────────────────────────────────────────────────────────────


def ask_confirm(
    label: str,
    *,
    default: bool = False,
    console: Console | None = None,
) -> bool:
    """Styled yes/no confirmation prompt."""
    con = console or Console()
    return Confirm.ask(
        f"  [bright_blue]{GLYPH_ARROW}[/] {label}",
        console=con,
        default=default,
    )


# ── Spinner ─────────────────────────────────────────────────────────────


def spinner(
    message: str,
    *,
    work: Callable[[], T] | None = None,
    console: Console | None = None,
) -> T | None:
    """Show a transient spinner while *work* runs in a background thread."""
    if work is None:
        return None

    con = console or Console()
    with Progress(
        SpinnerColumn("dots", style="bright_blue"),
        TextColumn("[bright_blue]{task.description}"),
        TimeElapsedColumn(),
        console=con,
        transient=True,
    ) as progress:
        progress.add_task(message, total=None)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(work)
            return future.result()
