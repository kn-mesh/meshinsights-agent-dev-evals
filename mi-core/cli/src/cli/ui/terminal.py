"""Low-level terminal control: cursor, screen buffers, key reading."""

from __future__ import annotations

import shutil
import sys
import termios
import tty
from enum import Enum

# ── Dimensions ──────────────────────────────────────────────────────────


def term_width() -> int:
    """Return the current terminal width in columns."""
    return shutil.get_terminal_size((80, 24)).columns


def term_height() -> int:
    """Return the current terminal height in rows."""
    return shutil.get_terminal_size((80, 24)).lines


# ── Raw cursor / erase control ──────────────────────────────────────────


def cursor_up(n: int = 1) -> None:
    """Move the cursor up *n* lines (does nothing if n <= 0)."""
    if n > 0:
        sys.stdout.write(f"\033[{n}A")


def cursor_down(n: int = 1) -> None:
    """Move the cursor down *n* lines."""
    if n > 0:
        sys.stdout.write(f"\033[{n}B")


def erase_down() -> None:
    """Erase from the cursor position to the end of the screen."""
    sys.stdout.write("\033[J")


def erase_line() -> None:
    """Erase the entire current line."""
    sys.stdout.write("\033[2K\r")


def flush() -> None:
    """Flush stdout."""
    sys.stdout.flush()


# ── Alternate screen buffer ─────────────────────────────────────────────


def enter_alt_screen() -> None:
    """Switch to the alternate screen buffer."""
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()


def leave_alt_screen() -> None:
    """Return from the alternate screen buffer to the normal one."""
    sys.stdout.write("\033[?1049l")
    sys.stdout.flush()


def clear_screen() -> None:
    """Clear the screen and move cursor to top-left."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


# ── Convenience: hide / show cursor ────────────────────────────────────


def hide_cursor() -> None:
    """Hide the terminal cursor."""
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def show_cursor() -> None:
    """Show the terminal cursor."""
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


# ── Key reading ─────────────────────────────────────────────────────────


class Key(Enum):
    """Recognised key types returned by :func:`read_key`."""

    UP = "up"
    DOWN = "down"
    ENTER = "enter"
    SPACE = "space"
    CHAR = "char"
    CTRL_C = "ctrl_c"
    TAB = "tab"
    UNKNOWN = "unknown"


def read_key() -> tuple[Key, str]:
    """Read a single keypress and return ``(Key, raw_char)``."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)

        if ch == "\x03":
            return Key.CTRL_C, ch
        if ch in ("\r", "\n"):
            return Key.ENTER, ch
        if ch == " ":
            return Key.SPACE, ch
        if ch == "\t":
            return Key.TAB, ch
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return Key.UP, ""
                if ch3 == "B":
                    return Key.DOWN, ""
            return Key.UNKNOWN, ch

        return Key.CHAR, ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
