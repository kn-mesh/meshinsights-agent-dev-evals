"""ASCII art banners, gradient figlets, and deploy animations."""

from __future__ import annotations

import random

import pyfiglet
from rich.console import Console
from rich.text import Text

from .terminal import term_width

# ── Re-exports from visuals package ─────────────────────────────────────
# Two progress-bar themes:
#   build_factory / build_factory_complete  — hopper→factory→rocket (init)
#   build_conveyor / build_conveyor_complete — conveyor belt machines (auth)
#
# ART_CHROME / ART_HEIGHT are exported from whichever theme callers need;
# display.py (auth) uses the conveyor constants, wizard.py (init) uses factory.

from .visuals.factory import (  # noqa: F401
    ART_CHROME as FACTORY_ART_CHROME,
    ART_HEIGHT as FACTORY_ART_HEIGHT,
    build_progress as build_factory,
    build_progress_complete as build_factory_complete,
)
from .visuals.conveyor import (  # noqa: F401
    ART_CHROME as CONVEYOR_ART_CHROME,
    ART_HEIGHT as CONVEYOR_ART_HEIGHT,
    build_progress as build_conveyor,
    build_progress_complete as build_conveyor_complete,
)
from .visuals.deploy import animate_deploy  # noqa: F401

# Per-theme constants are available as FACTORY_ART_CHROME / CONVEYOR_ART_CHROME
# etc.  For theme-agnostic code, use VisualTheme.art_chrome from runner.py.


# ── Gradient / color sets ───────────────────────────────────────────────

_GRADIENT_STOPS = [
    (255, 255, 255),  # white
    (0, 255, 255),  # cyan
    (15, 200, 255),  # cyan-dodger blend
    (30, 144, 255),  # dodger blue
    (30, 144, 255),  # dodger blue (hold)
]


def _lerp_color(
    stops: list[tuple[int, int, int]],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between gradient *stops* at position *t* (0-1)."""
    t = max(0.0, min(1.0, t))
    n = len(stops) - 1
    idx = t * n
    lo = int(idx)
    hi = min(lo + 1, n)
    frac = idx - lo
    r = int(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * frac)
    g = int(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * frac)
    b = int(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * frac)
    return (r, g, b)


# ── Figlet utilities ────────────────────────────────────────────────────


def figlet_banner(text: str, font: str = "slant") -> str:
    """Render text as a large figlet banner."""
    return pyfiglet.figlet_format(text, font=font, width=term_width())


def figlet_gradient(
    text: str,
    font: str = "slant",
    noise: float = 0.0,
) -> Text:
    """Return a Rich Text with a per-character gradient."""
    banner = figlet_banner(text, font=font)
    lines = banner.rstrip("\n").split("\n")
    n_lines = max(len(lines) - 1, 1)
    result = Text()
    for i, line in enumerate(lines):
        if i > 0:
            result.append("\n")
        base_t = i / n_lines
        for ch in line:
            if ch == " ":
                result.append(ch)
            else:
                jitter = random.uniform(-noise, noise)
                t = max(0.0, min(1.0, base_t + jitter))
                r, g, b = _lerp_color(_GRADIENT_STOPS, t)
                result.append(ch, style=f"bold #{r:02x}{g:02x}{b:02x}")
    return result


# ── Misc utilities (kept for backward compat) ──────────────────────────


def print_art(art: str, *, console: Console | None = None) -> None:
    """Print pre-styled ASCII art (contains Rich markup)."""
    con = console or Console()
    con.print(art, highlight=False)


def divider(*, console: Console | None = None) -> None:
    """Print a pipe-style divider line."""
    con = console or Console()
    w = min(term_width(), 56)
    pattern = "=-=~"
    repeated = (pattern * ((w // len(pattern)) + 1))[:w]
    con.print(f"  {repeated}", style="bright_blue", highlight=False)
