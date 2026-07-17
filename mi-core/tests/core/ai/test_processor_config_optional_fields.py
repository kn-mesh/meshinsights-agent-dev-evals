"""Tests for optional AIProcessorConfig fields and mixin fallbacks."""

from __future__ import annotations

import logging

import pytest
from pydantic import BaseModel

from mi.ai.mixins.base import AIProcessorConfig, AIProcessorMixin
from mi.core.objects import ProcessDataObject


class _DummyOutput(BaseModel):
    ok: bool = True


class _DummyMixin(AIProcessorMixin[ProcessDataObject, _DummyOutput]):
    name = "dummy"
    logger = logging.getLogger("test.ai.dummy")

    def __init__(self, config: AIProcessorConfig) -> None:
        self.config = config


def test_ai_processor_config_accepts_none_for_optional_fields() -> None:
    config = AIProcessorConfig(
        model="azure:gpt-5",
        backend=None,
        attach_usage=None,
        attach_response=None,
        timeout=None,
        retries=None,
        provider_options=None,
        backend_options=None,
    )

    assert config.backend is None
    assert config.attach_usage is None
    assert config.attach_response is None
    assert config.timeout is None
    assert config.retries is None
    assert config.provider_options is None
    assert config.backend_options is None


def test_ai_processor_config_retry_and_usage_limit_defaults() -> None:
    config = AIProcessorConfig(model="azure:gpt-5")

    assert config.retries is None
    assert config.transport_retries == 3
    assert config.tool_retries == 3
    assert config.output_retries is None
    assert config.input_tokens_limit is None
    assert config.output_tokens_limit is None
    assert config.total_tokens_limit is None
    assert config.tool_calls_limit is None
    assert config.count_tokens_before_request is False


def test_mixin_falls_back_to_defaults_when_optional_fields_are_none() -> None:
    config = AIProcessorConfig(
        model="azure:gpt-5",
        backend=None,
        attach_usage=None,
        attach_response=None,
        retries=None,
        provider_options=None,
        backend_options=None,
    )
    mixin = _DummyMixin(config)

    assert mixin._get_retries() == 3
    assert mixin._get_transport_retries() == 3
    assert mixin._get_tool_retries() == 3
    assert mixin._get_effective_output_retries() == 3
    assert mixin._should_attach_usage() is True
    assert mixin._should_attach_response() is True
    assert mixin._get_provider_options() == {}
    assert mixin._get_backend_options() == {}

    backend = mixin._resolve_backend()
    assert backend is not None
    assert getattr(backend, "BACKEND_NAME", None) == "pydantic_ai"


def test_mixin_uses_explicit_optional_values_when_provided() -> None:
    config = AIProcessorConfig(
        model="azure:gpt-5",
        attach_usage=False,
        attach_response=False,
        retries=7,
        provider_options={"deployment": "gpt5"},
        backend_options={"model_settings": {"temperature": 0.2}},
    )
    mixin = _DummyMixin(config)

    assert mixin._get_retries() == 7
    assert mixin._get_transport_retries() == 7
    assert mixin._get_tool_retries() == 7
    assert mixin._should_attach_usage() is False
    assert mixin._should_attach_response() is False
    assert mixin._get_provider_options() == {"deployment": "gpt5"}
    assert mixin._get_backend_options() == {"model_settings": {"temperature": 0.2}}


def test_split_retry_values_override_defaults_independently() -> None:
    config = AIProcessorConfig(
        model="azure:gpt-5",
        transport_retries=5,
        tool_retries=2,
        output_retries=1,
    )
    mixin = _DummyMixin(config)

    assert mixin._get_transport_retries() == 5
    assert mixin._get_tool_retries() == 2
    assert mixin._get_effective_output_retries() == 1


def test_usage_limits_are_backend_neutral_and_opt_in() -> None:
    config = AIProcessorConfig(
        model="azure:gpt-5",
        input_tokens_limit=1_000,
        output_tokens_limit=200,
        total_tokens_limit=1_100,
        tool_calls_limit=4,
        count_tokens_before_request=True,
    )
    limits = _DummyMixin(config)._get_usage_limits(request_limit=8)

    assert limits.request_limit == 8
    assert limits.input_tokens_limit == 1_000
    assert limits.output_tokens_limit == 200
    assert limits.total_tokens_limit == 1_100
    assert limits.tool_calls_limit == 4
    assert limits.count_tokens_before_request is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("transport_retries", 0),
        ("tool_retries", -1),
        ("input_tokens_limit", -1),
        ("output_tokens_limit", -1),
        ("total_tokens_limit", -1),
        ("tool_calls_limit", -1),
    ],
)
def test_retry_and_usage_limit_values_reject_invalid_negatives(
    field: str, value: int
) -> None:
    with pytest.raises(ValueError):
        AIProcessorConfig.model_validate({"model": "azure:gpt-5", field: value})
