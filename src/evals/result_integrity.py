"""Integrity checks for materialized schema-v3 evaluation results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.evals.run_store import LocalRunStore, RunStoreIntegrityError


class ResultIntegrityError(ValueError):
    """A materialized result contradicts its immutable run manifest."""


def load_verified_result(path: Path) -> dict[str, Any]:
    """Load a result through the run store's canonical integrity boundary."""
    path = path.resolve()
    if path.name != "result.json":
        raise ResultIntegrityError(
            f"Evaluation result must use the canonical result.json path: {path}"
        )
    store = LocalRunStore(path.parent, run_id=path.parent.name)
    try:
        return store.read_verified_result()
    except (OSError, ValueError, RunStoreIntegrityError) as error:
        raise ResultIntegrityError(
            f"Evaluation result failed durable-store verification: {path}: {error}"
        ) from error
