---
name: agent-eval-builder
description: Build or change the minimum Agent Workbench evaluation capability needed for an FDE to measure, inspect, compare, and improve connected-system agent variants against published benchmarks. Use for benchmark/evidence handoff contracts, evaluation profiles, graders, orchestration, result contracts, comparisons, or eval-result applications. Do not use merely to run or troubleshoot an existing eval; use run-use-case-evals. Prefer the simplest existing path and require evidence before adding reusable infrastructure, new persistence layers, execution modes, or artifact lifecycle features.
---

# Agent Eval Builder

Help an FDE answer: **Did this agent variant make better decisions for the
right units at the right decision points, and why?**

The skill guides product work, not preservation of every current implementation
detail. Existing behavior remains relevant when changing it, but it is not a
reason by itself to expand or reproduce the architecture.

## Preserve The Product Boundary

- Benchmark Studio owns published benchmark membership, approved labels,
  frozen label-schema identity, and immutable evidence.
- Agent Workbench consumes that truth read-only to develop, evaluate, compare,
  inspect, and package agent variants.
- Keep use-case labels, evidence meaning, prompts, and business rules in the
  use-case project. Keep genuinely reusable evaluation mechanics in shared code.
- Do not add Benchmark Studio write paths, local benchmark truth, production
  hosting, or generic agent-runtime infrastructure.

## Start With The FDE Outcome

Before proposing or editing code, answer these questions from repository
evidence:

1. What FDE job is being completed: measure, inspect, compare, or improve?
2. What concrete task is blocked or materially slow today?
3. What is the simplest existing path that can complete that task?
4. Does the change help launch or improve a decision about a unit at a decision
   point?
5. What evidence justifies a reusable abstraction rather than a use-case-local
   change?
6. What adjacent feature should explicitly **not** be added yet?

If the task does not have a clear FDE outcome, stop expanding the design and
report the mismatch.

## Use These Stage Gates

Advance only as far as the requested outcome requires.

### Gate 1: One measurable example

Require a working pipeline that:

- runs one exact example from a named published benchmark version;
- preserves unit, decision timestamp, example, source-snapshot, and evidence
  identity; and
- returns a structured decision that can be compared with approved labels.

If this gate fails, fix the pipeline or handoff contract before adding eval
orchestration.

### Gate 2: Minimum useful evaluation

Add only enough evaluation capability to:

- select the intended examples;
- execute the existing pipeline with an explicit model/configuration;
- distinguish execution failure, invalid output, and incorrect valid output;
- calculate the requested aggregate and per-field measures; and
- retain enough identity to reproduce or explain the result.

Do not add generalized filtering, execution modes, persistence schemas, or
recovery machinery unless the requested job depends on them.

### Gate 3: Inspect and compare

Enable the FDE or Codex to:

- find incorrect, invalid, failed, or unstable examples;
- inspect expected output, actual output, exact evidence identity, and available
  model inputs/outputs; and
- compare variants only across declared dimensions.

Prefer extending the current result and inspection path over creating another
representation of attempts, evidence, or comparisons.

### Gate 4: Reusable infrastructure

Promote behavior into shared evaluation code only when at least one of these is
true:

- two real use cases need the same semantic behavior;
- a current shared contract cannot correctly express the requested job; or
- an explicit product decision requires the capability.

Similarity of implementation is not enough. The abstraction must preserve the
same meaning across use cases.

### Gate 5: Operational hardening

Add concurrency variants, resumability generations, transactional capture,
content-addressed stores, new retention schemas, catalogs, quarantine, restore,
purge, or migration machinery only for a demonstrated operational failure or an
explicitly requested product requirement.

Local disk housekeeping and artifact lifecycle management are maintenance
concerns, not default Agent Workbench product capabilities.

## Prefer The Smallest Change

Use this order:

1. Reuse an existing evaluator, grader, result field, or inspection query.
2. Make a use-case-local profile, grader, adapter, or view.
3. Extend a shared contract with the smallest compatible change.
4. Add a new shared subsystem only after Gate 4 is satisfied.

Do not preserve an abstraction solely because current code is coherent. When a
simpler path can meet the requested outcome safely, identify the removable or
deprecated path instead of silently layering beside it.

## Preserve Only Strategic Invariants By Default

- Published benchmark and frozen-evidence access remains read-only.
- Unit, decision timestamp, example, benchmark, source snapshot, and agent
  configuration remain traceable through the result.
- Frozen artifact integrity is verified before evidence is interpreted.
- Expected labels and actual agent outputs remain separately inspectable.
- Accuracy excludes invalid, failed, or unscored attempts; reliability and
  coverage expose those attempts separately.
- Use-case-specific meaning does not leak into shared evaluation mechanics.
- Detailed inspection data can be absent without corrupting the durable score.

Everything else is an implementation choice to evaluate against the requested
FDE outcome.

## Work In This Sequence

1. Read the relevant product strategy, use-case context, pipeline, profile,
   result, and tests.
2. State the FDE outcome, current blocker, selected stage gate, and explicit
   non-goals.
3. Trace the narrowest current execution and inspection path end to end.
4. Implement the smallest change at the layer that owns its meaning.
5. Validate the changed behavior and the strategic invariants it touches.
6. Report the achieved outcome, remaining limitation, and any infrastructure
   deliberately deferred.

## Validate In Proportion To The Change

- Benchmark handoff: test project scope, immutable identity, label-schema
  integrity, artifact verification, and read-only behavior.
- Profile or grader: test valid, invalid, missing, conditional, and representative
  slice cases relevant to the change.
- Orchestration: test the selected execution path, failures relevant to it, and
  stable result materialization.
- Inspection or UI: test wrong-example discovery and the exact evidence and
  model detail the user needs.
- Comparison: test declared dimensions and paired examples used by the change.
- Lifecycle or recovery: test it only when the user explicitly requested that
  maintenance behavior.

Do not automatically require every runtime, storage, recovery, lifecycle, and
UI test category for a local scoring or orchestration change.

## Load Technical Detail Only When Needed

Read [references/current-evaluation-contracts.md](references/current-evaluation-contracts.md)
when a task changes an existing eval schema, run store, candidate-version
contract, review capture, explorer API, hosted input, comparison, or lifecycle
implementation. It describes current behavior for compatibility and diagnosis;
it does not make those features required for new work.

Use `EvalRunbook.md` and `$run-use-case-evals` for live commands. Use
`$eval-results-analysis` to explain an existing regression without changing the
evaluation system.
