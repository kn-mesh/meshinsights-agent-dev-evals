"""Provider-free execution tests for the pydantic-ai backend adapter."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage
from tenacity import wait_none

from mi.ai.backends.base import (
    AIUsage,
    AIUsageLimits,
    AgentRequest,
    WorkflowRequest,
)
from mi.ai.backends import pydantic_ai_backend as backend_module
from mi.ai.backends.pydantic_ai_backend import PydanticAIBackend
from mi.ai.capabilities import AICapability, AISkill
from mi.ai.message import UserMessage
from mi.ai.model_config import ModelRef, ReasoningEffort, ReasoningSpec
from mi.ai.tools import Tool, ToolContext, ToolSet
from mi.core import ProcessDataObject


class ExampleOutput(BaseModel):
    """Structured output used by the local test model."""

    value: int


def test_agent_execution_uses_v2_result_and_retry_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise v2 usage properties and per-category retry configuration."""
    backend = PydanticAIBackend()
    test_model = TestModel(custom_output_args={"value": 42})
    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: (test_model, "test:test"),
    )

    result = backend.run_agent(
        AgentRequest(
            model=ModelRef(provider="test", model="test"),
            system_prompt="Return the requested value.",
            user_message=UserMessage().add_text("Return a value."),
            output_schema=ExampleOutput,
            tools=[],
            reasoning_spec=ReasoningSpec(),
            reasoning_effort=ReasoningEffort.MEDIUM,
            transport_retries=1,
            tool_retries=2,
            output_retries=4,
            max_turns=3,
        )
    )

    assert result.output == ExampleOutput(value=42)
    assert result.usage.requests == 1
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0


def test_usage_limits_map_all_supported_fields() -> None:
    backend = PydanticAIBackend()

    limits = backend._build_usage_limits(
        AIUsageLimits(
            request_limit=9,
            tool_calls_limit=4,
            input_tokens_limit=1_000,
            output_tokens_limit=200,
            total_tokens_limit=1_100,
            count_tokens_before_request=True,
        )
    )

    assert limits.request_limit == 9
    assert limits.tool_calls_limit == 4
    assert limits.input_tokens_limit == 1_000
    assert limits.output_tokens_limit == 200
    assert limits.total_tokens_limit == 1_100
    assert limits.count_tokens_before_request is True


def test_direct_usage_limit_check_enforces_token_budgets() -> None:
    backend = PydanticAIBackend()

    with pytest.raises(UsageLimitExceeded, match="output_tokens_limit"):
        backend._check_direct_usage_limits(
            AIUsageLimits(output_tokens_limit=10),
            AIUsage(requests=1, input_tokens=20, output_tokens=11),
        )


def test_agent_token_limit_failure_is_not_retried_as_a_whole_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    test_model = TestModel(custom_output_args={"value": 42})
    request_count = 0
    original_request = test_model.request

    async def counting_request(
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        nonlocal request_count
        request_count += 1
        return await original_request(
            messages,
            model_settings,
            model_request_parameters,
        )

    monkeypatch.setattr(test_model, "request", counting_request)
    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: (test_model, "test:test"),
    )

    with pytest.raises(UsageLimitExceeded, match="output_tokens_limit"):
        backend.run_agent(
            AgentRequest(
                model=ModelRef(provider="test", model="test"),
                system_prompt="Return the requested value.",
                user_message=UserMessage().add_text("Return a value."),
                output_schema=ExampleOutput,
                tools=[],
                reasoning_spec=ReasoningSpec(),
                reasoning_effort=ReasoningEffort.MEDIUM,
                max_turns=3,
                transport_retries=3,
                tool_retries=3,
                usage_limits=AIUsageLimits(output_tokens_limit=1),
            )
        )

    assert request_count == 1


