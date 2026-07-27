"""Non-interactive CLI for local ephemeral eval review bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation import LocalReviewStore, ReviewStoreError

from workbench.evals.inspection import (
    find_run_directory,
    inspect_example,
    inspect_execution,
    inspection_summary,
    list_inspection_rows,
    materialize_review_index,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect disposable local eval review bundles."
    )
    parser.add_argument("--root", type=Path, default=Path(".workbench/evals"))
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("summary", "verify", "size", "materialize"):
        command = commands.add_parser(name)
        command.add_argument("--run", required=True)

    list_parser = commands.add_parser("list")
    list_parser.add_argument("--run", required=True)
    list_parser.add_argument(
        "--filter",
        default="all",
        choices=[
            "all",
            "incorrect",
            "invalid",
            "failed",
            "flaky",
            "unscored",
            "review-unavailable",
        ],
    )
    list_parser.add_argument("--limit", type=int, default=100)

    example_parser = commands.add_parser("example")
    example_parser.add_argument("--run", required=True)
    example_parser.add_argument("--example", required=True)
    example_parser.add_argument("--repetition", type=int)
    example_parser.add_argument("--resolve-text", action="store_true")

    execution_parser = commands.add_parser("execution")
    execution_parser.add_argument("--run", required=True)
    execution_parser.add_argument("--execution", required=True)
    execution_parser.add_argument("--section")
    execution_parser.add_argument("--resolve-text", action="store_true")

    diagnose_parser = commands.add_parser("diagnose")
    diagnose_parser.add_argument("--run", required=True)
    diagnose_parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="JSON object containing the compact evidence-based diagnosis.",
    )
    diagnose_parser.add_argument("--markdown", type=Path)
    return parser


def _run_store(run_dir: Path) -> LocalReviewStore:
    return LocalReviewStore(run_dir, run_id=run_dir.name)


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        run_dir = find_run_directory(args.run, root=args.root)
        store = _run_store(run_dir)
        if args.command == "summary":
            payload = inspection_summary(run_dir)
        elif args.command == "list":
            payload = list_inspection_rows(
                run_dir, filter_name=args.filter, limit=args.limit
            )
        elif args.command == "example":
            payload = inspect_example(
                run_dir,
                example_id=args.example,
                repetition=args.repetition,
                resolve_text=args.resolve_text,
            )
        elif args.command == "execution":
            payload = inspect_execution(
                run_dir,
                execution_id=args.execution,
                section=args.section,
                resolve_text=args.resolve_text,
            )
        elif args.command == "verify":
            payload = store.verify()
        elif args.command == "size":
            payload = store.size()
        elif args.command == "materialize":
            path = materialize_review_index(run_dir)
            payload = {"run_id": run_dir.name, "index_path": str(path)}
        elif args.command == "diagnose":
            diagnosis = _load_object(args.input)
            markdown = (
                args.markdown.read_text(encoding="utf-8")
                if args.markdown is not None
                else None
            )
            json_path, markdown_path = store.write_diagnosis(
                diagnosis, markdown=markdown
            )
            payload = {
                "run_id": run_dir.name,
                "diagnosis_path": str(json_path),
                "markdown_path": (
                    str(markdown_path) if markdown_path is not None else None
                ),
            }
        else:  # pragma: no cover - argparse enforces a known command
            raise ValueError(f"Unsupported command: {args.command}")
    except (OSError, ValueError, ReviewStoreError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
