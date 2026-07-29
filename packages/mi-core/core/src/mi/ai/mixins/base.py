"""Base AI mixin and config for workflow and agent processors."""

from __future__ import annotations

import logging
from typing import Any, Generic, TYPE_CHECKING, TypeVar

from pydantic import BaseModel, Field

from mi.ai.backends.base import AIUsage, AIUsageLimits
from mi.ai.backends.resolver import resolve_backend
from mi.ai.message import BuildableUserMessage, UserMessage, UserMessageBuilder
from mi.ai.model_config import (
    ModelName,
    ModelRef,
    ReasoningEffort,
    ReasoningSpec,
    match_reasoning_spec,
)
from mi.core.processors import BaseProcessorConfig

if TYPE_CHECKING:
    from mi.core.objects import ProcessDataObject
    from mi.core.pipeline import PipelineMetadata

PDO = TypeVar("PDO", bound="ProcessDataObject")
OutputT = TypeVar("OutputT", bound=BaseModel)


class AIProcessorConfig(BaseProcessorConfig):
    """Configuration for AI processors."""

    model_config = {"extra": "forbid"}

    model: ModelName | None = Field(
        default=None,
        description="Model identifier in provider:model format",
    )
    backend: str | None = Field(
        default="auto",
        description="Execution backend: auto or pydantic_ai",
    )
    reasoning_effort: ReasoningEffort = Field(
        default=ReasoningEffort.MEDIUM,
        description="How much reasoning/thinking the model should use",
    )
    max_turns: int = Field(
        default=10,
        ge=1,
        description="Maximum model requests for agent execution",
    )
    attach_usage: bool | None = Field(
        default=True, description="Whether to attach usage metrics"
    )
    attach_response: bool | None = Field(
        default=True, description="Whether to attach model response"
    )
    timeout: float | None = Field(
        default=None, description="Request timeout in seconds"
    )
    transport_retries: int = Field(
        default=3,
        ge=1,
        description="Maximum HTTP attempts, including the initial request",
    )
    tool_retries: int = Field(
        default=3,
        ge=0,
        description="Retries available to each agent tool",
    )
    output_retries: int | None = Field(
        default=None,
        ge=0,
        description="Retries for output validation; defaults to tool_retries",
    )
    tool_timeout: float | None = Field(
        default=None, description="Timeout per tool call in seconds"
    )
    input_tokens_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum input tokens per execution; unlimited by default",
    )
    output_tokens_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum output tokens per execution; unlimited by default",
    )
    total_tokens_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum combined tokens per execution; unlimited by default",
    )
    tool_calls_limit: int | None = Field(
        default=None,
        ge=0,
        description="Maximum successful tool calls; unlimited by default",
    )
    finalize_on_tool_call_limit: bool = Field(
        default=False,
        description=(
            "Hide function tools at the successful-call limit and require the "
            "agent to produce its final structured output"
        ),
    )
    count_tokens_before_request: bool = Field(
        default=False,
        description="Count tokens before agent requests when the provider supports it",
    )
    provider_options: dict[str, Any] | None = Field(
        default=None,
        description="Provider-specific options (e.g. Azure deployment override)",
    )
    backend_options: dict[str, Any] | None = Field(
        default=None,
        description="Backend-specific adapter options",
    )


