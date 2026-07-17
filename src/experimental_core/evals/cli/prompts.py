"""Generic interactive prompt primitives for terminal eval wizards."""

from __future__ import annotations

from collections.abc import Sequence


def prompt_select_option(prompt: str, options: Sequence[str]) -> str:
    """Prompt the user to choose one option by its displayed number."""
    if not options:
        raise ValueError(f"No options available for prompt: {prompt}")

    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {option}")

    while True:
        raw = input("Select option number: ").strip()
        if raw.isdigit():
            index = int(raw) - 1
            if 0 <= index < len(options):
                return options[index]
        print(f"Please enter a number between 1 and {len(options)}.")


def prompt_positive_int(prompt: str, *, default: int) -> int:
    """Prompt for a positive integer, accepting the default on empty input."""
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive integer.")


def prompt_optional_csv(prompt: str) -> list[str] | None:
    """Prompt for comma-separated values and return parsed non-empty entries."""
    raw = input(prompt).strip()
    if not raw:
        return None
    parsed = [token.strip() for token in raw.split(",") if token.strip()]
    return parsed or None


def prompt_free_text(prompt: str, *, default: str | None = None) -> str | None:
    """Prompt for free-form text, returning the default on empty input."""
    suffix = f" [{default}]" if default is not None else ""
    raw = input(f"{prompt}{suffix}: ").strip()
    if not raw:
        return default
    return raw
