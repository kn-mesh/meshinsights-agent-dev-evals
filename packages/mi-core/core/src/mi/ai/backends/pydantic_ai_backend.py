"""pydantic-ai backend adapter for mi.ai."""

from __future__ import annotations

import base64
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
import functools
import inspect
import os
import time
from typing import Any, TypeVar, cast, get_type_hints

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRetries, FunctionToolset, RunContext
from pydantic_ai.capabilities import (
    Capability as PydanticCapability,
    Hooks,
)
from pydantic_ai.direct import model_request_sync
from pydantic_ai.messages import (
    BinaryImage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestContext, ModelRequestParameters
from pydantic_ai.output import OutputObjectDefinition
from pydantic_ai.retries import (
    AsyncTenacityTransport,
    RetryConfig,
    wait_retry_after,
)
from pydantic_ai.tools import Tool as PydanticTool
from pydantic_ai.usage import RunUsage, UsageLimits
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mi.ai.backends.base import (
    AIBackend,
    AIModelRequestUsage,
    AIUsage,
    AIUsageLimits,
    AgentRequest,
    AgentResult,
    WorkflowRequest,
    WorkflowResult,
)
from mi.ai.capabilities import AICapability
from mi.ai.message import ImageContent, TextContent, UserMessage
from mi.ai.model_config import ReasoningEffort, ReasoningSpec
from mi.ai.review import (
    AIReviewError,
    agent_request_review,
    serialize_messages,
    workflow_request_review,
)
from mi.ai.tools import Tool, ToolSet, normalize_tool_output

OutputT = TypeVar("OutputT", bound=BaseModel)

_TRANSPORT_OBSERVATION_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "mi_ai_transport_observation_context", default=None
)


