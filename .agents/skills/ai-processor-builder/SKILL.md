---
name: ai-processor-builder
description: Build or update AI workflow and agent processors in this repo using mi.ai. Use this skill when a request involves adding structured-output AI processors, multimodal user messages, DataFrame-to-string inputs, tool-enabled agent processors, or stable AI artifact attachment for downstream hydrators and evals.
---

# AI Processor Builder

Use this skill for AI processor implementation work in this repo. It is grounded in the lightweight repo guidance plus the actual `mi.ai` API available in the project environment.

## Scope Of This Skill

This skill defines recommended AI processor patterns for an AI coding agent building on top of `mi.ai` and `mi-core`.

Treat it as default implementation guidance, not as a guarantee that every existing processor in the repo already follows the exact artifact names or handoff contracts described here.

Rules:
- Prefer these patterns by default when building new AI processors.
- If the repo already uses a different but coherent processor contract, preserve that local contract unless the user asks to migrate it.
- Keep concrete API details and referenced package behavior accurate to the local environment.
- When this skill describes a stable artifact or downstream handoff pattern, read that as the preferred agent-facing default unless the repo has a deliberate local alternative.

Use `$external-runtime-setup` when the task also depends on provider auth, tracing, or runtime AI overrides. Use `$agent-eval-builder` when the processor output must remain compatible with eval orchestration.

## When To Use It

Use this skill when the user asks you to:
- build a new AI workflow processor,
- build a tool-enabled AI agent processor,
- add structured model output with a Pydantic schema,
- attach DataFrames or images to AI inputs,
- fix unstable AI artifact or usage attachment behavior.

Do not add an AI processor when compute-only logic already solves the use case reliably enough.

## Processor Shapes

Choose one processor shape before coding.

### Workflow processor

Use for one-shot structured generation with no tool loop.

Inherit from:
- `AIWorkflowMixin[YourProcessObject, YourOutputSchema]`
- `BaseProcessor[YourProcessObject]`

Required members:
- `output_schema`
- `system_prompt` or `_build_system_prompt(...)`
- `_build_user_message(...)`

Optional overrides:
- `_attach_response(...)`
- `_attach_usage(...)`

### Agent processor

Use for multi-turn reasoning with tools.

Inherit from:
- `AIAgentMixin[YourProcessObject, YourOutputSchema]`
- `BaseProcessor[YourProcessObject]`

Required members:
- `output_schema`
- `system_prompt` or `_build_system_prompt(...)`
- `_build_user_message(...)`
- `_build_tools(...)`

Agent processors also require `max_turns` in `AIProcessorConfig`.

## Config Surface

Use `AIProcessorConfig` or a small subclass of it for processor config.

Important fields from the installed `mi.ai` package:
- `model`: required provider/model identifier such as `azure:gpt-5.4`
- `backend`: defaults to `"auto"`
- `reasoning_effort`: defaults to `medium`
- `max_turns`: defaults to `10`
- `attach_usage`: defaults to `True`
- `attach_response`: defaults to `True`
- `timeout`
- `retries`: defaults to `3`
- `output_retries`
- `tool_timeout`
- `provider_options`
- `backend_options`

Keep config focused. Do not bury prompt content or business logic in config objects.

## Structured Outputs

AI outputs should be structured Pydantic models, not raw strings.

Recommended pattern:
- define a dedicated `BaseModel`,
- set `output_schema = YourSchema`,
- forbid extra fields when the output contract matters.

```python
from pydantic import BaseModel, ConfigDict, Field


class ClassificationResult(BaseModel):
    """Structured AI classification output."""

    model_config = ConfigDict(extra="forbid")

    classification: str = Field(...)
    confidence: str = Field(...)
    explanation: str = Field(...)
```

## Message Construction

`mi.ai` accepts `UserMessage` or `UserMessageBuilder`. Either is valid because the mixin resolves builders automatically.

Use these helpers:
- `UserMessage().add_text(...)`
- `UserMessage().add_dataframe(df, string_format="csv")`
- `UserMessage().add_image_bytes(data, media_type="image/png")`
- `ImageContent.from_bytes(...)`
- `convert_dataframe_to_string(df, "csv" | "json" | "markdown" | "dataframe")`

Prefer `"csv"` for DataFrame inputs unless the task clearly benefits from another format.

## Prompt Style

- Write system prompts as explicit f-strings.
- Write user text blocks as explicit f-strings.
- Do not use adjacent string-literal concatenation for prompts.
- Keep system prompts narrow: task, rules, output criteria.
- Put unit-specific facts in the user message, not the system prompt.

## Input Shapes

### Text

Use `add_text(...)` for instructions, context, and derived observations.

### Tabular

Use `add_dataframe(...)` or `convert_dataframe_to_string(...)` instead of ad hoc table formatting.

