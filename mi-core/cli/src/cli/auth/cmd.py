"""``mi auth`` — interactive credential configuration wizard."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from ..ui.display import (
    CompletedEntry,
    mask_value,
    print_failure,
    print_steps,
)
from ..ui.picker import multiselect, select
from ..ui.prompts import (
    ask_confirm,
    ask_text,
    spinner,
)
from ..ui.runner import (
    CONVEYOR_THEME,
    SectionContext,
    WizardRunner,
    WizardSection,
)
from ..ui.theme import get_console
from .context import AuthContext
from .env import (
    extract_template_vars,
    find_env_template,
    load_existing_env,
    update_env_file,
)
from .prompts import (
    CheckboxPrompt,
    ConfirmPrompt,
    MessagePrompt,
    PromptRequest,
    SelectPrompt,
    SubprocessPrompt,
    TextPrompt,
)
from .providers import PROVIDERS, PROVIDER_BY_SLUG, match_providers_for_env_vars
from .providers.base import BaseProvider

logger = logging.getLogger(__name__)

# The three fixed phases shown in the conveyor art.
_PHASE_TITLES = ["Setup", "Configure", "Review"]

# Env-var name fragments that indicate a sensitive value worth masking.
_SENSITIVE_FRAGMENTS = {"KEY", "TOKEN", "SECRET", "PASSWORD"}


def _is_sensitive(env_var: str) -> bool:
    """Return whether an env-var name looks like it holds a secret."""
    parts = env_var.upper().split("_")
    return bool(_SENSITIVE_FRAGMENTS & set(parts))


# Prompt-type -> rough line count for content-height estimation.
_OVERHEAD_TEXT = 4
_OVERHEAD_SELECT = 8
_OVERHEAD_CONFIRM = 2
_OVERHEAD_MESSAGE = 2


# ---------------------------------------------------------------------------
# Setup section — env discovery + provider selection
# ---------------------------------------------------------------------------


def _setup_section_run(
    sctx: SectionContext,
    auth_ctx: AuthContext,
    *,
    env_file: Path | None,
) -> CompletedEntry | None:
    """Discover .env, select providers, inject provider sections."""
    console = sctx.console

    # -- .env update prompt (only if one already exists) --
    env_path = auth_ctx.project_root / ".env"
    has_existing_env = env_path.is_file()

    if has_existing_env:
        sctx.redraw(_OVERHEAD_CONFIRM)
        update = ask_confirm("Update existing .env?", default=True, console=console)
        if not update:
            # Ask for an alternative path instead of bailing out.
            sctx.breadcrumbs.append(("Update .env", "no"))
            sctx.redraw(_OVERHEAD_TEXT)
            raw = ask_text(
                "Path for new .env file",
                default=str(auth_ctx.project_root / ".env.local"),
                console=console,
            )
            if not raw.strip():
                return None
            alt_env_path = Path(raw).expanduser().resolve()
            sctx.breadcrumbs.append(("Env file", str(alt_env_path)))
            sctx.state["alt_env_path"] = alt_env_path
        else:
            sctx.breadcrumbs.append(("Update .env", "yes"))

    # -- Redraw with any answered fields compressed --
    sctx.redraw(_OVERHEAD_SELECT)

    # -- Build choice list from real providers --
    all_labels = [f"{p.name} - {p.description}" for p in PROVIDERS]

    # Auto-detect required providers from .env.template
    template_required = match_providers_for_env_vars(auth_ctx.template_vars)
    required_labels = [f"{p.name} - {p.description}" for p in template_required]

    # Pre-select required + offer all
    picker_height = sctx.picker_height()
    selected_labels = multiselect(
        "Select providers to configure:",
        all_labels,
        defaults=required_labels,
        forced=required_labels,
        max_visible=picker_height,
        console=console,
    )

    if not selected_labels:
        return None

    # Resolve labels back to provider objects
    label_to_provider = {f"{p.name} - {p.description}": p for p in PROVIDERS}
    selected_providers = [label_to_provider[lbl] for lbl in selected_labels]

    short_names = [p.name for p in selected_providers]
    sctx.breadcrumbs.append(("Providers", ", ".join(short_names)))

    # Store for use by on_execute
    sctx.state["selected_providers"] = selected_providers

    # New-file flow: don't leak os.environ values as defaults.
    alt_env_path = sctx.state.get("alt_env_path")
    target = alt_env_path or env_file or (auth_ctx.project_root / ".env")
    if not target.is_file():
        auth_ctx.existing_env = {}

    # Inject per-provider sections after this one
    total = len(selected_providers)
    provider_sections = [
        _make_provider_section(p, auth_ctx, i + 1, total)
        for i, p in enumerate(selected_providers)
    ]
    sctx.add_sections(*provider_sections)

    return ("done", "Setup", list(sctx.breadcrumbs))


def _make_setup_section(
    auth_ctx: AuthContext,
    env_file: Path | None,
) -> WizardSection:
    """Build the Setup wizard section."""

    def _run(sctx: SectionContext) -> CompletedEntry | None:
        return _setup_section_run(sctx, auth_ctx, env_file=env_file)

    return WizardSection(title="Setup", run=_run)


# ---------------------------------------------------------------------------
# Provider section — generator-driven per-provider flow
# ---------------------------------------------------------------------------


def _drive_provider_section(
    sctx: SectionContext,
    provider: BaseProvider,
    auth_ctx: AuthContext,
    progress: str,
) -> CompletedEntry:
    """Drive a single provider's fetch() generator through the UI."""
    console = sctx.console
    auth_ctx.active_provider = provider.name
    gen = provider.fetch(auth_ctx)
    results: dict[str, str] = {}

    # Store subtitle for the redraw header
    sctx.state["_subtitle"] = progress

    response: Any = None
    prompt: PromptRequest | None = None

    try:
        prompt = next(gen)
        while True:
            if isinstance(prompt, TextPrompt):
                sctx.redraw(_OVERHEAD_TEXT)
                response = ask_text(
                    prompt.label,
                    default=prompt.default or None,
                    console=console,
                )
                if response:
                    display = mask_value(response) if prompt.password else response
                    sctx.breadcrumbs.append((prompt.label, display))

            elif isinstance(prompt, SelectPrompt):
                sctx.redraw(_OVERHEAD_SELECT)
                choices = [c.label for c in prompt.choices]
                default_label = None
                if prompt.default is not None:
                    for c in prompt.choices:
                        if c.value == prompt.default:
                            default_label = c.label
                            break
                selected = select(
                    prompt.message,
                    choices,
                    default=default_label,
                    max_visible=sctx.picker_height(),
                    console=console,
                )
                # Map label back to value
                for c in prompt.choices:
                    if c.label == selected:
                        response = c.value
                        break
                else:
                    response = selected
                sctx.breadcrumbs.append((prompt.message, selected))

            elif isinstance(prompt, ConfirmPrompt):
                sctx.redraw(_OVERHEAD_CONFIRM)
                response = ask_confirm(
                    prompt.message,
                    default=prompt.default,
                    console=console,
                )
                sctx.breadcrumbs.append((prompt.message, "yes" if response else "no"))

            elif isinstance(prompt, CheckboxPrompt):
                sctx.redraw(_OVERHEAD_SELECT)
                choices = [c.label for c in prompt.choices]
                defaults = [c.label for c in prompt.choices if c.checked]
                forced = [c.label for c in prompt.choices if c.locked]
                selected_labels = multiselect(
                    prompt.message,
                    choices,
                    defaults=defaults,
                    forced=forced,
                    max_visible=sctx.picker_height(),
                    console=console,
                )
                # Map labels back to values
                label_to_val = {c.label: c.value for c in prompt.choices}
                response = [label_to_val[lbl] for lbl in selected_labels]
                sctx.breadcrumbs.append((prompt.message, ", ".join(selected_labels)))

            elif isinstance(prompt, MessagePrompt):
                # Informational messages become breadcrumbs so the
                # screen stays consistent (no inline flicker).
                # Strip Rich markup for the breadcrumb display value.
                clean = re.sub(r"\[/?[^\]]*\]", "", prompt.text)

                if prompt.style in ("error", "warn"):
                    # Errors/warnings: redraw then show inline so
                    # the user actually sees them before the next prompt.
                    sctx.redraw(_OVERHEAD_MESSAGE)
                    style_map = {"warn": "yellow", "error": "bright_red"}
                    s = style_map.get(prompt.style, "")
                    console.print(f"    [{s}]{prompt.text}[/]", highlight=False)
                elif prompt.style == "info" or not prompt.style:
                    # Status messages (e.g. "Using subscription: ...")
                    # -> silent breadcrumb, no print.
                    sctx.breadcrumbs.append((clean, ""))
                # "hint" / "success" -> skip entirely (noise reduction)

                response = None

            elif isinstance(prompt, SubprocessPrompt):
                # Run external command. Show label as spinner if capturing.
                label = prompt.label or " ".join(prompt.cmd[:3])
                if prompt.capture:
                    _cmd, _cwd = prompt.cmd, prompt.cwd
                    proc = spinner(
                        f"Running {label}...",
                        work=lambda: subprocess.run(
                            _cmd,
                            capture_output=True,
                            cwd=_cwd,
                        ),
                        console=console,
                    )
                    response = proc.returncode if proc else None
                else:
                    # Interactive subprocess (e.g. `az login`) — leave alt
                    # screen so the child process can use the terminal,
                    # then re-enter after.
                    sctx.leave_alt_screen()
                    console.print(f"  [dim]Running: {' '.join(prompt.cmd)}[/]")
                    proc = subprocess.run(
                        prompt.cmd,
                        cwd=prompt.cwd,
                    )
                    response = proc.returncode
                    sctx.enter_alt_screen()
                    sctx.redraw(_OVERHEAD_TEXT)

                sctx.breadcrumbs.append(
                    (label, "ok" if response == 0 else f"exit {response}")
                )

            else:
                # Unknown prompt type — skip
                logger.warning("Unknown prompt type: %s", type(prompt).__name__)
                response = None

            prompt = gen.send(response)

    except StopIteration as exc:
        results = exc.value or {}

    # Accumulate results for on_execute
    all_results: dict[str, str] = sctx.state.setdefault("all_results", {})
    all_results.update(results)

    # Clear subtitle after section completes
    sctx.state.pop("_subtitle", None)

    # Build the completed entry for this provider
    if results:
        # Only mask genuinely sensitive values (keys, tokens);
        # show endpoints, versions, resource names in plain text.
        field_display = [
            (env_var, mask_value(val) if _is_sensitive(env_var) else val)
            for env_var, val in results.items()
        ]
        return ("done", provider.name, field_display)

    return ("skip", provider.name, [])


