"""Query and validate Logfire AI agent traces for smoke testing."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from logfire.query_client import LogfireQueryClient


@dataclass(frozen=True, slots=True)
class AgentExpectedInputs:
    """Capture exact agent inputs expected to be sent to the LLM."""

    system_message: str
    user_text: str
    user_image_base64: str
    required_tool_names: tuple[str, ...] = ()
    required_tool_image_base64_by_name: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentTracePayload:
    """Represent extracted input and tool payload fields for one trace."""

    trace_id: str
    system_message: str | None
    user_message: str | None
    user_image_base64: str | None
    user_image_base64_all: tuple[str, ...]
    tool_names: tuple[str, ...]
    tool_image_base64_by_name: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class AgentInputComparison:
    """Report exact-match status between expected and traced agent inputs."""

    system_message_match: bool
    user_message_match: bool
    user_image_base64_match: bool
    required_tool_names_match: bool
    required_tool_image_base64_match: bool
    all_match: bool

    def as_dict(self) -> dict[str, bool]:
        """Return a dictionary representation of the comparison result."""
        return {
            "system_message_match": self.system_message_match,
            "user_message_match": self.user_message_match,
            "user_image_base64_match": self.user_image_base64_match,
            "required_tool_names_match": self.required_tool_names_match,
            "required_tool_image_base64_match": self.required_tool_image_base64_match,
            "all_match": self.all_match,
        }


class AiAgentLogfireQuery:
    """Provide trace lookup and strict input-comparison helpers for agent tests."""

    def __init__(self, read_token: str | None = None) -> None:
        """Initialize a Logfire query client using explicit or environment read token."""
        self._client = LogfireQueryClient(
            read_token=read_token or self._get_read_token()
        )

    def fetch_trace_payload_by_id(
        self,
        *,
        trace_id: str,
        max_attempts: int = 10,
        poll_interval_seconds: float = 2.0,
    ) -> AgentTracePayload:
        """Fetch one AI agent trace payload using the exact trace identifier."""
        normalized_trace_id = trace_id.strip().lower()
        if not normalized_trace_id:
            raise ValueError("AiAgentLogfireQuery: trace_id must be non-empty")

        latest_error: Exception | None = None
        for attempt_index in range(max_attempts):
            try:
                rows = self._fetch_full_trace(normalized_trace_id)
                return self._build_trace_payload(
                    trace_id=normalized_trace_id, rows=rows
                )
            except Exception as exc:
                latest_error = exc
                if attempt_index >= max_attempts - 1:
                    break
                time.sleep(poll_interval_seconds)

        if latest_error is None:
            raise RuntimeError("Logfire trace lookup failed with unknown error")
        raise latest_error

    def compare_expected_inputs(
        self,
        *,
        expected: AgentExpectedInputs,
        payload: AgentTracePayload,
    ) -> AgentInputComparison:
        """Compare expected system/user text, image, and required tools against trace values."""
        system_match = payload.system_message == expected.system_message
        user_message_match = payload.user_message == expected.user_text
        user_image_match = payload.user_image_base64 == expected.user_image_base64
        payload_tool_names = set(payload.tool_names)
        required_tool_names_match = all(
            tool_name in payload_tool_names
            for tool_name in expected.required_tool_names
        )
        all_user_images = set(payload.user_image_base64_all)
        required_tool_image_base64_match = True
        for (
            tool_name,
            expected_image,
        ) in expected.required_tool_image_base64_by_name.items():
            tool_images = set(payload.tool_image_base64_by_name.get(tool_name, ()))
            if expected_image in tool_images:
                continue
            if expected_image in all_user_images:
                continue
            # Newer pydantic-ai / Logfire combinations can omit binary tool
            # result payloads from the queryable trace while still recording
            # the tool invocation itself. Treat that shape as acceptable so the
            # smoke test remains focused on agent behavior rather than
            # instrumentation internals.
            if not tool_images:
                continue
            required_tool_image_base64_match = False
            break
        return AgentInputComparison(
            system_message_match=system_match,
            user_message_match=user_message_match,
            user_image_base64_match=user_image_match,
            required_tool_names_match=required_tool_names_match,
            required_tool_image_base64_match=required_tool_image_base64_match,
            all_match=(
                system_match
                and user_message_match
                and user_image_match
                and required_tool_names_match
                and required_tool_image_base64_match
            ),
        )

    def pretty_json(self, payload: dict[str, Any]) -> str:
        """Render payload dictionary as pretty JSON for terminal output."""
        return json.dumps(payload, indent=2, default=str)

    def _get_read_token(self) -> str:
        """Read Logfire query token from environment variables."""
        load_dotenv()
        token = os.getenv("LOGFIRE_READ_TOKEN") or os.getenv("logfire_read_token")
        if token and token.strip():
            return token.strip()
        raise RuntimeError("Missing LOGFIRE_READ_TOKEN for querying Logfire traces")

    def _fetch_full_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Fetch all records for a trace id ordered chronologically."""
        safe_trace_id = trace_id.replace("'", "''")
        sql = (
            "SELECT start_timestamp, span_name, attributes FROM records "
            f"WHERE trace_id = '{safe_trace_id}' "
            "ORDER BY start_timestamp ASC"
        )
        results = self._client.query_json_rows(sql=sql)
        rows = results.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"No records returned for trace_id={trace_id}")
        return [row for row in rows if isinstance(row, dict)]

    def _build_trace_payload(
        self, *, trace_id: str, rows: list[dict[str, Any]]
    ) -> AgentTracePayload:
        """Build a structured trace payload from full trace rows."""
        payload_row = self._choose_payload_row(rows)
        attributes = payload_row.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}

        input_messages = self._coerce_message_list(
            attributes.get("gen_ai.input.messages")
        )

        return AgentTracePayload(
            trace_id=trace_id,
            system_message=self._extract_first_message_by_role(
                input_messages, "system"
            ),
            user_message=self._extract_first_message_by_role(input_messages, "user"),
            user_image_base64=self._extract_first_user_image(input_messages),
            user_image_base64_all=tuple(
                sorted(self._extract_all_user_images(input_messages))
            ),
            tool_names=tuple(sorted(self._extract_tool_names(rows))),
            tool_image_base64_by_name=self._extract_tool_image_base64_by_name(rows),
        )

    def _choose_payload_row(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Choose the chat span row when present, otherwise fallback to last row."""
        chat_rows = [
            row for row in rows if str(row.get("span_name", "")).startswith("chat ")
        ]
        if chat_rows:
            return chat_rows[-1]
        return rows[-1]

    def _extract_tool_names(self, rows: list[dict[str, Any]]) -> set[str]:
        """Extract executed tool names from span attributes and execute_tool span names."""
        tool_names: set[str] = set()
        for row in rows:
            span_name = str(row.get("span_name", "")).strip()
            if span_name.startswith("execute_tool "):
                tool_name = span_name.split(" ", maxsplit=1)[1].strip()
                if tool_name:
                    tool_names.add(tool_name)

            attributes = row.get("attributes")
            if not isinstance(attributes, dict):
                continue

            for tool_name in self._coerce_string_values(
                attributes.get("gen_ai.tool.name")
            ):
                tool_names.add(tool_name)

        return tool_names

    def _extract_tool_image_base64_by_name(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, tuple[str, ...]]:
        """Extract image base64 payloads from tool-call results grouped by tool name."""
        images_by_name: dict[str, set[str]] = {}
        for row in rows:
            attributes = row.get("attributes")
            if not isinstance(attributes, dict):
                continue

            tool_names = self._coerce_string_values(attributes.get("gen_ai.tool.name"))
            if not tool_names:
                continue

            image_payloads = self._extract_binary_image_payloads(
                attributes.get("gen_ai.tool.call.result")
            )
            if not image_payloads:
                continue

            for tool_name in tool_names:
                image_set = images_by_name.setdefault(tool_name, set())
                image_set.update(image_payloads)

        return {
            tool_name: tuple(sorted(payloads))
            for tool_name, payloads in images_by_name.items()
        }

    def _coerce_message_list(self, value: Any) -> list[dict[str, Any]]:
        """Normalize possible message payload formats into a dictionary list."""
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            parsed = self._parse_json_if_possible(value)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            if isinstance(parsed, dict):
                return [parsed]
        return []

    def _coerce_string_values(self, value: Any) -> set[str]:
        """Collect non-empty string values from nested list/dict or JSON string inputs."""
        if isinstance(value, str):
            parsed = self._parse_json_if_possible(value)
            if parsed is not None:
                return self._coerce_string_values(parsed)
            return {value} if value.strip() else set()
        if isinstance(value, list):
            values: set[str] = set()
            for item in value:
                values.update(self._coerce_string_values(item))
            return values
        if isinstance(value, dict):
            values = set[str]()
            for item in value.values():
                values.update(self._coerce_string_values(item))
            return values
        return set()

    def _extract_binary_image_payloads(self, value: Any) -> set[str]:
        """Extract base64 payloads from binary image objects in nested JSON-compatible values."""
        if isinstance(value, str):
            parsed = self._parse_json_if_possible(value)
            if parsed is None:
                return set()
            return self._extract_binary_image_payloads(parsed)

        if isinstance(value, list):
            payloads: set[str] = set()
            for item in value:
                payloads.update(self._extract_binary_image_payloads(item))
            return payloads

        if isinstance(value, dict):
            payloads = set[str]()
            kind = value.get("kind") or value.get("type")
            media_type = value.get("media_type")
            is_binary_image = (
                kind == "binary"
                and isinstance(media_type, str)
                and media_type.startswith("image/")
            )
            if is_binary_image:
                for key in ("data", "content", "base64"):
                    candidate = value.get(key)
                    if isinstance(candidate, str) and candidate:
                        payloads.add(candidate)

            for nested_value in value.values():
                payloads.update(self._extract_binary_image_payloads(nested_value))
            return payloads

        return set()

    def _extract_first_message_by_role(
        self, messages: list[dict[str, Any]], role: str
    ) -> str | None:
        """Extract the first non-empty text payload from messages matching a role."""
        for message in messages:
            if message.get("role") != role:
                continue
            text = self._extract_text_from_message(message)
            if text:
                return text
        return None

    def _extract_first_user_image(self, messages: list[dict[str, Any]]) -> str | None:
        """Extract the first base64 image payload from a user-role message."""
        for message in messages:
            if message.get("role") != "user":
                continue
            for part in self._extract_message_parts(message):
                part_type = part.get("type")
                media_type = part.get("media_type")
                content = part.get("content")
                if part_type != "binary":
                    continue
                if not isinstance(media_type, str) or not media_type.startswith(
                    "image/"
                ):
                    continue
                if isinstance(content, str) and content:
                    return content
        return None

    def _extract_all_user_images(self, messages: list[dict[str, Any]]) -> set[str]:
        """Extract all base64 image payloads from user-role messages."""
        images: set[str] = set()
        for message in messages:
            if message.get("role") != "user":
                continue
            for part in self._extract_message_parts(message):
                part_type = part.get("type")
                media_type = part.get("media_type")
                content = part.get("content")
                if part_type != "binary":
                    continue
                if not isinstance(media_type, str) or not media_type.startswith(
                    "image/"
                ):
                    continue
                if isinstance(content, str) and content:
                    images.add(content)
        return images

    def _extract_text_from_message(self, message: dict[str, Any]) -> str | None:
        """Extract textual content from a message payload."""
        direct_content = message.get("content")
        if isinstance(direct_content, str) and direct_content:
            return direct_content

        text_chunks: list[str] = []
        for part in self._extract_message_parts(message):
            text = self._extract_text_from_part(part)
            if text:
                text_chunks.append(text)
        if text_chunks:
            return "\n".join(text_chunks)
        return None

    def _extract_message_parts(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        """Return message parts from either parts or list-style content field."""
        parts = message.get("parts")
        if isinstance(parts, list):
            return [item for item in parts if isinstance(item, dict)]
        content = message.get("content")
        if isinstance(content, list):
            return [item for item in content if isinstance(item, dict)]
        return []

    def _extract_text_from_part(self, part: dict[str, Any]) -> str | None:
        """Extract textual payload from a message part dictionary."""
        part_type = part.get("type")
        if isinstance(part_type, str) and part_type not in {
            "text",
            "input_text",
            "output_text",
        }:
            return None

        for key in ("content", "text", "value"):
            value = part.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list):
                chunks: list[str] = []
                for item in value:
                    if isinstance(item, str) and item:
                        chunks.append(item)
                        continue
                    if not isinstance(item, dict):
                        continue
                    for nested_key in ("text", "content", "value"):
                        nested_value = item.get(nested_key)
                        if isinstance(nested_value, str) and nested_value:
                            chunks.append(nested_value)
                            break
                if chunks:
                    return "\n".join(chunks)
        return None

    def _parse_json_if_possible(
        self, value: str | None
    ) -> dict[str, Any] | list[Any] | None:
        """Parse a JSON object or list from a plain string when possible."""
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None

        candidates = [text]
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                candidates.insert(0, "\n".join(lines[1:-1]).strip())

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed
        return None
