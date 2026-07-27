---
name: agent-eval-builder
description: "Build or change Agent Workbench evaluation capability: profiles, graders, orchestration, result or lifecycle contracts, and eval-result apps. Use when existing eval tooling must be implemented or modified. Use dedicated port, run, and analysis skills for those workflows."
---

# Agent Eval Builder

Help an FDE answer whether an agent made better decisions for the right units
at the right decision points, and why. Build only the capability required for
that outcome.

## Product Boundary

- Benchmark Studio owns published membership, approved labels, frozen label
  schema, and immutable evidence.
- Agent Workbench consumes that truth read-only for development and evaluation.
- Keep use-case meaning, prompts, graders, and views project-local; share only
  mechanics with the same meaning across real use cases.
- Do not add Studio writes, local benchmark truth, production hosting, or
  generic runtime infrastructure.

For product choices, read `docs/product-strategy/` when it exists. In generated
projects use `workbench.project.json`, `docs/use_case/`, and these boundaries.

## Select One Stage Gate

### 1. One measurable example

Require one explicitly versioned published example, preserved unit/timestamp/
example/evidence identity, and structured output comparable with approved
labels. Validate through the pipeline runner, not a one-example eval.

### 2. Minimum useful evaluation

Add only enough to select the requested benchmark scope; execute an explicit
agent/model configuration in bounded threads or serial debug mode; persist
completed units; resume missing work; distinguish failed, invalid, and
incorrect outputs; and report accuracy, reliability, coverage, usage, and cost
with reproducible identity.

Keep project predicates in profiles. Do not add process execution, arbitrary
operator predicates, generalized rerun/comparison orchestration, or another
persistence or identity system.

### 3. Inspection

Support bounded discovery of incorrect, invalid, failed, or unstable examples
and inspection of expected output, actual output, exact evidence, and available
model/tool detail. Compare high-level dimensions across independent runs; do
not create paired-delta artifacts or duplicate attempt representations.

### 4. Reusable capability

Share behavior only when two real use cases need the same semantics, an
existing shared contract is insufficient, or an explicit product decision
requires it. Similar code alone is not evidence.

### 5. Operational hardening

The supported lifecycle is rich working evals, explicit elevation of one
complete selected occurrence into compact retained aggregates, read-only
exploration, and exact permanent deletion. Route selected retained publication to
`$publish-retained-eval`.

Do not add quarantine, restore, recoverable deletion, archival tiers, generic
garbage collection, lifecycle UI mutation, automatic cloud sync, or Studio
writes.

## Strategic Invariants

- Preserve traceable benchmark, example, unit, decision timestamp, source
  snapshot, evidence, and agent/configuration identity.
- Verify frozen artifact integrity before interpretation.
- Keep expected labels and actual outputs separately inspectable.
- Exclude invalid, failed, and unscored attempts from accuracy; expose them in
  reliability and coverage.
- Treat missing detailed inspection data as unavailable, not score corruption.
- Prefer an existing evaluator/query, then a project profile/grader/adapter,
  then the smallest compatible shared extension.

## Workflow

1. Read `docs/use_case/`, the pipeline, profile, result, and focused tests.
2. State the FDE outcome, selected gate, blocker, and explicit non-goals.
3. Trace the narrowest current execution and inspection path.
4. Implement at the layer that owns the meaning.
5. Test only the contracts touched: benchmark handoff, profile/grader,
   orchestration/result, inspection/UI, or explicitly requested lifecycle.
6. When the first pipeline, agent policy, and profile are operable, finalize
   `EvalRunbook.md` with validated exact-example, discovery, eval, inspection,
   lifecycle, and publication commands; then remove
   `agent-workbench-eval-runbook-status: bootstrap-placeholder`.
7. Report the outcome, evidence, limitation, and deferred infrastructure.

Select completion checks from the
[repository verification matrix](../project-guide/references/verification-matrix.md)
for every changed layer.

Read
[references/current-evaluation-contracts.md](references/current-evaluation-contracts.md)
only when changing or diagnosing an existing schema, run store, candidate
version, review capture, explorer API, hosted input, publication, or lifecycle
contract. Use `EvalRunbook.md` and `$run-use-case-evals` for commands, and
`$eval-results-analysis` for regression analysis without system changes.
