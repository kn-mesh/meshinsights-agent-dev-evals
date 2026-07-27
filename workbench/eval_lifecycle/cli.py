"""Manage working and retained evals without quarantine or recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from workbench.eval_lifecycle.service import EvalLifecycleError, EvalLifecycleService
from workbench.evals.run_specs import repository_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--eval-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    listing = commands.add_parser("list")
    listing.add_argument("--state", choices=("all", "working", "retained"), default="all")
    listing.add_argument("--json", action="store_true")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("entity_id")
    inspect.add_argument("--json", action="store_true")

    elevate = commands.add_parser("elevate")
    elevate.add_argument("run_id")
    mode = elevate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")
    elevate.add_argument("--json", action="store_true")

    verify = commands.add_parser("verify")
    verify.add_argument("retained_eval_id")
    verify.add_argument("--json", action="store_true")

    delete = commands.add_parser("delete")
    delete.add_argument("state", choices=("working", "retained"))
    delete.add_argument("entity_id")
    delete.add_argument("--yes", action="store_true")
    delete.add_argument("--confirm-retained")
    delete.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = repository_root(args.project_root or Path.cwd())
    service = EvalLifecycleService(root, eval_root=args.eval_root)
    try:
        payload: Any
        if args.command == "list":
            payload = {
                "state": args.state,
                "evals": service.list_evals(args.state),
            }
        elif args.command == "inspect":
            payload = service.inspect(args.entity_id)
        elif args.command == "elevate":
            payload = (
                service.preview_elevation(args.run_id)
                if args.dry_run
                else service.elevate(args.run_id, confirmed=args.yes)
            )
        elif args.command == "verify":
            payload = service.verify(args.retained_eval_id)
        elif args.state == "working":
            if args.confirm_retained is not None:
                parser.error("--confirm-retained applies only to retained deletion.")
            payload = service.delete_working(args.entity_id, confirmed=args.yes)
        else:
            if args.yes:
                parser.error(
                    "Retained deletion uses --confirm-retained with the exact ID, "
                    "not --yes."
                )
            payload = service.delete_retained(
                args.entity_id, confirmation=args.confirm_retained
            )
    except (OSError, ValueError, EvalLifecycleError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(
        json.dumps(payload, indent=2, ensure_ascii=False)
        if getattr(args, "json", False)
        else _human(payload)
    )
    return 0


def _human(payload: Any) -> str:
    if isinstance(payload, dict) and "evals" in payload:
        counts = {
            state: sum(item["lifecycle_state"] == state for item in payload["evals"])
            for state in ("working", "retained")
        }
        return f"working: {counts['working']}; retained: {counts['retained']}"
    if isinstance(payload, dict):
        return json.dumps(payload, indent=2, ensure_ascii=False)
    return str(payload)


if __name__ == "__main__":
    raise SystemExit(main())
