"""Composable wizard runner — WizardRunner, WizardSection, and field data classes."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from rich.console import Console
from rich.text import Text

from .display import (
    CompletedEntry,
    count_entry_lines,
    print_failure,
    print_steps,
    print_success,
)
from .picker import multiselect as pick_multi, select as pick_one
from .prompts import GLYPH_CROSS, ask_confirm, ask_text, spinner
from .terminal import (
    clear_screen,
    enter_alt_screen,
    leave_alt_screen,
    term_height,
)
from .theme import get_console

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wizard field / step data classes
# ---------------------------------------------------------------------------


class FieldKind(str, Enum):
    """The type of input a wizard field presents."""

    TEXT = "text"
    SELECT = "select"
    MULTISELECT = "multiselect"
    CONFIRM = "confirm"


@dataclass
class WizardField:
    """A single prompt in the wizard."""

    name: str
    label: str
    kind: FieldKind = FieldKind.TEXT
    placeholder: str = ""
    choices: list[str] | None = None
    default: str | None = None
    defaults: list[str] | None = None  # for multiselect
    forced: list[str] | None = None  # multiselect: always-on, can't deselect
    disabled: list[str] | None = None  # multiselect: greyed-out, can't select
    required: bool = False


@dataclass
class WizardStep:
    """A group of related prompts shown together."""

    title: str
    description: str = ""
    fields: list[WizardField] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Visual theme
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisualTheme:
    """Swappable ASCII-art progress theme."""

    build_progress: Callable[..., Text]
    build_progress_complete: Callable[..., Text]
    art_chrome: int


# ---------------------------------------------------------------------------
# Section context — the section's interface to the runner
# ---------------------------------------------------------------------------


@dataclass
class SectionContext:
    """Passed to each section's run() — provides drawing and prompt access."""

    console: Console
    breadcrumbs: list[tuple[str, str]]  # (label, value) pairs; mutate in-place
    state: dict[str, Any]  # shared across sections + on_execute

    _runner: WizardRunner
    _section_index: int

    def redraw(self, prompt_overhead: int = 4) -> None:
        """Clear and redraw: art → completed entries → breadcrumbs."""
        self._runner._redraw(
            section_index=self._section_index,
            breadcrumbs=self.breadcrumbs,
            prompt_overhead=prompt_overhead,
        )

    def picker_height(self) -> int:
        """Remaining picker item slots on the current screen."""
        return self._runner._picker_height(
            breadcrumb_count=len(self.breadcrumbs),
        )

    def leave_alt_screen(self) -> None:
        """Temporarily leave alt-screen (for interactive subprocesses)."""
        leave_alt_screen()

    def enter_alt_screen(self) -> None:
        """Re-enter alt-screen after leave_alt_screen()."""
        enter_alt_screen()

    def add_sections(self, *sections: WizardSection) -> None:
        """Insert sections immediately after the current one."""
        self._runner._insert_sections(
            sections,
            after=self._section_index,
        )

    @property
    def completed(self) -> list[CompletedEntry]:
        """Completed entries so far (read-only copy)."""
        return list(self._runner._completed)


# ---------------------------------------------------------------------------
# Wizard section
# ---------------------------------------------------------------------------


@dataclass
class WizardSection:
    """A composable wizard section. run() returns CompletedEntry or None to skip."""

    title: str
    run: Callable[[SectionContext], CompletedEntry | None]


# ---------------------------------------------------------------------------
# Wizard runner
# ---------------------------------------------------------------------------


