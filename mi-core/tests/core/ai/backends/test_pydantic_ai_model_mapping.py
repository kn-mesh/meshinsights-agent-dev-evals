"""Tests for model mapping in the pydantic-ai backend.

Verifies that provider:model strings are parsed and resolved correctly, and
that reasoning config now maps to pydantic-ai's unified ``thinking`` setting
instead of provider-specific thinking fields.
"""

from __future__ import annotations

import pytest

from mi.ai.backends.pydantic_ai_backend import PydanticAIBackend
from mi.ai.model_config import (
    ModelRef,
    ReasoningEffort,
    ReasoningSpec,
    match_reasoning_spec,
)


@pytest.fixture
def backend() -> PydanticAIBackend:
    return PydanticAIBackend()


class TestModelRefParsing:
    """Validate that ModelRef.parse correctly splits and normalizes values."""

    @pytest.mark.parametrize(
        ("raw", "expected_provider", "expected_model"),
        [
            ("anthropic:claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5"),
            ("anthropic:claude-opus-4-5", "anthropic", "claude-opus-4-5"),
            ("azure:gpt-5", "azure", "gpt-5"),
            ("azure:gpt-5-mini", "azure", "gpt-5-mini"),
            ("azure:claude-sonnet-4-5", "azure", "claude-sonnet-4-5"),
            ("azure:claude-opus-4-5", "azure", "claude-opus-4-5"),
            (
                "google:gemini-3.1-flash-lite-preview",
                "google",
                "gemini-3.1-flash-lite-preview",
            ),
            (
                "openrouter:google/gemini-3-flash-preview",
                "openrouter",
                "google/gemini-3-flash-preview",
            ),
        ],
    )
    def test_known_models_parse(
        self, raw: str, expected_provider: str, expected_model: str
    ) -> None:
        ref = ModelRef.parse(raw)
        assert ref.provider == expected_provider
        assert ref.model == expected_model

    def test_provider_normalized_to_lowercase(self) -> None:
        assert ModelRef.parse("Azure:gpt-5").provider == "azure"

    def test_model_name_preserves_case(self) -> None:
        assert ModelRef.parse("azure:GPT-5").model == "GPT-5"

    def test_whitespace_stripped(self) -> None:
        ref = ModelRef.parse("  azure : gpt-5  ")
        assert ref.provider == "azure"
        assert ref.model == "gpt-5"

    def test_canonical_roundtrip(self) -> None:
        assert ModelRef.parse("azure:gpt-5").canonical() == "azure:gpt-5"

    @pytest.mark.parametrize(
        "bad_input",
        ["", "   ", "gpt-5", ":gpt-5", "azure:", "azure"],
    )
    def test_invalid_formats_raise(self, bad_input: str) -> None:
        with pytest.raises(ValueError):
            ModelRef.parse(bad_input)

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            ModelRef.parse("unknown_provider:some-model")


class TestResolveModel:
    """Validate provider/model resolution into pydantic-ai model handles."""

    @pytest.fixture(autouse=True)
    def _set_foundry_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_API_KEY", "test-key")
        monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "test-resource")
        monkeypatch.delenv("ANTHROPIC_FOUNDRY_BASE_URL", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-api-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-azure-api-key")
        monkeypatch.setenv("OPENAI_API_VERSION", "2025-01-01-preview")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-api-key")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-api-key")

    def test_azure_gpt_returns_string(self, backend: PydanticAIBackend) -> None:
        model, settings_id = backend._resolve_model("azure", "gpt-5", {})
        assert model == "azure:gpt-5"
        assert settings_id == "azure:gpt-5"

    def test_azure_gpt_with_deployment(self, backend: PydanticAIBackend) -> None:
        model, settings_id = backend._resolve_model(
            "azure", "gpt-5", {"deployment": "my-gpt5-deploy"}
        )
        assert model == "azure:my-gpt5-deploy"
        assert settings_id == "azure:my-gpt5-deploy"

    def test_azure_claude_returns_anthropic_model(
        self, backend: PydanticAIBackend
    ) -> None:
        from pydantic_ai.models.anthropic import AnthropicModel

        model, settings_id = backend._resolve_model("azure", "claude-sonnet-4-5", {})
        assert isinstance(model, AnthropicModel)
        assert settings_id == "azure:claude-sonnet-4-5"

    def test_azure_claude_uses_foundry_client(self, backend: PydanticAIBackend) -> None:
        from anthropic import AsyncAnthropicFoundry

        model, _ = backend._resolve_model("azure", "claude-sonnet-4-5", {})
        assert isinstance(model._provider._client, AsyncAnthropicFoundry)

    def test_anthropic_claude_returns_string(self, backend: PydanticAIBackend) -> None:
        model, settings_id = backend._resolve_model(
            "anthropic", "claude-sonnet-4-5", {}
        )
        assert model == "anthropic:claude-sonnet-4-5"
        assert settings_id == "anthropic:claude-sonnet-4-5"

    def test_google_gemini_returns_google_model(
        self, backend: PydanticAIBackend
    ) -> None:
        from pydantic_ai.models.google import GoogleModel

        model, settings_id = backend._resolve_model(
            "google", "gemini-3.1-flash-lite-preview", {}
        )
        assert isinstance(model, GoogleModel)
        assert settings_id == "google:gemini-3.1-flash-lite-preview"

    def test_google_gemini_provider_options_override_api_key(
        self, backend: PydanticAIBackend
    ) -> None:
        model, _ = backend._resolve_model(
            "google",
            "gemini-3.1-flash-lite-preview",
            {"api_key": "provider-option-key"},
        )
        assert model._provider._client._api_client.api_key == "provider-option-key"

    def test_openrouter_gemini(self, backend: PydanticAIBackend) -> None:
        model, settings_id = backend._resolve_model(
            "openrouter", "google/gemini-3-flash-preview", {}
        )
        assert model == "openrouter:google/gemini-3-flash-preview"
        assert settings_id == "openrouter:google/gemini-3-flash-preview"

    @pytest.mark.parametrize(
        ("provider", "model_name", "expected_class_name"),
        [
            ("azure", "gpt-5", "OpenAIChatModel"),
            ("anthropic", "claude-sonnet-4-5", "AnthropicModel"),
            ("google", "gemini-3.1-flash-lite-preview", "GoogleModel"),
            (
                "openrouter",
                "google/gemini-3-flash-preview",
                "OpenRouterModel",
            ),
            ("azure", "claude-sonnet-4-5", "AnthropicModel"),
        ],
    )
    def test_transport_retries_use_explicit_provider_models(
        self,
        backend: PydanticAIBackend,
        provider: str,
        model_name: str,
        expected_class_name: str,
    ) -> None:
        model, _ = backend._resolve_model(
            provider,
            model_name,
            {},
            transport_retries=3,
        )

        assert type(model).__name__ == expected_class_name


