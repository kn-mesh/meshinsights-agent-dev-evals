"""Backend contracts for mi.ai execution engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from mi.ai.capabilities import AICapability
from mi.ai.message import UserMessage
from mi.ai.model_config import ModelRef, ReasoningEffort, ReasoningSpec
from mi.ai.tools import Tool, ToolSet

OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class AIUsage:
    """Normalized usage metrics shared across backends."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    tool_calls: int = 0
    output_validation_attempts: int = 0


@dataclass(frozen=True, slots=True)
class AIUsageLimits:
    """Backend-neutral limits for one AI execution."""

    request_limit: int | None = None
    tool_calls_limit: int | None = None
    input_tokens_limit: int | None = None
    output_tokens_limit: int | None = None
    total_tokens_limit: int | None = None
    count_tokens_before_request: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowRequest(Generic[OutputT]):
    """Request payload for one-shot structured workflow execution."""

    model: ModelRef
    system_prompt: str
    user_message: UserMessage
    output_schema: type[OutputT]
    reasoning_spec: ReasoningSpec
    reasoning_effort: ReasoningEffort
    transport_retries: int = 3
    output_retries: int = 3
    usage_limits: AIUsageLimits = field(default_factory=AIUsageLimits)
    timeout: float | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)
    backend_options: dict[str, Any] = field(default_factory=dict)
    capture_review: bool = False


@dataclass(frozen=True, slots=True)
class WorkflowResult(Generic[OutputT]):
    """Normalized workflow execution result."""

    output: OutputT
    usage: AIUsage
    review: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentRequest(Generic[OutputT]):
    """Request payload for multi-turn agent execution."""

    model: ModelRef
    system_prompt: str
    user_message: UserMessage
    output_schema: type[OutputT]
    tools: list[Tool]
    reasoning_spec: ReasoningSpec
    reasoning_effort: ReasoningEffort
    max_turns: int
    toolsets: list[ToolSet] = field(default_factory=list)
    capabilities: list[AICapability] = field(default_factory=list)
    transport_retries: int = 3
    tool_retries: int = 3
    output_retries: int | None = None
    usage_limits: AIUsageLimits = field(default_factory=AIUsageLimits)
    tool_timeout: float | None = None
    timeout: float | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)
    backend_options: dict[str, Any] = field(default_factory=dict)
    capture_review: bool = False


@dataclass(frozen=True, slots=True)
class AgentResult(Generic[OutputT]):
    """Normalized agent execution result."""

    output: OutputT
    usage: AIUsage
    review: dict[str, Any] = field(default_factory=dict)


class AIBackend(ABC):
    """Base class for AI execution backends.

    Every concrete backend must:
    - Set ``BACKEND_NAME`` to a unique identifier string.
    - Implement ``run_workflow`` and ``run_agent``.
    """

    BACKEND_NAME: ClassVar[str]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "BACKEND_NAME") or not isinstance(cls.BACKEND_NAME, str):
            raise TypeError(
                f"{cls.__name__} must define BACKEND_NAME as a class-level string"
            )

    @abstractmethod
    def run_workflow(
        self, request: WorkflowRequest[OutputT]
    ) -> WorkflowResult[OutputT]:
        """Execute a one-shot workflow request."""

    @abstractmethod
    def run_agent(
        self, request: AgentRequest[OutputT], *, deps: Any | None = None
    ) -> AgentResult[OutputT]:
        """Execute a multi-turn agent request."""