class WizardRunner:
    """Orchestrates the full alt-screen wizard lifecycle."""

    def __init__(
        self,
        *,
        theme: VisualTheme,
        sections: list[WizardSection],
        phase_titles: list[str] | None = None,
        review_prompt: str = "Continue?",
        on_execute: Callable[[list[CompletedEntry], dict[str, Any]], Any] | None = None,
        execute_animation: Callable[..., None] | None = None,
        execute_message: str = "Working...",
        summary: Callable[[Console, list[CompletedEntry], dict[str, Any]], None]
        | None = None,
    ) -> None:
        self._theme = theme
        self._sections: list[WizardSection] = list(sections)
        self._phase_titles = phase_titles
        self._review_prompt = review_prompt
        self._on_execute = on_execute
        self._execute_animation = execute_animation
        self._execute_message = execute_message
        self._summary = summary

        # Mutable runtime state
        self._completed: list[CompletedEntry] = []
        self._state: dict[str, Any] = {}
        self._current_index: int = 0

    # -- Public API ----------------------------------------------------

    @property
    def phase_titles(self) -> list[str]:
        """Phase names shown in the progress art."""
        return self._phase_titles or [s.title for s in self._sections]

    def add_sections(
        self,
        *sections: WizardSection,
        after: int | None = None,
    ) -> None:
        """Insert sections after *after* (default: current section)."""
        self._insert_sections(sections, after=after)

    def run(self, console: Console | None = None) -> int:
        """Run the wizard. Returns an exit code."""
        con = console or get_console()

        enter_alt_screen()
        try:
            return self._run_inner(con)
        except KeyboardInterrupt:
            leave_alt_screen()
            con.print()
            print_failure(con, "Aborted.")
            con.print()
            return 130
        except Exception:
            leave_alt_screen()
            raise

    # -- Internal: section iteration -----------------------------------

    def _run_inner(self, console: Console) -> int:
        # Phase 1 — Collect answers from each section
        self._current_index = 0
        while self._current_index < len(self._sections):
            section = self._sections[self._current_index]
            ctx = SectionContext(
                console=console,
                breadcrumbs=[],
                state=self._state,
                _runner=self,
                _section_index=self._current_index,
            )
            entry = section.run(ctx)
            if entry is not None:
                self._completed.append(entry)
            self._current_index += 1

        # Phase 2 — Review screen
        if self._completed:
            self._draw_review(console)
            ok = ask_confirm(
                self._review_prompt,
                default=True,
                console=console,
            )
            if not ok:
                leave_alt_screen()
                console.print()
                print_failure(console, "Aborted.")
                console.print()
                return 130

        # Phase 3 — Execute
        if self._on_execute is not None:
            exec_error = self._run_execute(console)
            if exec_error is not None:
                return exec_error

        # Phase 4 — Summary (in normal terminal)
        if self._summary is not None:
            self._summary(console, self._completed, self._state)
        else:
            self._default_summary(console)

        return 0

    def _run_execute(self, console: Console) -> int | None:
        """Run the execute phase.  Returns an error exit code, or None."""
        assert self._on_execute is not None

        if self._execute_animation is not None:
            # Animation mode: leave alt-screen, run work + animation
            # concurrently.  The animation loops until *done* is set.
            leave_alt_screen()
            exec_error: BaseException | None = None
            done = threading.Event()

            def _do_work() -> None:
                nonlocal exec_error
                try:
                    self._on_execute(self._completed, self._state)  # type: ignore[misc]
                except BaseException as exc:
                    exec_error = exc
                finally:
                    done.set()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(_do_work)
                self._execute_animation(console=console, done=done)

            if exec_error is not None:
                if isinstance(exec_error, KeyboardInterrupt):
                    console.print(
                        f"\n  [bright_red]{GLYPH_CROSS}[/] [bold red]Aborted.[/]"
                    )
                    return 130
                if isinstance(exec_error, RuntimeError):
                    console.print(f"  [error]{exec_error}[/error]")
                    return 1
                raise exec_error
        else:
            # Spinner mode: stay in alt-screen, show spinner.
            _exec = self._on_execute
            _completed = self._completed
            _state = self._state
            spinner(
                self._execute_message,
                work=lambda: _exec(_completed, _state),
                console=console,
            )
            leave_alt_screen()

        return None

    # -- Internal: drawing helpers -------------------------------------

    def _step_index_for_section(self, section_index: int) -> int:
        """Map a section index to a phase/step index for the art."""
        titles = self.phase_titles
        section = self._sections[section_index]

        # Exact title match first
        for i, t in enumerate(titles):
            if t == section.title:
                return i

        # Sections whose title doesn't match a phase belong to the
        # last non-review phase (typically "Configure").
        # Heuristic: everything past the first phase and before the
        # last phase is the "middle" phase.
        if len(titles) >= 2:
            return min(section_index, len(titles) - 2)
        return min(section_index, len(titles) - 1)

    def _redraw(
        self,
        *,
        section_index: int,
        breadcrumbs: list[tuple[str, str]],
        prompt_overhead: int = 4,
    ) -> None:
        """Clear-and-redraw the wizard screen."""
        from .display import field_line

        console = get_console()
        clear_screen()

        step_idx = self._step_index_for_section(section_index)
        titles = self.phase_titles

        # Estimate content below the art
        below = count_entry_lines(self._completed)
        below += 1  # current section header
        below += len(breadcrumbs)
        below += prompt_overhead

        art = self._theme.build_progress(step_idx, titles, content_lines=below)
        console.print(art, highlight=False)
        console.print()

        # Completed entries
        if self._completed:
            print_steps(console, self._completed)

        # Current section header
        section = self._sections[section_index]
        subtitle = self._state.get("_subtitle")
        suffix = f"  [dim]{subtitle}[/]" if subtitle else ""
        console.print(
            f"  [bold bright_blue]{section.title}[/]{suffix}",
            highlight=False,
        )

        # Breadcrumbs
        if breadcrumbs:
            for label, value in breadcrumbs:
                field_line(console, label, value)

    def _draw_review(self, console: Console) -> None:
        """Render the review screen: completed art + all entries."""
        clear_screen()
        titles = self.phase_titles
        below = count_entry_lines(self._completed) + 2  # confirm overhead
        art = self._theme.build_progress_complete(titles, content_lines=below)
        console.print(art, highlight=False)
        console.print()
        print_steps(console, self._completed)

    def _picker_height(self, breadcrumb_count: int = 0) -> int:
        """Estimate remaining picker height."""
        _PICKER_CHROME = 4
        used = self._theme.art_chrome + 1 + _PICKER_CHROME
        used += count_entry_lines(self._completed)
        used += breadcrumb_count
        available = term_height() - used
        if available >= 12:
            return 0  # auto-detect
        return max(0, available)

    def _default_summary(self, console: Console) -> None:
        """Print a default post-wizard summary."""
        console.print()
        print_steps(console, self._completed)
        failed = [title for status, title, _ in self._completed if status == "fail"]
        if not failed:
            print_success(console, "All steps completed successfully!")
        else:
            print_failure(console, f"Failed: {', '.join(failed)}")
        console.print()

    # -- Internal: dynamic section management --------------------------

    def _insert_sections(
        self,
        sections: tuple[WizardSection, ...] | list[WizardSection],
        after: int | None = None,
    ) -> None:
        """Insert sections after *after* index (default: current)."""
        insert_at = (after if after is not None else self._current_index) + 1
        for i, section in enumerate(sections):
            self._sections.insert(insert_at + i, section)


