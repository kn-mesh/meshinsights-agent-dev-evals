"""Logfire credential provider for ``mi auth``.

Delegates to the ``logfire`` CLI for browser-based authentication and
project selection.  The Logfire CLI manages its own credential storage
in ``~/.logfire/`` and ``.logfire/``.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ..context import AuthContext, CredentialField
from ..prompts import ConfirmPrompt, MessagePrompt, SubprocessPrompt
from .base import BaseProvider, FetchGenerator

logger = logging.getLogger(__name__)


class LogfireProvider(BaseProvider):
    name = "Logfire"
    slug = "logfire"
    description = "Pydantic Logfire telemetry"
    fields = [
        CredentialField("LOGFIRE_TOKEN", "Logfire write token", required=False),
    ]

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        if not self._is_available():
            yield MessagePrompt(
                "Logfire CLI not found in venv. Install with: uv add logfire",
                style="warn",
                indent=True,
            )
            yield MessagePrompt("Skipping Logfire setup.", indent=True)
            return {}

        # Check if user is already authenticated
        if not self._is_authenticated():
            yield MessagePrompt("Logfire authentication required.", indent=True)
            should_auth: bool = yield ConfirmPrompt(
                "Run 'logfire auth' now?", default=True
            )
            if not should_auth:
                yield MessagePrompt("Skipping Logfire setup.", indent=True)
                return {}

            rc: int = yield SubprocessPrompt(
                ["uv", "run", "logfire", "auth"],
                label="logfire auth",
            )
            if rc != 0:
                yield MessagePrompt(
                    "Logfire authentication failed.", style="error", indent=True
                )
                return {}

        # Set up project credentials
        return (yield from self._setup_project(ctx))

    @staticmethod
    def _is_available() -> bool:
        """Check if ``logfire`` is installed in the uv-managed venv."""
        result = subprocess.run(
            ["uv", "run", "logfire", "--version"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def _is_authenticated(self) -> bool:
        """Check if the user has a Logfire session via ``logfire whoami``."""
        result = subprocess.run(
            ["uv", "run", "logfire", "whoami"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    def _setup_project(self, ctx: AuthContext) -> FetchGenerator:
        """Set up Logfire project credentials.

        If ``.logfire/logfire_credentials.json`` already exists in the project
        root, read the token from it.  Otherwise, run ``logfire projects use``
        to let the user select a project.
        """
        creds_file = ctx.project_root / ".logfire" / "logfire_credentials.json"

        if creds_file.is_file():
            token = self._read_token_from_credentials(creds_file)
            if token:
                yield MessagePrompt(
                    "Using existing Logfire project credentials.",
                    style="info",
                    indent=True,
                )
                return {"LOGFIRE_TOKEN": token}

        yield MessagePrompt("Setting up Logfire project...", indent=True)
        rc: int = yield SubprocessPrompt(
            ["uv", "run", "logfire", "projects", "use"],
            label="logfire projects use",
            cwd=str(ctx.project_root),
        )

        if rc != 0:
            yield MessagePrompt(
                "Logfire project setup did not complete. You can run 'uv run logfire projects use' later.",
                style="warn",
                indent=True,
            )
            return {}

        # Try to read the token from the credentials file written by logfire
        if creds_file.is_file():
            token = self._read_token_from_credentials(creds_file)
            if token:
                yield MessagePrompt(
                    "Logfire project configured.", style="info", indent=True
                )
                return {"LOGFIRE_TOKEN": token}

        yield MessagePrompt(
            "Logfire project configured (credentials managed by logfire).",
            style="info",
            indent=True,
        )
        return {}

    def _read_token_from_credentials(self, path: Path) -> str | None:
        """Read the write token from a ``logfire_credentials.json`` file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("token") or data.get("write_token")
        except (json.JSONDecodeError, OSError):
            logger.debug("Failed to read logfire credentials from %s", path)
            return None
