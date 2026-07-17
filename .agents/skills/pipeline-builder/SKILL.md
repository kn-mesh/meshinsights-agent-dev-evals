---
name: pipeline-builder
description: Build or evolve stage-based use-case pipelines in this repo. Use this skill when a request involves creating or modifying retrievers, hydrators, process or action objects, pipeline YAML, pipeline runner CLIs, pipeline receipts, processor variant organization, or the staged progression from visualization to compute-only control pipelines to optional AI and eval support.
---

# Pipeline Builder

Use this skill as the primary implementation guide for pipeline work in this repo. It defines the repo-specific build order, output contracts, and packaging rules that keep pipelines understandable and evaluation-ready.

## Scope Of This Skill

This skill defines recommended implementation patterns for an AI coding agent building or evolving pipelines in an `mi-core` style repo.

Treat it as agent guidance, not as a strict claim that every existing repo already matches every pattern here.

Rules:
- Prefer these patterns by default when building new pipeline functionality.
- If the existing repo already uses a different but coherent approach, treat the repo code as the source of truth for current local behavior unless the user asks to migrate toward the skill pattern.
- Keep concrete repo references such as file paths, startup docs, and named entrypoints accurate.
- When this skill describes a build order or recommended architecture, interpret that as the default agent path rather than a universal requirement that every repo already follows it.

Use these narrower skills when the task enters a specialized area:
- `$streamlit-app-builder` for Streamlit apps and UI patterns.
- `$ai-processor-builder` for workflow or agent processor implementation details.
- `$agent-eval-builder` for eval orchestration and eval JSON contracts.

Use `$external-runtime-setup` when the task also depends on provider auth, tracing, or runtime AI overrides.

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Its current checkout path is `/Users/kurt.neuens/Desktop/Code - Product/meshinsights-agent-dev-evals-mvp/mi-core`; use the repo-relative `mi-core/` path in code and documentation.
- Framework source lives under `mi-core/core/src/mi/`, and CLI source lives under `mi-core/cli/src/cli/`.
- The root `uv` environment installs both as editable local sources. Modify that source when the requested work belongs in the framework, then run the relevant `mi-core` tests.

## Read This First

Before writing pipeline code:
1. Read docs in [docs/use_case/...].
2. Treat these files as durable context, not an implementation log.
3. Reuse `mi.core`, `mi.ai`, and existing repo helpers before writing custom plumbing.
4. Make framework-level changes directly under `mi-core/` when the requested behavior belongs there; do not add a use-case workaround merely because core was formerly an external dependency.
5. Do not modify `src/experimental_core/` unless the user explicitly asks.

## Core Design Rules

### Receipt-first outputs

Design the pipeline so the final business outcome for a unit is captured on the returned `PipelineReceipt`, usually in act-stage metadata.

Rules:
- Keep receipt payloads compact, serializable, and stable.
- Keep intermediate computation on the process object as artifacts, not in the receipt.
- Use visualization sinks and debug outputs only as side effects, not as the durable record.

### Variant-first organization

Prefer organizing processors by pipeline variant before processor type.

Recommended layout:
- `src/processors/common/` for processors reused across distinct variants.
- `src/processors/<variant>/` for processors tied to one evolving pipeline shape.

Keep one shared process object, action object, and shared hydrators if that keeps experimentation simpler. Some temporary overlap is acceptable while variants evolve.

## Development Sequence

Build in this order unless the user explicitly asks to skip ahead:
1. Data visualization pipeline with no AI.
2. YAML control pipeline.
3. Stop at compute-only if that solves the use case reliably enough.
4. Add an AI baseline only if compute-only logic is insufficient or too brittle.
5. Add eval orchestration when you need repeated-run comparison.
6. Iterate using measured deltas, not intuition.

### Stage exit criteria

- Visualization stage:
  You can run one benchmark example and all examples in a published benchmark version, render raw and derived data, and inspect the first baseline artifact.
