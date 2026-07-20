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
- Its current checkout path is `/Users/kurt.neuens/Desktop/Code - Product/meshinsights-agent-dev-evals-mvp/mi-core`; use the repo-relative `mi-core/` path in code and documentation.
- Runtime source lives under `mi-core/core/src/mi/`, and the root `uv` environment installs it as an editable local source.
- When analysis depends on framework behavior, verify the implementation directly in that source rather than assuming behavior from a published package.

## Workflow

1. Confirm scope from the user.
   The user will usually tell you which pipeline versions, runs, or prompt revisions matter. Focus on those runs first instead of diffing every eval folder in the repo.
2. Read the relevant eval results.
   Start under root-level `eval_results/<pipeline-stem>/`.
   Typical `v1_3` files live under
   `eval_results/v1_3/<benchmark_key>/v<benchmark-version>/<scope>/*.json`.
3. Identify the main regression or improvement pattern.
   Use the top-level `summary` and then drill into `results`.
   Look for misses by classification, root cause, confidence band, and repeated failure modes across multiple units.
4. Inspect individual units behind the pattern.
   For the most informative correct and incorrect examples, review each unit's `runs` payload and compare the model explanation to the expected label.
5. Propose changes before editing anything.
   Explain the specific prompt, pipeline, or data-shaping changes you want to make and why those changes should address the observed failure pattern.

## What To Look At

- `summary`
  Use `summary.accuracy` for class, confidence, and root-cause breakdowns.
  Review `summary.reliability` separately for provider, pipeline, timeout,
  cancellation, and receipt-contract failures; failed runs are excluded from
  accuracy. Use `summary.performance` for throughput and latency distributions.
- `run_config`
  Use this to confirm the pipeline config, published benchmark version, model, reasoning effort, and frozen source snapshot identities used for that run.
- `results[].runs[]`
  Use this for unit-level expected vs actual outcomes, confidence, and explanation quality.


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
- First present the exact changes you want to make, the evidence behind them, and the expected tradeoffs.
- If the evidence is mixed, say so clearly instead of forcing a prompt tweak.

## Expected Output

When using this skill, give the user a concise analysis that covers:

1. Which run or pipeline version was reviewed.
2. The main accuracy changes or error clusters.
3. A few representative unit IDs with chart-grounded explanations of why the model likely succeeded or failed.
4. The proposed next changes, why they should help, and what overfitting risk they introduce.
5. A clear note that no evals were rerun and no prompts were edited unless the user asked for it.