class AIProcessorMixin(Generic[PDO, OutputT]):
    """Base mixin shared by workflow and agent processors."""

    output_schema: type[OutputT] | None = None
    system_prompt: str | None = None

    name: str
    logger: logging.Logger
    config: Any
    _backend_cache: Any | None = None

    def _resolve_model(self) -> ModelName:
        config = getattr(self, "config", None)
        if config is None:
            raise ValueError(
                f"{self.__class__.__name__} requires AIProcessorConfig with model"
            )
        model = getattr(config, "model", None)
        if model is None:
            raise ValueError(f"{self.__class__.__name__} config missing model")
        return model

    def _resolve_model_ref(self) -> ModelRef:
        return ModelRef.parse(self._resolve_model())

    def _resolve_backend(self) -> Any:
        if self._backend_cache is not None:
            return self._backend_cache

        config = getattr(self, "config", None)
        backend_name = (
            getattr(config, "backend", "auto") if config is not None else "auto"
        )
        self._backend_cache = resolve_backend(backend_name)
        return self._backend_cache

    def _get_output_schema(self) -> type[OutputT]:
        if self.output_schema is not None:
            return self.output_schema
        raise NotImplementedError(
            f"{self.__class__.__name__} must define 'output_schema' class attribute"
        )

    def _get_transport_retries(self) -> int:
        config = getattr(self, "config", None)
        if config is None:
            return 3
        return getattr(config, "transport_retries", 3)

    def _get_tool_retries(self) -> int:
        config = getattr(self, "config", None)
        if config is None:
            return 3
        return getattr(config, "tool_retries", 3)

    def _get_output_retries(self) -> int | None:
        config = getattr(self, "config", None)
        if config is None:
            return None
        return getattr(config, "output_retries", None)

    def _get_effective_output_retries(self) -> int:
        output_retries = self._get_output_retries()
        return self._get_tool_retries() if output_retries is None else output_retries

    def _get_usage_limits(self, *, request_limit: int | None) -> AIUsageLimits:
        config = getattr(self, "config", None)
        if config is None:
            return AIUsageLimits(request_limit=request_limit)
        return AIUsageLimits(
            request_limit=request_limit,
            tool_calls_limit=getattr(config, "tool_calls_limit", None),
            input_tokens_limit=getattr(config, "input_tokens_limit", None),
            output_tokens_limit=getattr(config, "output_tokens_limit", None),
            total_tokens_limit=getattr(config, "total_tokens_limit", None),
            count_tokens_before_request=getattr(
                config, "count_tokens_before_request", False
            ),
        )

    def _get_tool_timeout(self) -> float | None:
        config = getattr(self, "config", None)
        if config is None:
            return None
        return getattr(config, "tool_timeout", None)

    def _get_timeout(self) -> float | None:
        config = getattr(self, "config", None)
        if config is None:
            return None
        return getattr(config, "timeout", None)

    def _get_provider_options(self) -> dict[str, Any]:
        config = getattr(self, "config", None)
        if config is None:
            return {}
        options = getattr(config, "provider_options", {})
        return options if isinstance(options, dict) else {}

    def _get_backend_options(self) -> dict[str, Any]:
        config = getattr(self, "config", None)
        if config is None:
            return {}
        options = getattr(config, "backend_options", {})
        return options if isinstance(options, dict) else {}

    def _get_reasoning_effort(self) -> ReasoningEffort:
        config = getattr(self, "config", None)
        if config is None:
            raise ValueError(f"{self.__class__.__name__} requires AIProcessorConfig")
        return getattr(config, "reasoning_effort", ReasoningEffort.MEDIUM)

    def _get_reasoning_spec(self) -> ReasoningSpec:
        return match_reasoning_spec(self._resolve_model_ref())

    def _build_system_prompt(self, data_object: PDO) -> str:
        if self.system_prompt is not None:
            return self.system_prompt
        raise NotImplementedError(
            f"{self.__class__.__name__} must define 'system_prompt' or override '_build_system_prompt'"
        )

    def _build_user_message(self, data_object: PDO) -> BuildableUserMessage:
        raise NotImplementedError("Subclass must implement _build_user_message")

    def _resolve_user_message(self, data_object: PDO) -> UserMessage:
        """Resolve builder or concrete message into a UserMessage instance."""
        message = self._build_user_message(data_object)
        if isinstance(message, UserMessageBuilder):
            return message.build()
        return message

    def _get_artifact_key(self) -> str:
        model = self._resolve_model_ref()
        return f"{self.name}_{model.model}"

    def _attach_response(self, data_object: PDO, response: OutputT) -> None:
        key = f"{self._get_artifact_key()}_response"
        data_object.set_artifact(key, response.model_dump())

    def _attach_usage(self, data_object: PDO, usage: AIUsage) -> None:
        key = f"{self._get_artifact_key()}_usage"
        data_object.set_artifact(
            key,
            {
                "requests": usage.requests,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "cache_write_tokens": usage.cache_write_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
                "tool_calls": usage.tool_calls,
                "output_validation_attempts": usage.output_validation_attempts,
                "model_requests": [
                    request.to_dict() for request in usage.model_requests
                ],
            },
        )

    def _attach_performance(
        self, data_object: PDO, performance: dict[str, Any]
    ) -> None:
        """Attach short-lived backend timing observations to the process object."""
        if performance:
            data_object.set_artifact(
                f"{self._get_artifact_key()}_performance", performance
            )

    def _attach_review(self, data_object: PDO, review: dict[str, Any]) -> None:
        """Attach transient review evidence for the pipeline receipt hook."""
        if review:
            data_object.set_artifact(f"{self._get_artifact_key()}_review", review)

    @staticmethod
    def _review_capture_enabled(metadata: "PipelineMetadata | None") -> bool:
        if metadata is None:
            return False
        value = getattr(metadata, "review_capture", False)
        return value is True

    def _should_attach_usage(self) -> bool:
        config = getattr(self, "config", None)
        if config is None:
            return True
        attach_usage = getattr(config, "attach_usage", True)
        return True if attach_usage is None else attach_usage

    def _should_attach_response(self) -> bool:
        config = getattr(self, "config", None)
        if config is None:
            return True
        attach_response = getattr(config, "attach_response", True)
        return True if attach_response is None else attach_response

    def _get_metadata_extra(
        self, metadata: "PipelineMetadata | None", key: str
    ) -> str | None:
        if metadata is None:
            return None

        direct_value = getattr(metadata, key, None)
        if direct_value is not None:
            return str(direct_value)

        model_extra = getattr(metadata, "model_extra", None)
        if model_extra is None:
            return None

        value = model_extra.get(key)
        return str(value) if value is not None else None

    def _normalize_error(self, error: Exception, prefix: str = "AI") -> ValueError:
        if isinstance(error, ValueError) and str(error).startswith(f"{self.name}:"):
            return error
        message = self._describe_error(error)
        return ValueError(f"{self.name}: {prefix} failed: {message}")

    @staticmethod
    def _describe_error(error: Exception) -> str:
        """Retain provider exception identity and safe request diagnostics."""
        details = [f"{type(error).__name__}: {error}"]
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            details.append(f"status_code={status_code}")
        request_id = getattr(error, "request_id", None)
        if isinstance(request_id, str) and request_id:
            details.append(f"request_id={request_id}")
        return " | ".join(details)
