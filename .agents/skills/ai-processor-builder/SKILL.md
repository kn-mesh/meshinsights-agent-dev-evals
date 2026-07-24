---
name: ai-processor-builder
description: Build or update structured-output mi.ai workflow or agent processors in this repo. Use for multimodal inputs, tool-enabled agents, reusable toolsets, progressively disclosed capabilities or Agent Skills, typed processor configuration, and stable AI artifacts for downstream hydrators and evals. Do not add AI when deterministic logic is sufficient.
---

# AI Processor Builder

Build the smallest justified AI processor against the editable `mi.ai` source
under `mi-core/core/src/mi/`. Preserve coherent local contracts unless the user
asks to migrate them.

Use `$pipeline-builder` for a measurable pipeline variant,
`$external-runtime-setup` for auth or model runtime setup, and
`$agent-eval-builder` for eval contract changes.

## Boundaries

- Prefer deterministic logic when it solves the task reliably.
- Keep use-case prompts, schemas, and business rules under project-owned paths.
- Inspect `mi-core/core/src/mi/docs/ai.md` and current source when exact message,
  tool, capability, skill, retry, limit, or backend behavior matters.
- If the request explicitly authorizes the named reusable scope, proceed after
  stating its ownership and focused tests. Otherwise, identify the exact
  reusable paths/contracts and pause once for approval.

## Choose The Processor Shape

Use a workflow for one structured model call with fixed evidence. Inherit from
`AIWorkflowMixin[ProcessObject, OutputSchema]` and
`BaseProcessor[ProcessObject]`.

Use an agent only when multi-turn, targeted tool use materially improves the
decision. Inherit from `AIAgentMixin[ProcessObject, OutputSchema]` and
`BaseProcessor[ProcessObject]`; give it bounded tools and an appropriate
`max_turns`.

For agent composition, choose the smallest mechanism:

- standalone tool: one bounded operation;
- `ToolSet`: reusable related tools and shared instructions;
- `AICapability`: one cohesive, optionally deferred specialist workflow;
- `AISkill`: an Agent Skills-compatible runbook that benefits from progressive
  disclosure.

Keep universal rules eager. Defer only specialist behavior that most runs do
not need. Runtime authority comes from concrete tools attached by application
code, not skill metadata.

## Define Contracts First

1. Define a dedicated Pydantic output model; forbid extra fields when the
   contract is strict.
2. Use `AIProcessorConfig` or a small typed subclass. Keep prompts and business
   logic out of config.
3. Build messages with `UserMessage` helpers for text, dataframes, and images.
   Use deterministic, readable image rendering and fail on empty evidence.
4. Use plain strings for static prompts and f-strings only when interpolating
   values. Put unit-specific facts in the user message.
5. Write a stable serializable artifact when downstream hydrators or evals need
   a model-independent key.

The registry discovers the processor config from its concrete annotation. Use
this pattern:

```python
from mi.ai import AIProcessorConfig, AIWorkflowMixin, UserMessage
from mi.core.processors import BaseProcessor
from pydantic import BaseModel, ConfigDict


class ClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: str
    explanation: str


class ClassificationProcessorConfig(AIProcessorConfig):
    """Typed configuration for this workflow."""


class ClassificationProcessor(
    AIWorkflowMixin[YourProcessObject, ClassificationResult],
    BaseProcessor[YourProcessObject],
):
    output_schema = ClassificationResult
    config: ClassificationProcessorConfig

    def __init__(
        self,
        config: ClassificationProcessorConfig | None = None,
    ) -> None:
        resolved_config = config or ClassificationProcessorConfig()
        super().__init__(resolved_config)
        self.config = resolved_config

    def _build_system_prompt(self, data_object: YourProcessObject) -> str:
        return "Classify the unit from the supplied evidence."

    def _build_user_message(self, data_object: YourProcessObject) -> UserMessage:
        return (
            UserMessage()
            .add_text(f"Unit ID: {data_object.unit_id}")
            .add_dataframe(data_object.get_window_dataframe(), string_format="csv")
        )

    def _attach_response(
        self,
        data_object: YourProcessObject,
        response: ClassificationResult,
    ) -> None:
        data_object.set_artifact("ai_classification", response.model_dump())
```

## Tool And Evidence Rules

- Keep tools deterministic, narrowly named, documented, and bounded.
- Do deterministic computation outside the model loop.
- Do not expose filesystem, network, or other authority the task does not need.
- Use synchronous tools unless current `mi.ai` source explicitly supports the
  required async path.
- Do not send blank fallback images or ad hoc table serialization.
- Leave enough turn and tool-call budget for deferred discovery, execution, and
  final structured output.

Read `mi-core/core/src/mi/docs/ai.md` only when implementing these advanced
surfaces; it owns current constructors, supported return shapes, loaders, and
provider behavior.

## Stable Pipeline Handoff

The default response artifact includes processor and model names. Override
`_attach_response(...)` when downstream code needs a stable key or multiple
models share one pipeline contract.

Keep this chain explicit:

1. Processor stores `response.model_dump()` under a stable process artifact.
2. Process-to-action hydration copies it into the action decision.
3. Finalization writes the decision payload into receipt metadata.
4. Eval extraction reads that declared receipt contract.

Do not wrap normalized mixin errors unless adding actionable context. Fail
clearly on missing artifacts, empty evidence, or unsupported inputs.

## Acceptance Checks

Select affected layers from the
[repository verification matrix](../project-guide/references/verification-matrix.md).

- AI is justified and the workflow-versus-agent choice is explicit.
- Output and typed config contracts are registry-discoverable.
- Prompts are concise; tools and deferred behavior are minimal.
- The stable artifact reaches the declared receipt/eval path.
- Focused tests pass.
- One exact, explicitly versioned published benchmark example runs through the
  pipeline runner. Do not create a one-example eval occurrence for this
  development check.