def test_agent_tool_call_limit_prevents_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    test_model = TestModel(
        call_tools="all",
        custom_output_args={"value": 42},
    )
    tool_call_count = 0

    def do_work() -> str:
        nonlocal tool_call_count
        tool_call_count += 1
        return "done"

    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: (test_model, "test:test"),
    )

    with pytest.raises(UsageLimitExceeded, match="tool_calls_limit"):
        backend.run_agent(
            AgentRequest(
                model=ModelRef(provider="test", model="test"),
                system_prompt="Use the available tool.",
                user_message=UserMessage().add_text("Do the work."),
                output_schema=ExampleOutput,
                tools=[Tool(function=do_work)],
                reasoning_spec=ReasoningSpec(),
                reasoning_effort=ReasoningEffort.MEDIUM,
                max_turns=3,
                transport_retries=1,
                usage_limits=AIUsageLimits(tool_calls_limit=0),
            )
        )

    assert tool_call_count == 0


def test_retry_transport_retries_only_transient_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        status_code = 503 if attempts < 3 else 200
        return httpx.Response(status_code, request=request)

    monkeypatch.setattr(
        backend_module,
        "wait_retry_after",
        lambda **_kwargs: wait_none(),
    )
    transport = backend._build_retry_transport(
        3,
        wrapped=httpx.MockTransport(handler),
    )

    async def send_request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://example.test")

    response = asyncio.run(send_request())

    assert response.status_code == 200
    assert attempts == 3


def test_retry_transport_does_not_retry_non_transient_client_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, request=request)

    monkeypatch.setattr(
        backend_module,
        "wait_retry_after",
        lambda **_kwargs: wait_none(),
    )
    transport = backend._build_retry_transport(
        3,
        wrapped=httpx.MockTransport(handler),
    )

    async def send_request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get("https://example.test")

    response = asyncio.run(send_request())

    assert response.status_code == 401
    assert attempts == 1


def test_workflow_retries_output_validation_separately_from_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    responses = iter(
        [
            ModelResponse(
                parts=[TextPart("not-json")],
                usage=RequestUsage(input_tokens=10, output_tokens=2),
            ),
            ModelResponse(
                parts=[TextPart('{"value": 42}')],
                usage=RequestUsage(input_tokens=10, output_tokens=4),
            ),
        ]
    )
    request_count = 0

    def fake_model_request_sync(**_kwargs: object) -> ModelResponse:
        nonlocal request_count
        request_count += 1
        return next(responses)

    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: ("test", "test:test"),
    )
    monkeypatch.setattr(backend_module, "model_request_sync", fake_model_request_sync)

    result = backend.run_workflow(
        WorkflowRequest(
            model=ModelRef(provider="test", model="test"),
            system_prompt="Return the requested value.",
            user_message=UserMessage().add_text("Return a value."),
            output_schema=ExampleOutput,
            reasoning_spec=ReasoningSpec(),
            reasoning_effort=ReasoningEffort.MEDIUM,
            transport_retries=3,
            output_retries=1,
        )
    )

    assert result.output == ExampleOutput(value=42)
    assert request_count == 2


def test_workflow_does_not_treat_transport_failure_as_output_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = PydanticAIBackend()
    request_count = 0

    def failing_model_request_sync(**_kwargs: object) -> ModelResponse:
        nonlocal request_count
        request_count += 1
        raise RuntimeError("transport failed")

    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: ("test", "test:test"),
    )
    monkeypatch.setattr(
        backend_module,
        "model_request_sync",
        failing_model_request_sync,
    )

    with pytest.raises(RuntimeError, match="transport failed"):
        backend.run_workflow(
            WorkflowRequest(
                model=ModelRef(provider="test", model="test"),
                system_prompt="Return the requested value.",
                user_message=UserMessage().add_text("Return a value."),
                output_schema=ExampleOutput,
                reasoning_spec=ReasoningSpec(),
                reasoning_effort=ReasoningEffort.MEDIUM,
                transport_retries=3,
                output_retries=5,
            )
        )

    assert request_count == 1


