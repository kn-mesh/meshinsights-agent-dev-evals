"""Backend contracts for mi.ai execution engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from mi.ai.message import UserMessage
from mi.ai.model_config import ModelRef, ReasoningEffort, ReasoningSpec
from mi.ai.tools import Tool

OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class AIUsage:
    """Normalized usage metrics shared across backends."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowRequest(Generic[OutputT]):
    """Request payload for one-shot structured workflow execution."""

    model: ModelRef
    system_prompt: str
    user_message: UserMessage
    output_schema: type[OutputT]
    reasoning_spec: ReasoningSpec
    reasoning_effort: ReasoningEffort
    retries: int
    timeout: float | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)
    backend_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowResult(Generic[OutputT]):
    """Normalized workflow execution result."""

    output: OutputT
    usage: AIUsage


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
    retries: int
    max_turns: int
    output_retries: int | None = None
    tool_timeout: float | None = None
    timeout: float | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)
    backend_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentResult(Generic[OutputT]):
    """Normalized agent execution result."""

    output: OutputT
    usage: AIUsage


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