class TestReasoningSpecMatching:
    """Validate model-pattern matching to unified thinking policy."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "anthropic:claude-sonnet-4-5",
            "azure:claude-sonnet-4-5",
            "azure:gpt-5",
            "google:gemini-3.1-flash-lite-preview",
            "openrouter:google/gemini-3-flash-preview",
        ],
    )
    def test_supported_models_have_reasoning_effort_mapping(
        self, model_name: str
    ) -> None:
        spec = match_reasoning_spec(ModelRef.parse(model_name))
        assert spec.efforts

    @pytest.mark.parametrize("effort", list(ReasoningEffort))
    def test_built_in_specs_map_efforts_to_unified_thinking(
        self, effort: ReasoningEffort
    ) -> None:
        spec = match_reasoning_spec(ModelRef.parse("azure:gpt-5"))
        assert spec.efforts[effort] == effort

    def test_fallback_spec_disables_reasoning(self) -> None:
        spec = match_reasoning_spec(ModelRef(provider="custom", model="some-new-model"))
        assert spec.efforts == {}


class TestBuildModelSettings:
    """Validate model settings generation for unified thinking."""

    def _thinking_spec(self) -> ReasoningSpec:
        return ReasoningSpec(
            efforts={
                ReasoningEffort.LOW: ReasoningEffort.LOW,
                ReasoningEffort.MEDIUM: ReasoningEffort.MEDIUM,
                ReasoningEffort.HIGH: ReasoningEffort.HIGH,
            },
        )

    def test_build_model_settings_uses_unified_thinking(
        self, backend: PydanticAIBackend
    ) -> None:
        settings = backend._build_model_settings(
            self._thinking_spec(),
            ReasoningEffort.MEDIUM,
            "azure:gpt-5",
            None,
        )
        assert settings == {"thinking": "medium"}

    def test_reasoning_effort_enum_maps_to_unified_thinking(
        self, backend: PydanticAIBackend
    ) -> None:
        settings = backend._build_model_settings(
            ReasoningSpec(
                efforts={ReasoningEffort.HIGH: ReasoningEffort.HIGH},
            ),
            ReasoningEffort.HIGH,
            "azure:gpt-5",
            None,
        )
        assert settings == {"thinking": "high"}

    def test_no_reasoning_returns_none(self, backend: PydanticAIBackend) -> None:
        settings = backend._build_model_settings(
            ReasoningSpec(),
            ReasoningEffort.MEDIUM,
            "azure:gpt-5",
            None,
        )
        assert settings is None

    def test_false_thinking_value_is_preserved(
        self, backend: PydanticAIBackend
    ) -> None:
        settings = backend._build_model_settings(
            ReasoningSpec(
                efforts={ReasoningEffort.LOW: False},
            ),
            ReasoningEffort.LOW,
            "azure:gpt-5",
            None,
        )
        assert settings == {"thinking": False}

    def test_timeout_applied_to_settings(self, backend: PydanticAIBackend) -> None:
        settings = backend._build_model_settings(
            self._thinking_spec(),
            ReasoningEffort.LOW,
            "azure:gpt-5",
            timeout=30.0,
        )
        assert settings == {"thinking": "low", "timeout": 30.0}

    def test_timeout_alone_creates_dict(self, backend: PydanticAIBackend) -> None:
        settings = backend._build_model_settings(
            ReasoningSpec(),
            ReasoningEffort.LOW,
            "azure:gpt-5",
            timeout=60.0,
        )
        assert settings == {"timeout": 60.0}

    def test_backend_options_merge(self, backend: PydanticAIBackend) -> None:
        settings = backend._build_model_settings(
            self._thinking_spec(),
            ReasoningEffort.HIGH,
            "azure:gpt-5",
            None,
            backend_options={"model_settings": {"temperature": 0.5}},
        )
        assert settings == {"thinking": "high", "temperature": 0.5}

    def test_backend_options_override_thinking(
        self, backend: PydanticAIBackend
    ) -> None:
        settings = backend._build_model_settings(
            self._thinking_spec(),
            ReasoningEffort.LOW,
            "azure:gpt-5",
            None,
            backend_options={"model_settings": {"thinking": "xhigh"}},
        )
        assert settings == {"thinking": "xhigh"}
