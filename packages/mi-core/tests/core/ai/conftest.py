"""Shared pytest configuration for core AI smoke tests."""

from __future__ import annotations

import asyncio
from collections.abc import Generator

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add provider selector CLI option for AI smoke tests."""
    parser.addoption(
        "--pydantic-ai-provider",
        action="store",
        default="all",
        help=(
            "Provider selector for pydantic-ai smoke tests. "
            "Use 'all' (default) or one of: "
            "azure:gpt-5-mini, azure:claude-sonnet-4-5, google:gemini-3.1-flash-lite-preview."
        ),
    )


@pytest.fixture(scope="module", autouse=True)
def _install_current_event_loop() -> Generator[None, None, None]:
    """Install an explicit event loop for Python 3.13+ tests."""
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(None)
        event_loop.close()
