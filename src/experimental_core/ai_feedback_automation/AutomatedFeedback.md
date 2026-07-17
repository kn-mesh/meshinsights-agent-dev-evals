# Automated AI Feedback Instructions

This document covers automated feedback loops that analyze eval failures and suggest prompt/data/image improvements.

## Purpose

After eval runs, use automated feedback to inspect low-accuracy units and generate structured recommendations.

Why this exists:
- Manual failure analysis is slow.
- The feedback AI can review the original prompts, original inputs, and incorrect outputs in one pass.
- It gives repeatable suggestions for improving general accuracy.

Important:
- Do not overfit to one eval example.
- Optimize for generalizable instruction/data improvements, not hard-coded case behavior.

## Where The Shared Automation Lives

Feedback automation helpers are in:

```text
src/experimental_core/ai_feedback_automation/
├── eval_results_document.py
├── eval_feedback_orchestrator.py
└── AutomatedFeedback.md
```

Key classes:
- `EvalResultsDocument`: reads and filters eval JSON payloads.
- `EvalFeedbackOrchestrator`: selects low-accuracy units and runs the feedback pipeline.
- `EvalFeedbackOrchestratorConfig`: defines threshold and metadata keys.
- `EvalFeedbackReport` and `EvalFeedbackRunResult`: output report objects.

Use direct imports from module files:

```python
from src.experimental_core.ai_feedback_automation.eval_feedback_orchestrator import (
    EvalFeedbackOrchestrator,
    EvalFeedbackOrchestratorConfig,
)
from src.experimental_core.ai_feedback_automation.eval_results_document import EvalResultsDocument
from src.experimental_core.evals.ai_metadata import ErrorActionType, RuntimeType
```

## Eval Results Contract Required By Feedback

Input eval JSON must include:
- `summary.accuracy_by_unit_id`
- `run_config`
- `results`

`EvalFeedbackOrchestrator.select_units()` chooses units where:
- accuracy is numeric
- accuracy `< accuracy_threshold`

If `summary.accuracy_by_unit_id` is missing or empty, no units are selected.

## Metadata Contract Between Orchestrator And Feedback Pipeline

Two keys must be wired consistently.

1. Context metadata key (default `eval_context_json`)
- Written by orchestrator into `PipelineMetadata.model_extra`
- Read by feedback processor from `metadata.model_extra`
- Contains per-unit context:
  - `unit_id`
  - `accuracy`
  - `threshold`
  - `source_run_config`
  - `results` for that unit

2. Receipt feedback key (default `evaluation_feedback`)
- Written by finalize hydrator into `receipt.act_receipt.metadata`
- Read by orchestrator from act-stage receipt metadata
- Must contain a JSON-serializable dict feedback payload

## End-To-End Flow

1. Run eval orchestration and write eval JSON.
2. Load eval JSON via `EvalResultsDocument.from_json_file(...)`.
3. Build feedback orchestrator with an `accuracy_threshold` and metadata keys.
4. Orchestrator selects low-accuracy units and injects per-unit context metadata.
5. Feedback pipeline runs for each selected unit.
6. Feedback processor generates structured recommendations and stores them on the action decision.
7. Finalize hydrator copies that decision payload into act receipt metadata.
8. Orchestrator collects run results into `EvalFeedbackReport`.
9. Use-case wrapper writes the report JSON beside the source eval file.

## What You Build In A Use Case

You build five use-case pieces:

1. `USE_CASE_CONTEXT.md`
- Domain context for feedback analysis.
- Include classification criteria and common failure patterns.

2. Feedback AI processor (`src/processors/...`)
- Structured output schema (for example: prompt/data/image feedback fields).
- Reads eval context from metadata key.
- Reconstructs original processor inputs (system message, user message, image blocks).
- Attaches structured feedback to a process artifact.

3. Feedback pipeline YAML (`pipelines/<use_case>_evaluation_feedback_v1.ppln`)
- Same retrieval and preprocessing as original pipeline.
- Uses feedback AI processor.
- Uses finalize hydrator that writes feedback into receipt metadata.

4. Finalize hydrator update
- Copies feedback from action decision -> `receipt.act_receipt.metadata[receipt_feedback_key]`.

5. Use-case feedback orchestration (`src/evals/<use_case>_automated_eval_feedback_orchestration.py`)
- Loads eval results.
- Runs core feedback orchestrator.
- Writes report JSON.

## Wiring Artifacts Through Action Object To Receipt

The feedback payload must flow through three steps.

1. Feedback processor stores artifact:

```python
data_object.set_artifact("evaluation_feedback", response)
```

2. Action decision is populated (action class or process->action hydrator):

```python
feedback = process_object.get_artifact("evaluation_feedback")
if feedback is not None:
    payload = feedback.model_dump() if hasattr(feedback, "model_dump") else feedback
    action_object.set_decision("your_use_case.evaluation_feedback", payload)
```

3. Finalize hydrator writes to act receipt metadata:

```python
feedback = source.decision.get("your_use_case.evaluation_feedback")
if feedback is not None and receipt.act_receipt is not None:
    receipt.act_receipt.set_metadata("your_use_case.evaluation_feedback", feedback)
```

Set `receipt_feedback_key` in `EvalFeedbackOrchestratorConfig` to the exact key written in step 3.

## Feedback Processor Skeleton

