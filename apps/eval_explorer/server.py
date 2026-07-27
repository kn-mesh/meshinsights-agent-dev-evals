"""Compose the reusable eval explorer with the project evidence adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workbench.apps.eval_explorer import build_app, serve_app
from use_case.evidence import create_project_evidence_adapter


def build_project_app(*, project_root: Path | None = None) -> Any:
    """Build the fixed project explorer composition."""
    return build_app(
        project_root=project_root,
        evidence_adapter_factory=create_project_evidence_adapter,
    )


app = build_project_app()


def main(argv: list[str] | None = None) -> None:
    """Serve the project-composed local explorer."""
    serve_app(app, argv)


if __name__ == "__main__":
    main()
