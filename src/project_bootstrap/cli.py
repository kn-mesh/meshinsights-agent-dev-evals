"""Initialize and validate use-case Agent Workbench repositories."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.project_bootstrap.service import (
    DEFAULT_TEMPLATE_SOURCE,
    initialize_project,
    validate_project,
)


def _parser() -> argparse.ArgumentParser:
    """Build the stable non-interactive bootstrap command surface."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("destination", type=Path)
    init.add_argument("--spec", type=Path, required=True)
    init.add_argument("--template-source", default=DEFAULT_TEMPLATE_SOURCE)
    init.add_argument("--template-ref")
    init.add_argument("--template-revision")
    init.add_argument("--no-git", action="store_true")

    validate = commands.add_parser("validate")
    validate.add_argument("project", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute one bootstrap command and emit human or JSON output."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        payload: dict[str, Any]
        if args.command == "init":
            payload = initialize_project(
                args.destination,
                spec_path=args.spec,
                template_source=args.template_source,
                template_ref=args.template_ref,
                template_revision=args.template_revision,
                initialize_git=not args.no_git,
            )
        else:
            payload = validate_project(args.project)
    except (OSError, ValueError, ValidationError) as error:
        parser.error(str(error))
    print(json.dumps(payload, indent=2) if args.json else _human(payload))
    return 0


def _human(payload: dict[str, Any]) -> str:
    """Render a compact operator-oriented success message."""
    location = payload.get("destination") or payload.get("project_root")
    return f"{payload['status']}: {payload['project_key']} at {location}"


if __name__ == "__main__":
    raise SystemExit(main())