# ---------------------------------------------------------------------------
# Convenience: static field section
# ---------------------------------------------------------------------------


def fields_section(title: str, fields: list[WizardField]) -> WizardSection:
    """Build a WizardSection from declarative WizardField definitions."""

    def _run(ctx: SectionContext) -> CompletedEntry:
        for f in fields:
            ctx.redraw()
            console = ctx.console
            value: str = ""

            if f.kind == FieldKind.TEXT:
                value = ask_text(
                    f.label,
                    placeholder=f.placeholder,
                    default=f.default,
                    required=f.required,
                    console=console,
                )

            elif f.kind == FieldKind.SELECT:
                value = pick_one(
                    f.label,
                    f.choices or [],
                    default=f.default,
                    max_visible=ctx.picker_height(),
                    console=console,
                )

            elif f.kind == FieldKind.MULTISELECT:
                picks = pick_multi(
                    f.label,
                    f.choices or [],
                    defaults=f.defaults,
                    forced=f.forced,
                    disabled=f.disabled,
                    max_visible=ctx.picker_height(),
                    console=console,
                )
                value = ", ".join(picks)

            elif f.kind == FieldKind.CONFIRM:
                default_bool = (
                    f.default in ("true", "True", "yes", "1") if f.default else False
                )
                value = str(ask_confirm(f.label, default=default_bool, console=console))

            ctx.breadcrumbs.append((f.label, value))
            # Also store in shared state keyed by field name for easy
            # retrieval by on_execute / summary callbacks.
            ctx.state[f.name] = value

        return ("done", title, list(ctx.breadcrumbs))

    return WizardSection(title=title, run=_run)


# ---------------------------------------------------------------------------
# Pre-built themes (at module level to avoid circular imports)
# ---------------------------------------------------------------------------


def _make_factory_theme() -> VisualTheme:
    from .visuals.factory import (
        ART_CHROME,
        build_progress,
        build_progress_complete,
    )

    return VisualTheme(
        build_progress=build_progress,
        build_progress_complete=build_progress_complete,
        art_chrome=ART_CHROME,
    )


def _make_conveyor_theme() -> VisualTheme:
    from .visuals.conveyor import (
        ART_CHROME,
        build_progress,
        build_progress_complete,
    )

    return VisualTheme(
        build_progress=build_progress,
        build_progress_complete=build_progress_complete,
        art_chrome=ART_CHROME,
    )


# Eagerly constructed themes.  The deferred imports inside the
# factory functions prevent circular-import issues while still
# letting callers do ``from cli.ui.runner import FACTORY_THEME``.
FACTORY_THEME: VisualTheme = _make_factory_theme()
CONVEYOR_THEME: VisualTheme = _make_conveyor_theme()
