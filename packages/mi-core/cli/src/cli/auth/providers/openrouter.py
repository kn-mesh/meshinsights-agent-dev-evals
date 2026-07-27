"""OpenRouter credential provider for ``mi auth``.

Attempts automated key provisioning via OAuth PKCE flow:

1. Generate ``code_verifier`` + ``code_challenge`` (SHA-256).
2. Start a temporary localhost HTTP server to receive the callback.
3. Open the user's browser to OpenRouter's ``/auth`` endpoint.
4. Exchange the returned ``code`` for an API key via
   ``POST https://openrouter.ai/api/v1/auth/keys``.

Falls back to manual key entry if the PKCE flow fails or is declined.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from ..context import AuthContext, CredentialField
from ..prompts import ConfirmPrompt, MessagePrompt
from .base import BaseProvider, FetchGenerator, prompt_for_credentials

logger = logging.getLogger(__name__)

_OPENROUTER_AUTH_URL = "https://openrouter.ai/auth"
_OPENROUTER_EXCHANGE_URL = "https://openrouter.ai/api/v1/auth/keys"

# Fixed port for the OAuth callback server.  OpenRouter only allows callback
# URLs on ports 443 and 3000 — see their API docs for POST /api/v1/auth/keys/code.
# The PKCE guide explicitly recommends ``http://localhost:3000`` for local apps.
_CALLBACK_PORT = 3000

# Timeout in seconds for the localhost callback server
_CALLBACK_TIMEOUT = 120


def _generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and S256 code_challenge."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the ``?code=`` query parameter from OpenRouter."""

    code: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])

        if codes:
            _CallbackHandler.code = codes[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization complete!</h2>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Authorization failed</h2>"
                b"<p>No authorization code received.</p>"
                b"</body></html>"
            )

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server logging."""
        logger.debug(format, *args)


def _acquire_callback_port() -> int | None:
    """Check that the fixed callback port is available.

    Returns the port number, or ``None`` if it is already in use.
    """
    import socket  # stdlib, only needed here

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", _CALLBACK_PORT))
            return _CALLBACK_PORT
    except OSError:
        return None


def _exchange_code(
    code: str,
    code_verifier: str,
) -> str | None:
    """Exchange an OAuth code for an OpenRouter API key.

    Returns the API key string, or ``None`` on failure.
    """
    payload = json.dumps(
        {
            "code": code,
            "code_verifier": code_verifier,
            "code_challenge_method": "S256",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        _OPENROUTER_EXCHANGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            key = data.get("key")
            if key:
                return key
            logger.debug("Exchange response missing 'key': %s", data)
            return None
    except Exception:
        logger.debug("OAuth code exchange failed", exc_info=True)
        return None


def _run_pkce_flow() -> tuple[str | None, list[MessagePrompt]]:
    """Execute the full PKCE OAuth flow.

    Returns ``(api_key, messages)`` — the API key (or ``None``) and a list
    of :class:`MessagePrompt` objects to display.  This is a plain function
    (not a generator) because the PKCE flow is non-interactive from the
    terminal's perspective — it just opens a browser and waits.
    """
    messages: list[MessagePrompt] = []
    code_verifier, code_challenge = _generate_pkce_pair()

    port = _acquire_callback_port()
    if port is None:
        messages.append(
            MessagePrompt(
                f"Port {_CALLBACK_PORT} is in use (required for OpenRouter OAuth callback).",
                style="warn",
                indent=True,
            )
        )
        return None, messages
    callback_url = f"http://localhost:{port}"

    auth_params = urlencode(
        {
            "callback_url": callback_url,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    auth_url = f"{_OPENROUTER_AUTH_URL}?{auth_params}"

    # Reset class-level code before each flow
    _CallbackHandler.code = None

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    server.timeout = _CALLBACK_TIMEOUT

    messages.append(
        MessagePrompt(
            "Opening browser for OpenRouter authorization...", style="info", indent=True
        )
    )
    webbrowser.open(auth_url)
    messages.append(
        MessagePrompt(
            f"Waiting for authorization (up to {_CALLBACK_TIMEOUT}s)...",
            indent=True,
        )
    )
    messages.append(
        MessagePrompt(
            f"If the browser didn't open, visit: {auth_url}",
            style="hint",
            indent=True,
        )
    )

    # Wait for exactly one request (or timeout)
    done = threading.Event()
    received_code: list[str | None] = [None]

    def serve() -> None:
        server.handle_request()
        received_code[0] = _CallbackHandler.code
        done.set()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    done.wait(timeout=_CALLBACK_TIMEOUT)
    server.server_close()

    code = received_code[0]
    if not code:
        messages.append(
            MessagePrompt(
                "No authorization code received (timed out or cancelled).",
                style="warn",
                indent=True,
            )
        )
        return None, messages

    messages.append(
        MessagePrompt("Authorization received, exchanging for API key...", indent=True)
    )
    api_key = _exchange_code(code, code_verifier)

    if api_key:
        messages.append(
            MessagePrompt("API key provisioned via OAuth.", style="info", indent=True)
        )
    else:
        messages.append(
            MessagePrompt(
                "Failed to exchange authorization code.", style="error", indent=True
            )
        )

    return api_key, messages


class OpenRouterProvider(BaseProvider):
    name = "OpenRouter"
    slug = "openrouter"
    description = "OpenRouter multi-model gateway"
    console_url = "https://openrouter.ai/keys"
    fields = [
        CredentialField("OPENROUTER_API_KEY", "OpenRouter API key"),
    ]

    def fetch(self, ctx: AuthContext) -> FetchGenerator:
        ctx.active_provider = self.name

        if os.environ.get("MI_AUTH_NO_OAUTH"):
            # Escape hatch for CI / testing — skip OAuth entirely
            return (yield from prompt_for_credentials(self, ctx))

        try_oauth: bool = yield ConfirmPrompt(
            "Provision key automatically via browser OAuth?",
            default=True,
        )

        if try_oauth:
            api_key, messages = _run_pkce_flow()
            # Emit all accumulated messages
            for msg in messages:
                yield msg
            if api_key:
                return {"OPENROUTER_API_KEY": api_key}
            yield MessagePrompt(
                "Falling back to manual entry.", style="hint", indent=True
            )

        # Manual fallback
        return (yield from prompt_for_credentials(self, ctx))
