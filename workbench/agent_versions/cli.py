"""Non-interactive CLI for resolving, promoting, and inspecting agent versions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from workbench.agent_versions.resolver import resolve_agent_version
from workbench.agent_versions.store import AgentVersionStore, load_run_candidate
from workbench.evals.run_specs import repository_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("resolve", "promote"):
        command = subcommands.add_parser(name)
        command.add_argument("--pipeline", type=Path)
        command.add_argument("--agent-policy", type=Path)
        command.add_argument("--dirty-policy", choices=("reject", "capture"), default="reject")
        if name == "promote":
            command.add_argument("--from-run", type=Path)
            command.add_argument("--alias")
            command.add_argument("--notes")
    inspect = subcommands.add_parser("inspect")
    inspect.add_argument("agent_version")
    verify = subcommands.add_parser("verify")
    verify.add_argument("agent_version")
    verify.add_argument("--mode", choices=("available", "reconstruct"), default="available")
    reconstruct = subcommands.add_parser("reconstruct")
    reconstruct.add_argument("agent_version")
    reconstruct.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--store", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = repository_root(Path.cwd())
    store = AgentVersionStore(args.store or root / ".workbench" / "agent-versions")
    payload: dict[str, Any]
    if args.command == "resolve":
        if args.pipeline is None:
            raise ValueError("resolve requires --pipeline.")
        resolved = resolve_agent_version(
            args.pipeline,
            policy_path=args.agent_policy,
            dirty_policy=args.dirty_policy,
        )
        payload = resolved.manifest.model_dump(mode="json")
    elif args.command == "promote":
        if args.from_run is not None:
            run_dir = _resolve_run_dir(args.from_run, root)
            resolved = load_run_candidate(run_dir)
            source_run_id = run_dir.name
            if (
                resolved.manifest.identity["source"]["tree_state"] == "dirty"
                and args.dirty_policy != "capture"
            ):
                raise ValueError(
                    "Run candidate is dirty; pass --dirty-policy capture to "
                    "promote it explicitly."
                )
        else:
            if args.pipeline is None:
                raise ValueError("promote requires --pipeline or --from-run.")
            resolved = resolve_agent_version(
                args.pipeline,
                policy_path=args.agent_policy,
                dirty_policy=args.dirty_policy,
            )
            source_run_id = None
        path = store.promote(
            resolved,
            alias=args.alias,
            source_run_id=source_run_id,
            notes=args.notes,
            repository=root,
        )
        payload = {"agent_version_id": resolved.manifest.agent_version_id, "path": str(path)}
    elif args.command == "inspect":
        payload = store.load(args.agent_version).model_dump(mode="json")
    elif args.command == "verify":
        manifest = store.load(args.agent_version)
        store.verify(manifest, repository=root)
        if args.mode == "reconstruct":
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                store.reconstruct(
                    manifest,
                    repository=root,
                    destination=Path(directory) / "version",
                )
        payload = {"agent_version_id": manifest.agent_version_id, "verified": True}
    else:
        manifest = store.load(args.agent_version)
        destination = store.reconstruct(
            manifest, repository=root, destination=args.destination
        )
        payload = {
            "agent_version_id": manifest.agent_version_id,
            "destination": str(destination),
        }
    print(json.dumps(payload, indent=2) if args.json else _human(payload))
    return 0


def _human(payload: dict[str, Any]) -> str:
    if "agent_version_id" in payload:
        return f"agent_version_id: {payload['agent_version_id']}"
    return json.dumps(payload, indent=2)


def _resolve_run_dir(value: Path, root: Path) -> Path:
    if value.is_dir():
        return value.resolve()
    matches = tuple((root / ".workbench/evals").glob(f"**/runs/{value.name}"))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one local run directory for {value}; found {len(matches)}."
        )
    return matches[0].resolve()


if __name__ == "__main__":
    raise SystemExit(main())