```python
import json
from dataclasses import dataclass

from mi.ai import AIProcessorConfig, AIWorkflowMixin, ImageContent, TextContent, UserMessage
from mi.core.pipeline import PipelineMetadata
from mi.core.processors import BaseProcessor
from pydantic import BaseModel, ConfigDict, Field


class EvaluationFeedback(BaseModel):
    """Structured output for automated eval feedback."""

    model_config = ConfigDict(extra="forbid")

    prompt_feedback: str = Field(...)
    data_feedback: str = Field(...)
    image_feedback: str = Field(...)
    other_data_that_would_help: str = Field(...)


@dataclass(frozen=True, slots=True)
class PromptSnapshot:
    """Original processor prompts captured for analysis."""

    system_message: str
    user_message: UserMessage


class FeedbackProcessorConfig(AIProcessorConfig):
    """Feedback processor AI configuration."""


class FeedbackProcessor(
    AIWorkflowMixin[YourProcessObject, EvaluationFeedback],
    BaseProcessor[YourProcessObject],
):
    """Generate structured feedback for low-accuracy eval units."""

    output_schema = EvaluationFeedback

    _CONTEXT_ARTIFACT = "evaluation_feedback_context"
    _FEEDBACK_ARTIFACT = "evaluation_feedback"
    _CONTEXT_METADATA_KEY = "eval_context_json"

    def process(self, data_object: YourProcessObject, *, metadata: PipelineMetadata | None = None) -> None:
        """Attach eval context before AI workflow execution."""

        context = self._extract_eval_context(metadata)
        if context is not None:
            data_object.set_artifact(self._CONTEXT_ARTIFACT, context)
        super().process(data_object, metadata=metadata)

    def _extract_eval_context(self, metadata: PipelineMetadata | None) -> dict | None:
        """Read per-unit eval context from metadata."""

        if metadata is None or metadata.model_extra is None:
            return None
        raw = metadata.model_extra.get(self._CONTEXT_METADATA_KEY)
        if isinstance(raw, str):
            return json.loads(raw)
        return raw if isinstance(raw, dict) else None

    def _attach_response(self, data_object: YourProcessObject, response: EvaluationFeedback) -> None:
        """Store generated feedback on the process object."""

        data_object.set_artifact(self._FEEDBACK_ARTIFACT, response)
```

The processor should reconstruct the same original AI inputs the evaluated processor used.

## Use-Case Orchestration Wrapper Skeleton

```python
from pathlib import Path

from mi.core import PipelineBuilder

from src.experimental_core.ai_feedback_automation.eval_feedback_orchestrator import (
    EvalFeedbackOrchestrator,
    EvalFeedbackOrchestratorConfig,
)
from src.experimental_core.ai_feedback_automation.eval_results_document import EvalResultsDocument
from src.experimental_core.evals.ai_metadata import ErrorActionType, RuntimeType


def run_eval_feedback(
    *,
    eval_results_file: Path,
    yaml_path: Path,
    accuracy_threshold: float = 0.9,
    runtime: RuntimeType = "threaded",
    max_workers: int = 4,
    error_action: ErrorActionType = "stop",
    ai_provider: str | None = None,
    ai_model: str | None = None,
    ai_reasoning_effort: str | None = None,
) -> None:
    """Run automated feedback for units below threshold."""

    document = EvalResultsDocument.from_json_file(eval_results_file)
    builder = PipelineBuilder.from_yaml(yaml_path)
    orchestrator = EvalFeedbackOrchestrator(
        builder=builder,
        config=EvalFeedbackOrchestratorConfig(
            accuracy_threshold=accuracy_threshold,
            context_metadata_key="eval_context_json",
            receipt_feedback_key="your_use_case.evaluation_feedback",
        ),
    )
    report = orchestrator.run(
        document=document,
        runtime=runtime,
        max_workers=max_workers,
        error_action=error_action,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_reasoning_effort=ai_reasoning_effort,
        pipeline_yaml_path=str(yaml_path),
    )

    # Transform/write report JSON in your use-case format.
```

## Output Structure

`EvalFeedbackReport.to_json_dict()` contains:
- `source_eval_results`
- `accuracy_threshold`
- `selected_unit_ids`
- `eval_run_config`
- `eval_summary`
- `pipeline_run_config`
- `results` (list of `EvalFeedbackRunResult`)

Each run result includes:
- `unit_id`, `success`, `error`
- AI run config (`ai_provider`, `ai_model`, `ai_reasoning_effort`)
- `feedback` dict from receipt metadata
- `unit_context`

## CLI Usage Example

```bash
uv run python -m src.evals.<use_case>_automated_eval_feedback_orchestration \
  src/evals/eval_results_<pipeline>/azure_gpt-5-mini_low_all_3runs_20250101T120000Z.json \
  --accuracy-threshold 0.9 \
  --ai-model azure:gpt-5-mini \
  --ai-reasoning-effort low
```

## Runtime AI Configuration Notes

Follow the same provider/env conventions as normal pipeline runs.

Prefer runtime YAML overrides for AI settings in regular eval runs. In feedback runs, metadata extras are used intentionally for per-unit context injection.

## Practical Guardrails

- Reconstruct original prompts/images exactly before asking for feedback.
- Keep feedback schema stable for comparison over time.
- Use one generic feedback processor unless multiple feedback schemas are required.
- Keep feedback outputs in the same eval-results directory for discoverability.
