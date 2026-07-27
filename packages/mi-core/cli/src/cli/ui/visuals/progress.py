"""Common interface and helpers for composable ASCII-art progress bars.

Every visual module in this package exposes a ``build_progress`` function
with the same signature so callers can swap themes without changing code.
The minimal compact fallback lives here as a shared utility.
"""

from __future__ import annotations

from rich.text import Text

from ..terminal import term_height, term_width

# ── Dimension thresholds ────────────────────────────────────────────────
# Below these values the full art is replaced with a single-line summary.
MIN_WIDTH = 72
MIN_HEIGHT = 20

# Height of the compact fallback (1 line + 1 blank).
COMPACT_CHROME = 2


# ── Shared helpers ──────────────────────────────────────────────────────


def should_use_compact(art_height: int, content_lines: int = 0) -> bool:
    """Return ``True`` when the terminal is too small for full art.

    Args:
        art_height: Total lines the full art would occupy (including
            the blank line callers typically print after it).
        content_lines: Additional lines the caller will render below
            the art (completed answers, prompts, etc.).
    """
    if term_width() < MIN_WIDTH or term_height() < MIN_HEIGHT:
        return True
    if content_lines > 0 and (art_height + content_lines > term_height()):
        return True
    return False


def build_compact(step_idx: int, step_titles: list[str]) -> Text:
    """Compact single-line progress shown when the terminal is too small."""
    result = Text("  ")
    for i, title in enumerate(step_titles):
        if i < step_idx:
            result.append(f"\u2714 {title}", style="bright_blue")
        elif i == step_idx:
            result.append(f"\u00bb {title}", style="bright_cyan bold")
        else:
            result.append(f"\u2500 {title}", style="dim")

        if i < len(step_titles) - 1:
            if i < step_idx:
                result.append(" >>> ", style="bright_blue")
            else:
                result.append(" --- ", style="dim")
    return result
