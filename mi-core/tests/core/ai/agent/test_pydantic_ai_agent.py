"""
Pytest smoke agent for temperature/humidity pattern analysis with pydantic-ai backend.

Run all providers:
uv run -m pytest tests/core/ai/agent/test_pydantic_ai_agent.py -s

Run one provider:
uv run -m pytest tests/core/ai/agent/test_pydantic_ai_agent.py -s --pydantic-ai-provider google:gemini-3.1-flash-lite-preview
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import time
from collections.abc import Generator
from typing import Any, Literal

from dotenv import load_dotenv
import logfire
import pandas as pd
from pydantic import BaseModel, Field
import pytest

from mi.ai import (
    AIAgentMixin,
    AIProcessorConfig,
    ImageContent,
    ReasoningEffort,
    TextContent,
    UserMessage,
    ai_tool,
)
from mi.ai.backends.base import AIUsage
from mi.core import BaseProcessor, ProcessDataObject

from tests.core.ai.agent.logfire_query_ai_agent import (
    AgentExpectedInputs,
    AiAgentLogfireQuery,
)
from tests.core.ai.provider_test_utils import (
    build_provider_test_id,
    is_provider_connection_error,
    missing_prerequisites_for_provider,
    selected_models_from_pytest_option,
)
from tests.core.ai.use_case_simulation.data_simulation import (
    simulate_relative_humidity_data,
    simulate_temperature_data,
)
from tests.core.ai.use_case_simulation.graph_image import (
    generate_humidity_graph_image_bytes,
    generate_temperature_graph_image_bytes,
)

_RESPONSE_ARTIFACT_KEY = "temperature_humidity_pattern_response"
_USAGE_ARTIFACT_KEY = "temperature_humidity_pattern_usage"
_HUMIDITY_TOOL_CALLED_ARTIFACT_KEY = "humidity_graph_tool_called"
_HUMIDITY_GRAPH_TOOL_NAME = "get_last_7_day_humidity_graph"
_INTER_PROVIDER_PAUSE_SECONDS = 0
SUPPORTED_MODEL_OPTIONS: tuple[str, str, str] = (
    "azure:gpt-5-mini",
    "azure:claude-sonnet-4-5",
    "google:gemini-3.1-flash-lite-preview",
)
SupportedModelOption = Literal[
    "azure:gpt-5-mini",
    "azure:claude-sonnet-4-5",
    "google:gemini-3.1-flash-lite-preview",
]


class TemperatureHumidityPatternOutput(BaseModel):
    """Structured result for temperature and humidity pattern-shape classification."""

    temperature_pattern_shape: Literal[
        "sine_wave", "log", "linear", "step", "other"
    ] = Field(
        description="Whether the temperature pattern approximates a sine wave, log, linear, step, or other shape",
    )
    humidity_pattern_shape: Literal["sine_wave", "log", "linear", "step", "other"] = (
        Field(
            description="Whether the humidity pattern approximates a sine wave, log, linear, step, or other shape",
        )
    )
    confidence_temperature: Literal["high", "low"] = Field(
        description="Confidence in the temperature pattern-shape assessment",
    )
    confidence_humidity: Literal["high", "low"] = Field(
        description="Confidence in the humidity pattern-shape assessment",
    )


@dataclass
class TemperatureHumidityAgentDataObject(ProcessDataObject):
    """Carry simulated temperature and humidity data for AI agent execution."""

    temperature_data: pd.DataFrame = field(default_factory=pd.DataFrame)
    humidity_data: pd.DataFrame = field(default_factory=pd.DataFrame)


def _build_last_7_day_humidity_graph_tool(
    data_object: TemperatureHumidityAgentDataObject,
) -> Any:
    """Build a tool that returns a PNG graph of last-7-day humidity readings."""

    @ai_tool(name=_HUMIDITY_GRAPH_TOOL_NAME)
    def get_last_7_day_humidity_graph() -> ImageContent:
        """Return an image content block for a last-7-day humidity graph."""
        humidity_graph_bytes = generate_humidity_graph_image_bytes(
            data_object.humidity_data
        )
        data_object.set_artifact(_HUMIDITY_TOOL_CALLED_ARTIFACT_KEY, True)
        return ImageContent.from_bytes(
            data=humidity_graph_bytes, media_type="image/png"
        )

    return get_last_7_day_humidity_graph


class TemperatureHumidityPatternAgent(
    AIAgentMixin[TemperatureHumidityAgentDataObject, TemperatureHumidityPatternOutput],
    BaseProcessor[TemperatureHumidityAgentDataObject],
):
    """Classify temperature and humidity pattern shapes using image plus humidity tool."""

    output_schema = TemperatureHumidityPatternOutput

    def __init__(self, config: AIProcessorConfig) -> None:
        """Initialize agent with required AI processor configuration."""
        super().__init__(config)
        self._cached_user_message: UserMessage | None = None

    def _build_system_prompt(
        self, data_object: TemperatureHumidityAgentDataObject
    ) -> str:
        """Return system instructions for temperature and humidity shape classification."""
        return (
            "You are analyzing two time-series patterns: a temperature chart image and a humidity graph tool response. "
            f"You must call the tool '{_HUMIDITY_GRAPH_TOOL_NAME}' before finalizing your answer. "
            "Determine both pattern shapes and respond with structured JSON only. "
            "Set temperature_pattern_shape to 'sine_wave' when the chart shows a repeating sinusoidal cycle "
            "(peaks around midday, troughs around midnight), otherwise set 'other'. "
            "Set humidity_pattern_shape to 'step' when the humidity graph shows clear flat plateaus "
            "with abrupt jumps between levels, otherwise set 'other'. "
            "Set confidence_temperature to 'high' only when the temperature classification is strongly supported; otherwise set it to 'low'. "
            "Set confidence_humidity to 'high' only when the humidity classification is strongly supported; otherwise set it to 'low'."
        )

    def _build_user_message(
        self, data_object: TemperatureHumidityAgentDataObject
    ) -> UserMessage:
        """Build multimodal message with temperature chart image and brief data context."""
        if self._cached_user_message is not None:
            return self._cached_user_message

        graph_bytes = generate_temperature_graph_image_bytes(
            data_object.temperature_data
        )
        user_text = "This image shows temperature over time for the past month with hourly readings."
        self._cached_user_message = (
            UserMessage.builder()
            .text(user_text)
            .image_bytes(graph_bytes, media_type="image/png")
            .build()
        )
        return self._cached_user_message

    def _build_tools(
        self, data_object: TemperatureHumidityAgentDataObject
    ) -> list[Any]:
        """Build tools available to the agent during execution."""
        return [_build_last_7_day_humidity_graph_tool(data_object)]

    def _attach_response(
        self,
        data_object: TemperatureHumidityAgentDataObject,
        response: TemperatureHumidityPatternOutput,
    ) -> None:
        """Attach the structured output under a stable artifact key."""
        data_object.set_artifact(_RESPONSE_ARTIFACT_KEY, response.model_dump())

    def _attach_usage(
        self, data_object: TemperatureHumidityAgentDataObject, usage: AIUsage
    ) -> None:
        """Attach normalized usage metrics under a stable artifact key."""
        data_object.set_artifact(
            _USAGE_ARTIFACT_KEY,
            {
                "requests": usage.requests,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
            },
        )


class TemperatureHumidityPatternAgentOrchestrator:
    """Run the temperature/humidity agent with configurable model and reasoning effort."""

    def run(
        self,
        *,
        model_name: SupportedModelOption,
        reasoning_effort: ReasoningEffort | str,
    ) -> TemperatureHumidityPatternOutput:
        """Execute the agent, log artifacts to Logfire, and return structured output."""
        _configure_logfire()
        effort = self._normalize_reasoning_effort(reasoning_effort)
        config = self._build_config(
            model_name=model_name,
            reasoning_effort=effort,
        )
        agent = TemperatureHumidityPatternAgent(config=config)
        data_object = self._build_data_object()
        expected_inputs = self._build_expected_inputs(
            agent=agent, data_object=data_object
        )
        with logfire.span(
            "core-ai-agent-pydantic-ai-test",
            workflow_model=model_name,
        ) as workflow_span:
            agent.process(data_object)
            trace_id = self._extract_trace_id(workflow_span)
        response = self._read_response(data_object)
        self._query_logfire_and_print(
            expected_inputs=expected_inputs, trace_id=trace_id
        )
        self._verify_and_print_output_match(response=response, data_object=data_object)
        return response

    def _build_config(
        self,
        *,
        model_name: SupportedModelOption,
        reasoning_effort: ReasoningEffort,
    ) -> AIProcessorConfig:
        """Build AI processor config from model and effort selections."""
        return AIProcessorConfig(
            model=model_name,
            backend="pydantic_ai",
            reasoning_effort=reasoning_effort,
            max_turns=12,
            retries=2,
            timeout=120.0,
        )

    def _build_data_object(self) -> TemperatureHumidityAgentDataObject:
        """Construct agent data object with one-month temperature and humidity readings."""
        temperature_data = simulate_temperature_data()
        humidity_data = simulate_relative_humidity_data()
        return TemperatureHumidityAgentDataObject(
            temperature_data=temperature_data,
            humidity_data=humidity_data,
        )

    def _read_response(
        self,
        data_object: TemperatureHumidityAgentDataObject,
    ) -> TemperatureHumidityPatternOutput:
        """Parse and return structured agent output from artifacts."""
        payload = data_object.get_artifact(_RESPONSE_ARTIFACT_KEY)
        if payload is None:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Agent response artifact missing"
            )
        return TemperatureHumidityPatternOutput.model_validate(payload)

    def _normalize_reasoning_effort(
        self, reasoning_effort: ReasoningEffort | str
    ) -> ReasoningEffort:
        """Normalize string or enum effort input into ReasoningEffort."""
        if isinstance(reasoning_effort, ReasoningEffort):
            return reasoning_effort
        return ReasoningEffort(reasoning_effort.strip().lower())

    def _verify_and_print_output_match(
        self,
        *,
        response: TemperatureHumidityPatternOutput,
        data_object: TemperatureHumidityAgentDataObject,
    ) -> None:
        """Verify and print structured output match checks for schema, shapes, and tool usage."""
        output_payload = response.model_dump()
        expected_keys = set(TemperatureHumidityPatternOutput.model_fields.keys())
        actual_keys = set(output_payload.keys())

        schema_match = actual_keys == expected_keys
        temperature_pattern_shape_match = (
            response.temperature_pattern_shape == "sine_wave"
        )
        humidity_pattern_shape_match = response.humidity_pattern_shape == "step"
        temperature_confidence_valid = response.confidence_temperature in {
            "high",
            "low",
        }
        humidity_confidence_valid = response.confidence_humidity in {"high", "low"}
        humidity_tool_called = bool(
            data_object.get_artifact(_HUMIDITY_TOOL_CALLED_ARTIFACT_KEY)
        )
        all_match = (
            schema_match
            and temperature_pattern_shape_match
            and humidity_pattern_shape_match
            and temperature_confidence_valid
            and humidity_confidence_valid
            and humidity_tool_called
        )

        output_match = {
            "structured_output_schema_match": schema_match,
            "temperature_pattern_shape_match": temperature_pattern_shape_match,
            "humidity_pattern_shape_match": humidity_pattern_shape_match,
            "temperature_confidence_valid": temperature_confidence_valid,
            "humidity_confidence_valid": humidity_confidence_valid,
            "humidity_tool_called": humidity_tool_called,
            "all_match": all_match,
        }
        print("=== OUTPUT EXACT MATCH ===")
        print(self._pretty_json(output_match))

        if not all_match:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Output comparison failed "
                "(schema_match="
                f"{schema_match}, temperature_pattern_shape_match={temperature_pattern_shape_match}, "
                f"humidity_pattern_shape_match={humidity_pattern_shape_match}, "
                f"temperature_confidence_valid={temperature_confidence_valid}, "
                f"humidity_confidence_valid={humidity_confidence_valid}, "
                f"humidity_tool_called={humidity_tool_called})"
            )

    def _build_expected_inputs(
        self,
        *,
        agent: TemperatureHumidityPatternAgent,
        data_object: TemperatureHumidityAgentDataObject,
    ) -> AgentExpectedInputs:
        """Build exact expected system/user inputs and required tools for trace comparison."""
        system_message = agent._build_system_prompt(data_object)
        user_message = agent._resolve_user_message(data_object)
        user_text, user_image_base64 = self._extract_user_text_and_image(user_message)
        humidity_tool_image_base64 = ImageContent.from_bytes(
            data=generate_humidity_graph_image_bytes(data_object.humidity_data),
            media_type="image/png",
        ).base64_data
        return AgentExpectedInputs(
            system_message=system_message,
            user_text=user_text,
            user_image_base64=user_image_base64,
            required_tool_names=(_HUMIDITY_GRAPH_TOOL_NAME,),
            required_tool_image_base64_by_name={
                _HUMIDITY_GRAPH_TOOL_NAME: humidity_tool_image_base64,
            },
        )

    def _extract_user_text_and_image(
        self, user_message: UserMessage
    ) -> tuple[str, str]:
        """Extract first user text and first image base64 blocks from a user message."""
        user_text = ""
        user_image_base64 = ""
        for block in user_message.content:
            if isinstance(block, TextContent) and not user_text:
                user_text = block.text
            if isinstance(block, ImageContent) and not user_image_base64:
                user_image_base64 = block.base64_data

        if not user_text:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Missing user text block"
            )
        if not user_image_base64:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Missing user image block"
            )
        return user_text, user_image_base64

    def _extract_trace_id(self, span: Any) -> str:
        """Extract a 32-character lowercase trace id from a started Logfire span."""
        span_context = span.get_span_context()
        if not span_context.is_valid:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Unable to resolve a valid trace id"
            )
        return format(span_context.trace_id, "032x")

    def _query_logfire_and_print(
        self, *, expected_inputs: AgentExpectedInputs, trace_id: str
    ) -> None:
        """Query the exact Logfire trace and print exact input comparison results."""
        query = AiAgentLogfireQuery()
        last_comparison = None
        last_error: Exception | None = None
        max_attempts = 8
        poll_interval_seconds = 1.5
        for attempt_index in range(max_attempts):
            try:
                payload = query.fetch_trace_payload_by_id(
                    trace_id=trace_id,
                    max_attempts=1,
                    poll_interval_seconds=0.0,
                )
            except Exception as exc:
                last_error = exc
                if attempt_index >= max_attempts - 1:
                    raise
                time.sleep(
                    _poll_interval_for_logfire_error(
                        exc=exc,
                        default_seconds=poll_interval_seconds,
                        attempt_index=attempt_index,
                    )
                )
                continue
            comparison = query.compare_expected_inputs(
                expected=expected_inputs, payload=payload
            )
            last_comparison = comparison
            if comparison.all_match:
                break
            if attempt_index >= max_attempts - 1:
                break
            time.sleep(poll_interval_seconds)

        if last_comparison is None:
            if last_error is not None:
                raise last_error
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Unable to compute Logfire input comparison"
            )

        print("=== INPUT EXACT MATCH ===")
        print(query.pretty_json(last_comparison.as_dict()))
        if not last_comparison.all_match:
            raise ValueError(
                "TemperatureHumidityPatternAgentOrchestrator: Logfire input comparison failed exact match check"
            )

    def _pretty_json(self, payload: dict[str, bool]) -> str:
        """Render a compact pretty JSON string for terminal match output."""
        return json.dumps(payload, indent=2)


def _configure_logfire() -> None:
    """Configure Logfire and pydantic-ai instrumentation for this agent."""
    logfire.configure(
        service_name=os.getenv(
            "LOGFIRE_SERVICE_NAME", "core-ai-agent-pydantic-ai-test"
        ),
        send_to_logfire="if-token-present",
    )
    logfire.instrument_pydantic_ai(include_content=True, include_binary_content=True)


def _poll_interval_for_logfire_error(
    *, exc: Exception, default_seconds: float, attempt_index: int
) -> float:
    """Back off more aggressively when Logfire query rate limits are hit."""
    message = str(exc).lower()
    if "rate limit exceeded" in message or "429" in message:
        return max(default_seconds, 5.0 * (attempt_index + 1))
    return default_seconds


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize provider test with one or all providers based on pytest CLI selection."""
    if "model_name" not in metafunc.fixturenames:
        return

    selected_models = selected_models_from_pytest_option(
        metafunc.config, SUPPORTED_MODEL_OPTIONS
    )
    metafunc.parametrize(
        "model_name",
        selected_models,
        ids=[build_provider_test_id(model_name) for model_name in selected_models],
    )


