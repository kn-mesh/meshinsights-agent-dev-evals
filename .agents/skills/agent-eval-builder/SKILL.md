---
name: agent-eval-builder
description: Build or update rubric-based evaluation orchestration for AI-enabled pipelines in this repo. Use this skill when a request involves creating eval orchestration modules, rubric JSON contracts, repeated-run result outputs, or evaluation-results Streamlit apps for AI pipeline outputs.
---

# Agent Eval Builder

Use this skill for evaluation work tied to AI pipeline outputs in this repo. Treat this skill as the primary implementation guide for rubric-based eval orchestration. The goal is to build stable, repeated-run evals that compare expected rubric outcomes against the final AI output written to receipt metadata.

## Scope Of This Skill

This skill defines recommended eval-building patterns for an AI coding agent working on AI-enabled `mi-core` style pipelines.

Treat it as default guidance for how agents should build or evolve eval orchestration, not as a guarantee that every existing repo already uses the exact contracts or flow described here.

Rules:
- Prefer these patterns by default when creating or standardizing eval workflows.
- If the existing repo already emits a different but coherent eval contract, treat the current repo code and outputs as the source of truth unless the user asks to migrate them.
- Keep concrete path references and shared-helper references accurate.
- When this skill describes an output contract, interpret it as the intended stable contract for agent-built work unless the existing repo has a deliberate local variation.

Read these docs only when you need their exact details:
- [pipeline-builder](../pipeline-builder/SKILL.md) for the broader pipeline build flow.
- [external-runtime-setup](../external-runtime-setup/SKILL.md) for provider, auth, and tracing setup.
- [src/experimental_core/ai_feedback_automation/AutomatedFeedback.md](../../../src/experimental_core/ai_feedback_automation/AutomatedFeedback.md) only when the user asks about automated feedback follow-up.

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Its current checkout path is `/Users/kurt.neuens/Desktop/Code - Product/meshinsights-agent-dev-evals-mvp/mi-core`; use the repo-relative `mi-core/` path in code and documentation.
- Framework source lives under `mi-core/core/src/mi/`, and CLI source lives under `mi-core/cli/src/cli/`.
- The root `uv` environment installs both as editable local sources. Inspect or modify that source when the task requires framework changes, then run the relevant `mi-core` tests.

## When To Use It

Use this skill when the user asks you to:
- build a new eval orchestration module for an AI-enabled pipeline,
- add or revise rubric-based comparisons for AI outputs,
- standardize eval JSON output contracts,
- add a results-comparison Streamlit app for eval JSON files.

Do not use this skill for compute-only pipelines that do not need repeated model evaluation.

## Repo Guardrails

- Reuse `src/experimental_core/evals` helpers instead of hand-rolling core eval primitives.
- Do not modify `src/experimental_core/` unless the user explicitly asks.
- Keep downstream contracts stable: `summary`, `run_config`, `selected_unit_ids`, and `results`.
- Treat eval output as a receipt-driven comparison layer, not a second source of truth for pipeline logic.

## Preconditions

Before building evals, confirm:
1. The YAML pipeline runs successfully for at least one unit.
2. The AI output needed for comparison is present in act-stage receipt metadata.
3. External dependencies are configured if the pipeline depends on hosted models or tracing.

If any precondition is missing, fix that first or tell the user what contract is still absent.

## Core Helpers

Prefer these shared primitives:

```python
from src.experimental_core.evals import (
    EvalArgParserBuilder,
    EvalAttempt,
    EvalResultsEnvelope,
    EvalSummaryBuilder,
    EvalWizardSelections,
    EvalWizardStepConfig,
    InteractiveEvalWizard,
    JsonRubric,
    LoadedRubric,
    OrchestratedRunsReceipt,
    RepeatedEvalExecutor,
    RepeatedEvalExecutorConfig,
    RepeatedEvalWorkItem,
    ReceiptFieldSpec,
    Rubric,
    RubricEntry,
    RubricSource,
    RuntimeProfileSpec,
    RunOutcome,
    UnitEvalResult,
    build_eval_results_path,
    build_eval_run_config,
    build_results_dir_for_pipeline,
    build_results_filename,
    extract_receipt_fields,
    extract_stage_metadata_fields,
    evaluate_outcome,
    evaluate_outcomes,
    filter_rubric_entries,
    list_rubric_files,
    load_rubric,
    load_rubric_entries,
    load_rubric_payload,
    normalize_ai_reasoning_effort,
    resolve_rubric_display_name,
    resolve_execution_profile,
    write_eval_results,
    write_eval_results_json,
)
```

