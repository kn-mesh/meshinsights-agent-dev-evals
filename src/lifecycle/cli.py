"""Inspect and manage the local Agent Workbench lifecycle catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.evals.run_specs import repository_root
from src.lifecycle.models import EntityKind
from src.lifecycle.store import LifecycleError, LocalLifecycleStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--eval-root", type=Path)
    parser.add_argument("--agent-root", type=Path)
    parser.add_argument("--lifecycle-root", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("catalog", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true")

    inspect = commands.add_parser("inspect")
    inspect.add_argument("kind", choices=("run", "version", "comparison"))
    inspect.add_argument("entity_id")
    inspect.add_argument("--json", action="store_true")

    delete = commands.add_parser("delete")
    delete.add_argument("kind", choices=("run", "version", "comparison"))
    delete.add_argument("entity_id")
    mode = delete.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--yes", action="store_true")
    delete.add_argument("--json", action="store_true")

    for name in ("restore", "purge"):
        command = commands.add_parser(name)
        command.add_argument("operation_id")
        mode = command.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--yes", action="store_true")
        command.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    root = repository_root(args.project_root or Path.cwd())
    store = LocalLifecycleStore(
        root,
        eval_root=args.eval_root,
        agent_root=args.agent_root,
        lifecycle_root=args.lifecycle_root,
    )
    try:
        payload: Any
        if args.command in {"catalog", "verify"}:
            catalog = store.catalog()
            payload = catalog.model_dump(mode="json")
            if args.command == "verify":
                payload = {
                    "verified": not catalog.findings,
                    "finding_count": len(catalog.findings),
                    **payload,
                }
        elif args.command == "inspect":
            payload = _inspect(store, args.kind, args.entity_id)
        elif args.command == "delete":
            kind: EntityKind = args.kind
            if args.dry_run:
                payload = {
                    "dry_run": True,
                    **store.plan_delete(kind, args.entity_id).model_dump(mode="json"),
                }
            else:
                payload = store.quarantine(
                    kind, args.entity_id, confirmed=args.yes
                ).model_dump(mode="json")
        elif args.command in {"restore", "purge"}:
            if args.dry_run:
                payload = store.preview_operation(args.operation_id, args.command)
            elif args.command == "restore":
                payload = store.restore(
                    args.operation_id, confirmed=args.yes
                ).model_dump(mode="json")
            else:
                payload = store.purge(args.operation_id, confirmed=args.yes).model_dump(
                    mode="json"
                )
        else:  # pragma: no cover
            raise LifecycleError(f"Unsupported command: {args.command}")
    except (OSError, ValueError, LifecycleError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(
        json.dumps(payload, indent=2, ensure_ascii=False)
        if args.json
        else _human(args.command, payload)
    )
    if args.command == "verify" and not payload["verified"]:
        return 2
    return 0


def _inspect(
    store: LocalLifecycleStore, kind: EntityKind, entity_id: str
) -> dict[str, Any]:
    catalog = store.catalog()
    collection = {
        "run": catalog.runs,
        "version": catalog.versions,
        "comparison": catalog.comparisons,
    }[kind]
    id_field = {
        "run": "run_id",
        "version": "agent_version_id",
        "comparison": "comparison_id",
    }[kind]
    matches = [item for item in collection if getattr(item, id_field) == entity_id]
    if len(matches) != 1:
        raise LifecycleError(
            f"Expected one managed {kind} {entity_id}; found {len(matches)}."
        )
    references = [
        item.model_dump(mode="json")
        for item in catalog.references
        if (item.source_kind == kind and item.source_id == entity_id)
        or (item.target_kind == kind and item.target_id == entity_id)
    ]
    return {
        "kind": kind,
        "entity": matches[0].model_dump(mode="json"),
        "references": references,
    }


def _human(command: str, payload: dict[str, Any]) -> str:
    if command in {"catalog", "verify"}:
        return (
            f"runs: {len(payload['runs'])}; versions: {len(payload['versions'])}; "
            f"comparisons: {len(payload['comparisons'])}; "
            f"findings: {len(payload['findings'])}"
        )
    if command == "delete" and payload.get("dry_run"):
        return (
            f"delete preview: {payload['target_kind']} {payload['target_id']}; "
            f"{payload['file_count']} files; {payload['bytes']} bytes; "
            f"{len(payload['warnings'])} warnings"
        )
    if "operation_id" in payload:
        return f"{payload['operation_id']}: {payload['state']}"
    return json.dumps(payload, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
