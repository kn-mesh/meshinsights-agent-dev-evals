"""Arrow-key driven select and multiselect pickers."""

from __future__ import annotations

from rich.console import Console

from .terminal import Key, cursor_up, erase_down, flush, read_key, term_height


_MIN_VISIBLE = 5
_MAX_VISIBLE = 10


def _max_visible_items(max_visible: int = 0) -> int:
    """How many picker items can fit on screen.

    When *max_visible* is provided and positive, it is used directly
    (clamped to ``_MIN_VISIBLE`` / ``_MAX_VISIBLE``).  Otherwise a
    dynamic value based on terminal height is returned, still capped
    at ``_MAX_VISIBLE``.
    """
    if max_visible > 0:
        return max(_MIN_VISIBLE, min(max_visible, _MAX_VISIBLE))
    return max(_MIN_VISIBLE, min(term_height() - 12, _MAX_VISIBLE))


# ── Glyphs ──────────────────────────────────────────────────────────────

_POINTER = "\u00bb"  # >>  (pipeline flow indicator)
_CHECK = "\u25c9"  # filled circle (single-select: focused)
_UNCHECK = "\u25ef"  # empty circle (single-select: unfocused)
_BOX_ON = "\u25a0"  # filled square (multi: selected)
_BOX_OFF = "\u25a1"  # empty square (multi: unselected)
_BOX_FORCED = "\u25a3"  # square with inner square (multi: forced / locked-in)
_BOX_DISABLED = "\u25a1"  # empty square (multi: disabled / unavailable)


# ── Rendering ───────────────────────────────────────────────────────────


def _viewport(cursor: int, total: int, max_vis: int) -> tuple[int, int]:
    """Return (start, end) slice indices for a scrolling viewport."""
    if total <= max_vis:
        return 0, total
    half = max_vis // 2
    start = cursor - half
    start = max(0, min(start, total - max_vis))
    end = start + max_vis
    return start, end


def _draw_select(
    console: Console,
    label: str,
    choices: list[str],
    cursor: int,
    hint: str,
    max_visible: int = 0,
) -> int:
    """Draw the select picker and return the number of lines printed."""
    lines = 0
    console.print(f"  [bright_blue]{_POINTER}[/] [prompt]{label}[/]", highlight=False)
    lines += 1
    console.print(f"    [dim]({hint})[/]", highlight=False)
    lines += 1

    max_vis = _max_visible_items(max_visible)
    start, end = _viewport(cursor, len(choices), max_vis)

    if start > 0:
        console.print("    [dim]\u2191 more[/]", highlight=False)
        lines += 1

    for i in range(start, end):
        opt = choices[i]
        if i == cursor:
            console.print(
                f"    [bright_blue]{_POINTER} {_CHECK} {opt}[/]",
                highlight=False,
            )
        else:
            console.print(
                f"      [dim]{_UNCHECK} {opt}[/]",
                highlight=False,
            )
        lines += 1

    if end < len(choices):
        console.print("    [dim]\u2193 more[/]", highlight=False)
        lines += 1

    return lines


def _draw_multiselect(
    console: Console,
    label: str,
    choices: list[str],
    cursor: int,
    selected: set[int],
    forced: set[int],
    disabled: set[int],
    hint: str,
    max_visible: int = 0,
) -> int:
    """Draw the multiselect picker and return the number of lines printed."""
    lines = 0
    console.print(f"  [bright_blue]{_POINTER}[/] [prompt]{label}[/]", highlight=False)
    lines += 1
    console.print(f"    [dim]({hint})[/]", highlight=False)
    lines += 1

    max_vis = _max_visible_items(max_visible)
    start, end = _viewport(cursor, len(choices), max_vis)

    if start > 0:
        console.print("    [dim]\u2191 more[/]", highlight=False)
        lines += 1

    for i in range(start, end):
        opt = choices[i]
        is_cursor = i == cursor
        is_forced = i in forced
        is_disabled = i in disabled
        is_on = i in selected

        # Pick the right glyph for this item's state
        if is_forced:
            box = _BOX_FORCED
        elif is_disabled:
            box = _BOX_DISABLED
        else:
            box = _BOX_ON if is_on else _BOX_OFF

        ptr = _POINTER if is_cursor else " "

        if is_forced:
            style = "bright_blue" if is_cursor else "blue"
        elif is_disabled:
            style = "dim" if is_cursor else "dim"
        else:
            if is_cursor:
                style = "bright_blue" if is_on else "bright_white"
            else:
                style = "bright_blue" if is_on else "dim"

        if is_disabled:
            console.print(
                f"    [{style}]{ptr} [strike]{box}[/strike] {opt}[/]",
                highlight=False,
            )
        else:
            console.print(
                f"    [{style}]{ptr} {box} {opt}[/]",
                highlight=False,
            )
        lines += 1

    if end < len(choices):
        console.print("    [dim]\u2193 more[/]", highlight=False)
        lines += 1

    return lines


