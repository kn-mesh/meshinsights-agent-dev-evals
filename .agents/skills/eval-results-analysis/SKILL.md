---
name: eval-results-analysis
description: Review evaluation results for a specific pipeline version, prompt revision, or data-input change in this repo. Use this skill when the user wants to understand why accuracy changed, which units regressed, or what prompt or pipeline changes to consider based on versioned eval JSON outputs. Do not run evals or edit prompts unless the user explicitly asks.
---

# Eval Results Analysis

## Overview

Use this skill to analyze eval outcomes after a pipeline change, prompt change, and/or data input change. The goal is to explain what improved or regressed, identify likely causes grounded in the actual unit data, and propose targeted next changes that improve accuracy without overfitting to a small eval set.

## Scope Of This Skill

This skill defines a recommended analysis workflow for an AI coding agent reviewing eval outputs in an `mi-core` style repo.

Treat it as default analysis guidance, not as a guarantee that every repo organizes eval outputs or supporting context in exactly the same way.

Rules:
- Prefer this workflow when investigating regressions or improvements.
- If the repo uses a different but coherent eval layout or naming scheme, treat the current repo outputs as the source of truth for local analysis.
- Keep concrete paths and file-layout references accurate.
- When this skill describes a typical results layout, interpret that as the default pattern rather than a universal requirement.

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Runtime source lives under `mi-core/core/src/mi/`, and the root `uv` environment installs it as an editable local source.
- When analysis depends on framework behavior, verify the implementation directly in that source rather than assuming behavior from a published package.

## Workflow

1. Confirm scope from the user.
   The user will usually tell you which pipeline versions, runs, or prompt revisions matter. Focus on those runs first instead of diffing every eval folder in the repo.
2. Resolve lifecycle state before loading detail:

   ```bash
   uv run python -m src.eval_lifecycle.cli inspect <eval-id> --json
   ```

   A working eval has rich local attempts/review and optional performance. A
   retained eval has aggregate `result.json`, `units.json`,
   `agent-provenance.json`, and `evidence-references.json`; tool traces and
   performance were intentionally pruned.
3. For a working eval, start with the bounded inspection summary instead of
   loading a complete result or review tree:

   ```bash
   uv run python -m src.evals.inspection_cli summary --run <run-id>
   ```

4. Identify the main regression or improvement pattern with compact filters.
   For working evals use:

   ```bash
   uv run python -m src.evals.inspection_cli list \
     --run <run-id> --filter incorrect --limit 20
   ```

   Supported filters include `incorrect`, `invalid`, `failed`, `flaky`,
   `unscored`, and `review-unavailable`.
   For retained evals query the local read-only explorer or select bounded rows
   from `units.json`. Never treat pruned detail as corruption.
5. Inspect only the representative units behind the pattern:

   ```bash
   uv run python -m src.evals.inspection_cli example \
     --run <run-id> --example '<example-id>'

   uv run python -m src.evals.inspection_cli execution \
     --run <run-id> --execution '<execution-id>' \
     --section model_interactions --resolve-text
   ```

   Exact generated images remain local object references; Benchmark Studio
   source evidence remains a credential-free immutable Azure reference. Review
   working review artifacts are temporary and may be absent, which must be
   reported rather than reconstructed or guessed. Retained evals deliberately
   preserve final AI outputs and grading while pruning tool and intermediate
   traces. When working review is unavailable, report its typed reason
   (`disabled`, `capture_failed`, `capture_partial`, or `absent`) rather than
   describing the durable eval attempt as failed.
   Report review integrity separately when the summary marks the bundle
   `invalid`; the disposable inspection index refreshes automatically when
   capture, attempt generations, manifests, objects, or staging changes.
6. Propose changes before editing anything. Explain the specific prompt,
   pipeline, or data-shaping changes and why they address the observed pattern.
7. When the user asks to preserve the analysis, write a compact diagnosis JSON
   with the reviewed run/execution identities and evidence-based hypothesis via
   `src.evals.inspection_cli diagnose`.

## What To Look At