Use them for:
- shared eval CLI parser and interactive wizard scaffolding,
- rubric loading and validation,
- shared rubric source resolution, display naming, and generic unit selection,
- shared eval attempt and aggregated unit-result modeling,
- schema-driven receipt field extraction from `PipelineReceipt` or raw stage metadata,
- run outcome modeling,
- repeated-run execution across supported runtimes,
- correctness comparison,
- summary metric construction,
- stable eval output envelope, run config, and results-path generation.

Helper selection guidance:
- prefer `load_rubric(...)`, `load_rubric_entries(...)`, and `filter_rubric_entries(...)` for orchestration modules that need source loading plus generic selection,
- use `JsonRubric` when a consumer specifically benefits from the `Rubric` object interface such as `get_entry(...)` or `list_unit_ids(...)`,
- treat `list_rubric_files(...)` as path discovery only; validate each candidate with `load_rubric_payload(...)` or `load_rubric(...)` before presenting it to users or running an eval against it.

## Verified Runtime Contract

In the repository-local `mi-core` source, whose project metadata currently declares version `0.5.2`, `PipelineOrchestrator` supports:

- `serial`
- `threaded`
- `process`

And it also supports:

- `error_action` of `stop` or `continue`
- `max_workers` for threaded and process execution

When building shared eval execution helpers, keep those runtime names aligned with `mi-core`.

Do not invent alternate runtime labels or a parallelism vocabulary that diverges from the orchestrator contract unless the user explicitly asks to introduce a repo-local abstraction.

Important:

- `mi-core`'s orchestrator does not provide eval-specific heartbeat logging.
- `mi-core`'s orchestrator does not provide hard per-unit wall-clock timeouts.
- `mi-core`'s orchestrator does not provide stale-worker eviction for hung eval runs.

Those behaviors may still belong in shared eval helpers, but they should be layered on top of the `mi-core` runtime contract rather than replacing it.

## What To Build

The default deliverable is one use-case module:
- `src/evals/<use_case>_eval_orchestration.py`

That module should usually contain:
1. An orchestration layer plus CLI entrypoint that resolves the YAML and rubric, selects units, runs repeated evaluations, and writes one JSON file per invocation.
2. Local parsing and summary logic that converts pipeline receipts into shared `EvalAttempt` and `UnitEvalResult` instances.
3. Any truly use-case-specific helpers needed for receipt extraction, derived metrics, or output shaping.

Even after the current shared extractions, each pipeline-specific eval module still usually owns:
- translation from repo-local scope labels into concrete `unit_ids`, expected-outcome filters, or metadata filters,
- any rubric-entry-to-runtime-input mapping such as `sensor_id`, `detected_at`, or other metadata-derived pipeline inputs,
- any derived correctness rules that go beyond direct expected-vs-actual comparison,
- any provider-specific runtime policy or timeout heuristics,
- any repo-specific CLI flags such as local snapshots, retriever options, or specialized preprocessing steps.

Design the public API first. Keep helper methods private and intent-revealing.

Prefer reusing `RepeatedEvalExecutor` for repeated runs rather than hand-rolling nested serial / threaded / process loops inside each eval module.

Prefer reusing the shared `EvalAttempt` and `UnitEvalResult` models rather than redefining local private dataclasses for repeated-run eval state.

When a repo needs to carry raw model payloads or other non-scalar per-attempt data, put them in `EvalAttempt.artifacts` under stable generic keys instead of introducing use-case-specific fields on the shared model.

