"""Publish one verified retained eval to the dedicated Azure results container."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from azure.core.exceptions import AzureError

from workbench.eval_publication import EvalPublicationError, EvalPublicationService
from workbench.evals.run_specs import repository_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--eval-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    publish = commands.add_parser("publish")
    publish.add_argument("retained_eval_id")
    mode = publish.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")
    publish.add_argument("--account-url")
    publish.add_argument("--container")
    publish.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = repository_root(args.project_root or Path.cwd())
    service = EvalPublicationService(
        root,
        eval_root=args.eval_root,
        account_url=args.account_url,
        container=args.container,
    )
    try:
        payload = (
            service.dry_run(args.retained_eval_id)
            if args.dry_run
            else service.publish(args.retained_eval_id, confirmed=args.yes)
        )
    except (
        OSError,
        ValueError,
        AzureError,
        EvalPublicationError,
        json.JSONDecodeError,
    ) as error:
        parser.error(str(error))
    print(
        json.dumps(payload, indent=2, ensure_ascii=False)
        if args.json
        else _human(payload)
    )
    return 0


def _human(payload: dict[str, Any]) -> str:
    if payload["dry_run"]:
        return (
            f"publishable: {payload['retained_eval_id']}; no publication ID allocated"
        )
    return (
        f"published {payload['retained_eval_id']} as "
        f"{payload['publication_id']} at {payload['prefix']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
