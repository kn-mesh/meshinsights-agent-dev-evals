"""Message/content primitives shared by prompts and tool outputs."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypeAlias, cast

from mi.ai.dataframe import (
    DataFrameStringFormat,
    convert_dataframe_to_string,
    is_pandas_dataframe,
)

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class TextContent:
    """Text content block."""

    text: str


@dataclass
class ImageContent:
    """Image content block (base64 data + media type)."""

    base64_data: str
    media_type: str = "image/png"

    @classmethod
    def from_bytes(cls, data: bytes, media_type: str = "image/png") -> "ImageContent":
        """Build an image content block from raw bytes."""
        return cls(base64_data=_encode_base64_bytes(data), media_type=media_type)


ContentBlock: TypeAlias = TextContent | ImageContent
if TYPE_CHECKING:
    ToolContentResult: TypeAlias = (
        ContentBlock | list[ContentBlock] | str | pd.DataFrame
    )
else:
    ToolContentResult: TypeAlias = ContentBlock | list[ContentBlock] | str


@dataclass
class UserMessage:
    """Builder target for user messages containing multimodal blocks."""

    content: list[ContentBlock] = field(default_factory=list)

    @classmethod
    def builder(cls) -> "UserMessageBuilder":
        return UserMessageBuilder()

    def add_text(self, text: str) -> "UserMessage":
        self.content.append(TextContent(text=text))
        return self

    def add_image(
        self, base64_data: str, media_type: str = "image/png"
    ) -> "UserMessage":
        self.content.append(
            ImageContent(base64_data=base64_data, media_type=media_type)
        )
        return self

    def add_image_bytes(
        self, data: bytes, media_type: str = "image/png"
    ) -> "UserMessage":
        self.content.append(ImageContent.from_bytes(data=data, media_type=media_type))
        return self

    def add_dataframe(
        self,
        dataframe: "pd.DataFrame",
        string_format: DataFrameStringFormat | str = "csv",
    ) -> "UserMessage":
        self.content.append(
            TextContent(
                text=convert_dataframe_to_string(dataframe, string_format=string_format)
            )
        )
        return self


@dataclass
class UserMessageBuilder:
    """Fluent builder for ``UserMessage``."""

    _content: list[ContentBlock] = field(default_factory=list)

    def text(self, value: str) -> "UserMessageBuilder":
        self._content.append(TextContent(text=value))
        return self

    def image(
        self, base64_data: str, media_type: str = "image/png"
    ) -> "UserMessageBuilder":
        self._content.append(
            ImageContent(base64_data=base64_data, media_type=media_type)
        )
        return self

    def image_bytes(
        self, data: bytes, media_type: str = "image/png"
    ) -> "UserMessageBuilder":
        self._content.append(ImageContent.from_bytes(data=data, media_type=media_type))
        return self

    def dataframe(
        self,
        value: "pd.DataFrame",
        string_format: DataFrameStringFormat | str = "csv",
    ) -> "UserMessageBuilder":
        self._content.append(
            TextContent(
                text=convert_dataframe_to_string(value, string_format=string_format)
            )
        )
        return self

    def build(self) -> UserMessage:
        return UserMessage(content=list(self._content))


BuildableUserMessage: TypeAlias = UserMessage | UserMessageBuilder


def normalize_content_blocks(value: ToolContentResult) -> list[ContentBlock]:
    """Normalize string/content tool output into blocks.

    Strings are auto-wrapped as ``TextContent``.
    pandas ``DataFrame`` values are auto-converted to full text via
    ``convert_dataframe_to_string(..., 'csv')``.
    """
    if isinstance(value, str):
        return [TextContent(text=value)]
    if is_pandas_dataframe(value):
        dataframe = cast("pd.DataFrame", value)
        return [
            TextContent(
                text=convert_dataframe_to_string(dataframe, string_format="csv")
            )
        ]
    if isinstance(value, list):
        normalized: list[ContentBlock] = []
        for item in value:
            if isinstance(item, (TextContent, ImageContent)):
                normalized.append(item)
                continue
            if isinstance(item, str):
                normalized.append(TextContent(text=item))
                continue
            if is_pandas_dataframe(item):
                dataframe = cast("pd.DataFrame", item)
                normalized.append(
                    TextContent(
                        text=convert_dataframe_to_string(dataframe, string_format="csv")
                    )
                )
                continue
            raise TypeError(f"Unsupported content block type: {type(item).__name__}")
        return normalized
    if isinstance(value, (TextContent, ImageContent)):
        return [value]
    raise TypeError(f"Unsupported tool output type: {type(value).__name__}")


def render_content_blocks_as_text(blocks: list[ContentBlock]) -> str:
    """Render blocks into plain text for backends that need text-only tool output."""
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, TextContent):
            lines.append(block.text)
        elif isinstance(block, ImageContent):
            lines.append(f"[image:{block.media_type}]")
    return "\n".join(lines)


def _encode_base64_bytes(data: bytes) -> str:
    if not isinstance(data, bytes) or not data:
        raise ValueError("data must be non-empty bytes")
    return base64.b64encode(data).decode("ascii")
