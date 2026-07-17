"""Deploy animation — truck drives across the screen then a rocket launches.

This is the existing end-of-wizard celebration, extracted into its own
module so ``art.py`` stays thin.
"""

from __future__ import annotations

import random
import threading
import time

from rich.console import Console
from rich.text import Text

from ..terminal import (
    cursor_up,
    erase_down,
    flush,
    hide_cursor,
    show_cursor,
    term_width,
)

# ── Truck ───────────────────────────────────────────────────────────────

_ANIM_TRUCK = [
    r"   ______   ",
    r"  |_>>>>>|  ",
    r"  _|____|_  ",
    r" |O|====|O| ",
]

# ── Rocket frames ───────────────────────────────────────────────────────

_FIRE_STYLES = ["bright_red", "red", "yellow", "dark_orange", "orange1"]
_FIRE_CHARS = list("*^~#@%&!")
_SMOKE_STYLES = ["grey50", "grey39", "grey30"]
_SMOKE_CHARS = list(".:;'`~,")

_W_FRAME = 14
_B = "bright_blue"

_R = [
    r"      /\      ",  # 0  nose
    r"     /  \     ",  # 1  cone
    r"    | OK |    ",  # 2  label
    r"    |    |    ",  # 3  body
    r"   /|    |\   ",  # 4  upper fin
    r"  / |/--\| \  ",  # 5  lower fin + engine bell
]


def _rand_fire(inner_w: int) -> str:
    chars = "".join(random.choice(_FIRE_CHARS) for _ in range(inner_w))
    return chars.center(_W_FRAME)


def _rand_smoke(inner_w: int) -> str:
    chars = "".join(random.choice(_SMOKE_CHARS) for _ in range(inner_w))
    return chars.center(_W_FRAME)


def _build_rocket_frames() -> list[list[tuple[str, str]]]:
    E = "              "  # empty line (14 chars)
    PAD = r"  ==|====|==  "
    F = [
        ("fire:4", "fire"),
        ("fire:6", "fire"),
        ("fire:8", "fire"),
        ("fire:6", "fire"),
        ("fire:4", "fire"),
        ("fire:2", "fire"),
    ]

    # fmt: off
    return [
        [   # 0: on the pad
            (E, _B), (E, _B),
            (_R[0], _B), (_R[1], _B), (_R[2], _B),
            (_R[3], _B), (_R[4], _B), (_R[5], _B),
            (PAD, _B), (E, _B),
        ],
        [   # 1: ignition
            (E, _B), (E, _B),
            (_R[0], _B), (_R[1], _B), (_R[2], _B),
            (_R[3], _B), (_R[4], _B), (_R[5], _B),
            F[0], (E, _B),
        ],
        [   # 2: liftoff
            (E, _B),
            (_R[0], _B), (_R[1], _B), (_R[2], _B),
            (_R[3], _B), (_R[4], _B), (_R[5], _B),
            F[0], F[1], (E, _B),
        ],
        [   # 3: rising
            (_R[0], _B), (_R[1], _B), (_R[2], _B),
            (_R[3], _B), (_R[4], _B), (_R[5], _B),
            F[0], F[1], F[2], (E, _B),
        ],
        [   # 4: climbing
            (_R[0], _B), (_R[1], _B), (_R[2], _B),
            (_R[3], _B), (_R[4], _B), (_R[5], _B),
            F[0], F[1], F[2], F[3],
        ],
        [   # 5: nose cropped
            (_R[1], _B), (_R[2], _B), (_R[3], _B),
            (_R[4], _B), (_R[5], _B),
            F[0], F[1], F[2], F[3], F[4],
        ],
        [   # 6: nose + cone cropped
            (_R[2], _B), (_R[3], _B), (_R[4], _B), (_R[5], _B),
            F[0], F[1], F[2], F[3], F[4], F[5],
        ],
        [   # 7: only fins visible
            (_R[4], _B), (_R[5], _B),
            F[0], F[1], F[2], F[3], F[4],
            ("smoke:4", "smoke"), (E, _B), (E, _B),
        ],
        [   # 8: just the engine bell tip
            (_R[5], _B), F[0], F[1], F[2], F[3],
            ("smoke:4", "smoke"), ("smoke:3", "smoke"),
            ("smoke:2", "smoke"), (E, _B), (E, _B),
        ],
        [   # 9: fire trail + smoke
            (E, _B), F[0], F[1],
            ("smoke:6", "smoke"), ("smoke:4", "smoke"),
            ("smoke:3", "smoke"), ("smoke:2", "smoke"),
            (E, _B), (E, _B), (E, _B),
        ],
        [   # 10: fading smoke
            (E, _B), (E, _B),
            ("smoke:4", "smoke"), ("smoke:3", "smoke"),
            ("smoke:2", "smoke"),
            (E, _B), (E, _B), (E, _B), (E, _B), (E, _B),
        ],
        [   # 11: clear
            (E, _B), (E, _B), (E, _B),
            ("smoke:2", "smoke"),
            (E, _B), (E, _B), (E, _B), (E, _B), (E, _B), (E, _B),
        ],
    ]
    # fmt: on