- Control pipeline stage:
  YAML runs for single and all units and the final pipeline determination appears on receipts.
- AI stage:
  The AI path runs successfully and its output reaches receipt metadata.
- Eval stage:
  Eval JSON is written with summary and per-run rows for the selected units.

## Stage 1: Data Visualization Pipeline

Build this first to validate data quality and feature usefulness before committing to pipeline logic.

There are two valid implementation options for the visualization stage. Choose based on how much reusable pipeline plumbing the visualization work actually needs.

### Option 1: Query data directly in the Streamlit app

Use this when retrieval and normalization are relatively simple and the main goal is fast inspection rather than building a reusable visualization-stage pipeline.

This is the faster path when:

- the app can query the source system directly with limited shared plumbing,
- normalization is lightweight and can live close to the app,
- you do not need process-stage artifacts to flow through `mi.core`,
- the visualization work is mainly exploratory rather than a durable pipeline stage.

#### What to build

1. Published benchmark and raw-source access appropriate to the use case.
2. A Streamlit app in `src/streamlit_apps/` that:
   reads benchmark example-selection context,
   queries the backing data source directly,
   performs only the normalization needed for display and debugging,
   renders the raw data, derived views, and unit context needed for developer inspection.
3. Shared helper functions or lightweight service code only when it keeps the app readable.

Use `$streamlit-app-builder` when building the app.

#### Rules

- Keep direct-query logic scoped to the visualization/debugging use case.
- Do not pretend this is already a reusable pipeline stage if it is not.
- Keep the app honest about what is app-only logic versus reusable pipeline logic.

#### Done checklist

- One selected unit can be queried and visualized directly from the app.
- The app renders the raw source data, any lightweight derived views, and key unit metadata.
- The implementation remains small enough that introducing a dedicated visualization pipeline would add more plumbing than value.


### Option 2: Build a real visualization pipeline

Use this when the visualization stage is doing meaningful retrieval, normalization, artifact production, or processor experimentation that you expect to reuse in later pipeline stages.

#### What to build

1. Published benchmark and immutable raw-source access.
2. A retriever in `src/retrievers/` that:
   resolves `PipelineMetadata.unit`,
   loads and normalizes raw rows,
   attaches benchmark example and source-snapshot context needed downstream.
3. A retrieve-to-process hydrator in `src/hydrators/` that validates retriever outputs and populates datasets and artifacts on the process object.
4. A process object subclass in `src/objects/` with typed getters and setters for normalized datasets and important artifacts.
5. One baseline compute processor in the relevant processor package.
6. An action object, process-to-action hydrator, visualization hydrator, finalize hydrator, and visualization action.
7. A visualization pipeline module in `src/pipelines/`.
8. A Streamlit app in `src/streamlit_apps/`.

Use `$streamlit-app-builder` when building the app.

#### Why the visualization sink exists

`mi.core` clears intermediate objects as stages complete. If you need post-run inspection of process-stage artifacts, emit them through an action side effect rather than trying to read the process object after `pipeline.run()`.

#### Critical deepcopy rule

If the visualization action stores a caller-provided sink dict, preserve that sink by reference in `__deepcopy__`. Otherwise `PipelineBuilder.build()` will deepcopy the action and the caller will read an empty sink.

Required pattern:

```python
import copy


def __deepcopy__(self, memo: dict[int, object]) -> "MyVisualizationAction":
    """Preserve the sink reference across pipeline deepcopy."""

    cls = self.__class__
    result = cls.__new__(cls)
    memo[id(self)] = result
    for key, value in self.__dict__.items():
        object.__setattr__(
            result,
            key,
            self._sink if key == "_sink" else copy.deepcopy(value, memo),
        )
    return result
```

#### Done checklist

- `run_unit(unit_id)` returns a receipt plus visualization payload.
- `run_all_units(...)` works through orchestrator execution.
- The app renders raw normalized data, the first baseline artifact, and key unit metadata.



