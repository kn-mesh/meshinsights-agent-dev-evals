"""
Pytest smoke workflow for temperature-pattern analysis with pydantic-ai backend.

Run all providers:
uv run -m pytest tests/core/ai/workflow/test_pydantic_ai_workflow.py -s

Run one provider:
uv run -m pytest tests/core/ai/workflow/test_pydantic_ai_workflow.py -s --pydantic-ai-provider google:gemini-3.1-flash-lite-preview
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
    AIProcessorConfig,
    AIWorkflowMixin,
    ImageContent,
    ReasoningEffort,
    TextContent,
    UserMessage,
)
from mi.ai.backends.base import AIUsage
from mi.core import BaseProcessor, ProcessDataObject

from tests.core.ai.provider_test_utils import (
    build_provider_test_id,
    is_provider_connection_error,
    missing_prerequisites_for_provider,
    selected_models_from_pytest_option,
)
from tests.core.ai.workflow.logfire_query_ai_workflow import (
    AiWorkflowLogfireQuery,
    WorkflowExpectedInputs,
)
from tests.core.ai.use_case_simulation.data_simulation import (
    select_last_n_days,
    simulate_temperature_data,
)
from tests.core.ai.use_case_simulation.graph_image import (
    generate_temperature_graph_image_bytes,
)

_RESPONSE_ARTIFACT_KEY = "temperature_pattern_response"
_USAGE_ARTIFACT_KEY = "temperature_pattern_usage"
_INTER_PROVIDER_PAUSE_SECONDS = (
    0  # sometimes we run into logfire query rate limits, bumping this helps
)
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


class TemperaturePatternOutput(BaseModel):
    """Structured result for chart pattern-shape classification."""

    pattern_shape: Literal["sine_wave", "log", "linear", "step", "other"] = Field(
        description="Whether the plotted temperature pattern approximates a sine wave, log, linear, step, or other shape",
    )
    confidence: Literal["high", "low"] = Field(
        description="Confidence in the pattern-shape assessment",
    )


@dataclass
class TemperatureWorkflowDataObject(ProcessDataObject):
    """Carry simulated temperature data for AI workflow execution."""

    temperature_data: pd.DataFrame = field(default_factory=pd.DataFrame)


class TemperaturePatternWorkflow(
    AIWorkflowMixin[TemperatureWorkflowDataObject, TemperaturePatternOutput],
    BaseProcessor[TemperatureWorkflowDataObject],
):
    """Classify temperature-chart shape from a one-month hourly trend image."""

    output_schema = TemperaturePatternOutput

    def __init__(self, config: AIProcessorConfig) -> None:
        """Initialize workflow with required AI processor configuration."""
        super().__init__(config)
        self._cached_user_message: UserMessage | None = None

    def _build_system_prompt(self, data_object: TemperatureWorkflowDataObject) -> str:
        """Return system instructions for chart shape classification."""
        return (
            "You are analyzing a time-series temperature chart. "
            "Determine the overall pattern shape. "
            "Respond with structured JSON only. "
            "Set pattern_shape to 'sine_wave' when the chart shows a repeating sinusoidal cycle "
            "(peaks around midday, troughs around midnight), otherwise set 'other'. "
            "Set confidence to 'high' only when the evidence is visually consistent across the month; "
            "otherwise set it to 'low'."
        )

    def _build_user_message(
        self, data_object: TemperatureWorkflowDataObject
    ) -> UserMessage:
        """Build multimodal message with chart image and brief data context."""
        if self._cached_user_message is not None:
            return self._cached_user_message

        graph_bytes = generate_temperature_graph_image_bytes(
            data_object.temperature_data
        )
        last_day_temperature_data = select_last_n_days(
            data_object.temperature_data,
            timestamp_column="timestamp",
            days=1,
        )
        user_text = "This image shows temperature over time for the past month with hourly readings."
        self._cached_user_message = (
            UserMessage.builder()
            .text(user_text)
            .dataframe(last_day_temperature_data, string_format="csv")
            .image_bytes(graph_bytes, media_type="image/png")
            .build()
        )
        return self._cached_user_message

    def _attach_response(
        self,
        data_object: TemperatureWorkflowDataObject,
        response: TemperaturePatternOutput,
    ) -> None:
        """Attach the structured output under a stable artifact key."""
        data_object.set_artifact(_RESPONSE_ARTIFACT_KEY, response.model_dump())

    def _attach_usage(
        self, data_object: TemperatureWorkflowDataObject, usage: AIUsage
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


class TemperaturePatternWorkflowOrchestrator:
    """Run the temperature-pattern workflow with configurable model/effort."""

    def run(
        self,
        *,
        model_name: SupportedModelOption,
        reasoning_effort: ReasoningEffort | str,
    ) -> TemperaturePatternOutput:
        """Execute the workflow, log artifacts to Logfire, and return structured output."""
        _configure_logfire()
        effort = self._normalize_reasoning_effort(reasoning_effort)
        config = self._build_config(
            model_name=model_name,
            reasoning_effort=effort,
        )
        workflow = TemperaturePatternWorkflow(config=config)
        data_object = self._build_data_object()
        expected_inputs = self._build_expected_inputs(
            workflow=workflow, data_object=data_object
        )
        with logfire.span(
            "core-ai-workflow-pydantic-ai-test",
            workflow_model=model_name,
        ) as workflow_span:
            workflow.process(data_object)
            trace_id = self._extract_trace_id(workflow_span)
        response = self._read_response(data_object)
        self._query_logfire_and_print(
            expected_inputs=expected_inputs, trace_id=trace_id
        )
        self._verify_and_print_output_match(response=response)
        return response

    def _build_config(
        self,
        *,
        model_name: SupportedModelOption,
        reasoning_effort: ReasoningEffort,
    ) -> AIProcessorConfig:
        """Build AI processor config from model/effort selections."""
        return AIProcessorConfig(
            model=model_name,
            backend="pydantic_ai",
            reasoning_effort=reasoning_effort,
            retries=2,
            timeout=120.0,
        )

    def _build_data_object(self) -> TemperatureWorkflowDataObject:
        """Construct workflow data object with one-month simulated readings."""
        temperature_data = simulate_temperature_data()
        return TemperatureWorkflowDataObject(temperature_data=temperature_data)

    def _read_response(
        self, data_object: TemperatureWorkflowDataObject
    ) -> TemperaturePatternOutput:
        """Parse and return structured workflow output from artifacts."""
        payload = data_object.get_artifact(_RESPONSE_ARTIFACT_KEY)
        if payload is None:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Workflow response artifact missing"
            )
        return TemperaturePatternOutput.model_validate(payload)

    def _normalize_reasoning_effort(
        self, reasoning_effort: ReasoningEffort | str
    ) -> ReasoningEffort:
        """Normalize string or enum effort input into ReasoningEffort."""
        if isinstance(reasoning_effort, ReasoningEffort):
            return reasoning_effort
        return ReasoningEffort(reasoning_effort.strip().lower())

    def _verify_and_print_output_match(
        self, *, response: TemperaturePatternOutput
    ) -> None:
        """Verify and print structured output match checks for schema and shape."""
        output_payload = response.model_dump()
        expected_keys = set(TemperaturePatternOutput.model_fields.keys())
        actual_keys = set(output_payload.keys())

        schema_match = actual_keys == expected_keys
        pattern_shape_match = response.pattern_shape == "sine_wave"
        all_match = schema_match and pattern_shape_match

        output_match = {
            "structured_output_schema_match": schema_match,
            "pattern_shape_match": pattern_shape_match,
            "all_match": all_match,
        }
        print("=== OUTPUT EXACT MATCH ===")
        print(self._pretty_json(output_match))

        if not all_match:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Output comparison failed "
                f"(schema_match={schema_match}, pattern_shape_match={pattern_shape_match})"
            )

    def _build_expected_inputs(
        self,
        *,
        workflow: TemperaturePatternWorkflow,
        data_object: TemperatureWorkflowDataObject,
    ) -> WorkflowExpectedInputs:
        """Build exact expected system and user inputs for post-run trace comparison."""
        system_message = workflow._build_system_prompt(data_object)
        user_message = workflow._resolve_user_message(data_object)
        user_text, user_image_base64 = self._extract_user_text_and_image(user_message)
        return WorkflowExpectedInputs(
            system_message=system_message,
            user_text=user_text,
            user_image_base64=user_image_base64,
        )

    def _extract_user_text_and_image(
        self, user_message: UserMessage
    ) -> tuple[str, str]:
        """Extract all user text blocks and first image base64 block from a user message."""
        user_text_chunks: list[str] = []
        user_image_base64 = ""
        for block in user_message.content:
            if isinstance(block, TextContent):
                user_text_chunks.append(block.text)
            if isinstance(block, ImageContent) and not user_image_base64:
                user_image_base64 = block.base64_data

        # Preserve exact text payload (including trailing newline from CSV blocks)
        # so Logfire exact-match comparisons stay byte-for-byte aligned.
        user_text = "\n".join(user_text_chunks)
        if not user_text:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Missing user text block"
            )
        if not user_image_base64:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Missing user image block"
            )
        return user_text, user_image_base64

    def _extract_trace_id(self, span: Any) -> str:
        """Extract a 32-character lowercase trace id from a started Logfire span."""
        span_context = span.get_span_context()
        if not span_context.is_valid:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Unable to resolve a valid trace id"
            )
        return format(span_context.trace_id, "032x")

    def _query_logfire_and_print(
        self, *, expected_inputs: WorkflowExpectedInputs, trace_id: str
    ) -> None:
        """Query the exact Logfire trace and print exact input comparison results."""
        query = AiWorkflowLogfireQuery()
        payload = None
        comparison = None
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
            if comparison.all_match:
                break
            if attempt_index >= max_attempts - 1:
                break
            time.sleep(poll_interval_seconds)

        if payload is None:
            if last_error is not None:
                raise last_error
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Unable to fetch Logfire trace payload"
            )
        if comparison is None:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Unable to compute Logfire input comparison"
            )

        print("=== INPUT EXACT MATCH ===")
        print(query.pretty_json(comparison.as_dict()))
        if not comparison.all_match:
            raise ValueError(
                "TemperaturePatternWorkflowOrchestrator: Logfire input comparison failed exact match check"
            )

    def _pretty_json(self, payload: dict[str, bool]) -> str:
        """Render a compact pretty JSON string for terminal match output."""
        return json.dumps(payload, indent=2)


def _configure_logfire() -> None:
    """Configure Logfire and pydantic-ai instrumentation for this workflow."""
    logfire.configure(
        service_name=os.getenv(
            "LOGFIRE_SERVICE_NAME", "core-ai-workflow-pydantic-ai-test"
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
    """Pause 20 seconds between provider tests to avoid Logfire short-window throttling."""
    if _provider_pause_state["has_completed_run"]:
        time.sleep(_INTER_PROVIDER_PAUSE_SECONDS)
    try:
        yield
    finally:
        _provider_pause_state["has_completed_run"] = True


@pytest.mark.smoke
def test_pydantic_ai_workflow_model(model_name: SupportedModelOption) -> None:
    """Run one provider variant and validate structured output and trace-input exact match."""
    load_dotenv()
    missing_prereq = missing_prerequisites_for_provider(model_name)
    if missing_prereq is not None:
        pytest.skip(f"Skipping {model_name}: missing {missing_prereq}")
    reasoning_effort = os.getenv("PYDANTIC_AI_REASONING_EFFORT", "low")
    orchestrator = TemperaturePatternWorkflowOrchestrator()
    try:
        result = orchestrator.run(
            model_name=model_name,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        if is_provider_connection_error(exc):
            pytest.skip(f"Skipping {model_name}: provider connection unavailable")
        raise
    expected_keys = set(TemperaturePatternOutput.model_fields.keys())
    actual_keys = set(result.model_dump().keys())
    assert actual_keys == expected_keys
    assert result.pattern_shape == "sine_wave"
    assert result.confidence in {"high", "low"}
