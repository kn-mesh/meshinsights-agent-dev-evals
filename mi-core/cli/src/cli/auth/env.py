"""``.env`` template discovery, parsing, and in-place writing for ``mi auth``."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_NAMES = (
    ".env.template",
    ".env.example",
    "env.template",
    "env.example",
)


def find_env_template(project_root: Path) -> Path | None:
    """Scan *project_root* for a known env template file.

    Checks, in order: ``.env.template``, ``.env.example``, ``env.template``,
    ``env.example``.  Returns the first match, or ``None``.
    """
    for name in _TEMPLATE_NAMES:
        candidate = project_root / name
        if candidate.is_file():
            logger.debug("Found env template: %s", candidate)
            return candidate
    return None


def parse_env_file(path: Path) -> tuple[list[str], dict[str, str]]:
    """Parse a ``.env`` (or template) file, preserving raw lines.

    Returns:
        A 2-tuple of:
        - **raw_lines**: every line in the file (including comments, blanks).
        - **values**: a ``{KEY: VALUE}`` dict for all ``KEY=VALUE`` lines.
          Values are stripped of surrounding quotes.

    Lines that do not match ``KEY=VALUE`` (comments, blanks, ``export``
    prefixed) are preserved in *raw_lines* but not added to *values*.
    """
    raw_lines: list[str] = []
    values: dict[str, str] = {}

    if not path.is_file():
        return raw_lines, values

    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        raw_lines.append(line)

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Handle optional ``export`` prefix
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]

        key, sep, value = stripped.partition("=")
        if sep != "=":
            continue

        key = key.strip()
        value = value.strip()

        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        values[key] = value

    return raw_lines, values


def extract_template_vars(path: Path) -> set[str]:
    """Return the set of environment variable names defined in a template file."""
    _, values = parse_env_file(path)
    return set(values.keys())


def load_existing_env(
    project_root: Path, env_file: Path | None = None
) -> tuple[list[str], dict[str, str]]:
    """Load the existing ``.env`` file and merge with ``os.environ``.

    Returns:
        A 2-tuple of:
        - **raw_lines**: the raw lines from the ``.env`` file (empty if no
          file exists).
        - **merged**: merged dict with ``os.environ`` values as fallbacks
          (existing ``.env`` values take precedence).
    """
    env_path = env_file or (project_root / ".env")
    raw_lines, file_values = parse_env_file(env_path)

    # Merge: .env values override os.environ
    merged = dict(os.environ)
    merged.update(file_values)

    return raw_lines, merged


def update_env_file(
    project_root: Path,
    updates: dict[str, str],
    raw_lines: list[str] | None = None,
    env_file: Path | None = None,
) -> Path:
    """Write *updates* into the ``.env`` file using in-place editing.

    - Keys already present in the file have their values replaced.
    - New keys are appended at the end.
    - Comments and blank lines are preserved.
    - When the target file does **not** yet exist, the ``.env.template``
      (if found) is copied as the starting scaffold so that comments,
      grouping, and placeholder vars carry over.

    The write is atomic (temp file + rename in the same directory).

    Returns the path to the written ``.env`` file.
    """
    env_path = env_file or (project_root / ".env")

    if raw_lines is None:
        if env_path.is_file():
            raw_lines, _ = parse_env_file(env_path)
        else:
            # New file — seed from the template so we keep its
            # comments, structure, and placeholder variables.
            template = find_env_template(project_root)
            if template:
                logger.debug("Seeding new %s from template %s", env_path, template)
                raw_lines, _ = parse_env_file(template)
            else:
                raw_lines = []

    remaining = dict(updates)
    output_lines: list[str] = []

    for line in raw_lines:
        stripped = line.strip()

        # Try to match a KEY=VALUE line
        effective = stripped
        if effective.startswith("export "):
            effective = effective[len("export ") :]

        key, sep, _ = effective.partition("=")
        if sep == "=" and key.strip() in remaining:
            k = key.strip()
            new_value = remaining.pop(k)
            # Preserve any leading whitespace / ``export`` prefix
            prefix = line[: line.index(k)]
            output_lines.append(f"{prefix}{k}={_quote_value(new_value)}")
        else:
            output_lines.append(line)

    # Append any new keys not already in the file
    if remaining:
        if output_lines and output_lines[-1].strip():
            output_lines.append("")  # blank separator

        for key, value in remaining.items():
            output_lines.append(f"{key}={_quote_value(value)}")

    content = "\n".join(output_lines)
    if not content.endswith("\n"):
        content += "\n"

    # Atomic write
    fd, tmp_path = tempfile.mkstemp(
        dir=env_path.parent,
        prefix=".env.tmp.",
        suffix="",
    )
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp_path, env_path)
    except BaseException:
        os.close(fd) if not os.get_inheritable(fd) else None
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    return env_path


def _quote_value(value: str) -> str:
    """Always wrap values in double quotes for ``.env`` safety."""
    if not value:
        return '""'
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
