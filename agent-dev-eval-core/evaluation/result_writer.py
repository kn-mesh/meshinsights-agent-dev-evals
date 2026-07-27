"""Safe filesystem helpers for immutable evaluation evidence."""

from __future__ import annotations

import re


def normalize_filename_token(value: str | None) -> str:
    """Normalize a value into a non-empty filesystem-safe token."""
    token = (value or "default").strip().replace("/", "_")
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", token).strip("._-")
    return token or "default"
