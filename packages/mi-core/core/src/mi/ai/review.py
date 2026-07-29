"""Provider-neutral serialization for ephemeral AI execution review."""

from __future__ import annotations

import inspect
from typing import Any

from pydantic_ai.messages import ModelMessagesTypeAdapter

from mi.ai.capabilities import AICapability
from mi.ai.message import ImageContent, TextContent, UserMessage
from mi.ai.tools import Tool, ToolSet


class AIReviewError(ValueError):
    """AI failure carrying transient, secret-scrubbed-at-storage review data."""

    def __init__(self, message: str, *, review: dict[str, Any]) -> None:
        super().__init__(message)
        self.review = review


def serialize_user_message(message: UserMessage) -> list[dict[str, Any]]:
    """Serialize exact mi.ai content blocks without provider SDK objects."""
    output: list[dict[str, Any]] = []
    for block in message.content:
        if isinstance(block, TextContent):
            output.append({"kind": "text", "text": block.text})
        elif isinstance(block, ImageContent):
            output.append(
                {
                    "kind": "image",
                    "base64_data": block.base64_data,
                    "media_type": block.media_type,
                }
            )
    return output


def serialize_tool(tool: Tool) -> dict[str, Any]:
    """Serialize one tool definition without executable code or dependencies."""
    try:
        signature = inspect.signature(tool.function)
        parameters = [
            {
                "name": parameter.name,
                "kind": parameter.kind.name.lower(),
                "required": parameter.default is inspect.Signature.empty,
                "annotation": (
                    None
                    if parameter.annotation is inspect.Signature.empty
                    else str(parameter.annotation)
                ),
            }
            for parameter in signature.parameters.values()
        ]
    except (TypeError, ValueError):
        parameters = []
    return {
        "name": tool.resolved_name(),
        "description": tool.resolved_description(),
        "parameters": parameters,
        "takes_context": tool.resolved_takes_ctx(),
        "timeout": tool.timeout,
        "strict": tool.strict,
        "metadata": tool.metadata,
    }


def serialize_toolset(toolset: ToolSet) -> dict[str, Any]:
    return {
        "id": toolset.id,
        "instructions": toolset.instructions,
        "defer_loading": toolset.defer_loading,
        "tools": [serialize_tool(tool) for tool in toolset.tools],
    }


def serialize_capability(capability: AICapability) -> dict[str, Any]:
    return {
        "id": capability.id,
        "description": capability.description,
        "instructions": capability.instructions,
        "defer_loading": capability.defer_loading,
        "tools": [serialize_tool(tool) for tool in capability.tools],
        "toolsets": [serialize_toolset(item) for item in capability.toolsets],
    }


def serialize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    """Serialize pydantic-ai message history through its stable adapter."""
    payload = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
    return payload if isinstance(payload, list) else []


def workflow_request_review(request: Any) -> dict[str, Any]:
    return {
        "kind": "workflow",
        "model": request.model.canonical(),
        "reasoning_effort": request.reasoning_effort.value,
        "system_prompt": request.system_prompt,
        "user_message": serialize_user_message(request.user_message),
        "output_schema": request.output_schema.model_json_schema(),
        "execution_policy": {
            "transport_retries": request.transport_retries,
            "output_retries": request.output_retries,
            "timeout": request.timeout,
        },
    }


def agent_request_review(request: Any) -> dict[str, Any]:
    return {
        "kind": "agent",
        "model": request.model.canonical(),
        "reasoning_effort": request.reasoning_effort.value,
        "system_prompt": request.system_prompt,
        "user_message": serialize_user_message(request.user_message),
        "output_schema": request.output_schema.model_json_schema(),
        "tools": [serialize_tool(tool) for tool in request.tools],
        "toolsets": [serialize_toolset(item) for item in request.toolsets],
        "capabilities": [serialize_capability(item) for item in request.capabilities],
        "execution_policy": {
            "transport_retries": request.transport_retries,
            "tool_retries": request.tool_retries,
            "output_retries": request.output_retries,
            "max_turns": request.max_turns,
            "tool_calls_limit": request.usage_limits.tool_calls_limit,
            "finalize_on_tool_call_limit": request.finalize_on_tool_call_limit,
            "tool_timeout": request.tool_timeout,
            "timeout": request.timeout,
        },
    }