def _make_provider_section(
    provider: BaseProvider,
    auth_ctx: AuthContext,
    index: int,
    total: int,
) -> WizardSection:
    """Build a wizard section for a single provider."""
    progress = f"[{index}/{total}]"

    def _run(sctx: SectionContext) -> CompletedEntry | None:
        try:
            return _drive_provider_section(sctx, provider, auth_ctx, progress)
        except Exception:
            logger.exception("Provider %s failed", provider.name)
            return ("fail", provider.name, [])

    return WizardSection(title=provider.name, run=_run)


# ---------------------------------------------------------------------------
# Execute + summary callbacks
# ---------------------------------------------------------------------------


def _on_execute(
    _entries: list[CompletedEntry],
    state: dict[str, Any],
) -> None:
    """Write credentials to .env.  Called by the wizard runner."""
    all_results: dict[str, str] = state.get("all_results", {})
    if not all_results:
        return

    project_root: Path = state["project_root"]
    target_env: Path | None = state.get("alt_env_path") or state.get("env_file")

    env_path = update_env_file(project_root, all_results, env_file=target_env)
    state["written_env_path"] = env_path


def _auth_summary(
    console: Console,
    entries: list[CompletedEntry],
    state: dict[str, Any],
) -> None:
    """Post-wizard summary printed in the normal terminal."""
    console.print()
    print_steps(console, entries)

    env_path = state.get("written_env_path")
    if env_path:
        console.print(f"  [dim]Written to {env_path}[/]")
    console.print()


