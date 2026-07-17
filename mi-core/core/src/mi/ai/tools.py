"""Thin tool abstraction used by mi.ai agent processors."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Sequence,
    TypeAlias,
    TypeVar,
    get_origin,
    get_type_hints,
)

from mi.ai.message import ContentBlock, ToolContentResult, normalize_content_blocks

if TYPE_CHECKING:
    from mi.core.objects import ProcessDataObject
    from mi.core.pipeline import PipelineMetadata

PDO = TypeVar("PDO", bound="ProcessDataObject")


@dataclass(slots=True)
class ToolContext(Generic[PDO]):
    """Tool execution context exposed to mi.ai tool handlers."""

    data_object: PDO
    metadata: PipelineMetadata | None = None


@dataclass(slots=True)
class Tool:
    """Tool definition for mi.ai agent runs."""

    function: Callable[..., ToolContentResult]
    name: str | None = None
    description: str | None = None
    takes_ctx: bool | None = None
    timeout: float | None = None
    strict: bool | None = None
    metadata: dict[str, Any] | None = None

    def resolved_name(self) -> str:
        """Return the effective tool name."""
        return self.name or self.function.__name__

    def resolved_description(self) -> str | None:
        """Return the effective tool description."""
        return self.description or inspect.getdoc(self.function)

    def resolved_takes_ctx(self) -> bool:
        """Infer whether the tool expects ToolContext as first parameter."""
        if self.takes_ctx is not None:
            return self.takes_ctx

        signature = inspect.signature(self.function)
        parameters = list(signature.parameters.values())
        if not parameters:
            return False

        first = parameters[0]
        annotation = first.annotation
        if annotation is inspect.Signature.empty:
            return first.name == "ctx"

        try:
            annotation = get_type_hints(
                self.function,
                include_extras=True,
            ).get(first.name, annotation)
        except (NameError, TypeError):
            pass

        if isinstance(annotation, str):
            annotation_name = (
                annotation.split("[", maxsplit=1)[0]
                .strip(" '\"")
                .rsplit(".", maxsplit=1)[-1]
            )
            return annotation_name == "ToolContext" or first.name == "ctx"

        if annotation is ToolContext:
            return True

        return get_origin(annotation) is ToolContext or first.name == "ctx"


ToolLike = Tool | Callable[..., ToolContentResult]


@dataclass(slots=True)
class ToolSet:
    """Reusable collection of tools with optional shared instructions."""

    tools: list[Tool] = field(default_factory=list)
    instructions: str | None = None
    id: str | None = None
    defer_loading: bool = False

    @classmethod
    def builder(cls) -> "ToolSetBuilder":
        return ToolSetBuilder()


@dataclass(slots=True)
class ToolSetBuilder:
    """Fluent builder for composing tool sets."""

    _tools: list[Tool] = field(default_factory=list)
    _instructions: str | None = None
    _id: str | None = None
    _defer_loading: bool = False

    def add(self, tool: ToolLike) -> "ToolSetBuilder":
        self._tools.append(as_tool(tool))
        return self

    def add_many(self, tools: Sequence[ToolLike]) -> "ToolSetBuilder":
        for tool in tools:
            self._tools.append(as_tool(tool))
        return self

    def with_instructions(self, instructions: str) -> "ToolSetBuilder":
        """Attach instructions that travel with this toolset."""
        self._instructions = instructions
        return self

    def with_id(self, toolset_id: str) -> "ToolSetBuilder":
        """Assign a stable identifier to this toolset."""
        self._id = toolset_id
        return self

    def deferred(self, enabled: bool = True) -> "ToolSetBuilder":
        """Control whether tools are exposed through deferred discovery."""
        self._defer_loading = enabled
        return self

    def build(self) -> ToolSet:
        return ToolSet(
            tools=list(self._tools),
            instructions=self._instructions,
            id=self._id,
            defer_loading=self._defer_loading,
        )


ToolCollectionLike: TypeAlias = Sequence[ToolLike] | ToolSet | ToolSetBuilder


def ai_tool(
    *,
    name: str | None = None,
    description: str | None = None,
    takes_ctx: bool | None = None,
    timeout: float | None = None,
    strict: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> Callable[[Callable[..., ToolContentResult]], Tool]:
    """Decorator that converts a function into a ``Tool`` instance."""

    def decorator(function: Callable[..., ToolContentResult]) -> Tool:
        return Tool(
            function=function,
            name=name,
            description=description,
            takes_ctx=takes_ctx,
            timeout=timeout,
            strict=strict,
            metadata=metadata,
        )

    return decorator


def as_tool(value: ToolLike) -> Tool:
    """Normalize a callable or Tool-like value into a Tool instance."""
    if isinstance(value, Tool):
        return value
    return Tool(function=value)


def normalize_tool_output(value: ToolContentResult) -> list[ContentBlock]:
    """Normalize tool outputs to content blocks.

    Strings are converted to ``TextContent`` automatically.
    pandas ``DataFrame`` values are converted to full text automatically.
    """
    return normalize_content_blocks(value)


def normalize_tools(value: ToolCollectionLike) -> list[Tool]:
    """Normalize supported tool collection shapes into a list of Tool."""
    if isinstance(value, ToolSetBuilder):
        return value.build().tools
    if isinstance(value, ToolSet):
        return list(value.tools)
    return [as_tool(tool) for tool in value]


def normalize_toolsets(value: Sequence[ToolSet | ToolSetBuilder]) -> list[ToolSet]:
    """Normalize explicit and builder-based toolset collections."""
    return [item.build() if isinstance(item, ToolSetBuilder) else item for item in value]
