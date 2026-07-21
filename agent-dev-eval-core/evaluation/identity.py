"""Canonical identities for reproducible evaluation execution."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_bytes(payload: object) -> bytes:
    """Encode JSON-compatible data with one stable representation."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(payload: object) -> str:
    """Return the SHA-256 of canonical JSON-compatible data."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_run_identity(run_spec: dict[str, Any]) -> tuple[str, str]:
    """Return the short run id and complete canonical specification hash."""
    digest = canonical_sha256(run_spec)
    return f"eval_{digest[:24]}", digest


def build_comparison_identity(comparison_spec: dict[str, Any]) -> tuple[str, str]:
    """Return the short comparison id and complete specification hash."""
    digest = canonical_sha256(comparison_spec)
    return f"cmp_{digest[:24]}", digest


def build_work_item_id(*, run_id: str, item_id: str, attempt_index: int) -> str:
    """Return the stable identity for one logical repetition slot."""
    if not run_id.strip() or not item_id.strip():
        raise ValueError("Run and item ids must not be empty.")
    if attempt_index < 1:
        raise ValueError("attempt_index must be at least 1.")
    payload = f"{run_id}\n{item_id}\n{attempt_index}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