# ── Public API ──────────────────────────────────────────────────────────


def select(
    label: str,
    choices: list[str],
    *,
    default: str | None = None,
    max_visible: int = 0,
    console: Console | None = None,
) -> str:
    """Interactive single-select with arrow keys. Returns the selected choice."""
    con = console or Console()
    cursor = 0
    if default and default in choices:
        cursor = choices.index(default)

    hint = "\u2191\u2193 move, enter select"
    printed_lines = _draw_select(con, label, choices, cursor, hint, max_visible)
    flush()

    while True:
        key, _ = read_key()

        if key == Key.CTRL_C:
            raise KeyboardInterrupt

        moved = False
        if key == Key.UP:
            cursor = (cursor - 1) % len(choices)
            moved = True
        elif key == Key.DOWN:
            cursor = (cursor + 1) % len(choices)
            moved = True
        elif key == Key.ENTER:
            break

        if moved:
            cursor_up(printed_lines)
            erase_down()
            flush()
            printed_lines = _draw_select(con, label, choices, cursor, hint, max_visible)
            flush()

    # Erase picker, print final inline result
    cursor_up(printed_lines)
    erase_down()
    flush()
    con.print(
        f"  [bright_blue]\u2714[/] [bold]{label}[/]  "
        f"[bright_white]{choices[cursor]}[/]",
        highlight=False,
    )
    return choices[cursor]


def multiselect(
    label: str,
    choices: list[str],
    *,
    defaults: list[str] | None = None,
    forced: list[str] | None = None,
    disabled: list[str] | None = None,
    min_select: int = 0,
    max_visible: int = 0,
    console: Console | None = None,
) -> list[str]:
    """Interactive multi-select with arrow keys and space to toggle."""
    con = console or Console()
    cursor = 0
    selected: set[int] = set()

    # Build forced/disabled index sets
    forced_idx: set[int] = set()
    if forced:
        for f in forced:
            if f in choices:
                idx = choices.index(f)
                forced_idx.add(idx)
                selected.add(idx)  # forced items are always selected

    disabled_idx: set[int] = set()
    if disabled:
        for d in disabled:
            if d in choices:
                disabled_idx.add(choices.index(d))

    # Add defaults (but not disabled ones)
    if defaults:
        for d in defaults:
            if d in choices:
                idx = choices.index(d)
                if idx not in disabled_idx:
                    selected.add(idx)

    hint = "\u2191\u2193 move, space toggle, enter confirm"
    printed_lines = _draw_multiselect(
        con,
        label,
        choices,
        cursor,
        selected,
        forced_idx,
        disabled_idx,
        hint,
        max_visible,
    )
    flush()

    while True:
        key, _ = read_key()

        if key == Key.CTRL_C:
            raise KeyboardInterrupt

        redraw = False
        if key == Key.UP:
            cursor = (cursor - 1) % len(choices)
            redraw = True
        elif key == Key.DOWN:
            cursor = (cursor + 1) % len(choices)
            redraw = True
        elif key == Key.SPACE:
            # Only toggle if not forced or disabled
            if cursor not in forced_idx and cursor not in disabled_idx:
                if cursor in selected:
                    selected.discard(cursor)
                else:
                    selected.add(cursor)
                redraw = True
        elif key == Key.ENTER:
            if len(selected) >= min_select:
                break

        if redraw:
            cursor_up(printed_lines)
            erase_down()
            flush()
            printed_lines = _draw_multiselect(
                con,
                label,
                choices,
                cursor,
                selected,
                forced_idx,
                disabled_idx,
                hint,
                max_visible,
            )
            flush()

    # Erase picker, print final inline result
    cursor_up(printed_lines)
    erase_down()
    flush()
    result = [choices[i] for i in sorted(selected)]
    display = ", ".join(result) if result else "[dim]<none>[/]"
    con.print(
        f"  [bright_blue]\u2714[/] [bold]{label}[/]  [bright_white]{display}[/]",
        highlight=False,
    )
    return result
