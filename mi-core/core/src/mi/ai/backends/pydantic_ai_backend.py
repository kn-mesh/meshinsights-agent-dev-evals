"""pydantic-ai backend adapter for mi.ai."""

from __future__ import annotations

import base64
import functools
import inspect
import os
from typing import Any, TypeVar, get_type_hints

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent, AgentRetries, FunctionToolset, RunContext
from pydantic_ai.capabilities import Capability as PydanticCapability
from pydantic_ai.direct import model_request_sync
from pydantic_ai.messages import (
    BinaryImage,
    ModelRequest,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.output import OutputObjectDefinition
from pydantic_ai.retries import (
    AsyncTenacityTransport,
    RetryConfig,
    wait_retry_after,
)
from pydantic_ai.tools import Tool as PydanticTool
from pydantic_ai.usage import RunUsage, UsageLimits
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from mi.ai.backends.base import (
    AIBackend,
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


class PydanticAIBackend(AIBackend):
    """Executes mi.ai requests via pydantic-ai."""

    BACKEND_NAME = "pydantic_ai"
    _RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504, 507})

    def __init__(self) -> None:
        self._retrying_http_clients: dict[int, httpx.AsyncClient] = {}

    def run_workflow(
        self, request: WorkflowRequest[OutputT]
    ) -> WorkflowResult[OutputT]:
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
                response = model_request_sync(
                    model=model,
                    messages=[request_message],
                    model_settings=model_settings,
                    model_request_parameters=params,
                )
                usage = self._combine_usage(
                    usage,
                    self._extract_direct_usage(response),
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
                    if request.capture_review:
                        raise AIReviewError(
                            str(exc),
                            review={
                                "request": workflow_request_review(request),
                                "validation_attempts": validation_attempts,
                                "capture_status": "partial",
                            },
                        ) from exc
                    raise
        raise (
            last_exc
            if last_exc is not None
            else ValueError("Workflow execution failed")
        )

    def run_agent(
        self, request: AgentRequest[OutputT], *, deps: Any | None = None
    ) -> AgentResult[OutputT]:
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
        pydantic_capabilities = [
            self._build_capability(capability) for capability in request.capabilities
        ]
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

        try:
            result = agent.run_sync(
                self._build_user_content(request.user_message),
                deps=deps,
                usage_limits=self._build_usage_limits(
                    request.usage_limits,
                    default_request_limit=request.max_turns,
                ),
            )
        except Exception as error:
            if request.capture_review:
                raise AIReviewError(
                    str(error),
                    review={
                        "request": agent_request_review(request),
                        "messages": [],
                        "capture_status": "partial",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                ) from error
            raise
        usage = result.usage
        return AgentResult(
            output=result.output,
            usage=AIUsage(
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=getattr(usage, "cache_read_tokens", 0) or 0,
                reasoning_tokens=self._reasoning_tokens(getattr(usage, "details", {})),
                tool_calls=getattr(usage, "tool_calls", 0) or 0,
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

        if http_client is None:
            foundry_client = AsyncAnthropicFoundry()
        else:
            foundry_client = AsyncAnthropicFoundry(
                http_client=http_client,
                max_retries=0,
            )
        anthropic_provider = AnthropicProvider(anthropic_client=foundry_client)
        return AnthropicModel(model, provider=anthropic_provider)

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

        return AsyncTenacityTransport(
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

    def _extract_direct_usage(self, response: Any) -> AIUsage:
        req_usage = getattr(response, "usage", None)
        if req_usage is None:
            return AIUsage(requests=1)
        return AIUsage(
            requests=1,
            input_tokens=getattr(req_usage, "input_tokens", 0) or 0,
            output_tokens=getattr(req_usage, "output_tokens", 0) or 0,
            cached_input_tokens=getattr(req_usage, "cache_read_tokens", 0) or 0,
            reasoning_tokens=self._reasoning_tokens(getattr(req_usage, "details", {})),
            output_validation_attempts=1,
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
            reasoning_tokens=current.reasoning_tokens + additional.reasoning_tokens,
            tool_calls=current.tool_calls + additional.tool_calls,
            output_validation_attempts=(
                current.output_validation_attempts
                + additional.output_validation_attempts
            ),
        )

    @staticmethod
    def _reasoning_tokens(details: Any) -> int:
        if not isinstance(details, dict):
            return 0
        return sum(
            int(value)
            for key, value in details.items()
            if "reasoning" in str(key).lower()
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        )
