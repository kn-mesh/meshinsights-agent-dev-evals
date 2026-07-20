"""Safe filesystem helpers for immutable evaluation evidence."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import tempfile
from typing import Any


def normalize_filename_token(value: str | None) -> str:
    """Normalize a value into a non-empty filesystem-safe token."""
    token = (value or "default").strip().replace("/", "_")
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", token).strip("._-")
    return token or "default"


def build_results_dir_for_pipeline(*, base_results_dir: Path, yaml_path: Path) -> Path:
    """Return the output directory scoped to one pipeline filename."""
    pipeline_token = normalize_filename_token(yaml_path.stem)
    return base_results_dir.parent / f"{base_results_dir.name}_{pipeline_token}"


def write_json_exclusive(output_path: Path, payload: dict[str, Any]) -> Path:
    """Atomically write JSON evidence without overwriting an existing result."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(encoded)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        collision_index = 0
        while True:
            candidate = (
                output_path
                if collision_index == 0
                else output_path.with_stem(f"{output_path.stem}_{collision_index}")
            )
            try:
                os.link(temporary_path, candidate)
                return candidate
            except FileExistsError:
                collision_index += 1
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