Prefer defining shared `ReceiptFieldSpec` tuples for stage-metadata extraction rather than hand-writing repeated `metadata.get(...)` and nested `value` parsing logic in each eval module.

Use `extract_receipt_fields(...)` when you have a full `PipelineReceipt`, and `extract_stage_metadata_fields(...)` when you only have raw stage metadata such as a subprocess CLI payload.

Keep the shared receipt extraction layer generic:
- define which metadata keys and nested value paths to read,
- optionally capture raw metadata sections into `EvalAttempt.artifacts`,
- keep domain-specific normalization like label aliases or derived correctness local to the eval module.

Prefer reusing `EvalArgParserBuilder` and `InteractiveEvalWizard` for standard eval CLI scaffolding rather than re-implementing prompt helpers and argparse boilerplate inside each eval module.

Keep repo-specific scope translation local. If the interactive wizard offers labels like `failure: open failure`, the shared wizard should return the selected scope, and the local eval module should translate that scope into its own `classifications`, `unit_ids`, or other filter arguments.

When configuring the shared interactive wizard:
- use collision-safe display labels for selectable paths; do not assume `path.name` is unique across pipeline or rubric directories,
- treat `EvalWizardSelections.ai_reasoning_effort` as already normalized output; the shared wizard should return `None` for the `default` sentinel rather than leaking the raw label into orchestration code.

## Required Receipt Handoff Contract

Eval parsing depends on the AI output moving through the pipeline in a stable way:

1. The AI processor writes an artifact on the process object, commonly `ai_classification`.
2. The process-to-action hydrator copies that artifact into the action decision payload.
3. The finalize action hydrator writes that payload into act-stage receipt metadata.
4. The eval parser reads the act-stage metadata from the final receipt.

Minimal pattern:

```python
# process stage
process_object.set_artifact("ai_classification", response_payload)

# process -> action hydrator
action_object.set_decision(
    "ai_classification",
    process_object.get_artifact("ai_classification"),
)

# finalize action hydrator
payload = source.decision.get("ai_classification")
if payload is not None:
    act_receipt = receipt.get_stage_receipt("act")
    if act_receipt is not None:
        act_receipt.set_metadata("ai_classification", payload)
```

Parser target:

```python
act_receipt = receipt.get_stage_receipt("act")
payload = act_receipt.get_metadata("ai_classification") if act_receipt else None
```

If expected or actual values are missing, treat that run as unevaluated rather than forcing a false incorrect result.

## Rubric Contract

Rubric JSON must follow the standardized schema enforced by `JsonRubric`:

```json
{
  "units": [
    {
      "unit_id": "UNIT_001",
      "expected_outcomes": {
        "classification": "Failed - Blow Through",
        "confidence": "High"
      },
      "metadata": {
        "location_name": "Building A, Trap 14"
      }
    }
  ]
}
```

Rules:
- `units` is the required top-level array.
- `unit_id` is required, non-empty, and unique.
- `expected_outcomes` is required and must be a non-empty `dict[str, str]`.
- `metadata` is optional and defaults to `{}`.

Useful helpers:
- `entry.get_outcome("classification")`
- `entry.outcome_names`

Prefer reusing the shared rubric-source layer when the orchestration module needs to:
- load a rubric from a file path or inline payload,
- carry a stable display / directory name for the selected rubric,
- filter entries by `unit_id`,
- filter entries by generic expected outcome fields or metadata.

Recommended shared helpers:
- `RubricSource`
- `LoadedRubric`
- `load_rubric_payload(...)`
- `load_rubric_entries(...)`
- `load_rubric(...)`
- `resolve_rubric_display_name(...)`
- `filter_rubric_entries(...)`
- `list_rubric_files(...)`

Keep repo-specific runtime parsing local. If a repo needs to translate one rubric entry into use-case-specific runtime values such as `sensor_id`, `detected_at`, or other metadata-derived inputs, that logic should remain outside `experimental_core`.

