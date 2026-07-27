"""Conveyor-belt progress bar visual with inline machines.

Each wizard step is represented by a machine on the conveyor belt.  A
free box on the belt approaches the current machine; completed and
pending machines are empty.

The public entry points are :func:`build_progress` and
:func:`build_progress_complete`, which share the same signature as the
other visual themes so callers can swap freely.
"""

from __future__ import annotations

from rich.text import Text

from ..terminal import term_width
from .progress import build_compact, should_use_compact

# ── Machine definitions ─────────────────────────────────────────────────
# Each machine has:
#   "above":  3 lines rising above the belt (empty machine)
#   "belt":   replaces the belt surface at this position
#   "below":  replaces the roller line (machine legs/base)
#
# All strings within a machine are the same width (10 chars).
# The belt base is plain underscores (no interior rollers), so "below"
# strings use underscores for continuity — no (o) collision possible.

_MACHINES: dict[str, dict] = {}

_MACHINES["Hopper B"] = {
    "above": [
        r" \======/ ",
        r" |\    /| ",
        r" | \__/ | ",
    ],
    "belt": r"_|______|_",
    "below": r"_|\    /|_",
}

_MACHINES["Press A"] = {
    "above": [
        r"  _=[]=_  ",
        r" |/ [] \| ",
        r" | [==] | ",
    ],
    "belt": r"_|______|_",
    "below": r"_|X====X|_",
}

_MACHINES["Scanner A"] = {
    "above": [
        r"  ______  ",
        r" ||/~~\|| ",
        r" |/    \| ",
    ],
    "belt": r"_|\____/|_",
    "below": r"_||XXXX||_",
}

_MACHINES["Gate A"] = {
    "above": [
        r" |      | ",
        r" |  []  | ",
        r" |      | ",
    ],
    "belt": r"_|______|_",
    "below": r"_|______|_",
}

_MACHINES["Furnace A"] = {
    "above": [
        r"   ^^^^   ",
        r"  |~~~~|  ",
        r"  |    |  ",
    ],
    "belt": r"__|____|__",
    "below": r"__|____|__",
}

# Default machine rotation for wizard steps.
_DEFAULT_ROTATION = ["Hopper B", "Press A", "Scanner A", "Gate A", "Furnace A"]

_W_MACH = 10  # all machines are 10 chars wide

# ── Box constants ───────────────────────────────────────────────────────
_BOX_TOP = " ___ "  # 5 chars
_BOX_BOT = "|___|"  # 5 chars
_W_BOX = 5

# ── Layout constants ────────────────────────────────────────────────────
#
# 6 rows:
#   Row 0-2: machine above lines (3 rows)
#   Row 3:   belt surface
#   Row 4:   belt rollers
#   Row 5:   labels
#
ART_HEIGHT = 6
ART_CHROME = ART_HEIGHT + 1  # callers print a blank line after


# ── Helpers ─────────────────────────────────────────────────────────────


def _build_roller_line(width: int, machine_footprints: list[tuple[int, int]]) -> str:
    """Build the roller line with ``(o)`` rollers.

    Layout:
    - One ``(o)`` hardcoded at each end of the belt (right after / before
      the enclosing ``|``).
    - One ``(o)`` on each side of every machine, placed flush against the
      machine footprint (if space allows).

    *machine_footprints* is a list of ``(left, right_exclusive)`` column
    ranges where machines sit.  Machine ``below`` strings overwrite
    these columns afterwards.
    """
    total = width + 2
    buf = list("|" + "_" * width + "|")

    # Build a set of all columns occupied by machines so we can
    # check that a roller won't overlap one.
    occupied: set[int] = set()
    for ml, mr in machine_footprints:
        occupied.update(range(ml, mr))

    def _put(pos: int) -> None:
        """Place (o) at *pos* if it fits without overlapping anything."""
        if pos < 1 or pos + 2 >= total - 1:
            return
        if pos in occupied or pos + 1 in occupied or pos + 2 in occupied:
            return
        buf[pos] = "("
        buf[pos + 1] = "o"
        buf[pos + 2] = ")"
        occupied.update((pos, pos + 1, pos + 2))

    # Hardcoded rollers at belt start and end.
    _put(1)  # right after opening |
    _put(total - 4)  # right before closing |

    # One roller on each side of every machine.
    for ml, mr in sorted(machine_footprints):
        _put(ml - 3)  # just left of the machine
        _put(mr)  # just right of the machine

    return "".join(buf)


def _place(buf: list[str], text: str, pos: int) -> None:
    """Place characters onto a buffer, clipping at boundaries."""
    for i, ch in enumerate(text):
        p = pos + i
        if 0 <= p < len(buf):
            buf[p] = ch


def _machine_for_step(step_index: int) -> dict:
    """Return the machine dict for a given step index."""
    name = _DEFAULT_ROTATION[step_index % len(_DEFAULT_ROTATION)]
    return _MACHINES[name]


# ── Scene renderer ──────────────────────────────────────────────────────


