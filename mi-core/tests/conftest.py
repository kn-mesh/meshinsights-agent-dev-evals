"""Root test configuration."""

from __future__ import annotations


import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --all flag to include smoke tests that require live API keys."""
    parser.addoption(
        "--all",
        action="store_true",
        default=False,
        help="Include smoke tests that require live provider API keys.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Override the default marker filter when --all is passed."""
    config.addinivalue_line(
        "markers",
        "smoke: tests that exercise live external providers and services",
    )
    if config.getoption("all", default=False):
        # Remove the default '-m not smoke' so all tests run.
        config.option.markexpr = ""
