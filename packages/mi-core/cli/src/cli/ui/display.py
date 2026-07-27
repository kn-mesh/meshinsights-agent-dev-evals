"""Reusable display primitives for wizard-style output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

from .prompts import GLYPH_CHECK, GLYPH_CROSS
from .terminal import clear_screen, term_height

if TYPE_CHECKING:
    from .runner import VisualTheme

# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------

MAX_DISPLAY_LEN = 50


def truncate(val: str, max_len: int = MAX_DISPLAY_LEN) -> str:
    """Truncate a value for compact display."""
    return val if len(val) <= max_len else val[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Field line — the core visual atom
# ---------------------------------------------------------------------------


def field_line(console: Console, label: str, value: str) -> None:
    """Print ``✔ Label  value`` summary line."""
    if value:
        console.print(
            f"    [bright_blue]{GLYPH_CHECK}[/] [dim]{label}[/]  "
            f"[bright_cyan]{truncate(value)}[/]",
            highlight=False,
        )
    else:
        console.print(
            f"    [bright_blue]{GLYPH_CHECK}[/] [dim]{label}[/]",
            highlight=False,
        )


# ---------------------------------------------------------------------------
# Grouped step / provider rendering
# ---------------------------------------------------------------------------

# A completed entry: (status, title, fields)
#   status: "done" | "skip" | "fail"
#   title:  step or provider name
#   fields: list of (label, display_value)
CompletedEntry = tuple[str, str, list[tuple[str, str]]]


def count_entry_lines(completed: list[CompletedEntry]) -> int:
    """Count how many terminal lines print_steps would produce."""
    n = 0
    for status, _title, fields in completed:
        if status == "done":
            n += 1  # group header
            n += len(fields)  # field lines
            n += 1  # trailing blank line
        else:
            # "skip" / "fail": 1 status line + 1 blank
            n += 2
    return n


def remaining_picker_height(
    art_chrome: int,
    completed: list[CompletedEntry] | None = None,
    breadcrumb_count: int = 0,
) -> int:
    """Estimate how many picker items fit on screen. Returns 0 for auto-detect."""
    _ART_OVERHEAD = art_chrome + 1  # art chrome + group header
    _PICKER_CHROME = 4  # label + hint + possible scroll indicators
    used = _ART_OVERHEAD + _PICKER_CHROME
    used += count_entry_lines(completed or [])
    used += breadcrumb_count
    available = term_height() - used
    # Return 0 (auto-detect) when there is plenty of room; the picker's
    # own _max_visible_items default already handles this case well.
    if available >= 12:
        return 0
    return max(0, available)


def print_steps(console: Console, completed: list[CompletedEntry]) -> None:
    """Render completed steps grouped by title."""
    for status, title, fields in completed:
        if status == "done":
            console.print(f"  [bold bright_blue]{title}[/]", highlight=False)
            for label, display in fields:
                field_line(console, label, display)
            console.print()
        elif status == "skip":
            console.print(f"  [dim]{title} — skipped[/]", highlight=False)
            console.print()
        elif status == "fail":
            console.print(
                f"  [bright_red]{GLYPH_CROSS}[/] [dim]{title} — failed[/]",
                highlight=False,
            )
            console.print()


# ---------------------------------------------------------------------------
# Result messages
# ---------------------------------------------------------------------------


def print_success(console: Console, message: str) -> None:
    """Print a success line: ``✔ message`` in bright green."""
    console.print(f"  [bright_green]{GLYPH_CHECK}[/] [bold bright_green]{message}[/]")


def print_failure(console: Console, message: str) -> None:
    """Print a failure line: ``✘ message`` in red."""
    console.print(f"  [bright_red]{GLYPH_CROSS}[/] [bold red]{message}[/]")


def print_hint(console: Console, message: str) -> None:
    """Print a dim hint line."""
    console.print(f"  [dim]{message}[/]")


# ---------------------------------------------------------------------------
# Value masking
# ---------------------------------------------------------------------------


def mask_value(value: str | None, visible: int = 5) -> str:
    """Mask a sensitive value, showing only the first *visible* chars."""
    if not value:
        return ""
    if len(value) <= visible:
        return value
    return value[:visible] + "*" * (len(value) - visible)


# ---------------------------------------------------------------------------
# Full-screen drawing helpers (alt-screen wizard pattern)
# ---------------------------------------------------------------------------

# Rough line allowances for prompt types when estimating content height.
_PROMPT_OVERHEAD_TEXT = 4  # label + input + padding
_PROMPT_OVERHEAD_MULTISELECT = 8  # label + hint + ~6 visible choices
_PROMPT_OVERHEAD_CONFIRM = 2  # label + y/n


def draw_screen(
    console: Console,
    *,
    theme: VisualTheme,
    step_idx: int,
    phase_titles: list[str],
    completed: list[CompletedEntry] | None = None,
    current_title: str | None = None,
    current_subtitle: str | None = None,
    breadcrumbs: list[tuple[str, str]] | None = None,
    prompt_overhead: int = _PROMPT_OVERHEAD_TEXT,
) -> None:
    """Clear-and-redraw a wizard screen: art → completed → breadcrumbs."""
    clear_screen()

    # Estimate total content below the art
    below = count_entry_lines(completed or [])
    if current_title:
        below += 1  # group header
    below += len(breadcrumbs) if breadcrumbs else 0
    below += prompt_overhead

    art = theme.build_progress(step_idx, phase_titles, content_lines=below)
    console.print(art, highlight=False)
    console.print()

    if completed:
        print_steps(console, completed)

    if current_title:
        suffix = f"  [dim]{current_subtitle}[/]" if current_subtitle else ""
        console.print(
            f"  [bold bright_blue]{current_title}[/]{suffix}",
            highlight=False,
        )

    if breadcrumbs:
        for label, value in breadcrumbs:
            field_line(console, label, value)


def review_screen(
    console: Console,
    *,
    theme: VisualTheme,
    phase_titles: list[str],
    completed: list[CompletedEntry],
) -> None:
    """Render the review screen: completed art + all entries."""
    clear_screen()

    below = count_entry_lines(completed) + _PROMPT_OVERHEAD_CONFIRM
    art_done = theme.build_progress_complete(phase_titles, content_lines=below)
    console.print(art_done, highlight=False)
    console.print()

    print_steps(console, completed)


def print_summary(
    console: Console,
    completed: list[CompletedEntry],
    *,
    success_msg: str = "All steps completed successfully!",
    failure_msg: str | None = None,
    hint_msg: str | None = None,
) -> None:
    """Print post-wizard summary: entries + success/failure + optional hint."""
    console.print()
    print_steps(console, completed)

    failed = [title for status, title, _ in completed if status == "fail"]
    if not failed:
        print_success(console, success_msg)
    else:
        msg = failure_msg or f"Failed: {', '.join(failed)}"
        print_failure(console, msg)

    console.print()
    if hint_msg:
        print_hint(console, hint_msg)
        console.print()