def test_agent_maps_eager_capabilities_and_reusable_toolsets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose eager capability and top-level toolset instructions immediately."""
    backend = PydanticAIBackend()
    observed: dict[str, object] = {}

    def capability_tool() -> str:
        return "capability result"

    def toolset_tool() -> str:
        return "toolset result"

    def model_function(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        _ = messages
        observed["tools"] = {
            tool.name: tool.defer_loading for tool in info.function_tools
        }
        observed["instructions"] = info.instructions
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"value": 42},
                    tool_call_id="result",
                )
            ]
        )

    model = FunctionModel(model_function)
    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: (model, "test:test"),
    )

    result = backend.run_agent(
        AgentRequest(
            model=ModelRef(provider="test", model="test"),
            system_prompt="Return a value.",
            user_message=UserMessage().add_text("Return 42."),
            output_schema=ExampleOutput,
            tools=[],
            toolsets=[
                ToolSet(
                    tools=[Tool(function=toolset_tool)],
                    instructions="Toolset instructions.",
                )
            ],
            capabilities=[
                AICapability(
                    id="diagnostics",
                    instructions="Capability instructions.",
                    tools=[Tool(function=capability_tool)],
                )
            ],
            reasoning_spec=ReasoningSpec(),
            reasoning_effort=ReasoningEffort.MEDIUM,
            max_turns=3,
            transport_retries=1,
        )
    )

    assert result.output == ExampleOutput(value=42)
    assert observed["tools"] == {
        "toolset_tool": False,
        "capability_tool": False,
    }
    assert "Toolset instructions." in str(observed["instructions"])
    assert "Capability instructions." in str(observed["instructions"])


def test_agent_skill_uses_progressive_disclosure_before_running_its_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep skill tools deferred until load_capability activates the skill."""
    backend = PydanticAIBackend()
    tool_called = False
    expected_context = ToolContext(data_object=ProcessDataObject())
    observed_defer_states: list[bool] = []
    request_number = 0

    def specialist_tool(ctx: ToolContext[ProcessDataObject]) -> str:
        nonlocal tool_called
        assert ctx is expected_context
        tool_called = True
        return "specialist evidence"

    skill = AISkill(
        name="specialist-review",
        description="Use when specialist evidence is required.",
        instructions="Follow the specialist review procedure.",
        tools=[Tool(function=specialist_tool)],
    )

    def model_function(
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        nonlocal request_number
        _ = messages
        request_number += 1
        specialist_definition = next(
            tool for tool in info.function_tools if tool.name == "specialist_tool"
        )
        observed_defer_states.append(specialist_definition.defer_loading)

        if request_number == 1:
            assert "specialist-review" in str(info.instructions)
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "load_capability",
                        {"id": "specialist-review"},
                        tool_call_id="load-skill",
                    )
                ]
            )
        if request_number == 2:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "specialist_tool",
                        {},
                        tool_call_id="run-specialist",
                    )
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    info.output_tools[0].name,
                    {"value": 42},
                    tool_call_id="result",
                )
            ]
        )

    model = FunctionModel(model_function)
    monkeypatch.setattr(
        backend,
        "_resolve_model",
        lambda *_args, **_kwargs: (model, "test:test"),
    )

    result = backend.run_agent(
        AgentRequest(
            model=ModelRef(provider="test", model="test"),
            system_prompt="Use specialist evidence when needed.",
            user_message=UserMessage().add_text("Perform the review."),
            output_schema=ExampleOutput,
            tools=[],
            capabilities=[skill.as_capability()],
            reasoning_spec=ReasoningSpec(),
            reasoning_effort=ReasoningEffort.MEDIUM,
            max_turns=4,
            transport_retries=1,
        ),
        deps=SimpleNamespace(context=expected_context),
    )

    assert result.output == ExampleOutput(value=42)
    assert tool_called is True
    assert observed_defer_states == [True, False, False]
