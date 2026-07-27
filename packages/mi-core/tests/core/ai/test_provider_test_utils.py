"""Tests for provider_test_utils prerequisite helpers.

Uses monkeypatched environment variables with fake values to verify that
the skip-guard correctly identifies missing credentials for each provider
path without requiring real provider keys.
"""

from __future__ import annotations

import pytest

from tests.core.ai.provider_test_utils import missing_prerequisites_for_provider


class TestMissingPrerequisites:
    """Validate skip-guard logic for each provider's env var requirements."""

    # -- Logfire (required for all providers) ---------------------------------

    def test_logfire_token_required_for_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("LOGFIRE_READ_TOKEN", raising=False)
        assert (
            missing_prerequisites_for_provider("azure:gpt-5-mini")
            == "LOGFIRE_READ_TOKEN"
        )

    # -- anthropic:* — direct Anthropic API key only -------------------------

    def test_anthropic_direct_key_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "foobar-direct-key")
        assert missing_prerequisites_for_provider("anthropic:claude-sonnet-4-5") is None

    def test_anthropic_missing_direct_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = missing_prerequisites_for_provider("anthropic:claude-sonnet-4-5")
        assert result == "ANTHROPIC_API_KEY"

    def test_anthropic_foundry_key_alone_not_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Foundry vars are irrelevant for the anthropic:* path."""
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foobar-foundry-key")
        result = missing_prerequisites_for_provider("anthropic:claude-sonnet-4-5")
        assert result == "ANTHROPIC_API_KEY"

    # -- azure:claude-* — Foundry credentials --------------------------------

    def test_azure_claude_foundry_key_plus_resource_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foobar-foundry-key")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "foobar-resource")
        assert missing_prerequisites_for_provider("azure:claude-sonnet-4-5") is None

    def test_azure_claude_foundry_key_plus_base_url_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foobar-foundry-key")
        monkeypatch.setenv(
            "ANTHROPIC_FOUNDRY_BASE_URL", "https://foobar.example.com/anthropic"
        )
        assert missing_prerequisites_for_provider("azure:claude-sonnet-4-5") is None

    def test_azure_claude_missing_foundry_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("ANTHROPIC_FOUNDRY_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "foobar-resource")
        result = missing_prerequisites_for_provider("azure:claude-sonnet-4-5")
        assert result == "ANTHROPIC_FOUNDRY_API_KEY"

    def test_azure_claude_foundry_key_without_endpoint_insufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Foundry key alone (no resource or base_url) should report missing endpoint."""
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foobar-foundry-key")
        monkeypatch.delenv("ANTHROPIC_FOUNDRY_BASE_URL", raising=False)
        monkeypatch.delenv("ANTHROPIC_FOUNDRY_RESOURCE", raising=False)
        result = missing_prerequisites_for_provider("azure:claude-sonnet-4-5")
        assert result is not None
        assert "ANTHROPIC_FOUNDRY_BASE_URL" in result
        assert "ANTHROPIC_FOUNDRY_RESOURCE" in result

    def test_azure_claude_opus_uses_foundry_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """azure:claude-opus-* should also route through the Foundry prereq check."""
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "foobar-foundry-key")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "foobar-resource")
        assert missing_prerequisites_for_provider("azure:claude-opus-4-5") is None

    # -- azure:* (non-Claude) — Azure OpenAI credentials --------------------

    def test_azure_gpt_requires_endpoint_and_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "foobar-azure-key")
        assert missing_prerequisites_for_provider("azure:gpt-5-mini") is None

    def test_azure_gpt_missing_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "foobar-azure-key")
        assert (
            missing_prerequisites_for_provider("azure:gpt-5-mini")
            == "AZURE_OPENAI_ENDPOINT"
        )

    def test_azure_gpt_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        assert (
            missing_prerequisites_for_provider("azure:gpt-5-mini")
            == "AZURE_OPENAI_API_KEY"
        )

    # -- openrouter:* --------------------------------------------------------

    def test_openrouter_requires_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert (
            missing_prerequisites_for_provider(
                "openrouter:google/gemini-3-flash-preview"
            )
            == "OPENROUTER_API_KEY"
        )

    def test_openrouter_key_sufficient(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("OPENROUTER_API_KEY", "foobar-openrouter-key")
        assert (
            missing_prerequisites_for_provider(
                "openrouter:google/gemini-3-flash-preview"
            )
            is None
        )

    # -- google:* ------------------------------------------------------------

    def test_google_requires_either_google_or_gemini_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert (
            missing_prerequisites_for_provider("google:gemini-3.1-flash-lite-preview")
            == "GOOGLE_API_KEY or GEMINI_API_KEY"
        )

    def test_google_api_key_is_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.setenv("GOOGLE_API_KEY", "foobar-google-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert (
            missing_prerequisites_for_provider("google:gemini-3.1-flash-lite-preview")
            is None
        )

    def test_gemini_api_key_is_sufficient(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LOGFIRE_READ_TOKEN", "tok")
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", "foobar-gemini-key")
        assert (
            missing_prerequisites_for_provider("google:gemini-3.1-flash-lite-preview")
            is None
        )
