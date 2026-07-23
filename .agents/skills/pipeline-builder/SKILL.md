---
name: pipeline-builder
description: Build or evolve stage-based use-case pipelines in this repo. Use this skill when a request involves creating or modifying retrievers, hydrators, process or action objects, pipeline YAML, the exact-example pipeline runner, pipeline receipts, processor variant organization, or the progression from compute-only logic to optional AI and eval support.
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
- `$benchmark-pipeline-port` when the task starts from a working Benchmark
  Studio evidence pipeline and a clean Agent Workbench project.
- `$ai-processor-builder` for workflow or agent processor implementation details.
- `$agent-eval-builder` for eval orchestration and eval JSON contracts.

Use `$external-runtime-setup` when the task also depends on provider auth, tracing, or runtime AI overrides.

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Framework source lives under `mi-core/core/src/mi/`, and CLI source lives under `mi-core/cli/src/cli/`.
- The root `uv` environment installs both as editable local sources. Before
  modifying it, show why a use-case-local change is insufficient, identify the
  exact paths and contracts, and obtain explicit user approval. Then run the
  focused `mi-core` tests.

## Read This First

Before writing pipeline code:
1. Read docs in [docs/use_case/...].
2. Treat these files as durable context, not an implementation log.
3. Reuse `mi.core`, `mi.ai`, and existing repo helpers before writing custom plumbing.
4. If behavior appears framework-level, propose the exact `mi-core/` change and
   ask for approval before editing. Do not add a use-case workaround solely to
   avoid the approval gate.
5. Do not modify `src/experimental_core/` unless the user explicitly asks.

## Core Design Rules

### Receipt-first outputs

Design the pipeline so the final business outcome for a unit is captured on the returned `PipelineReceipt`, usually in act-stage metadata.

Rules:
- Keep receipt payloads compact, serializable, and stable.
- Keep intermediate computation on the process object as artifacts, not in the receipt.
- Treat debug and inspection outputs as optional side effects, not as the durable record.

### Variant-first organization

Prefer organizing processors by pipeline variant before processor type.

Recommended layout:
- `src/processors/common/` for processors reused across distinct variants.
- `src/processors/<variant>/` for processors tied to one evolving pipeline shape.

Keep one shared process object, action object, and shared hydrators if that keeps experimentation simpler. Some temporary overlap is acceptable while variants evolve.

## Development Sequence

Build in this order unless the user explicitly asks to skip ahead:
1. Inspect one exact published benchmark example and its frozen evidence.
2. Build or evolve the YAML pipeline for one-example execution.
3. Stop at compute-only if that solves the use case reliably enough.
4. Add an AI baseline only if compute-only logic is insufficient or too brittle.
5. Verify one exact example through the pipeline runner.
6. Use eval orchestration for benchmark selection, repeated runs, concurrency, and comparison.
7. Iterate using measured deltas, not intuition.

### Stage exit criteria

- Evidence-inspection stage:
  You can load one exact published benchmark example, verify its frozen raw artifacts, and inspect the normalized evidence needed by the pipeline.
- Pipeline stage:
  YAML runs for one exact example and the final pipeline determination appears on the returned receipt.
- AI stage:
  The AI path runs successfully and its output reaches receipt metadata.
- Eval stage:
  The existing eval path selects the intended examples, executes the variant,
  and produces an inspectable result with benchmark, agent, and configuration
  identity.

## Stage 1: Exact-Example Pipeline

Build or evolve the reusable pipeline shape against one exact published example before running an eval set.

The pipeline runner owns one-example execution. It does not own benchmark-wide
selection, batching, repetition, concurrency, resume, or aggregation; those
belong to eval orchestration.

### What to build

1. Published benchmark and immutable raw-source access.
2. A retriever in `src/retrievers/` that:
   resolves `PipelineMetadata.unit`,
   loads and normalizes raw rows,
   attaches benchmark example and source-snapshot context needed downstream.
3. A retrieve-to-process hydrator in `src/hydrators/` that validates retriever outputs and populates datasets and artifacts on the process object.
4. A process object subclass in `src/objects/` with typed getters and setters for normalized datasets and important artifacts.
5. One baseline compute processor in the relevant processor package.
6. An action object, process-to-action hydrator, finalize hydrator, and action.
7. A `.ppln` config under `pipeline_configs/` and any use-case-specific runner helpers required by `src/pipelines/pipeline_run_from_yaml.py`.

### Done checklist

- `run_pipeline(...)` receives one exact `BenchmarkVersion` and
  `BenchmarkExample` and returns a `PipelineReceipt`.