# ---------------------------------------------------------------------------
# Flow helpers
# ---------------------------------------------------------------------------


def _resolve_project_root(env_file: Path | None = None) -> Path:
    """Find the project root by walking up from cwd looking for markers."""
    if env_file:
        return env_file.parent.resolve()

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        markers = ("pyproject.toml", ".env", ".env.template", "pipeline.yaml")
        if any((parent / m).exists() for m in markers):
            return parent
    return cwd


def _build_auth_context(
    project_root: Path,
    env_file: Path | None = None,
) -> AuthContext:
    """Build the shared auth context from real .env discovery."""
    raw_lines, existing_env = load_existing_env(project_root, env_file)

    template_path = find_env_template(project_root)
    template_vars = extract_template_vars(template_path) if template_path else set()

    return AuthContext(
        project_root=project_root,
        existing_env=existing_env,
        template_vars=template_vars,
    )


# ---------------------------------------------------------------------------
# Flow orchestrator
# ---------------------------------------------------------------------------


def run_auth_flow(
    *,
    env_file: Path | None = None,
    provider: str | None = None,
) -> int:
    console = get_console()

    # -- Real discovery --
    project_root = _resolve_project_root(env_file)
    auth_ctx = _build_auth_context(project_root, env_file)

    # -- Single-provider mode (--provider flag) --
    if provider:
        p = PROVIDER_BY_SLUG.get(provider)
        if not p:
            print_failure(console, f"Unknown provider: {provider}")
            console.print(f"  [dim]Available: {', '.join(PROVIDER_BY_SLUG)}[/]")
            return 1

        # Build a runner with just the one provider section, no setup.
        runner = WizardRunner(
            theme=CONVEYOR_THEME,
            phase_titles=_PHASE_TITLES,
            sections=[
                _make_provider_section(p, auth_ctx, 1, 1),
            ],
            review_prompt="Write credentials to .env?",
            on_execute=_on_execute,
            execute_message="Writing credentials to .env...",
            summary=_auth_summary,
        )
        # Pre-populate state needed by on_execute
        runner._state["project_root"] = project_root
        runner._state["env_file"] = env_file
        # Inject a synthetic setup entry so the summary looks right
        runner._completed.append(
            ("done", "Setup", [("Provider", p.name)]),
        )
        return runner.run(console)

    # -- Interactive multi-provider mode --
    runner = WizardRunner(
        theme=CONVEYOR_THEME,
        phase_titles=_PHASE_TITLES,
        sections=[_make_setup_section(auth_ctx, env_file)],
        review_prompt="Write credentials to .env?",
        on_execute=_on_execute,
        execute_message="Writing credentials to .env...",
        summary=_auth_summary,
    )
    # Pre-populate state needed by on_execute / setup section
    runner._state["project_root"] = project_root
    runner._state["env_file"] = env_file

    return runner.run(console)


# ---------------------------------------------------------------------------
# Typer command registration
# ---------------------------------------------------------------------------


def register_auth_command(app: typer.Typer) -> None:
    @app.command("auth")
    def auth(
        env_file: Path | None = typer.Option(
            None,
            "--env-file",
            help="Path to .env file (default: <project_root>/.env).",
        ),
        provider: str | None = typer.Option(
            None,
            "--provider",
            "-p",
            help="Configure a single provider by slug (e.g. azure_foundry, anthropic).",
        ),
    ) -> None:
        """Configure project authentication credentials.

        Scans for an .env.template, shows a provider selection list, fetches
        credentials automatically where possible, and writes results to .env.
        """
        code = run_auth_flow(env_file=env_file, provider=provider)
        raise typer.Exit(code)