@pytest.fixture(scope="module")
def _provider_pause_state() -> dict[str, bool]:
    """Track whether at least one provider test has already completed in this module."""
    return {"has_completed_run": False}


@pytest.fixture(autouse=True)
def _pause_between_provider_tests(
    _provider_pause_state: dict[str, bool],
) -> Generator[None, None, None]:
    """Pause between provider tests to avoid short-window throttling."""
    if _provider_pause_state["has_completed_run"]:
        time.sleep(_INTER_PROVIDER_PAUSE_SECONDS)
    try:
        yield
    finally:
        _provider_pause_state["has_completed_run"] = True


@pytest.mark.smoke
def test_pydantic_ai_agent_model(model_name: SupportedModelOption) -> None:
    """Run one provider variant and validate structured output and trace-input exact match."""
    load_dotenv()
    missing_prereq = missing_prerequisites_for_provider(model_name)
    if missing_prereq is not None:
        pytest.skip(f"Skipping {model_name}: missing {missing_prereq}")
    reasoning_effort = os.getenv("PYDANTIC_AI_REASONING_EFFORT", "low")
    orchestrator = TemperatureHumidityPatternAgentOrchestrator()
    try:
        orchestrator.run(
            model_name=model_name,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        if is_provider_connection_error(exc):
            pytest.skip(f"Skipping {model_name}: provider connection unavailable")
        raise
