"""Environment variable bootstrapping for mi-core.

Loads a ``.env`` file (via ``python-dotenv``) so that environment variables
are available to pipeline components, telemetry configuration, and any
downstream SDK that reads ``os.environ``.

This module mirrors the pattern established by :mod:`mi.core.utils.telemetry`:
an idempotent ``bootstrap_environment()`` function that is called once at
application startup — either by :meth:`Pipeline.run`, the CLI, or the
orchestrator subprocess path.

**Call order**: ``bootstrap_environment()`` must run *before*
``bootstrap_telemetry()`` so that env vars like ``LOGFIRE_TOKEN`` or
``OTEL_EXPORTER_OTLP_ENDPOINT`` are already present when the telemetry
layer reads them.

Usage:
    from mi.core.utils.environment import bootstrap_environment

    bootstrap_environment()          # loads .env from cwd
    bootstrap_environment(".env.prod")  # loads a specific file

See docs/yaml-configuration.md for the ``environment`` and
``bootstrap_environment`` pipeline config keys.
"""

from __future__ import annotations

import logging
from pathlib import Path

_bootstrapped = False


def bootstrap_environment(
    dotenv_path: str | Path = ".env",
    *,
    override: bool = False,
) -> None:
    """Load environment variables from a dotenv file.

    Intended to be called once at application startup — NOT by library
    internals.  Subsequent calls are silently ignored (idempotent).

    Args:
        dotenv_path: Path to the ``.env`` file.  Resolved relative to the
            current working directory when not absolute.  Defaults to
            ``".env"``.
        override: When ``True``, values in the dotenv file take precedence
            over existing environment variables.  Defaults to ``False``
            (existing env vars are preserved).

    Detection / graceful degradation:
        1. If ``python-dotenv`` is installed, ``load_dotenv`` is called with
           the resolved path.
        2. If ``python-dotenv`` is **not** installed, a debug-level log
           message is emitted and the function returns silently.
        3. If the dotenv file does not exist, ``load_dotenv`` itself is a
           no-op — no error is raised.

    This function is idempotent — subsequent calls are ignored.
    """
    global _bootstrapped

    if _bootstrapped:
        return
    _bootstrapped = True

    logger = logging.getLogger(__name__)

    resolved = Path(dotenv_path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved

    try:
        from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]
    except ImportError:
        logger.debug(
            "python-dotenv is not installed; environment bootstrap skipped "
            "(install it or the [ai] extra to enable .env loading)"
        )
        return

    if not resolved.exists():
        logger.debug("Dotenv file not found at %s; skipping", resolved)
        return

    load_dotenv(dotenv_path=resolved, override=override)
    logger.debug("Environment bootstrapped from %s", resolved)
