"""pydantic-ai backend adapter for mi.ai."""

from __future__ import annotations

import base64
import functools
import inspect
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai import Agent
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
from pydantic_ai.tools import Tool as PydanticTool
from pydantic_ai.usage import UsageLimits

from mi.ai.backends.base import (
    AIBackend,
    AIUsage,
    AgentRequest,
    AgentResult,
    WorkflowRequest,
    WorkflowResult,
)
from mi.ai.message import ImageContent, TextContent, UserMessage
from mi.ai.model_config import ReasoningEffort, ReasoningSpec
from mi.ai.tools import Tool, normalize_tool_output

OutputT = TypeVar("OutputT", bound=BaseModel)


class PydanticAIBackend(AIBackend):
    """Executes mi.ai requests via pydantic-ai."""

    BACKEND_NAME = "pydantic_ai"

    def run_workflow(
        self, request: WorkflowRequest[OutputT]
    ) -> WorkflowResult[OutputT]:
        model, settings_id = self._resolve_model(
            request.model.provider, request.model.model, request.provider_options
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

        last_exc: Exception | None = None
        for attempt in range(1, request.retries + 1):
            try:
                response = model_request_sync(
                    model=model,
                    messages=[
                        ModelRequest(
                            parts=[
                                SystemPromptPart(content=request.system_prompt),
                                UserPromptPart(
                                    content=self._build_user_content(
                                        request.user_message
                                    )
                                ),
                            ]
                        )
                    ],
                    model_settings=model_settings,
                    model_request_parameters=params,
                )
                raw_text = self._extract_text(response)
                if raw_text is None:
                    raise ValueError("Missing text output in model response.")
                output = request.output_schema.model_validate_json(raw_text)
                return WorkflowResult(
                    output=output, usage=self._extract_direct_usage(response)
                )
            except Exception as exc:
                last_exc = exc
                if attempt >= request.retries:
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
            request.model.provider, request.model.model, request.provider_options
        )
        model_settings = self._build_model_settings(
            request.reasoning_spec,
            request.reasoning_effort,
            settings_id,
            request.timeout,
            request.backend_options,
        )
        pydantic_tools = [self._build_tool(tool) for tool in request.tools]

        agent: Agent[Any, OutputT] = Agent(
            model,
            deps_type=type(deps) if deps is not None else object,
            output_type=request.output_schema,
            system_prompt=request.system_prompt,
            model_settings=model_settings,
            tools=pydantic_tools,
            retries=request.retries,
            output_retries=request.output_retries,
            tool_timeout=request.tool_timeout,
        )

        last_exc: Exception | None = None
        for attempt in range(1, request.retries + 1):
            try:
                result = agent.run_sync(
                    self._build_user_content(request.user_message),
                    deps=deps,
                    usage_limits=UsageLimits(request_limit=request.max_turns),
                )
                usage = result.usage()
                return AgentResult(
                    output=result.output,
                    usage=AIUsage(
                        requests=usage.requests,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                    ),
                )
            except Exception as exc:
                last_exc = exc
                if attempt >= request.retries:
                    raise
        raise last_exc if last_exc is not None else ValueError("Agent execution failed")

    def _resolve_model(
        self, provider: str, model: str, provider_options: dict[str, Any]
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
        if provider == "azure":
            deployment = provider_options.get("deployment")
            name = deployment if isinstance(deployment, str) and deployment else model
            settings_id = f"azure:{name}"

            if model.startswith("claude"):
                return self._build_foundry_model(model, provider_options), settings_id

            return f"azure:{name}", settings_id

        if provider == "google":
            return self._build_google_model(model, provider_options), f"google:{model}"

        model_str = f"{provider}:{model}"
        return model_str, model_str

    def _build_foundry_model(self, model: str, provider_options: dict[str, Any]) -> Any:
        """Build an ``AnthropicModel`` configured for Microsoft Azure Foundry.

        Credentials are resolved automatically by the ``anthropic`` SDK from
        environment variables ``ANTHROPIC_FOUNDRY_API_KEY`` and either
        ``ANTHROPIC_FOUNDRY_RESOURCE`` or ``ANTHROPIC_FOUNDRY_BASE_URL``
        (mutually exclusive).
        """
        from anthropic import AsyncAnthropicFoundry
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        foundry_client = AsyncAnthropicFoundry()
        anthropic_provider = AnthropicProvider(anthropic_client=foundry_client)
        return AnthropicModel(model, provider=anthropic_provider)

    def _build_google_model(self, model: str, provider_options: dict[str, Any]) -> Any:
        """Build a direct Google Gemini model using the Generative Language API."""
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        api_key = provider_options.get("api_key")

        google_provider = GoogleProvider(
            api_key=api_key if isinstance(api_key, str) and api_key else None,
        )
        return GoogleModel(model, provider=google_provider)

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

    def _build_tool(self, tool: Tool) -> PydanticTool:
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
        if tool.name or tool.description or tool.takes_ctx is not None:
            return PydanticTool(
                function,
                name=tool.resolved_name(),
                description=tool.resolved_description(),
                takes_ctx=tool.resolved_takes_ctx(),
            )
        return function  # type: ignore[return-value]

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
                "ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Any
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
        )