class _ObservedAsyncTenacityTransport(AsyncTenacityTransport):
    """Record each HTTP transport attempt when this adapter owns the transport."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        attempt_number = 0

        @retry(**cast(Any, self.config))
        async def execute(req: httpx.Request) -> httpx.Response:
            nonlocal attempt_number
            attempt_number += 1
            started = time.monotonic()
            response: httpx.Response | None = None
            try:
                response = await self.wrapped.handle_async_request(req)
                response.request = req
                if self.validate_response:
                    try:
                        self.validate_response(response)
                    except Exception:
                        await response.aclose()
                        raise
                self._record_attempt(
                    request=req,
                    response=response,
                    error=None,
                    attempt_number=attempt_number,
                    duration_seconds=time.monotonic() - started,
                )
                return response
            except Exception as error:
                self._record_attempt(
                    request=req,
                    response=response,
                    error=error,
                    attempt_number=attempt_number,
                    duration_seconds=time.monotonic() - started,
                )
                raise

        return await execute(request)

    @staticmethod
    def _record_attempt(
        *,
        request: httpx.Request,
        response: httpx.Response | None,
        error: Exception | None,
        attempt_number: int,
        duration_seconds: float,
    ) -> None:
        context = _TRANSPORT_OBSERVATION_CONTEXT.get()
        if context is None:
            return
        status_code = response.status_code if response is not None else None
        response_headers = response.headers if response is not None else {}
        context["attempts"].append(
            {
                "attempt_number": attempt_number,
                "duration_seconds": duration_seconds,
                "terminal_status": "succeeded" if error is None else "failed",
                "retry_category": _transport_retry_category(error, status_code),
                "status_code": status_code,
                "configured_request_timeout_seconds": context.get("timeout_seconds"),
                "provider_request_id": next(
                    (
                        response_headers.get(name)
                        for name in (
                            "x-request-id",
                            "apim-request-id",
                            "request-id",
                            "x-ms-request-id",
                        )
                        if response_headers.get(name)
                    ),
                    None,
                ),
                "client_request_id": next(
                    (
                        request.headers.get(name)
                        for name in ("x-ms-client-request-id", "x-request-id")
                        if request.headers.get(name)
                    ),
                    None,
                ),
                "error_type": type(error).__name__ if error is not None else None,
                "error": str(error)[:1000] if error is not None else None,
            }
        )


def _transport_retry_category(
    error: Exception | None, status_code: int | None
) -> str | None:
    if error is None:
        return None
    if status_code == 429:
        return "rate_limit"
    if status_code is not None and status_code >= 500:
        return "server_error"
    if status_code is not None:
        return "http_status"
    if isinstance(error, httpx.TimeoutException):
        return "timeout"
    if isinstance(error, httpx.ConnectError):
        return "connection"
    if isinstance(error, httpx.TransportError):
        return "transport"
    return "unknown"


class PydanticAIBackend(AIBackend):
    """Executes mi.ai requests via pydantic-ai."""

    BACKEND_NAME = "pydantic_ai"
    _RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504, 507})

    def __init__(self) -> None:
        self._retrying_http_clients: dict[int, httpx.AsyncClient] = {}

    def run_workflow(
        self, request: WorkflowRequest[OutputT]
    ) -> WorkflowResult[OutputT]:
        operation_started = time.monotonic()
        operation_started_at = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        model_calls: list[dict[str, Any]] = []
        model, settings_id = self._resolve_model(
            request.model.provider,
            request.model.model,
            request.provider_options,
            backend_options=request.backend_options,
            transport_retries=request.transport_retries,
        )
        model_settings = self._build_model_settings(
            request.reasoning_spec,
            request.reasoning_effort,
            settings_id,
            request.timeout,
            request.backend_options,
        )
        params = ModelRequestParameters(
            output_mode="native",
            output_object=OutputObjectDefinition(
                json_schema=request.output_schema.model_json_schema(),
                name=request.output_schema.__name__,
                description=request.output_schema.__doc__,
                strict=True,
            ),
        )

        last_exc: ValueError | None = None
        usage = AIUsage()
        request_message = ModelRequest(
            parts=[
                SystemPromptPart(content=request.system_prompt),
                UserPromptPart(content=self._build_user_content(request.user_message)),
            ]
        )
        validation_attempts: list[dict[str, Any]] = []
        for attempt in range(request.output_retries + 1):
            response = None
            raw_text = None
            try:
                call_started = time.monotonic()
                call_started_at = datetime.now(timezone.utc).isoformat(
                    timespec="microseconds"
                )
                transport_context = {
                    "attempts": [],
                    "timeout_seconds": request.timeout,
                }
                transport_attempts: list[dict[str, Any]] = []
                transport_token = _TRANSPORT_OBSERVATION_CONTEXT.set(transport_context)
                try:
                    try:
                        response = model_request_sync(
                            model=model,
                            messages=[request_message],
                            model_settings=model_settings,
                            model_request_parameters=params,
                        )
                    finally:
                        transport_attempts = list(transport_context["attempts"])
                        _TRANSPORT_OBSERVATION_CONTEXT.reset(transport_token)
                except Exception as call_error:
                    model_calls.append(
                        self._model_call_performance(
                            sequence=len(model_calls) + 1,
                            output_attempt=attempt + 1,
                            started_at_utc=call_started_at,
                            duration_seconds=time.monotonic() - call_started,
                            status="failed",
                            timeout_seconds=request.timeout,
                            transport_attempts_configured=request.transport_retries,
                            transport_attempts=transport_attempts,
                            error=call_error,
                        )
                    )
                    raise
                model_calls.append(
                    self._model_call_performance(
                        sequence=len(model_calls) + 1,
                        output_attempt=attempt + 1,
                        started_at_utc=call_started_at,
                        duration_seconds=time.monotonic() - call_started,
                        status="completed",
                        timeout_seconds=request.timeout,
                        transport_attempts_configured=request.transport_retries,
                        transport_attempts=transport_attempts,
                        response=response,
                    )
                )
                usage = self._combine_usage(
                    usage,
                    self._extract_direct_usage(
                        response,
                        provider=request.model.provider,
                        model=request.model.model,
                    ),
                )
                self._check_direct_usage_limits(request.usage_limits, usage)
                raw_text = self._extract_text(response)
                if raw_text is None:
                    raise ValueError("Missing text output in model response.")
                output = request.output_schema.model_validate_json(raw_text)
                if request.capture_review:
                    validation_attempts.append(
                        {
                            "attempt": attempt + 1,
                            "valid": True,
                            "raw_text": raw_text,
                            "messages": serialize_messages([request_message, response]),
                        }
                    )
                return WorkflowResult(
                    output=output,
                    usage=usage,
                    performance=self._operation_performance(
                        kind="workflow",
                        started_at_utc=operation_started_at,
                        duration_seconds=time.monotonic() - operation_started,
                        model_calls=model_calls,
                    ),
                    review=(
                        {
                            "request": workflow_request_review(request),
                            "validation_attempts": validation_attempts,
                            "parsed_output": output.model_dump(mode="json"),
                        }
                        if request.capture_review
                        else {}
                    ),
                )
            except ValueError as exc:
                last_exc = exc
                if request.capture_review:
                    validation_attempts.append(
                        {
                            "attempt": attempt + 1,
                            "valid": False,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "raw_text": raw_text,
                            "messages": (
                                serialize_messages([request_message, response])
                                if response is not None
                                else serialize_messages([request_message])
                            ),
                        }
                    )
                if attempt >= request.output_retries:
                    performance = self._operation_performance(
                        kind="workflow",
                        started_at_utc=operation_started_at,
                        duration_seconds=time.monotonic() - operation_started,
                        model_calls=model_calls,
                    )
                    if request.capture_review:
                        error = AIReviewError(
                            str(exc),
                            review={
                                "request": workflow_request_review(request),
                                "validation_attempts": validation_attempts,
                                "capture_status": "partial",
                            },
                        )
                        setattr(error, "performance", performance)
                        raise error from exc
                    setattr(exc, "performance", performance)
                    raise
        raise (
            last_exc
            if last_exc is not None
            else ValueError("Workflow execution failed")
        )

    def run_agent(
        self, request: AgentRequest[OutputT], *, deps: Any | None = None
    ) -> AgentResult[OutputT]:
        operation_started = time.monotonic()
        operation_started_at = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        model, settings_id = self._resolve_model(
            request.model.provider,
            request.model.model,
            request.provider_options,
            backend_options=request.backend_options,
            transport_retries=request.transport_retries,
        )
        model_settings = self._build_model_settings(
            request.reasoning_spec,
            request.reasoning_effort,
            settings_id,
            request.timeout,
            request.backend_options,
        )
        pydantic_tools: list[PydanticTool[Any]] = [
            self._build_tool(tool) for tool in request.tools
        ]
        pydantic_toolsets = [
            self._build_toolset(toolset) for toolset in request.toolsets
        ]
        pydantic_capabilities: list[Any] = [
            self._build_capability(capability) for capability in request.capabilities
        ]
        if request.finalize_on_tool_call_limit:
            tool_calls_limit = request.usage_limits.tool_calls_limit
            if tool_calls_limit is None:
                raise ValueError(
                    "finalize_on_tool_call_limit requires tool_calls_limit"
                )

            async def hide_tools_at_limit(
                ctx: RunContext[Any],
                request_context: ModelRequestContext,
            ) -> ModelRequestContext:
                if ctx.usage.tool_calls >= tool_calls_limit:
                    request_context.model_request_parameters = replace(
                        request_context.model_request_parameters,
                        function_tools=[],
                    )
                return request_context

            pydantic_capabilities.append(
                Hooks(before_model_request=hide_tools_at_limit)
            )
            if model_settings is None:
                model_settings = {}
            else:
                model_settings = dict(model_settings)
            model_settings["parallel_tool_calls"] = False
            model_settings = cast(Any, model_settings)
        agent_retries: int | AgentRetries = request.tool_retries
        if request.output_retries is not None:
            agent_retries = AgentRetries(
                tools=request.tool_retries,
                output=request.output_retries,
            )

        agent = Agent[Any, OutputT](
            model,
            deps_type=type(deps) if deps is not None else object,
            output_type=request.output_schema,
            system_prompt=request.system_prompt,
            model_settings=model_settings,
            tools=pydantic_tools,
            toolsets=pydantic_toolsets or None,
            capabilities=pydantic_capabilities or None,
            retries=agent_retries,
            tool_timeout=request.tool_timeout,
            # Preserve v1 behavior: do not execute sibling function tools once
            # a valid structured output has completed the run.
            end_strategy="early",
        )

        transport_context = {"attempts": [], "timeout_seconds": request.timeout}
        transport_attempts: list[dict[str, Any]] = []
        transport_token = _TRANSPORT_OBSERVATION_CONTEXT.set(transport_context)
        try:
            try:
                result = agent.run_sync(
                    self._build_user_content(request.user_message),
                    deps=deps,
                    usage_limits=self._build_usage_limits(
                        request.usage_limits,
                        default_request_limit=request.max_turns,
                    ),
                )
            finally:
                transport_attempts = list(transport_context["attempts"])
                _TRANSPORT_OBSERVATION_CONTEXT.reset(transport_token)
        except Exception as error:
            performance = self._operation_performance(
                kind="agent",
                started_at_utc=operation_started_at,
                duration_seconds=time.monotonic() - operation_started,
                model_calls=[
                    self._model_call_performance(
                        sequence=1,
                        output_attempt=None,
                        started_at_utc=operation_started_at,
                        duration_seconds=time.monotonic() - operation_started,
                        status="failed",
                        timeout_seconds=request.timeout,
                        transport_attempts_configured=request.transport_retries,
                        transport_attempts=transport_attempts,
                        error=error,
                    )
                ],
            )
            if request.capture_review:
                review_error = AIReviewError(
                    str(error),
                    review={
                        "request": agent_request_review(request),
                        "messages": [],
                        "capture_status": "partial",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                )
                setattr(review_error, "performance", performance)
                raise review_error from error
            setattr(error, "performance", performance)
            raise
        usage = result.usage
        model_requests = tuple(
            self._model_request_usage(
                message,
                provider=request.model.provider,
                model=request.model.model,
            )
            for message in result.all_messages()
            if isinstance(message, ModelResponse) and message.usage.has_values()
        )
        duration_seconds = time.monotonic() - operation_started
        return AgentResult(
            output=result.output,
            usage=AIUsage(
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=getattr(usage, "cache_read_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_write_tokens", 0) or 0,
                reasoning_tokens=self._reasoning_tokens(getattr(usage, "details", {})),
                tool_calls=getattr(usage, "tool_calls", 0) or 0,
                model_requests=model_requests,
            ),
            performance=self._operation_performance(
                kind="agent",
                started_at_utc=operation_started_at,
                duration_seconds=duration_seconds,
                model_calls=[
                    self._model_call_performance(
                        sequence=1,
                        output_attempt=None,
                        started_at_utc=operation_started_at,
                        duration_seconds=duration_seconds,
                        status="completed",
                        timeout_seconds=request.timeout,
                        transport_attempts_configured=request.transport_retries,
                        transport_attempts=transport_attempts,
                        response=result,
                        observed_model_requests=usage.requests,
                    )
                ],
            ),
            review=(
                {
                    "request": agent_request_review(request),
                    "messages": serialize_messages(result.all_messages()),
                    "parsed_output": result.output.model_dump(mode="json"),
                    "provider": {
                        "response_id": getattr(result, "response_id", None),
                    },
                }
                if request.capture_review
                else {}
            ),
        )

    @staticmethod
    def _operation_performance(
        *,
        kind: str,
        started_at_utc: str,
        duration_seconds: float,
        model_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": kind,
            "started_at_utc": started_at_utc,
            "duration_seconds": duration_seconds,
            "model_calls": list(model_calls),
        }

    @staticmethod
    def _model_call_performance(
        *,
        sequence: int,
        output_attempt: int | None,
        started_at_utc: str,
        duration_seconds: float,
        status: str,
        timeout_seconds: float | None,
        transport_attempts_configured: int,
        transport_attempts: list[dict[str, Any]] | None = None,
        response: Any | None = None,
        error: Exception | None = None,
        observed_model_requests: int = 1,
    ) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "output_attempt": output_attempt,
            "started_at_utc": started_at_utc,
            "duration_seconds": duration_seconds,
            "status": status,
            "timeout_seconds": timeout_seconds,
            "duration_exceeded_configured_timeout": (
                timeout_seconds is not None and duration_seconds > timeout_seconds
            ),
            "transport_attempts_configured": transport_attempts_configured,
            "transport_attempts_observed": (
                len(transport_attempts) if transport_attempts else None
            ),
            "transport_attempts": list(transport_attempts or []),
            "observed_model_requests": observed_model_requests,
            "provider_response_id": (
                getattr(response, "response_id", None) if response is not None else None
            ),
            "error_type": type(error).__name__ if error is not None else None,
            "error": str(error) if error is not None else None,
        }

    def _resolve_model(
        self,
        provider: str,
        model: str,
        provider_options: dict[str, Any],
        *,
        backend_options: dict[str, Any] | None = None,
        transport_retries: int | None = None,
    ) -> tuple[Any, str]:
        """Resolve provider + model + options into a pydantic-ai model reference.

        Returns:
            A ``(pydantic_ai_model, settings_model_id)`` tuple where:

            * *pydantic_ai_model* is the value passed to ``model_request_sync``
              or ``Agent`` — either a plain string (e.g. ``"azure:gpt-5"``,
              ``"openrouter:google/gemini-3-flash-preview"``) or a
              ``pydantic_ai.models.Model`` instance (e.g. ``AnthropicModel``
              configured for Azure Foundry).
            * *settings_model_id* is a canonical ``provider:model`` string used
              only for settings-builder prefix matching (e.g.
              ``"azure:claude-sonnet-4-5"``).
        """
        http_client = (
            self._get_retrying_http_client(transport_retries)
            if transport_retries is not None
            else None
        )
        model_api = (backend_options or {}).get("model_api")
        if model_api is not None and not isinstance(model_api, str):
            raise ValueError("backend_options.model_api must be a string.")

        if provider == "azure":
            deployment = provider_options.get("deployment")
            name = deployment if isinstance(deployment, str) and deployment else model
            settings_id = f"azure:{name}"

            if model.startswith("claude"):
                self._validate_model_api(
                    model_api,
                    expected="anthropic_messages",
                    provider=provider,
                    model=model,
                )
                return (
                    self._build_foundry_model(
                        model,
                        provider_options,
                        http_client=http_client,
                    ),
                    settings_id,
                )

            if model_api == "openai_responses":
                return (
                    self._build_azure_model(
                        name,
                        http_client,
                        model_api=model_api,
                    ),
                    settings_id,
                )

            self._validate_model_api(
                model_api,
                expected="openai_chat_completions",
                provider=provider,
                model=model,
            )
            if http_client is not None:
                return (
                    self._build_azure_model(
                        name,
                        http_client,
                        model_api="openai_chat_completions",
                    ),
                    settings_id,
                )

            return f"azure:{name}", settings_id

        if provider == "google":
            self._validate_model_api(
                model_api,
                expected="google_generate_content",
                provider=provider,
                model=model,
            )
            return (
                self._build_google_model(
                    model,
                    provider_options,
                    http_client=http_client,
                ),
                f"google:{model}",
            )

        if provider == "anthropic":
            self._validate_model_api(
                model_api,
                expected="anthropic_messages",
                provider=provider,
                model=model,
            )
            if http_client is not None:
                return (
                    self._build_anthropic_model(model, http_client),
                    f"anthropic:{model}",
                )

        if provider == "openrouter":
            self._validate_model_api(
                model_api,
                expected="openai_chat_completions",
                provider=provider,
                model=model,
            )
            if http_client is not None:
                return (
                    self._build_openrouter_model(model, http_client),
                    f"openrouter:{model}",
                )

        model_str = f"{provider}:{model}"
        return model_str, model_str

    def _build_foundry_model(
        self,
        model: str,
        provider_options: dict[str, Any],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> Any:
        """Build an ``AnthropicModel`` configured for Microsoft Azure Foundry.

        Credentials are resolved automatically by the ``anthropic`` SDK from
        environment variables ``ANTHROPIC_FOUNDRY_API_KEY`` and either
        ``ANTHROPIC_FOUNDRY_RESOURCE`` or ``ANTHROPIC_FOUNDRY_BASE_URL``
        (mutually exclusive).
        """
        from anthropic import AsyncAnthropicFoundry
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        class FoundryAnthropicModel(AnthropicModel):
            """Preserve Foundry billing fields discarded by generic normalization."""

            def _process_response(
                self,
                response: Any,
                model_request_parameters: Any,
                model_settings: Any,
            ) -> ModelResponse:
                mapped = super()._process_response(
                    response,
                    model_request_parameters,
                    model_settings,
                )
                response_usage = response.usage
                cache_creation = getattr(response_usage, "cache_creation", None)
                if cache_creation is not None:
                    mapped.usage.details["cache_write_5m_tokens"] = (
                        getattr(cache_creation, "ephemeral_5m_input_tokens", 0) or 0
                    )
                    mapped.usage.details["cache_write_1h_tokens"] = (
                        getattr(cache_creation, "ephemeral_1h_input_tokens", 0) or 0
                    )
                provider_details = dict(mapped.provider_details or {})
                for key in ("inference_geo", "service_tier", "speed"):
                    value = getattr(response_usage, key, None)
                    if value is not None:
                        provider_details[key] = value
                mapped.provider_details = provider_details or None
                return mapped

        if http_client is None:
            foundry_client = AsyncAnthropicFoundry()
        else:
            foundry_client = AsyncAnthropicFoundry(
                http_client=http_client,
                max_retries=0,
            )
        anthropic_provider = AnthropicProvider(anthropic_client=foundry_client)
        return FoundryAnthropicModel(model, provider=anthropic_provider)

    def _build_google_model(
        self,
        model: str,
        provider_options: dict[str, Any],
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> Any:
        """Build a direct Google Gemini model using the Generative Language API."""
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider
        from google.genai.types import HttpRetryOptions

        api_key = provider_options.get("api_key")
        retry_options = (
            HttpRetryOptions(attempts=1) if http_client is not None else None
        )

        if isinstance(api_key, str) and api_key:
            google_provider = GoogleProvider(
                api_key=api_key,
                http_client=http_client,
                retry_options=retry_options,
            )
        else:
            # The runtime signature supports environment-based credential lookup,
            # but the public overloads only describe explicit key/client usage.
            google_provider = GoogleProvider(  # pyright: ignore[reportCallIssue]
                http_client=http_client,
                retry_options=retry_options,
            )
        return GoogleModel(model, provider=google_provider)

    def _build_azure_model(
        self,
        model: str,
        http_client: httpx.AsyncClient | None,
        *,
        model_api: str,
    ) -> Any:
        from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
        from pydantic_ai.providers.azure import AzureProvider

        provider_kwargs: dict[str, Any] = {}
        if http_client is not None:
            provider_kwargs["http_client"] = http_client
        if model_api == "openai_responses":
            provider_kwargs["azure_endpoint"] = self._azure_responses_endpoint()
        provider = AzureProvider(**provider_kwargs)
        if http_client is not None:
            provider.client.max_retries = 0
        if model_api == "openai_responses":
            return OpenAIResponsesModel(model, provider=provider)
        return OpenAIChatModel(model, provider=provider)

    def _azure_responses_endpoint(self) -> str:
        """Return the configured Azure endpoint normalized to its v1 API root."""
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        if not endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT is required for Azure Responses API models."
            )
        if endpoint.endswith("/openai/v1") or endpoint.endswith("/v1"):
            return endpoint
        if endpoint.endswith("/openai"):
            return f"{endpoint}/v1"
        return f"{endpoint}/openai/v1"

    def _validate_model_api(
        self,
        model_api: str | None,
        *,
        expected: str,
        provider: str,
        model: str,
    ) -> None:
        """Reject project metadata that conflicts with provider routing."""
        if model_api is not None and model_api != expected:
            raise ValueError(
                f"Model {provider}:{model} requires model_api={expected}; "
                f"got {model_api}."
            )

    def _build_anthropic_model(self, model: str, http_client: httpx.AsyncClient) -> Any:
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(  # pyright: ignore[reportCallIssue]
            http_client=http_client
        )
        provider.client.max_retries = 0
        return AnthropicModel(model, provider=provider)

    def _build_openrouter_model(
        self, model: str, http_client: httpx.AsyncClient
    ) -> Any:
        from pydantic_ai.models.openrouter import OpenRouterModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider(  # pyright: ignore[reportCallIssue]
            http_client=http_client
        )
        provider.client.max_retries = 0
        return OpenRouterModel(model, provider=provider)

    def _get_retrying_http_client(self, attempts: int) -> httpx.AsyncClient:
        client = self._retrying_http_clients.get(attempts)
        if client is None:
            client = httpx.AsyncClient(
                transport=self._build_retry_transport(attempts),
                timeout=httpx.Timeout(600, connect=5),
            )
            self._retrying_http_clients[attempts] = client
        return client

    def _build_retry_transport(
        self,
        attempts: int,
        *,
        wrapped: httpx.AsyncBaseTransport | None = None,
    ) -> AsyncTenacityTransport:
        if attempts < 1:
            raise ValueError("Transport retry attempts must be at least 1")

        return _ObservedAsyncTenacityTransport(
            config=RetryConfig(
                retry=retry_if_exception_type(
                    (httpx.TransportError, httpx.HTTPStatusError)
                ),
                wait=wait_retry_after(
                    fallback_strategy=wait_exponential(multiplier=1, max=30),
                    max_wait=60,
                ),
                stop=stop_after_attempt(attempts),
                reraise=True,
            ),
            wrapped=wrapped,
            validate_response=self._validate_retryable_response,
        )

    def _validate_retryable_response(self, response: httpx.Response) -> None:
        if response.status_code in self._RETRYABLE_STATUS_CODES:
            response.raise_for_status()

    def _build_usage_limits(
        self,
        limits: AIUsageLimits,
        *,
        default_request_limit: int | None = None,
    ) -> UsageLimits:
        return UsageLimits(
            request_limit=(
                limits.request_limit
                if limits.request_limit is not None
                else default_request_limit
            ),
            tool_calls_limit=limits.tool_calls_limit,
            input_tokens_limit=limits.input_tokens_limit,
            output_tokens_limit=limits.output_tokens_limit,
            total_tokens_limit=limits.total_tokens_limit,
            count_tokens_before_request=limits.count_tokens_before_request,
        )

    def _check_direct_usage_limits(self, limits: AIUsageLimits, usage: AIUsage) -> None:
        self._build_usage_limits(limits).check_tokens(
            RunUsage(
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
            )
        )

    def _build_model_settings(
        self,
        spec: ReasoningSpec,
        effort: ReasoningEffort,
        _model_id: str,
        timeout: float | None,
        backend_options: dict[str, Any] | None = None,
    ) -> Any:
        """Build pydantic-ai model settings.

        Merge order:
        1. Reasoning spec + effort -> unified ``thinking`` setting.
        2. ``backend_options["model_settings"]`` overrides (processor-level).
        3. Timeout (applied last).
        """
        settings: Any = None
        thinking_value = spec.efforts.get(effort)

        if thinking_value is not None:
            settings = {
                "thinking": (
                    thinking_value.value
                    if isinstance(thinking_value, ReasoningEffort)
                    else thinking_value
                )
            }

        # Merge processor-level model settings overrides
        overrides = (backend_options or {}).get("model_settings")
        if isinstance(overrides, dict) and overrides:
            if settings is None:
                settings = dict(overrides)
            else:
                for key, value in overrides.items():
                    settings[key] = value

        # Apply timeout
        if timeout is not None:
            if settings is None:
                settings = {"timeout": timeout}
            else:
                settings["timeout"] = timeout

        return settings

    def _build_tool(self, tool: Tool) -> PydanticTool[Any]:
        function = self._adapt_tool_function(tool)
        if (
            tool.timeout is not None
            or tool.strict is not None
            or tool.metadata is not None
        ):
            return PydanticTool(
                function,
                name=tool.resolved_name(),
                description=tool.resolved_description(),
                takes_ctx=tool.resolved_takes_ctx(),
                timeout=tool.timeout,
                strict=tool.strict,
                metadata=tool.metadata,
            )
        if (
            tool.name
            or tool.description
            or tool.takes_ctx is not None
            or tool.resolved_takes_ctx()
        ):
            return PydanticTool(
                function,
                name=tool.resolved_name(),
                description=tool.resolved_description(),
                takes_ctx=tool.resolved_takes_ctx(),
            )
        return function  # type: ignore[return-value]

    def _build_toolset(self, toolset: ToolSet) -> FunctionToolset[Any]:
        """Convert a backend-neutral toolset to a pydantic-ai toolset."""
        return FunctionToolset(
            tools=[self._build_tool(tool) for tool in toolset.tools],
            id=toolset.id,
            instructions=toolset.instructions,
            defer_loading=toolset.defer_loading,
        )

    def _build_capability(self, capability: AICapability) -> PydanticCapability[Any]:
        """Convert a backend-neutral capability to a pydantic-ai capability."""
        return PydanticCapability(
            id=capability.id,
            description=capability.description,
            instructions=capability.instructions,
            tools=[self._build_tool(tool) for tool in capability.tools],
            toolsets=[self._build_toolset(toolset) for toolset in capability.toolsets],
            defer_loading=capability.defer_loading,
        )

    def _adapt_tool_function(self, tool: Tool) -> Any:
        """Wrap an ``mi.ai.Tool`` function for pydantic-ai compatibility.

        Two bridges are needed:

        1. **Return value conversion** — our tools return ``ToolContentResult``
           (text / image content blocks). pydantic-ai expects its own
           native types (``str``, ``BinaryImage``). The
           wrapper calls ``_build_tool_content`` to translate.

        2. **Context bridging** — tools that accept a ``ToolContext`` as their
           first parameter receive our domain context (data object, metadata).
           pydantic-ai passes a ``RunContext`` instead, so the wrapper extracts
           ``ctx.deps.context`` (our ``ToolContext``) and forwards it.

        The original function's ``__signature__`` is preserved on the wrapper
        so pydantic-ai can introspect parameter names and types for schema
        generation.
        """
        original = tool.function
        original_sig = inspect.signature(original)
        original_params = list(original_sig.parameters.values())

        if not tool.resolved_takes_ctx():

            @functools.wraps(original)
            def _plain_adapter(**kwargs: Any) -> Any:
                raw = original(**kwargs)
                return self._build_tool_content(raw)

            _plain_adapter.__signature__ = original_sig  # type: ignore[attr-defined]
            return _plain_adapter

        # Swap the first param (ToolContext) with a generic 'ctx' param that
        # pydantic-ai will populate as RunContext.  Keep all other params.
        adapted_params = [
            inspect.Parameter(
                "ctx",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=RunContext[Any],
            ),
            *original_params[1:],
        ]
        adapted_sig = original_sig.replace(parameters=adapted_params)

        @functools.wraps(original)
        def _ctx_adapter(ctx: Any, **kwargs: Any) -> Any:
            deps = getattr(ctx, "deps", None)
            context = getattr(deps, "context", None)
            raw = original(context, **kwargs)
            return self._build_tool_content(raw)

        try:
            resolved_hints = get_type_hints(original, include_extras=True)
        except (NameError, TypeError):
            resolved_hints = {}
        adapter_annotations: dict[str, Any] = {"ctx": RunContext[Any]}
        for parameter in original_params[1:]:
            annotation = resolved_hints.get(parameter.name, parameter.annotation)
            if annotation is not inspect.Signature.empty:
                adapter_annotations[parameter.name] = annotation
        return_annotation = resolved_hints.get("return", original_sig.return_annotation)
        if return_annotation is not inspect.Signature.empty:
            adapter_annotations["return"] = return_annotation
        _ctx_adapter.__annotations__ = adapter_annotations
        _ctx_adapter.__signature__ = adapted_sig  # type: ignore[attr-defined]
        return _ctx_adapter

    def _build_tool_content(self, raw: Any) -> Any:
        blocks = normalize_tool_output(raw)
        parts = [self._convert_tool_part(part) for part in blocks]
        if len(parts) == 1:
            return parts[0]
        return parts

    def _convert_tool_part(self, part: Any) -> Any:
        if isinstance(part, TextContent):
            return part.text
        if isinstance(part, ImageContent):
            image_bytes = base64.b64decode(part.base64_data)
            return BinaryImage(data=image_bytes, media_type=part.media_type)
        raise TypeError(f"Unsupported tool content part: {type(part).__name__}")

    def _build_user_content(self, user_message: UserMessage) -> str | list[Any]:
        parts: list[Any] = []
        for item in user_message.content:
            if isinstance(item, TextContent):
                parts.append(item.text)
            elif isinstance(item, ImageContent):
                image_bytes = base64.b64decode(item.base64_data)
                parts.append(BinaryImage(data=image_bytes, media_type=item.media_type))

        if not parts:
            return ""
        if len(parts) == 1 and isinstance(parts[0], str):
            return parts[0]
        return parts

    def _extract_text(self, response: Any) -> str | None:
        text_value = getattr(response, "text", None)
        if isinstance(text_value, str) and text_value.strip():
            return text_value

        parts = getattr(response, "parts", [])
        if not isinstance(parts, list):
            return None

        text_parts = [
            part.content
            for part in parts
            if isinstance(part, TextPart) and part.content.strip()
        ]
        return "\n".join(text_parts) if text_parts else None

    def _extract_direct_usage(
        self,
        response: Any,
        *,
        provider: str = "unknown",
        model: str = "unknown",
    ) -> AIUsage:
        req_usage = getattr(response, "usage", None)
        if req_usage is None:
            return AIUsage(requests=1)
        request_usage = self._model_request_usage(
            response,
            provider=provider,
            model=model,
        )
        return AIUsage(
            requests=1,
            input_tokens=getattr(req_usage, "input_tokens", 0) or 0,
            output_tokens=getattr(req_usage, "output_tokens", 0) or 0,
            cached_input_tokens=getattr(req_usage, "cache_read_tokens", 0) or 0,
            cache_write_tokens=getattr(req_usage, "cache_write_tokens", 0) or 0,
            reasoning_tokens=self._reasoning_tokens(getattr(req_usage, "details", {})),
            output_validation_attempts=1,
            model_requests=(request_usage,),
        )

    def _combine_usage(self, current: AIUsage, additional: AIUsage) -> AIUsage:
        """Return cumulative usage across repeated direct model requests."""
        return AIUsage(
            requests=current.requests + additional.requests,
            input_tokens=current.input_tokens + additional.input_tokens,
            output_tokens=current.output_tokens + additional.output_tokens,
            cached_input_tokens=(
                current.cached_input_tokens + additional.cached_input_tokens
            ),
            cache_write_tokens=(
                current.cache_write_tokens + additional.cache_write_tokens
            ),
            reasoning_tokens=current.reasoning_tokens + additional.reasoning_tokens,
            tool_calls=current.tool_calls + additional.tool_calls,
            output_validation_attempts=(
                current.output_validation_attempts
                + additional.output_validation_attempts
            ),
            model_requests=current.model_requests + additional.model_requests,
        )

    @staticmethod
    def _reasoning_tokens(details: Any) -> int:
        if not isinstance(details, dict):
            return 0
        return sum(
            int(value)
            for key, value in details.items()
            if (
                "reasoning" in str(key).lower()
                or str(key).lower() in {"thoughts_tokens", "thought_tokens"}
            )
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        )

    def _model_request_usage(
        self,
        response: Any,
        *,
        provider: str,
        model: str,
    ) -> AIModelRequestUsage:
        """Normalize one provider response into disjoint billable buckets."""
        req_usage = getattr(response, "usage", None)
        details = dict(getattr(req_usage, "details", {}) or {})
        input_tokens = getattr(req_usage, "input_tokens", 0) or 0
        output_tokens = getattr(req_usage, "output_tokens", 0) or 0
        cache_read = getattr(req_usage, "cache_read_tokens", 0) or 0
        cache_write = getattr(req_usage, "cache_write_tokens", 0) or 0
        cache_write_5m = details.get("cache_write_5m_tokens", 0) or 0
        cache_write_1h = details.get("cache_write_1h_tokens", 0) or 0
        reasoning = self._reasoning_tokens(details)
        gaps: list[str] = []
        input_children = cache_read + cache_write
        output_children = reasoning
        input_uncached = (
            input_tokens - input_children if input_children <= input_tokens else None
        )
        output_visible = (
            output_tokens - output_children
            if output_children <= output_tokens
            else None
        )
        if input_uncached is None:
            gaps.append("inconsistent_input_token_buckets")
        if output_visible is None:
            gaps.append("inconsistent_output_token_buckets")
        if (
            provider == "azure"
            and not model.startswith("claude")
            and model.startswith("gpt-5.6")
            and input_tokens >= 1_024
        ):
            # Azure documents that GPT-5.6 cache writes are billable but the
            # Responses API does not report their quantity.
            gaps.append("input_cache_write_tokens_unreported")
        normalized_provider = (
            "azure_claude"
            if provider == "azure" and model.startswith("claude")
            else "azure_openai"
            if provider == "azure"
            else "google_direct"
            if provider == "google"
            else provider
        )
        provider_details = {
            key: value
            for key, value in dict(
                getattr(response, "provider_details", {}) or {}
            ).items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        provider_details["reported_provider"] = getattr(response, "provider_name", None)
        return AIModelRequestUsage(
            provider=normalized_provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_uncached_tokens=input_uncached,
            input_cache_read_tokens=cache_read,
            input_cache_write_tokens=cache_write,
            input_cache_write_5m_tokens=cache_write_5m,
            input_cache_write_1h_tokens=cache_write_1h,
            output_visible_tokens=output_visible,
            output_reasoning_tokens=reasoning,
            billable_usage_gaps=tuple(gaps),
            provider_details=provider_details,
        )
