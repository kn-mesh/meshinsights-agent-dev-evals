"""Canonical identities for reproducible evaluation execution."""

from __future__ import annotations

import hashlib
import json
import secrets
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
    """Return the legacy schema-v1 deterministic run identity."""
    digest = canonical_sha256(run_spec)
    return f"eval_{digest[:24]}", digest


def build_eval_run_identity(
    *,
    run_spec_sha256: str,
    created_at_utc: str,
    nonce: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return one unique eval occurrence ID and its complete canonical seed."""
    if len(run_spec_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in run_spec_sha256
    ):
        raise ValueError("run_spec_sha256 must be a lowercase SHA-256 digest.")
    if not created_at_utc.strip():
        raise ValueError("created_at_utc must not be empty.")
    resolved_nonce = nonce or secrets.token_hex(32)
    if not resolved_nonce.strip():
        raise ValueError("nonce must not be empty.")
    seed = {
        "schema_version": 1,
        "created_at_utc": created_at_utc,
        "nonce": resolved_nonce,
        "run_spec_sha256": run_spec_sha256,
    }
    digest = canonical_sha256(seed)
    return f"eval_{digest[:24]}", seed


def verify_eval_run_identity(
    eval_run_id: str,
    *,
    occurrence_seed: dict[str, Any],
    run_spec_sha256: str,
) -> bool:
    """Return whether an occurrence seed binds the run ID and specification."""
    if occurrence_seed.get("schema_version") != 1:
        return False
    if occurrence_seed.get("run_spec_sha256") != run_spec_sha256:
        return False
    return eval_run_id == f"eval_{canonical_sha256(occurrence_seed)[:24]}"


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