_ANIM_ROCKET = _build_rocket_frames()


def _resolve_line(text: str, style: str) -> tuple[str, str]:
    if style == "fire" and text.startswith("fire:"):
        w = int(text.split(":")[1])
        return _rand_fire(w), random.choice(_FIRE_STYLES)
    if style == "smoke" and text.startswith("smoke:"):
        w = int(text.split(":")[1])
        return _rand_smoke(w), random.choice(_SMOKE_STYLES)
    return text, style


def _print_frame(console: Console, lines: list[tuple[str, str]]) -> None:
    frame = Text()
    for i, (line, style) in enumerate(lines):
        if i > 0:
            frame.append("\n")
        frame.append("  ")
        frame.append(line, style=style)
    console.print(frame, highlight=False)
    flush()


# ── Public API ──────────────────────────────────────────────────────────


def animate_deploy(
    *,
    console: Console | None = None,
    done: threading.Event | None = None,
) -> None:
    """Truck drives across the screen, transforms into a rocket, and launches.

    When *done* is provided the animation loops until the event is set,
    finishing the current cycle before exiting so visuals stay clean.
    """
    con = console or Console()
    w = term_width()

    if w < 40:
        # Too narrow for animation — just wait for the work to finish.
        if done is not None:
            done.wait()
        return

    hide_cursor()
    try:
        truck_w = max(len(line) for line in _ANIM_TRUCK)
        target_x = min(w // 2 - truck_w // 2, w - truck_w - 4)
        road_w = target_x + truck_w + 4
        road = "=" * road_w
        n_truck_lines = len(_ANIM_TRUCK) + 1  # +1 for road
        n_rocket_lines = len(_ANIM_ROCKET[0])
        step_size = max(2, w // 30)

        first_cycle = True
        while True:
            # Phase 1: truck drives to centre.
            first_frame = True
            for x in range(0, target_x, step_size):
                lines = [" " * x + tl for tl in _ANIM_TRUCK] + [road]
                if not (first_cycle and first_frame):
                    cursor_up(n_truck_lines)
                    erase_down()
                    flush()
                _print_frame(con, [(line, "bright_blue") for line in lines])
                first_frame = False
                time.sleep(0.1)

            # Final truck position.
            cursor_up(n_truck_lines)
            erase_down()
            flush()
            final_lines = [" " * target_x + tl for tl in _ANIM_TRUCK] + [road]
            _print_frame(con, [(line, "bright_blue") for line in final_lines])
            time.sleep(0.25)

            # Phase 2: rocket launch.
            cursor_up(n_truck_lines)
            erase_down()
            flush()

            for fi, rocket_frame in enumerate(_ANIM_ROCKET):
                styled_lines = []
                for text, style in rocket_frame:
                    resolved_text, resolved_style = _resolve_line(text, style)
                    styled_lines.append(
                        (" " * target_x + resolved_text, resolved_style)
                    )
                if fi > 0:
                    cursor_up(n_rocket_lines)
                    erase_down()
                    flush()
                _print_frame(con, styled_lines)
                time.sleep(0.1)

            # Collapse the rocket frame area so no whitespace is left behind.
            cursor_up(n_rocket_lines)
            erase_down()
            flush()

            first_cycle = False

            # If no done event was provided, run once (original behaviour).
            # Otherwise loop until the work is finished.
            if done is None or done.is_set():
                break

    finally:
        show_cursor()
