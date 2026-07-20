"""Small terminal prompt helpers owned by the benchmark evaluator."""

from __future__ import annotations

from collections.abc import Sequence


def normalize_ai_reasoning_effort(value: str | None) -> str | None:
    """Normalize an optional model reasoning override."""
    if value is None:
        return None
    normalized = value.strip().lower()
    return None if not normalized or normalized == "default" else normalized


def prompt_select_option(prompt: str, options: Sequence[str]) -> str:
    """Prompt for one displayed option by number."""
    if not options:
        raise ValueError(f"No options available for prompt: {prompt}")
    print(f"\n{prompt}")
    for index, option in enumerate(options, 1):
        print(f"  {index}. {option}")
    while True:
        raw = input("Select option number: ").strip()
        if raw.isdigit() and 0 <= int(raw) - 1 < len(options):
            return options[int(raw) - 1]
        print(f"Please enter a number between 1 and {len(options)}.")


def prompt_positive_int(prompt: str, *, default: int) -> int:
    """Prompt for a positive integer with an empty-input default."""
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        print("Please enter a positive integer.")
