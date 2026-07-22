"""Agent mixin for multi-turn LLM processing with tool use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Sequence, TypeVar, TYPE_CHECKING

from mi.ai.backends.base import AgentRequest
from mi.ai.capabilities import AICapability, AISkill, normalize_capabilities
from mi.ai.mixins.base import AIProcessorMixin, OutputT, PDO
from mi.ai.tools import (
    ToolCollectionLike,
    ToolContext,
    ToolSet,
    ToolSetBuilder,
    normalize_tools,
    normalize_toolsets,
)

if TYPE_CHECKING:
    from mi.core.objects import ProcessDataObject
    from mi.core.pipeline import PipelineMetadata

_PDO = TypeVar("_PDO", bound="ProcessDataObject")


@dataclass
class AgentDeps(Generic[_PDO]):
    """Dependencies passed to backend tool adapters."""

    context: ToolContext[_PDO]


class AIAgentMixin(AIProcessorMixin[PDO, OutputT]):
    """Mixin for multi-turn agent execution with tools."""

    def process(
        self, data_object: PDO, *, metadata: "PipelineMetadata | None" = None
    ) -> None:
        try:
            backend = self._resolve_backend()
            tools = normalize_tools(self._build_tools(data_object))
            toolsets = normalize_toolsets(self._build_toolsets(data_object))
            skills = list(self._build_skills(data_object))
            capabilities = normalize_capabilities(
                self._build_capabilities(data_object),
                skills,
            )
            request = AgentRequest(
                model=self._resolve_model_ref(),
                system_prompt=self._build_system_prompt(data_object),
                user_message=self._resolve_user_message(data_object),
                output_schema=self._get_output_schema(),
                tools=tools,
                reasoning_spec=self._get_reasoning_spec(),
                reasoning_effort=self._get_reasoning_effort(),
                max_turns=self._get_max_turns(),
                toolsets=toolsets,
                capabilities=capabilities,
                transport_retries=self._get_transport_retries(),
                tool_retries=self._get_tool_retries(),
                output_retries=self._get_output_retries(),
                usage_limits=self._get_usage_limits(
                    request_limit=self._get_max_turns()
                ),
                tool_timeout=self._get_tool_timeout(),
                timeout=self._get_timeout(),
                provider_options=self._get_provider_options(),
                backend_options=self._get_backend_options(),
                capture_review=self._review_capture_enabled(metadata),
            )

            self.logger.info(
                f"AI agent: model={request.model.canonical()}, backend={self.config.backend}, tools={len(tools)}, toolsets={len(toolsets)}, capabilities={len(capabilities)}, skills={len(skills)}, max_turns={request.max_turns}, transport_retries={request.transport_retries}, tool_retries={request.tool_retries}"
            )

            deps = AgentDeps(
                context=ToolContext(data_object=data_object, metadata=metadata)
            )
            result = backend.run_agent(request, deps=deps)

            if request.capture_review:
                self._attach_review(data_object, result.review)

            if self._should_attach_response():
                self._attach_response(data_object, result.output)
            if self._should_attach_usage():
                self._attach_usage(data_object, result.usage)
                self.logger.info(
                    f"Agent usage: requests={result.usage.requests}, input={result.usage.input_tokens}, output={result.usage.output_tokens}"
                )

        except Exception as exc:
            review = getattr(exc, "review", None)
            if isinstance(review, dict) and self._review_capture_enabled(metadata):
                self._attach_review(data_object, review)
            raise self._normalize_error(exc, "Agent") from exc

    def _get_max_turns(self) -> int:
        config = getattr(self, "config", None)
        if config is None:
            raise ValueError(
                f"{self.__class__.__name__} requires AIProcessorConfig with max_turns"
            )
        max_turns = getattr(config, "max_turns", None)
        if max_turns is None:
            raise ValueError(f"{self.__class__.__name__} config missing max_turns")
        return max_turns

    def _build_tools(self, data_object: PDO) -> ToolCollectionLike:
        """Build standalone tools available to the agent."""
        _ = data_object
        return []

    def _build_toolsets(self, data_object: PDO) -> Sequence[ToolSet | ToolSetBuilder]:
        """Build reusable toolsets available to the agent."""
        _ = data_object
        return []

    def _build_capabilities(self, data_object: PDO) -> Sequence[AICapability]:
        """Build eager or deferred capabilities available to the agent."""
        _ = data_object
        return []

    def _build_skills(self, data_object: PDO) -> Sequence[AISkill]:
        """Build Agent Skills exposed as deferred capabilities by default."""
        _ = data_object
        return []