Keep generic filtering expectations narrow:
- `filter_rubric_entries(...)` performs exact-value filtering after basic string trimming,
- it does not implement aliases, fuzzy matching, or compound scope semantics,
- if the repo uses domain labels like `failure: open failure`, translate them locally before calling the shared filter helper.

## Evaluation Workflow

Implement this sequence unless the task clearly calls for a smaller change:

1. Parse CLI args and validate the combinations.
   Prefer composing the parser from `EvalArgParserBuilder` and layering only repo-specific flags on top.
2. Resolve the source YAML path.
3. Apply temporary runtime AI overrides only when the CLI supports them and the user asked for them.
4. Load the rubric and resolve unit selection for `all`, `single`, or an explicit list.
   Prefer reusing `load_rubric(...)` plus `filter_rubric_entries(...)` for generic source loading and selection, while keeping repo-local scope language translation outside core.
5. Choose the execution primitive:
   - use `PipelineOrchestrator` when one orchestrated batch run is the right abstraction,
   - use `RepeatedEvalExecutor` when you need repeated per-unit eval attempts with shared runtime/error/timeout handling.
6. Build the unit runner or orchestrator-backed adapter for one eval attempt.
7. Execute repeated runs through the shared executor using `serial`, `threaded`, or `process` runtime names that match `mi-core`.
8. Convert each unit receipt into one eval row.
   Prefer doing this through shared `ReceiptFieldSpec` definitions plus `extract_receipt_fields(...)` rather than custom metadata walkers.
9. Compute correctness with `evaluate_outcome(...)` for one expected field or `evaluate_outcomes(...)` for multiple expected fields.
10. Build the summary with `EvalSummaryBuilder`.
11. Write the JSON output file and clean up any temporary runtime YAML.

For repeated single-unit subprocess runs, prefer a top-level or otherwise picklable run function so process runtime remains usable.

If you add eval-specific protections such as heartbeat logging, hard subprocess timeouts, or stale-run eviction, keep them inside shared eval execution helpers instead of duplicating them in each orchestration module.

If the module supports an interactive terminal flow, prefer one local `_run_interactive_wizard()` wrapper that builds `EvalWizardStepConfig`, runs `InteractiveEvalWizard`, and then translates `EvalWizardSelections` into the local `run_eval(...)` arguments.

If the interactive flow offers scope labels such as `failure: open failure`, keep that translation local:
- the shared wizard can return the selected scope label,
- the local eval module can translate that label into `filter_rubric_entries(...)` calls or repo-local compound selection logic,
- `experimental_core` should not encode one repo's semantic scope vocabulary.

## Single And Multi-Outcome Comparisons

Use `evaluate_outcome(expected, actual)` when there is only one expected field to compare.

Use `evaluate_outcomes(entry, actual_values)` when the rubric defines multiple expected outcomes:

```python
entry = rubric.get_entry(unit_id)
actual_values = {"classification": parsed_class, "confidence": parsed_conf}
results = evaluate_outcomes(entry, actual_values)
```

`evaluate_outcomes` also treats unexpected actual keys as explicit incorrect outputs. Keep that behavior because it catches output drift early.

## Output Contract

Keep the top-level JSON payload stable:
1. `summary`
2. `run_config`
3. `selected_unit_ids`
4. `results`

Prefer building that payload through shared helpers:
- `EvalResultsEnvelope`
- `build_eval_run_config(...)`
- `build_eval_results_path(...)`
- `write_eval_results(...)`

`write_eval_results_json(...)` remains acceptable as a compatibility wrapper, but new shared work should treat `selected_unit_ids` as the canonical top-level field name and avoid emitting `selected_location_ids`.

Recommended `run_config` fields:
- `yaml_path`
- `rubric_file`
- `units`
- `unit_id`
- `runs` or `runs_per_unit`
- `runtime`
- `max_workers`
- `error_action`
- `ai_provider`
- `ai_model`
- `ai_reasoning_effort`
- `completed_at_utc`

