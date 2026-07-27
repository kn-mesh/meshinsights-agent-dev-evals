"""
Tests for DataFrame and image inputs across user-message and tool paths.

uv run -m pytest tests/core/ai/test_data_image_inputs.py -s
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from pydantic_ai.messages import BinaryImage

from mi.ai import ImageContent, TextContent, UserMessage, convert_dataframe_to_string
from mi.ai.backends.pydantic_ai_backend import PydanticAIBackend
from mi.ai.message import normalize_content_blocks
from mi.ai.tools import normalize_tool_output
from tests.core.ai.use_case_simulation.data_simulation import select_last_n_days


def _build_dataframe(rows: int = 250) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "col1": range(rows),
            "col2": pd.date_range("2021-01-01", periods=rows, tz="UTC"),
            "col3": range(rows),
        }
    )


def test_convert_dataframe_to_string_default_is_untruncated() -> None:
    dataframe = _build_dataframe(rows=250)
    value = convert_dataframe_to_string(dataframe)

    assert isinstance(value, str)
    assert "249" in value
    assert "..." not in value


@pytest.mark.parametrize("string_format", ["csv", "json", "markdown"])
def test_convert_dataframe_to_string_supported_formats(string_format: str) -> None:
    if string_format == "markdown":
        pytest.importorskip("tabulate")

    dataframe = _build_dataframe(rows=3)
    value = convert_dataframe_to_string(dataframe, string_format=string_format)
    assert isinstance(value, str)
    assert value.strip()


def test_convert_dataframe_to_string_json_shape() -> None:
    dataframe = _build_dataframe(rows=3)
    value = convert_dataframe_to_string(dataframe, string_format="json")
    parsed = json.loads(value)

    assert isinstance(parsed, list)
    assert len(parsed) == 3
    assert parsed[2]["col1"] == 2


def test_convert_dataframe_to_string_markdown_missing_tabulate_propagates_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = _build_dataframe(rows=3)

    def _raise_import_error(*_args: object, **_kwargs: object) -> str:
        raise ImportError("No module named 'tabulate'")

    monkeypatch.setattr(pd.DataFrame, "to_markdown", _raise_import_error)

    with pytest.raises(ImportError, match="tabulate"):
        convert_dataframe_to_string(dataframe, string_format="markdown")


def test_convert_dataframe_to_string_invalid_format_raises() -> None:
    dataframe = _build_dataframe(rows=3)
    with pytest.raises(ValueError, match="Unsupported string_format"):
        convert_dataframe_to_string(dataframe, string_format="xml")


def test_select_last_n_days_returns_recent_window() -> None:
    dataframe = _build_dataframe(rows=72)
    last_day = select_last_n_days(dataframe, timestamp_column="col2", days=1)

    assert not last_day.empty
    assert last_day["col2"].max() == dataframe["col2"].max()
    assert len(last_day) <= 25


def test_dataframe_user_message_conversion() -> None:
    dataframe = _build_dataframe(rows=3)
    message = (
        UserMessage.builder()
        .text("analyze table")
        .dataframe(dataframe, string_format="csv")
        .build()
    )

    assert len(message.content) == 2
    assert isinstance(message.content[1], TextContent)
    assert message.content[1].text.startswith("col1,col2,col3")


def test_dataframe_tool_output_conversion() -> None:
    dataframe = _build_dataframe(rows=250)
    tool_output = normalize_tool_output(dataframe)

    assert len(tool_output) == 1
    assert isinstance(tool_output[0], TextContent)
    assert "249" in tool_output[0].text
    assert "..." not in tool_output[0].text


def test_normalize_content_blocks_rejects_unsupported_scalar_type() -> None:
    with pytest.raises(TypeError, match="Unsupported tool output type"):
        normalize_content_blocks(123)  # type: ignore[arg-type]


def test_normalize_content_blocks_rejects_unsupported_list_item_type() -> None:
    with pytest.raises(TypeError, match="Unsupported content block type"):
        normalize_content_blocks([TextContent(text="ok"), object()])  # type: ignore[list-item]


def test_image_user_message_conversion_through_backend() -> None:
    backend = PydanticAIBackend()
    png_bytes = b"\x89PNG\r\n\x1a\n"
    message = (
        UserMessage.builder()
        .text("describe this chart")
        .image_bytes(png_bytes, media_type="image/png")
        .build()
    )

    payload = backend._build_user_content(message)
    assert isinstance(payload, list)
    assert payload[0] == "describe this chart"
    assert isinstance(payload[1], BinaryImage)
    assert payload[1].media_type == "image/png"
    assert payload[1].data == png_bytes


def test_image_tool_output_conversion_through_backend() -> None:
    backend = PydanticAIBackend()
    png_bytes = b"\x89PNG\r\n\x1a\n"
    image = ImageContent.from_bytes(png_bytes, media_type="image/png")

    payload = backend._build_tool_content(image)
    assert isinstance(payload, BinaryImage)
    assert payload.media_type == "image/png"
    assert payload.data == png_bytes


def test_dataframe_tool_output_conversion_through_backend() -> None:
    backend = PydanticAIBackend()
    dataframe = _build_dataframe(rows=250)

    payload = backend._build_tool_content(dataframe)
    assert isinstance(payload, str)
    assert "249" in payload
    assert "..." not in payload


def test_backend_tool_content_rejects_unsupported_part() -> None:
    backend = PydanticAIBackend()
    with pytest.raises(TypeError, match="Unsupported content block type"):
        backend._build_tool_content([TextContent(text="ok"), object()])  # type: ignore[list-item]
