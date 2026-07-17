"""Agent mixin for multi-turn LLM processing with tool use."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, TYPE_CHECKING

from mi.ai.backends.base import AgentRequest
from mi.ai.mixins.base import AIProcessorMixin, OutputT, PDO
from mi.ai.tools import ToolCollectionLike, ToolContext, normalize_tools

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
            request = AgentRequest(
                model=self._resolve_model_ref(),
                system_prompt=self._build_system_prompt(data_object),
                user_message=self._resolve_user_message(data_object),
                output_schema=self._get_output_schema(),
                tools=tools,
                reasoning_spec=self._get_reasoning_spec(),
                reasoning_effort=self._get_reasoning_effort(),
                retries=self._get_retries(),
                max_turns=self._get_max_turns(),
                output_retries=self._get_output_retries(),
                tool_timeout=self._get_tool_timeout(),
                timeout=self._get_timeout(),
                provider_options=self._get_provider_options(),
                backend_options=self._get_backend_options(),
            )

            self.logger.info(
                f"AI agent: model={request.model.canonical()}, backend={self.config.backend}, tools={len(tools)}, max_turns={request.max_turns}, retries={request.retries}"
            )

            deps = AgentDeps(
                context=ToolContext(data_object=data_object, metadata=metadata)
            )
            result = backend.run_agent(request, deps=deps)

            if self._should_attach_response():
                self._attach_response(data_object, result.output)
            if self._should_attach_usage():
                self._attach_usage(data_object, result.usage)
                self.logger.info(
                    f"Agent usage: requests={result.usage.requests}, input={result.usage.input_tokens}, output={result.usage.output_tokens}"
                )

        except Exception as exc:
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
        """Build the list of tools. Must be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _build_tools")