## Stage 2: YAML Control Pipeline

Turn the visualization prototype into the real runnable pipeline shape for the repo.

### What to build

1. A pipeline YAML in `pipeline_configs/`.
2. A YAML runner in `src/pipelines/` that supports:
   single unit execution,
   all examples in one published benchmark version,
   optional runtime AI overrides when AI processors exist.
3. A process processor list that includes exactly the processors required for the use case.

### YAML rules

- Keep YAML focused on class wiring and constructor arguments.
- Let `PipelineBuilder.from_yaml(...)` resolve relative `file_path` keys.
- Require an explicit benchmark key and resolve the requested or latest published version from the benchmark repository.
- Keep benchmark identity and raw artifact manifests in runtime metadata rather than YAML secrets or local files.

Minimal shape:

```yaml
name: your_use_case
version: 1.0.0

objects:
  process: YourProcessObject
  action: YourActionObject

retrieve:
  hydrator: YourRetrieveToProcessHydrator
  retrievers:
    - retriever: YourCsvRetriever
      file_path: ../../data/your_use_case/data.csv
      # Raw artifact identity is injected from the published benchmark example.
      unit_id: ${unit}
      dataset_name: your_dataset

process:
  hydrator: YourProcessToActionHydrator
  processors:
    - processor: YourBaselineProcessor
    - processor: YourAiWorkflowProcessor

action:
  hydrator: YourFinalizeActionHydrator
  actions:
    - action: YourAction
      # Benchmark identity is injected by the runner.
```

### Runtime AI overrides

If the pipeline includes AI processors, the runner may write a temporary runtime YAML with:
- `--ai-model`
- `--ai-reasoning-effort`

Rules:
- Apply overrides only to AI-related entries.
- Never modify the source YAML in place.
- Keep provider support and credential validation in the runner layer, not in processor business logic.

## Stage 3: Optional AI Baseline

Only add AI when compute-only logic is not good enough.

Use `$ai-processor-builder` for the actual processor implementation patterns. In the broader pipeline flow, the important rule is the handoff contract:

1. The AI processor writes a stable artifact on the process object, commonly `ai_classification`.
2. The process-to-action hydrator copies that payload into the action object decision payload.
3. The finalize action hydrator writes the final payload into act-stage receipt metadata.

If this chain is broken, evals and downstream consumers will not see the final AI determination reliably.

## Stage 4: Evaluation Orchestration

Use `$agent-eval-builder` once the YAML pipeline and receipt contract are stable enough for repeated-run comparison.

Primary goals:
- repeat runs per unit to reduce single-run variance,
- compute aggregate and segmented accuracy,
- persist JSON results for comparison over time.

Do not build eval orchestration before the pipeline can already run successfully and write the relevant final output to the receipt.

## Adding New Artifacts Or Processors

When introducing a new artifact:
1. Add typed getter and setter methods on the process object.
2. Add one processor that validates inputs, computes the artifact, and writes it to the process object.
3. Update downstream hydrators and processors that consume that artifact.
4. Update visualization output so the artifact is inspectable during debugging.
5. Re-run evals if AI behavior depends on that artifact.

Keep one clear producer for each artifact whenever practical.

## Common Failure Modes

- Empty visualization payload after a run:
  the sink reference was lost during deepcopy.
- Benchmark example selection fails:
  the runner did not resolve the requested published benchmark version or example IDs.
- AI provider validation fails:
  environment variables or provider settings are missing.
- AI runtime overrides report that no processors were updated:
  the YAML entries do not look AI-related.
- Evals show missing classifications:
  the AI output never reached act-stage receipt metadata.

## Expected Behavior When Using This Skill

When using this skill:
- build the next correct stage instead of over-building the whole stack at once,
- prefer compute-only solutions first,
- make receipt outputs explicit and stable,
- reuse the specialized repo skills rather than re-explaining their domains,
- call out obvious follow-up improvements separately instead of silently expanding scope.
