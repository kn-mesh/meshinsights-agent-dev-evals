"""Prompt request types for the generator-based auth wizard.

Providers yield these request objects from their ``fetch()`` generators
instead of calling interactive UI functions directly.  The wizard
orchestrator interprets each request, drives the appropriate standalone
UI component, and ``send()``\\s the result back.

Prompt types
~~~~~~~~~~~~
- :class:`SelectPrompt` — single-select list (→ value or ``None``).
- :class:`ConfirmPrompt` — yes / no (→ ``bool``).
- :class:`TextPrompt` — free-form text input (→ ``str``).
- :class:`MessagePrompt` — informational text, no user input (→ ``None``).
- :class:`SubprocessPrompt` — run an external command (→ ``int`` exit code).
- :class:`CheckboxPrompt` — multi-select checkbox (→ ``list[str]``).

A provider generator's type signature is::

    Generator[PromptRequest, Any, dict[str, str]]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass(frozen=True, slots=True)
class SelectChoice:
    """An item in a :class:`SelectPrompt`."""

    label: str
    value: Any = None
    hint: str = ""

    def __post_init__(self) -> None:
        if self.value is None:
            object.__setattr__(self, "value", self.label)


@dataclass(frozen=True, slots=True)
class SelectPrompt:
    """Request a single-select list prompt.

    The orchestrator sends back the selected ``value``, or ``None`` if
    the user cancels.
    """

    message: str
    choices: list[SelectChoice]
    default: Any = None
    max_height: int = 10


@dataclass(frozen=True, slots=True)
class ConfirmPrompt:
    """Request a yes / no confirmation.

    The orchestrator sends back ``True`` (Yes) or ``False`` (No).
    """

    message: str
    default: bool = True


@dataclass(frozen=True, slots=True)
class TextPrompt:
    """Request free-form text input.

    The orchestrator shows a Rich Prompt and sends back the entered string.
    """

    label: str
    default: str = ""
    hint: str = ""
    password: bool = False


@dataclass(frozen=True, slots=True)
class MessagePrompt:
    """Display informational text — no user input required.

    The orchestrator prints the text and sends back ``None``.
    Use ``style`` for Rich markup style names (e.g. ``"info"``,
    ``"warn"``, ``"error"``, ``"hint"``, ``"success"``).
    """

    text: str
    style: str = ""
    indent: bool = True


@dataclass(frozen=True, slots=True)
class SubprocessPrompt:
    """Request execution of an external command.

    The orchestrator runs the command via ``subprocess.run()`` and sends
    back the exit code (``int``).
    """

    cmd: list[str]
    label: str = ""
    capture: bool = False
    cwd: str | None = None


@dataclass(frozen=True, slots=True)
class CheckboxPrompt:
    """Request a multi-select checkbox prompt.

    The orchestrator sends back a list of selected ``value`` strings.
    """

    message: str
    choices: list[CheckboxChoice]
    instruction: str | None = None
    max_height: int = 10


@dataclass(frozen=True, slots=True)
class CheckboxChoice:
    """An item in a :class:`CheckboxPrompt`."""

    label: str
    value: str
    checked: bool = False
    locked: bool = False
    hint: str = ""


# Union of all prompt request types for type annotations.
PromptRequest = Union[
    SelectPrompt,
    ConfirmPrompt,
    TextPrompt,
    MessagePrompt,
    SubprocessPrompt,
    CheckboxPrompt,
]
