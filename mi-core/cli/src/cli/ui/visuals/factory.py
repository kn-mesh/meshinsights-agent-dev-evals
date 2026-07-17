"""Factory progress bar visual.

Three stage shapes (Hopper → Factory → Rocket) are rendered
side-by-side with trucks connecting them.  As the wizard progresses
each shape transitions from dim → active → done.

The public entry points are :func:`build_progress` and
:func:`build_progress_complete`.
"""

from __future__ import annotations

from rich.text import Text

from .progress import build_compact, should_use_compact

# ── Stage shapes ────────────────────────────────────────────────────────
# Each shape is 7 lines tall.  {s} is a 2-char status placeholder.

_W_HOPPER = 12
_W_FACTORY = 18
_W_ROCKET = 16
_W_TRUCK = 13

_HOPPER_RAW = [
    r" \======/   ",
    r"  \    /    ",
    r"   \  /     ",
    r"  _|__|___   ",
    r" |  {s}    |  ",
    r" |________| ",
    r"   INTAKE   ",
]

_FACTORY_RAW = [
    r"   _|_            ",
    r"  |_~_|  _____    ",
    r"  _|__|_|     |   ",
    r" |      | {s}  |   ",
    r" | {s}   | >>> |   ",
    r" |______|_____|   ",
    r"    PROCESS       ",
]

_ROCKET_RAW = [
    r"      /\        ",
    r"     /  \       ",
    r"    | {s} |     ",
    r"    |    |      ",
    r"   /|    |\     ",
    r"  / |/--\| \    ",
    r"    DEPLOY      ",
]

_STAGE_SHAPES = [_HOPPER_RAW, _FACTORY_RAW, _ROCKET_RAW]
_STAGE_WIDTHS = [_W_HOPPER, _W_FACTORY, _W_ROCKET]

_TRUCK_RAW = [
    r"             ",
    r"             ",
    r"    ______   ",
    r"   |_>>>>>|  ",
    r"   _|____|_  ",
    r"  |O|====|O| ",
    r"             ",
]

_TRUCK_DIM_RAW = [
    r"             ",
    r"             ",
    r"    ......   ",
    r"   :......:  ",
    r"   .:....:.  ",
    r"  .O.===.O.  ",
    r"             ",
]

# Art dimensions: 7 art rows + 1 blank = 8 lines.
ART_HEIGHT = 7
ART_CHROME = ART_HEIGHT + 1

# Status indicators.
_S_ACTIVE = ">>"
_S_DONE = "\u2714 "
_S_PENDING = "--"


def _pad(lines: list[str], w: int) -> list[str]:
    return [line.ljust(w)[:w] for line in lines]


def _stamp(lines: list[str], status: str) -> list[str]:
    return [line.replace("{s}", status) for line in lines]


def _compose_horizontal(blocks: list[list[str]], styles: list[str]) -> Text:
    """Compose blocks side-by-side into a Rich Text with per-block styles."""
    max_h = max(len(b) for b in blocks)
    widths = [max(len(line) for line in b) for b in blocks]
    result = Text()
    for row in range(max_h):
        if row > 0:
            result.append("\n")
        result.append("  ")  # left margin
        for bi, (block, style) in enumerate(zip(blocks, styles)):
            w = widths[bi]
            if row < len(block):
                result.append(block[row].ljust(w), style=style)
            else:
                result.append(" " * w, style=style)
    return result


# ── Public API ──────────────────────────────────────────────────────────


def build_progress(
    step_idx: int,
    step_titles: list[str],
    *,
    content_lines: int = 0,
) -> Text:
    """Build the horizontal factory progress art.

    Falls back to a compact inline bar when the terminal is too small.
    """
    if should_use_compact(ART_CHROME, content_lines):
        return build_compact(step_idx, step_titles)

    n = len(step_titles)
    blocks: list[list[str]] = []
    styles: list[str] = []

    for i in range(n):
        if i > 0:
            if i < step_idx:
                blocks.append(_pad(_TRUCK_RAW, _W_TRUCK))
                styles.append("bright_blue")
            elif i == step_idx:
                blocks.append(_pad(_TRUCK_RAW, _W_TRUCK))
                styles.append("bright_cyan")
            else:
                blocks.append(_pad(_TRUCK_DIM_RAW, _W_TRUCK))
                styles.append("dim")

        shape = _STAGE_SHAPES[i % len(_STAGE_SHAPES)]
        sw = _STAGE_WIDTHS[i % len(_STAGE_WIDTHS)]

        if i < step_idx:
            blocks.append(_pad(_stamp(shape, _S_DONE), sw))
            styles.append("bright_blue")
        elif i == step_idx:
            blocks.append(_pad(_stamp(shape, _S_ACTIVE), sw))
            styles.append("bold bright_cyan")
        else:
            blocks.append(_pad(_stamp(shape, _S_PENDING), sw))
            styles.append("dim")

    return _compose_horizontal(blocks, styles)


def build_progress_complete(
    step_titles: list[str],
    *,
    content_lines: int = 0,
) -> Text:
    """Build the factory art with every stage marked done."""
    if should_use_compact(ART_CHROME, content_lines):
        return build_compact(len(step_titles), step_titles)

    blocks: list[list[str]] = []
    styles: list[str] = []

    for i, _ in enumerate(step_titles):
        if i > 0:
            blocks.append(_pad(_TRUCK_RAW, _W_TRUCK))
            styles.append("bright_blue")

        shape = _STAGE_SHAPES[i % len(_STAGE_SHAPES)]
        sw = _STAGE_WIDTHS[i % len(_STAGE_WIDTHS)]
        blocks.append(_pad(_stamp(shape, _S_DONE), sw))
        styles.append("bright_blue")

    return _compose_horizontal(blocks, styles)
