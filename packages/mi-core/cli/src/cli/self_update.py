from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from typing import Literal

import typer

PACKAGE = "meshinsights-cli"
DEFAULT_REPO_URL = (
    "git+https://github.com/Mesh-Systems-Eng/mesh.insights.core.git#subdirectory=cli"
)
ALLOWED_REFS = ("main", "develop")


def _build_git_url(ref: str) -> str:
    repo_url = DEFAULT_REPO_URL
    if "#" in repo_url:
        base_url, fragment = repo_url.split("#", 1)
        if "@" in base_url:
            base_url = base_url.rsplit("@", 1)[0]
        return f"{base_url}@{ref}#{fragment}"
    return f"{repo_url}@{ref}#subdirectory=cli"


def self_update_command(
    *,
    pre: bool = False,
    ref: str | None = None,
) -> int:
    from .ui.theme import print_banner

    print_banner()

    uv_exe = shutil.which("uv")
    pip_exe = shutil.which("pip")

    if not uv_exe and not pip_exe:
        typer.secho(
            "Neither uv nor pip is available. Cannot update package.",
            fg=typer.colors.RED,
            err=True,
        )
        return 1

    if ref is not None:
        if ref not in ALLOWED_REFS:
            typer.secho(
                f"Error: Ref must be one of {', '.join(ALLOWED_REFS)}. Got: {ref}",
                fg=typer.colors.RED,
                err=True,
            )
            return 1
        git_url = _build_git_url(ref)
        if uv_exe:
            cmd = [uv_exe, "tool", "install", "--from", git_url, PACKAGE]
            if pre:
                cmd.extend(["--prerelease", "allow"])
        else:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", git_url]
            if pre:
                cmd.append("--pre")
        action = f"Installing {PACKAGE} from ref '{ref}'"
    else:
        if uv_exe:
            cmd = [uv_exe, "tool", "upgrade", PACKAGE]
            if pre:
                cmd.extend(["--prerelease", "allow"])
        else:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]
            if pre:
                cmd.append("--pre")
        action = f"Updating {PACKAGE}"

    logging.info("%s using: %s", action, " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode == 0:
        logging.info("%s completed successfully", action)
    else:
        logging.error("%s failed (exit code %s)", action, result.returncode)
    return result.returncode


def register_update_command(app: typer.Typer) -> None:
    @app.command("update")
    def update_cli(
        pre: bool = typer.Option(
            False, "--pre", help="Allow installing pre-release versions."
        ),
        ref: Literal["main", "develop"] | None = typer.Option(
            None,
            "--ref",
            "-r",
            help=f"Git ref (branch or tag) to install from. Allowed values: {', '.join(ALLOWED_REFS)}.",
        ),
    ) -> None:
        """
        Update the meshinsights CLI package in the current environment.

        By default, upgrades from the same source as the original installation.
        Use --ref to install from a specific git branch or tag.
        """
        code = self_update_command(pre=pre, ref=ref)
        raise typer.Exit(code)
