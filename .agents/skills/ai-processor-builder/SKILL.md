---
name: ai-processor-builder
description: Build or update AI workflow and agent processors in this repo using mi.ai. Use this skill when a request involves structured-output AI processors, multimodal inputs, tool-enabled agents, reusable toolsets, progressively disclosed capabilities or Agent Skills, or stable AI artifacts for downstream hydrators and evals.
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

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Its current checkout path is `/Users/kurt.neuens/Desktop/Code - Product/meshinsights-agent-dev-evals-mvp/mi-core`; use the repo-relative `mi-core/` path in code and documentation.
- `mi.ai` and `mi.core` live under `mi-core/core/src/mi/`; CLI source lives under `mi-core/cli/src/cli/`.
- The root `uv` environment installs both as editable local sources. Inspect or modify that source when the task requires framework changes, then run the relevant `mi-core` tests.

## When To Use It

Use this skill when the user asks you to:
- build a new AI workflow processor,
- build a tool-enabled AI agent processor,
- compose an agent from reusable toolsets or capabilities,
- load an Agent Skills-compatible `SKILL.md` for progressive disclosure,
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
- at least one of `_build_tools(...)`, `_build_toolsets(...)`,
  `_build_capabilities(...)`, or `_build_skills(...)` when tool-driven behavior
  is needed

Agent processors also require `max_turns` in `AIProcessorConfig`.

Agent extension methods default to empty collections, so capability-only and
skill-only agents do not need a dummy `_build_tools(...)` implementation.

## Config Surface

Use `AIProcessorConfig` or a small subclass of it for processor config.

Important fields from the repository-local `mi.ai` source:
- `model`: required provider/model identifier such as `azure:gpt-5.4`
- `backend`: defaults to `"auto"`
- `reasoning_effort`: defaults to `medium`
- `max_turns`: defaults to `10`
- `attach_usage`: defaults to `True`
- `attach_response`: defaults to `True`
- `timeout`
- `transport_retries`: defaults to `3` HTTP attempts including the initial request
- `tool_retries`: defaults to `3`
- `output_retries`: defaults to the tool retry budget
- `tool_timeout`
- `input_tokens_limit`: defaults to no limit
- `output_tokens_limit`: defaults to no limit
- `total_tokens_limit`: defaults to no limit
- `tool_calls_limit`: defaults to no limit
- `count_tokens_before_request`: defaults to `False`
- `provider_options`
- `backend_options`

The legacy `retries` field is a compatibility override for both transport and
tool retries. Prefer the split fields in new processors.

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

Supported DataFrame string formats from the repository-local `mi.ai` source:
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

## Toolsets, Capabilities, And Skills

Choose the smallest composition primitive that represents the behavior:

- Use a standalone `Tool` for one independent operation.
- Use `ToolSet` when related tools share instructions or should be reused as a
  collection.
- Use `AICapability` when instructions, tools, and one or more toolsets form a
  cohesive workflow.
- Use `AISkill` when a specialist runbook should use Agent Skills-compatible
  Markdown and progressive disclosure.

### Reusable toolsets

Return instruction-bearing toolsets from `_build_toolsets(...)`. A `ToolSet`
returned from `_build_tools(...)` is flattened for backward compatibility, so
its instructions and deferred-loading behavior are not preserved there.

```python
from mi.ai import ToolSet


def _build_toolsets(self, data_object):
    return [
        (
            ToolSet.builder()
            .add(fetch_recent_events)
            .add(fetch_historical_events)
            .with_id("event-analysis")
            .with_instructions("Use these tools together to compare event windows.")
            .build()
        )
    ]
```

Use `.deferred()` only for large tool catalogs that benefit from per-tool
discovery. A deferred toolset requires a stable ID.

### Capabilities

Capabilities are eager by default. Use `defer_loading=True` when an agent has
several specialist workflows and most runs need only one. The model initially
sees the capability ID and description, then pydantic-ai activates the bundled
instructions and tools after `load_capability`.

```python
from mi.ai import AICapability


def _build_capabilities(self, data_object):
    return [
        AICapability(
            id="historical-review",
            description="Use when the current pattern may have occurred before.",
            instructions="Compare timing, magnitude, duration, and recovery.",
            tools=[fetch_historical_events],
            defer_loading=True,
        )
    ]
```

Deferred capability IDs must be stable and unique within the agent. Capability
tools support `ToolContext` exactly like standalone tools. Loading and invoking
them consumes the existing model-request and tool-call budgets, so leave enough
`max_turns` for discovery, tool execution, and structured output.

Keep always-used domain rules and the output contract in the base system prompt.
Moving universally required instructions into a deferred capability adds cost
and makes the agent less reliable.

### Agent Skills

Use `AISkill.from_path(...)` for Agent Skills-compatible directories containing
`SKILL.md`. Skills are deferred by default.

```python
from pathlib import Path

from mi.ai import AISkill, ai_tool


def _build_skills(self, data_object):
    @ai_tool(name="compare_with_history")
    def compare_with_history(start: str, end: str) -> str:
        return data_object.compare_window_with_history(start, end)

    return [
        AISkill.from_path(
            Path("skills/historical-review"),
            tools=[compare_with_history],
        )
    ]
```

The skill directory name must match its lowercase, hyphenated `name` field.
`description` must clearly state what the skill does and when to use it. The
loader reads only `SKILL.md`; it does not grant filesystem access, load reference
files, or execute scripts. Expose any safe resource access explicitly through
bounded tools.

Use `load_skills("skills")` for a static catalog of child skill directories.
Construct skills inside `_build_skills(...)` when their attached tools close over
the current data object.

### When capabilities are not useful

Do not convert a one-shot workflow to an agent merely to use skills. Keep a
workflow when every run needs the same instructions and evidence and no
tool-driven investigation is useful. Capabilities and skills are most valuable
for adaptive agents with distinct, selectively used specialist paths.

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
5. Choose standalone tools, toolsets, capabilities, or skills deliberately.
6. Keep common rules eager and defer only selectively used specialist behavior.
7. Override `_attach_response(...)` if downstream code needs a stable artifact key.
8. Keep the final AI determination flowing into receipt metadata if the pipeline exposes it as an output.
9. Verify prompts are explicit f-strings and easy to edit.

## When Exact API Details Matter

This skill is based on the editable source in `mi-core/core/src/mi/`. If you need exact behavior beyond the guidance above, inspect:
- `mi.ai.message`
- `mi.ai.mixins.base`
- `mi.ai.mixins.workflow`
- `mi.ai.mixins.agent`
- `mi.ai.tools`