- `summary`
  Use `summary.accuracy.complete_evaluation`, `by_field`, and `by_slice` for
  valid-run accuracy. Review `summary.reliability` and
  `summary.scoring_coverage` separately for execution, contract, and grader
  failures; those runs are excluded from accuracy. Use
  `summary.execution_recovery` for missing/rerun generations and
  `summary.usage` plus `summary.cost` with their explicit availability states.
- `run` and `run.dimensions`
  Use this to confirm the pipeline config, published benchmark version, model,
  reasoning effort, and frozen source snapshot identities used for that run.
  Confirm `run_id` and `run_spec_sha256` before treating two materializations as
  distinct conditions. Use `run.dimensions` when grouping multiple result
  documents by model, agent version, pipeline hash, grader set, or
  project-declared configuration.
- Working reconstructed attempt rows
  Use the bounded inspection commands or `LocalRunStore.evaluation_rows()`;
  rows are not duplicated in `result.json`. Complete frozen benchmark labels
  come from `manifest.json`, while immutable attempt generations supply
  `agent_output`, `evaluations`, contract errors, usage, cost, and failure
  details. Attempts are local and Git-ignored by default, so report detailed
  analysis as unavailable when they were removed after initial analysis; use
  the compact result only for aggregate conclusions in that case.
- Retained unit aggregate
  `units.json` preserves per-unit expected outputs, full final AI outputs,
  validation, grading, usage, and cost. State plainly when a question requires
  tool or intermediate traces that elevation pruned.
- Frozen evidence
  Load charts through the working manifest or retained
  `evidence-references.json` selected-example source snapshot, exact Azure
  account/container, and complete artifact hash/size contract. Do not re-query
  current benchmark membership or use an unverified local copy. If a legacy run
  predates that contract, report evidence as unavailable and rerun it rather
  than weakening integrity.
- `performance/summary.json`
  When present, use its `summary`, `model_calls`, and `retries` sections for
  throughput, stage/API latency, slowest execution IDs, timeout observations,
  and observed retry telemetry. Primary aggregates and links describe only the
  current/latest durable generation for each logical work item. The whole
  `performance/` tree is disposable. If it is absent or invalid, report
  performance diagnostics as unavailable and continue analyzing durable
  quality, reliability, coverage, usage, and cost.
- `review/executions/` and `review/objects/`
  Access these only through the inspection CLI. Execution manifests contain
  normalized messages, model/tool activity, raw/parsed output history,
  pipeline-stage context, and typed artifact references. Do not recursively
  load the object store or print binary objects as base64.


## Analysis Standards

- Anchor every recommendation in concrete evidence from the eval JSON
- Prioritize repeated failure patterns over one-off anecdotes.
- Separate these questions:
  Is the model reading the data/charts incorrectly?
  Is the prompt asking the wrong question or weighting the wrong cues?
  Is the pipeline giving the model incomplete or misleading context?
  Is the approved benchmark label itself uncertain?
- Prefer changes that are likely to generalize across similar units, not just fix a single example.
- Treat the eval set as a proxy for production accuracy, not the final objective. The target is better real-world performance with limited overfitting.

## Guardrails

- Do not run evals unless the user explicitly gives permission.
- Do not directly edit prompts unless the user explicitly asks for that change.
- Do not upload review artifacts to Azure or another cloud destination.
- Do not treat disposable review content as benchmark truth or durable run
  recovery state.
- Do not treat disposable performance observations as durable result fields or
  infer unavailable retry counts from configured retry limits.
- Use `$eval-lifecycle` for exact permanent deletion; deletion is not
  recoverable.
- First present the exact changes you want to make, the evidence behind them, and the expected tradeoffs.
- If the evidence is mixed, say so clearly instead of forcing a prompt tweak.

## Expected Output

When using this skill, give the user a concise analysis that covers:

1. Which run or pipeline version was reviewed.
2. The main accuracy changes or error clusters.
3. A few representative unit IDs with chart-grounded explanations of why the model likely succeeded or failed.
4. The proposed next changes, why they should help, and what overfitting risk they introduce.
5. A clear note that no evals were rerun and no prompts were edited unless the user asked for it.