Supported DataFrame string formats from the installed `mi.ai` package:
- `"csv"`
- `"json"`
- `"markdown"`
- `"dataframe"`

```python
from mi.ai import UserMessage


def _build_user_message(self, data_object: YourProcessObject) -> UserMessage:
    """Build the user message for the current unit."""

    return (
        UserMessage()
        .add_text(f"Analyze unit {data_object.unit_id}.")
        .add_dataframe(data_object.get_window_dataframe(), string_format="csv")
    )
```

### Images

Use deterministic static rendering for AI-facing plots or charts. In AI paths:
- render with a deterministic backend,
- keep labels and legend readable,
- fail fast on empty data windows,
- do not send blank fallback images.

Attach image content with:
- `UserMessage.add_image_bytes(...)`
- `UserMessage.add_image(...)`
- `ImageContent.from_bytes(...)`

## Workflow Skeleton

```python
from mi.ai import AIProcessorConfig, AIWorkflowMixin, UserMessage
from mi.core.processors import BaseProcessor


class ClassificationProcessorConfig(AIProcessorConfig):
    """AI config for classification workflow."""


class ClassificationProcessor(
    AIWorkflowMixin[YourProcessObject, ClassificationResult],
    BaseProcessor[YourProcessObject],
):
    """Run one structured AI classification call."""

    output_schema = ClassificationResult

    def _build_system_prompt(self, data_object: YourProcessObject) -> str:
        """Build the system prompt."""

        return f"You classify the unit outcome using the provided evidence."

    def _build_user_message(self, data_object: YourProcessObject) -> UserMessage:
        """Build the user message."""

        return (
            UserMessage()
            .add_text(f"Unit ID: {data_object.unit_id}")
            .add_dataframe(data_object.get_window_dataframe(), string_format="csv")
        )

    def _attach_response(
        self, data_object: YourProcessObject, response: ClassificationResult
    ) -> None:
        """Store a stable artifact for downstream hydrators."""

        data_object.set_artifact("ai_classification", response)
```

## Agent Tool Patterns

Prefer small, deterministic tools with clear names and docstrings.

Use `@ai_tool(...)` when possible:

```python
from mi.ai import ToolContext, ai_tool


@ai_tool(name="fetch_recent_events")
def fetch_recent_events(ctx: ToolContext[YourProcessObject], limit: int = 5) -> str:
    """Return recent events relevant to the current unit."""

    return ctx.data_object.get_recent_events(limit=limit)
```

Tool context is inferred if the first parameter is annotated as `ToolContext[...]` or named `ctx`.

Supported tool return shapes from `mi.ai`:
- `str`
- one `ContentBlock`
- `list[ContentBlock]`
- `pd.DataFrame` converted automatically to CSV text

Keep tools bounded. If a tool can compute the answer deterministically, prefer doing that outside the model loop entirely.

## Attachment Behavior

This is the most important default to understand from `mi.ai`:

- If you do not override `_attach_response(...)`, the mixin stores `response.model_dump()` under the artifact key `{processor_name}_{model_name}_response`.
- If you do not override `_attach_usage(...)`, the mixin stores usage under `{processor_name}_{model_name}_usage`.

That default is often wrong for pipeline contracts because downstream hydrators and evals usually need a stable artifact key such as `ai_classification`.

Override `_attach_response(...)` when:
- downstream hydrators expect a stable artifact name,
- multiple models may run against the same pipeline contract,
- eval orchestration reads a specific payload from receipt metadata.

If the processor output drives evals, keep this chain stable:
1. AI processor writes a stable artifact on the process object.
2. Process-to-action hydrator copies that artifact into the action decision payload.
3. Finalize action hydrator writes the final payload into act-stage receipt metadata.

Use `$agent-eval-builder` for the eval-side contract.

## Error Handling

The mixins already normalize raised exceptions into `ValueError` with the processor name prefix. Do not wrap errors again unless you are adding materially better context.

Private helpers can assume validated inputs. Public processor behavior should fail clearly on missing required artifacts, empty data windows, or unsupported prompt inputs.

## Implementation Checklist

Before finishing an AI processor:
1. Confirm AI is justified over compute-only logic.
2. Define the output schema first.
3. Choose workflow or agent shape deliberately.
4. Build the user message with `mi.ai` helpers instead of custom serializers.
5. Override `_attach_response(...)` if downstream code needs a stable artifact key.
6. Keep the final AI determination flowing into receipt metadata if the pipeline exposes it as an output.
7. Verify prompts are explicit f-strings and easy to edit.

## When Exact API Details Matter

This skill is based on the installed package in the local environment. If you need exact behavior beyond the guidance above, inspect:
- `mi.ai.message`
- `mi.ai.mixins.base`
- `mi.ai.mixins.workflow`
- `mi.ai.mixins.agent`
- `mi.ai.tools`
