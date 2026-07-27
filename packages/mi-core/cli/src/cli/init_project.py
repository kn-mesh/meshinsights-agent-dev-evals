"""``mi init`` — interactive project scaffolding wizard."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import typer

from .ui.art import animate_deploy
from .ui.display import CompletedEntry, print_success
from .ui.prompts import GLYPH_CROSS, ask_confirm, ask_text
from .ui.runner import (
    FACTORY_THEME,
    FieldKind,
    WizardField,
    WizardRunner,
    fields_section,
)
from .ui.theme import get_console

DEFAULT_TEMPLATE_REPO = (
    "https://github.com/Mesh-Systems-Eng/mesh.insights.templates.git"
)


@dataclass
class TemplateOption:
    key: str
    label: str
    repo: str
    ref: str


PIPELINE_TEMPLATES: list[TemplateOption] = [
    TemplateOption(
        key="standard",
        label="Standard pipeline",
        repo=DEFAULT_TEMPLATE_REPO,
        ref="main",
    ),
    TemplateOption(
        key="hotseat",
        label="Hotseat pipeline",
        repo=DEFAULT_TEMPLATE_REPO,
        ref="hotseat",
    ),
]
TEMPLATE_BY_KEY = {template.key: template for template in PIPELINE_TEMPLATES}
DEFAULT_TEMPLATE_KEY = PIPELINE_TEMPLATES[0].key

ADJECTIVES = [
    "bright",
    "calm",
    "brisk",
    "clever",
    "crisp",
    "eager",
    "gentle",
    "keen",
    "lively",
    "merry",
    "nimble",
    "quick",
    "spry",
    "stout",
    "swift",
]

ANIMALS = [
    "otter",
    "falcon",
    "sparrow",
    "badger",
    "lynx",
    "puffin",
    "heron",
    "tern",
    "wren",
    "beaver",
    "fox",
    "marten",
    "stoat",
    "ferret",
]


def _random_project_name() -> str:
    import random

    return f"mesh.{random.choice(ADJECTIVES)}.{random.choice(ANIMALS)}"


@dataclass
class InitConfig:
    project_name: str
    target_dir: Path
    template: TemplateOption
    run_uv_sync: bool
    init_git_repo: bool
    overwrite: bool


# ── Scaffolding helpers ─────────────────────────────────────────────────


def _clone_template(config: InitConfig) -> Path:
    temp_parent = Path(tempfile.mkdtemp(prefix="meshinsights-init-"))
    clone_dir = temp_parent / "template"
    try:
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            config.template.ref,
            config.template.repo,
            str(clone_dir),
        ]
        logging.info(
            "Cloning template: %s@%s", config.template.repo, config.template.ref
        )
        subprocess.run(cmd, check=True, capture_output=True)
        return clone_dir
    except FileNotFoundError as exc:
        raise RuntimeError(
            "git is not installed or not on PATH. Please install git and retry."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Failed to clone template: {exc}") from exc


def _copy_template(clone_dir: Path, config: InitConfig) -> None:
    target = config.target_dir
    target.mkdir(parents=True, exist_ok=True)

    for item in clone_dir.iterdir():
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)

    git_dir = target / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)


def _run_git_init(config: InitConfig) -> None:
    if not config.init_git_repo:
        return
    try:
        subprocess.run(
            ["git", "init"], cwd=config.target_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "add", "."], cwd=config.target_dir, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial project setup"],
            cwd=config.target_dir,
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        logging.warning("git not found. Skipping git init: %s", exc)
    except subprocess.CalledProcessError as exc:
        logging.warning("git init/commit failed: %s", exc)


def _run_uv_sync(config: InitConfig) -> None:
    if not config.run_uv_sync:
        return
    try:
        subprocess.run(
            ["uv", "sync"], cwd=config.target_dir, check=True, capture_output=True
        )
    except FileNotFoundError as exc:
        logging.warning("uv not found. Skipping 'uv sync': %s", exc)
    except subprocess.CalledProcessError as exc:
        logging.warning("'uv sync' failed. You may need to run it manually: %s", exc)


def _scaffold_project(config: InitConfig) -> None:
    """Clone template, copy files, init git, sync deps."""
    clone_dir: Path | None = None
    try:
        clone_dir = _clone_template(config)
        _copy_template(clone_dir, config)
        _run_git_init(config)
        _run_uv_sync(config)
    finally:
        if clone_dir is not None:
            shutil.rmtree(clone_dir.parent, ignore_errors=True)


# ── Non-interactive config gathering ────────────────────────────────────


def _gather_config_noninteractive(args: SimpleNamespace) -> InitConfig:
    """Config gathering for --template or non-tty."""
    use_prompts = sys.stdin.isatty()

    default_directory = args.directory or _random_project_name()
    directory_input = (
        args.directory
        if args.directory
        else ask_text(
            "Where should we create this project?", default=str(default_directory)
        )
        if use_prompts
        else default_directory
    )
    target_dir = Path(str(directory_input)).expanduser().resolve()
    project_name = target_dir.name or target_dir.stem or _random_project_name()

    overwrite = bool(args.force)
    if target_dir.exists() and any(target_dir.iterdir()):
        if use_prompts and not overwrite:
            overwrite = ask_confirm(
                f"Directory {target_dir} is not empty. Continue and merge the template?",
                default=False,
            )
        elif not overwrite:
            raise ValueError(
                f"Directory {target_dir} is not empty. Use --force or choose another directory."
            )

    if args.template:
        template = TEMPLATE_BY_KEY.get(args.template)
        if template is None:
            raise ValueError(
                f"Unknown template '{args.template}'. Available choices: {', '.join(TEMPLATE_BY_KEY)}."
            )
    else:
        template = TEMPLATE_BY_KEY[DEFAULT_TEMPLATE_KEY]

    run_uv_sync = not args.skip_uv_sync
    init_git_repo = not args.no_git_init

    return InitConfig(
        project_name=project_name,
        target_dir=target_dir,
        template=template,
        run_uv_sync=run_uv_sync,
        init_git_repo=init_git_repo,
        overwrite=overwrite,
    )


# ── Config resolution from wizard state ─────────────────────────────────


def _build_config(state: dict[str, Any], args: SimpleNamespace) -> InitConfig:
    """Resolve an :class:`InitConfig` from wizard-collected state."""
    default_name = args.directory or _random_project_name()
    directory_input = state.get("project_dir", str(default_name))
    target_dir = Path(directory_input).expanduser().resolve()
    project_name = target_dir.name or target_dir.stem or _random_project_name()

    template_label = state.get("template", PIPELINE_TEMPLATES[0].label)
    template = next(
        (t for t in PIPELINE_TEMPLATES if t.label == template_label),
        PIPELINE_TEMPLATES[0],
    )

    return InitConfig(
        project_name=project_name,
        target_dir=target_dir,
        template=template,
        run_uv_sync=state.get("run_uv_sync", "True") == "True",
        init_git_repo=state.get("init_git", "True") == "True",
        overwrite=bool(args.force),
    )


# ── Execute + summary callbacks ─────────────────────────────────────────


def _on_execute(
    _entries: list[CompletedEntry],
    state: dict[str, Any],
) -> None:
    """Scaffold the project.  Called by the wizard runner."""
    config: InitConfig = state["_config"]
    _scaffold_project(config)


def _summary(
    console: Any,
    entries: list[CompletedEntry],
    state: dict[str, Any],
) -> None:
    """Post-wizard summary printed in the normal terminal."""
    from .ui.display import print_steps

    console.print()
    print_steps(console, entries)
    print_success(console, "Project created successfully!")
    console.print()
    console.print(f"  [dim]cd {state.get('project_dir', '.')} && get started![/]")
    console.print()


# ── Main command ────────────────────────────────────────────────────────


def init_project_command(args: SimpleNamespace) -> int:
    console = get_console()
    use_interactive = sys.stdin.isatty() and not args.template

    # ── Non-interactive fast path (--template or piped stdin) ──
    if not use_interactive:
        try:
            config = _gather_config_noninteractive(args)
        except KeyboardInterrupt:
            console.print("\nAborted.")
            return 130
        except ValueError as exc:
            console.print(f"[error]{exc}[/error]")
            return 1

        console.print(
            f"  [info]Creating project[/info] [bold]{config.project_name}[/bold]"
        )
        console.print(f"  [info]Template:[/info] {config.template.label}")
        console.print(f"  [info]Location:[/info] {config.target_dir}")
        console.print()

        if (
            config.target_dir.exists()
            and not config.overwrite
            and any(config.target_dir.iterdir())
        ):
            console.print(
                f"  [error]Directory {config.target_dir} is not empty. Use --force to override.[/error]"
            )
            return 1

        try:
            _scaffold_project(config)
        except KeyboardInterrupt:
            console.print(f"\n  [bright_red]{GLYPH_CROSS}[/] [bold red]Aborted.[/]")
            return 130
        except RuntimeError as exc:
            console.print(f"  [error]{exc}[/error]")
            return 1

        return 0

    # ── Interactive wizard flow ─────────────────────────────────────────
    default_name = args.directory or _random_project_name()

    # Build the config *after* collection but *before* execute.
    # We intercept via the runner's state dict.
    def _pre_execute(
        _entries: list[CompletedEntry],
        state: dict[str, Any],
    ) -> None:
        config = _build_config(state, args)

        # Check for non-empty directory (can't be done in the wizard fields)
        if (
            config.target_dir.exists()
            and any(config.target_dir.iterdir())
            and not config.overwrite
        ):
            console.print(f"  [warn]Directory {config.target_dir} is not empty.[/warn]")
            if not ask_confirm("Continue and merge the template?", default=False):
                raise KeyboardInterrupt  # runner treats as abort

        state["_config"] = config
        _scaffold_project(config)

    runner = WizardRunner(
        theme=FACTORY_THEME,
        sections=[
            fields_section(
                "Project",
                [
                    WizardField(
                        name="project_dir",
                        label="Project directory",
                        kind=FieldKind.TEXT,
                        placeholder=str(default_name),
                        default=str(args.directory) if args.directory else None,
                        required=True,
                    ),
                ],
            ),
            fields_section(
                "Template",
                [
                    WizardField(
                        name="template",
                        label="Pipeline template",
                        kind=FieldKind.SELECT,
                        choices=[t.label for t in PIPELINE_TEMPLATES],
                        default=PIPELINE_TEMPLATES[0].label,
                    ),
                ],
            ),
            fields_section(
                "Setup",
                [
                    WizardField(
                        name="run_uv_sync",
                        label="Run 'uv sync' after scaffolding?",
                        kind=FieldKind.CONFIRM,
                        default="true" if not args.skip_uv_sync else "false",
                    ),
                    WizardField(
                        name="init_git",
                        label="Initialize git repository?",
                        kind=FieldKind.CONFIRM,
                        default="true" if not args.no_git_init else "false",
                    ),
                ],
            ),
        ],
        review_prompt="Configuration looks good? Continue?",
        on_execute=_pre_execute,
        execute_animation=animate_deploy,
        summary=_summary,
    )

    return runner.run(console)


def register_init_command(app: typer.Typer) -> None:
    @app.command("init")
    def init_project(
        directory: Path | None = typer.Argument(
            None,
            help="Target directory for the new project (also used for the project name).",
        ),
        template: str | None = typer.Option(
            None,
            "--template",
            "-t",
            help="Skip the template selection prompt by choosing a predefined template key.",
        ),
        skip_uv_sync: bool = typer.Option(
            False,
            "--skip-uv-sync",
            help="Skip running 'uv sync' after creating the project.",
        ),
        no_git_init: bool = typer.Option(
            False, "--no-git-init", help="Do not initialize a new git repository."
        ),
        force: bool = typer.Option(
            False, "--force", "-f", help="Overwrite existing files."
        ),
    ) -> None:
        """Interactive project scaffolding wizard."""
        args = SimpleNamespace(
            directory=directory,
            template=template,
            skip_uv_sync=skip_uv_sync,
            no_git_init=no_git_init,
            force=force,
        )
        code = init_project_command(args)
        raise typer.Exit(code)
