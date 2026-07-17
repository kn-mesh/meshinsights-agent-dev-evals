"""Query and validate Logfire AI workflow traces for smoke testing."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from logfire.query_client import LogfireQueryClient


@dataclass(frozen=True, slots=True)
class WorkflowExpectedInputs:
    """Capture exact workflow inputs expected to be sent to the LLM."""

    system_message: str
    user_text: str
    user_image_base64: str


@dataclass(frozen=True, slots=True)
class WorkflowTracePayload:
    """Represent extracted input and output payload fields for one trace."""

    trace_id: str
    system_message: str | None
    user_message: str | None
    user_image_base64: str | None


@dataclass(frozen=True, slots=True)
class WorkflowInputComparison:
    """Report exact-match status between expected and traced workflow inputs."""

    system_message_match: bool
    user_message_match: bool
    user_image_base64_match: bool
    all_match: bool

    def as_dict(self) -> dict[str, bool]:
        """Return a dictionary representation of the comparison result."""
        return {
            "system_message_match": self.system_message_match,
            "user_message_match": self.user_message_match,
            "user_image_base64_match": self.user_image_base64_match,
            "all_match": self.all_match,
        }


class AiWorkflowLogfireQuery:
    """Provide trace lookup and strict input-comparison helpers for workflow tests."""

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
    ) -> WorkflowTracePayload:
        """Fetch one AI chat trace payload using the exact trace identifier."""
        normalized_trace_id = trace_id.strip().lower()
        if not normalized_trace_id:
            raise ValueError("AiWorkflowLogfireQuery: trace_id must be non-empty")

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
        expected: WorkflowExpectedInputs,
        payload: WorkflowTracePayload,
    ) -> WorkflowInputComparison:
        """Compare expected system/user text and image inputs against traced payload values."""
        system_match = payload.system_message == expected.system_message
        user_message_match = payload.user_message == expected.user_text
        user_image_match = payload.user_image_base64 == expected.user_image_base64
        return WorkflowInputComparison(
            system_message_match=system_match,
            user_message_match=user_message_match,
            user_image_base64_match=user_image_match,
            all_match=system_match and user_message_match and user_image_match,
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
    ) -> WorkflowTracePayload:
        """Build a structured trace payload from full trace rows."""
        payload_row = self._choose_payload_row(rows)
        attributes = payload_row.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}

        input_messages = self._coerce_message_list(
            attributes.get("gen_ai.input.messages")
        )

        return WorkflowTracePayload(
            trace_id=trace_id,
            system_message=self._extract_first_message_by_role(
                input_messages, "system"
            ),
            user_message=self._extract_first_message_by_role(input_messages, "user"),
            user_image_base64=self._extract_first_user_image(input_messages),
        )

    def _choose_payload_row(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Choose the richest chat span row when present, otherwise fallback to last row."""
        chat_rows = [
            row for row in rows if str(row.get("span_name", "")).startswith("chat ")
        ]
        if chat_rows:
            scored_rows = [
                (self._score_payload_row(row), index, row)
                for index, row in enumerate(chat_rows)
            ]
            scored_rows.sort(key=lambda item: (item[0], item[1]))
            return scored_rows[-1][2]
        return rows[-1]

    def _score_payload_row(self, row: dict[str, Any]) -> int:
        """Score a candidate payload row by how much input context it preserves."""
        attributes = row.get("attributes")
        if not isinstance(attributes, dict):
            return 0
        input_messages = self._coerce_message_list(
            attributes.get("gen_ai.input.messages")
        )
        score = 0
        if self._extract_first_message_by_role(input_messages, "system"):
            score += 1
        if self._extract_first_message_by_role(input_messages, "user"):
            score += 1
        if self._extract_first_user_image(input_messages):
            score += 1
        return score

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