def _render_scene(
    step_idx: int,
    step_titles: list[str],
    *,
    all_done: bool = False,
) -> Text:
    """Compose the conveyor scene into a styled Rich ``Text``."""
    track_w = min(term_width() - 4, 76)
    n = len(step_titles)

    # Evenly-spaced machine positions (centre of each machine).
    spacing = track_w // (n + 1)
    positions = [spacing * (i + 1) for i in range(n)]

    machines = [_machine_for_step(i) for i in range(n)]

    # Total buffer width: track_w + 2 (enclosing | on roller line)
    total = track_w + 2

    # ── Free box position (to the left of the active machine) ───────
    box_x: int | None = None
    if not all_done and 0 <= step_idx < n:
        mach_left = positions[step_idx] - _W_MACH // 2 + 1
        box_x = mach_left - _W_BOX - 1  # 1-char gap
        if box_x < 1:
            box_x = 1

    # ── Build a per-column owner map ────────────────────────────────
    # Each column is tagged with a state for styling:
    #   "done"    — left of the active step (completed machines + belt)
    #   "active"  — the active machine + the free box
    #   "pending" — right of the active step
    #   None      — unowned (spaces, or infrastructure when all_done)
    col_owner: list[str | None] = [None] * total

    for i, pos in enumerate(positions):
        mach_left = pos - _W_MACH // 2 + 1
        tag: str
        if all_done or i < step_idx:
            tag = "done"
        elif i == step_idx:
            tag = "active"
        else:
            tag = "pending"
        for c in range(mach_left, mach_left + _W_MACH):
            if 0 <= c < total:
                col_owner[c] = tag

    # Tag the free box columns + gap to active machine as active.
    if box_x is not None:
        active_right = positions[step_idx] - _W_MACH // 2 + 1 + _W_MACH
        for c in range(box_x, active_right):
            if 0 <= c < total:
                col_owner[c] = "active"

    # Tag belt infrastructure between machines.
    # Everything left of the box/active zone is "done",
    # everything right of the active machine is "pending".
    if not all_done and 0 <= step_idx < n:
        active_left = positions[step_idx] - _W_MACH // 2 + 1
        done_boundary = box_x if box_x is not None else active_left
        for c in range(total):
            if col_owner[c] is None:
                if c < done_boundary:
                    col_owner[c] = "done"
                else:
                    col_owner[c] = "pending"
    elif all_done:
        for c in range(total):
            if col_owner[c] is None:
                col_owner[c] = "done"

    _STYLE_MAP = {
        "done": "bright_blue",
        "active": "bold bright_cyan",
        "pending": "dim",
        None: "dim",
    }

    # ── Build character rows ────────────────────────────────────────
    # Rows 0-2: machine "above" art + free box top on row 2
    above_rows: list[list[str]] = []
    for r in range(3):
        buf = list(" " * total)
        for i, (mach, pos) in enumerate(zip(machines, positions)):
            if r < len(mach["above"]):
                _place(buf, mach["above"][r], pos - _W_MACH // 2 + 1)
        if r == 2 and box_x is not None:
            _place(buf, _BOX_TOP, box_x)
        above_rows.append(buf)

    # Row 3: belt surface + free box body
    surface = list(" " + "_" * track_w + " ")
    if box_x is not None:
        _place(surface, _BOX_BOT, box_x)
    for i, (mach, pos) in enumerate(zip(machines, positions)):
        _place(surface, mach["belt"], pos - _W_MACH // 2 + 1)

    # Row 4: roller line with (o) in gaps, then machine legs stamped over
    mach_footprints = []
    for pos in positions:
        left = pos - _W_MACH // 2 + 1
        mach_footprints.append((left, left + _W_MACH))
    rollers = list(_build_roller_line(track_w, mach_footprints))
    for i, (mach, pos) in enumerate(zip(machines, positions)):
        if "below" in mach:
            _place(rollers, mach["below"], pos - _W_MACH // 2 + 1)

    # Row 5: labels
    lbl = list(" " * total)
    for i, (pos, title) in enumerate(zip(positions, step_titles)):
        lx = pos - len(title) // 2 + 1
        for ci, ch in enumerate(title):
            x = lx + ci
            if 0 <= x < total:
                lbl[x] = ch

    rows_raw = [
        "".join(above_rows[0]),
        "".join(above_rows[1]),
        "".join(above_rows[2]),
        "".join(surface),
        "".join(rollers),
        "".join(lbl),
    ]

    # ── Styled Rich Text ────────────────────────────────────────────
    result = Text()
    for ri, row in enumerate(rows_raw):
        if ri > 0:
            result.append("\n")
        result.append("  ")  # left margin

        if ri == 5:
            # Labels row — lookup by label span, not column map.
            for ci, ch in enumerate(row):
                if ch == " ":
                    result.append(ch)
                    continue
                style = "dim"
                for si, (sp, title) in enumerate(zip(positions, step_titles)):
                    lx = sp - len(title) // 2 + 1
                    rx = lx + len(title)
                    if lx <= ci < rx:
                        if all_done or si < step_idx:
                            style = "bright_blue"
                        elif si == step_idx:
                            style = "bold bright_cyan"
                        break
                result.append(ch, style=style)
        else:
            # All other rows: use the per-column owner map.
            for ci, ch in enumerate(row):
                if ch == " ":
                    result.append(ch)
                    continue
                result.append(ch, style=_STYLE_MAP[col_owner[ci]])

    return result


# ── Public API ──────────────────────────────────────────────────────────


def build_progress(
    step_idx: int,
    step_titles: list[str],
    *,
    content_lines: int = 0,
) -> Text:
    """Build the conveyor-belt progress art.

    Falls back to a compact inline progress bar when the terminal is
    too small for the full art.
    """
    if should_use_compact(ART_CHROME, content_lines):
        return build_compact(step_idx, step_titles)
    return _render_scene(step_idx, step_titles)


def build_progress_complete(
    step_titles: list[str],
    *,
    content_lines: int = 0,
) -> Text:
    """Build the conveyor art with every machine showing as complete."""
    if should_use_compact(ART_CHROME, content_lines):
        return build_compact(len(step_titles), step_titles)
    return _render_scene(len(step_titles), step_titles, all_done=True)