Use one stable naming choice per repo/output contract. In this repo today, `runs_per_unit` is already used in emitted eval results, so preserve that unless the user explicitly asks to migrate the contract.

Recommended per-result fields:
- `unit_id`
- `run_index`
- `success`
- `correct`
- `expected_classification`
- `ai_classification`
- `ai_confidence`
- `ai_explanation`
- `category`
- `scenario`
- `run_started_at`
- `error`

Recommended summary fields:
- `total_runs`
- `successful_runs`
- `evaluated_runs`
- `correct_runs`
- `accuracy_total`
- `accuracy_by_category`
- `accuracy_by_confidence`
- `accuracy_by_unit_id`

`accuracy_total` should be `correct_runs / evaluated_runs`, or `None` when no runs were evaluable.

## Results Layout

Use the shared naming helpers for consistency.

Recommended structure:

```text
src/evals/
├── eval_results_{pipeline_yaml_stem}/
│   └── {optional_repo_subdirs}/
│       └── {provider}_{model}_{reasoning}_{units}_{runs}runsPerUnit_{timestamp}.json
```

Do not invent a new directory or filename scheme unless the user explicitly asks.

If the existing repo already has a coherent local filename or directory convention, preserve it until the user asks to standardize or migrate it.

## CLI Pattern

Typical commands:

```bash
uv run python -m src.evals.<use_case>_eval_orchestration \
  pipeline_configs/v1.ppln \
  --units all \
  --runs 3 \
  --runtime threaded --max-workers 4 \
  --ai-model <provider:model> \
  --ai-reasoning-effort <low|medium|high>
```

```bash
uv run python -m src.evals.<use_case>_eval_orchestration \
  pipeline_configs/v1.ppln \
  --units single --unit-id <UNIT_ID> \
  --runs 5
```

Use one trailing `\` per continued shell line.

When an interactive flow is also supported, keep it aligned with the non-interactive CLI:
- shared wizard selections should map cleanly onto the same arguments accepted by `run_eval(...)`,
- named execution profiles should resolve through shared `RuntimeProfileSpec` and `resolve_execution_profile(...)`,
- repo-specific flags that do not belong in core, such as local snapshot or retriever options, should still be added in the local module after the shared parser builder is composed.

## Optional Streamlit App

If the user asks for a results UI, build a simple comparison app after eval JSON files exist.

Recommended behavior:
1. Discover `eval_results_*` folders under `src/evals`.
2. Parse JSON defensively and skip malformed files.
3. Build a ranking table across runs using summary metrics and model/config fields.
4. Provide run-detail drill-down to per-unit rows, explanations, and errors.
5. Exclude non-eval artifacts such as feedback sidecar files.

When building the app, also use the repo's `streamlit-app-builder` skill.

## Common Failure Modes

- Runs succeed but `evaluated_runs` is low or zero:
  act-stage `ai_classification` metadata is missing or malformed.
- Rows are unevaluated with `correct=None`:
  expected rubric values or parsed actual values are missing.
- Unit selection fails:
  requested unit ids are not present in the rubric.
- Generic rubric filtering behaves unexpectedly:
  repo-local scope labels were passed into core directly instead of being translated into concrete `unit_ids`, expected-outcome filters, or metadata filters first.
- Results files are inconsistent:
  custom output naming bypassed the shared helper utilities.
- Eval orchestration fails before the run starts:
  provider, auth, or tracing setup is incomplete.
- Process runtime fails unexpectedly:
  the repeated-run callable or one of its bound inputs is not picklable.
- Parallel evals appear hung:
  the underlying pipeline run lacks a hard timeout, so executor-level stale detection can mark a run failed but cannot instantly kill already-running work on its own.

## Expected Output Style

When using this skill:
- implement the eval module instead of only restating the plan unless the user asked for design only,
- preserve stable receipt and JSON contracts,
- check the repository-local `mi-core` source and behavior before introducing new shared runtime assumptions,
- mention any missing upstream handoff contract before adding workaround code,
- call out any obvious follow-up improvements separately instead of expanding the scope silently.