- `src.pipelines.pipeline_run_from_yaml` requires explicit benchmark and
  example identity and runs that exact example.
- Frozen evidence identity is preflighted before execution, and raw artifacts
  are verified before decoding.
- Important derived artifacts flow through the process and action objects, and
  the final business output appears in act-stage receipt metadata.

## Stage 2: YAML Pipeline Contract

Keep the runnable pipeline shape explicit and compatible with benchmark preflight.

### What to build

1. A pipeline YAML in `pipeline_configs/`.
2. The exact-example runner in `src/pipelines/` with optional runtime AI
   overrides when AI processors exist.
3. A process processor list that includes exactly the processors required for the use case.

### YAML rules

- Keep YAML focused on class wiring and constructor arguments.
- For benchmark-backed pipelines, declare `benchmark_contract` with the
  published schema version, evidence-recipe ID, source-snapshot contract ID,
  and required artifact kinds. The benchmark-aware runner validates and strips
  this block before calling `PipelineBuilder`.
- Let the benchmark-aware runner inject exact example and raw-artifact
  metadata, strip `benchmark_contract`, and build an ephemeral runtime config.
- Require explicit benchmark and example identity at the CLI boundary. A
  benchmark version may resolve to the latest published version when omitted.
- Keep benchmark identity and raw artifact manifests in runtime metadata rather than YAML secrets or local files.
- Do not add all-example or repeated-run helpers to the pipeline runner. Route
  those requests through `src.evals.eval_orchestration`.

Minimal shape:

```yaml
name: your_use_case
version: 1.0.0

metadata_class: BenchmarkExamplePipelineMetadata

benchmark_contract:
  published_contract_schema_version: 2
  evidence_recipe_id: your-evidence-recipe@v1
  source_snapshot_contract: azure-blob-sha256-v1
  required_artifact_kinds: [your-artifact-kind]

objects:
  process: YourProcessObject
  action: YourActionObject

retrieve:
  hydrator: YourRetrieveToProcessHydrator
  retrievers:
    - retriever: YourFrozenEvidenceRetriever
      # Exact example and raw-artifact identity are injected at runtime.

process:
  hydrator: YourProcessToActionHydrator
  processors:
    - processor: YourBaselineProcessor
    - processor: YourAiWorkflowProcessor

action:
  hydrator: YourFinalizeActionHydrator
  actions:
    - action: NoOpAction
      # The final business output is already carried in action/receipt metadata.
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
Do not add a new execution mode, persistence layer, identity system, recovery
mechanism, or artifact-lifecycle feature unless a demonstrated FDE task requires
it. Use `$agent-eval-builder` to select the minimum stage gate for the outcome.

## Build The First Agent Or Next Variant

Use this short workflow after the ported control pipeline is sound:

1. Preserve the working parent `.ppln`; add the candidate at a new pipeline
   path.
2. Define the benchmark-aligned structured output and its evaluation-profile
   receipt paths before writing prompts or tools.
3. Choose the simplest useful shape: deterministic logic first, one-shot AI
   workflow when prepared evidence is sufficient, and a tool-using agent only
   when the model must choose a bounded investigation at runtime.
4. Reuse retrieval, evidence preparation, objects, hydrators, and actions unless
   the variant hypothesis requires changing them. Use `$ai-processor-builder`
   for AI implementation details.
5. Verify the result flows from a stable process artifact through the action
   payload into act-stage receipt metadata.
6. Run focused tests and one exact published benchmark example, then use
   `$run-use-case-evals` for a one-example serial eval.
7. Report the changed and held-constant dimensions, pipeline path, candidate
   `agent_version_id`, smoke `run_id`, and wider-eval command. Do not silently
   run a broad eval, make another variant change, or promote the candidate.

Record the short hypothesis in the project's existing pipeline-version notes.
Do not add a parallel variant manifest, generator, catalog, or identity; the
existing agent-version and eval identities preserve exact comparison points.

## Adding New Artifacts Or Processors

When introducing a new artifact:
1. Add typed getter and setter methods on the process object.
2. Add one processor that validates inputs, computes the artifact, and writes it to the process object.
3. Update downstream hydrators and processors that consume that artifact.
4. Update focused tests or optional diagnostics so the artifact is inspectable during debugging.
5. Re-run evals if AI behavior depends on that artifact.

Keep one clear producer for each artifact whenever practical.

## Common Failure Modes

- Benchmark example selection fails:
  the runner did not resolve the requested published benchmark version or example ID.
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
