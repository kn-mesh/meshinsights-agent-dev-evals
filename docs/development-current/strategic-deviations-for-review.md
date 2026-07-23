# Agent Workbench Strategic Deviations For Review

## Purpose

This document captures strategic concerns discovered while comparing the current
Agent Workbench repository with `docs/product-strategy/`. It is decision material
for later product-owner reaction, not an approved implementation plan.

The repository-skill ratchet was addressed separately by making
`agent-eval-builder` and `project-guide` outcome- and stage-gate-driven. This
document records the other findings. It intentionally does not propose changes
to `docs/product-strategy/architecture-feature-decisions.md`.

## Strategy Anchors

Use these commitments when evaluating the findings:

- Mesh differentiates through readiness and continuous improvement, not generic
  agent runtime or infrastructure.
- Agent Workbench exists to develop, evaluate, compare, inspect, and package
  agent variants against published Benchmark Studio truth.
- The portable agent package is the practical handoff into a Microsoft,
  customer, or other approved production runtime.
- The readiness environment should optimize for speed, flexibility, and
  measurement.
- FDE capacity is the primary scaling constraint.
- Work should remain centered on decisions about units at decision points.

## Findings At A Glance

| Priority | Finding | Decision needed |
|---|---|---|
| Resolved | Local artifact lifecycle is ahead of portable handoff and feedback | MVP boundary reaffirmed; implementation must be narrowed to the working-versus-retained eval lifecycle |
| Resolved | Evaluation orchestration has grown into a generic local platform | Protected eval path defined; implementation alignment remains |
| Resolved | Experiment provenance and meaningful agent-version promotion are conflated | Lightweight working provenance and explicit eval-plus-agent elevation are defined; implementation alignment remains |
| Resolved | One repository is acting as use-case project, template, and framework monorepo | Separate use-case repos start from a template with distinct reusable components, root skills, and a replaceable reference seam |
| Resolved | Human inspection is strategically correct, but default review capture is heavy | Full working capture, Azure evidence references, compact full-run elevation, and read-only app behavior are defined |

## 1. Local Artifact Lifecycle Versus Portable Handoff

**Status:** Resolved at the product-scope level. Implementation alignment
remains.

### Observation

The MVP backlog marks local version/result cataloging, intentional retention,
recoverable deletion, restore, and purge as complete. The implementation includes
a derived reference graph, content-addressed reachability, deletion plans,
quarantine operations, locks, recovery, and permanent purge.

Portable agent packaging, Microsoft Foundry translation, production-feedback
routing, and selective cloud publication remain post-MVP.

Relevant evidence:

- `docs/development-backlog/features.md`, MVP boundary and checklist
- `src/lifecycle/`
- `src/agent_versions/`
- `docs/development-backlog/features.md`, Portable Agent Package
- Product strategy sections "Strategic Point Of View" and "Product Strategy"

### Product Owner Decision

The MVP is intentionally limited to the eval and agent-improvement loop. It is
not intended to create the portable agent package, translate an agent into
Microsoft Foundry, prove Agent Launch, or implement a production-feedback
return path.

Local eval data has two product-relevant classes:

- **Working evals** are rich local debugging and review data. They are
  disposable and may be deleted within minutes as the FDE changes the agent.
- **Retained evals** represent meaningful agent versions selected for future
  comparison and review. They retain the exact benchmark and agent versions,
  relevant configuration, full AI outputs, expected outputs, grading outcomes,
  accuracy calculations, and aggregate statistics.

Retained evals do not require detailed speed or latency telemetry, and they do
not require one file per evaluated unit. A small number of aggregate JSON
artifacts is preferred.

Deletion is permanent. Quarantine, restore, recoverable deletion, distributed
coordination, and generalized local storage administration are not MVP or
near-term product requirements. One FDE manages the local project and its
retained artifacts.

Selected retained evals may move to Azure Blob Storage after MVP, likely near
but logically separate from frozen benchmark evidence. That storage design is
deferred.

See `docs/product-strategy/mvp-scope.md` for the durable decision.

### Required Alignment

- Freeze lifecycle capabilities outside the decided boundary at safe
  maintenance.
- Make working-run deletion simple and permanent.
- Protect explicitly retained evals and meaningful agent versions from casual
  working-run cleanup.
- Prefer compact aggregate JSON artifacts for retained evals.
- Do not treat existing quarantine, restore, purge recovery, generalized
  reachability, or multi-user safety machinery as required product behavior.
- Evaluate the implementation separately before deciding whether excess
  machinery should be removed, bypassed, or merely left unsupported.

## 2. Evaluation Harness Becoming A Generic Platform

**Status:** Resolved at the product-scope level. Implementation alignment
remains.

### Observation

The current evaluation surface includes repeated execution, three runtime modes,
generic label filters, a predicate language, slices, deterministic identities,
immutable attempt generations, selective reruns, resumability, cooperative
signals, materialization-only operations, comparisons, performance schema,
review schema, integrity verification, and lifecycle integration.

The implementation is concentrated in:

- `src/evals/eval_orchestration.py`
- `src/evals/run_store.py`
- `src/evals/evaluation_profile.py`
- `src/evals/comparisons.py`
- `agent-dev-eval-core/evaluation/`

This is substantially broader than the core FDE job described in
`docs/product-strategy/jobs-to-be-done.md`: run against a benchmark, write the
critical statistics, inspect wrong examples, compare a few models/configurations,
and iterate.

### Why This May Be Strategically Wrong

Every generalized execution, persistence, and recovery contract increases:

- FDE cognitive load and command complexity;
- the number of invariants that slow future product changes;
- testing and migration cost;
- pressure to preserve internal abstractions instead of improving the agent; and
- the likelihood that Agent Workbench competes as generic eval infrastructure.

Some advanced features may be justified by expensive, long-running evaluations.
The concern is that they are being treated as one mandatory product rather than
optional responses to demonstrated bottlenecks.

### Product Owner Decision

The protected workflow is: select a published benchmark and version, select an
agent and model configuration, select the intended benchmark scope, run with
bounded threaded concurrency, produce the eval result, and review it with Codex,
the local evaluation review app, or both.

Comparison happens after eval execution. Codex or the review app may compare
completed evals; comparison is not a mandatory step coupled to the runner.

The required scope choices are:

- the full benchmark;
- a hand-selected list of units or examples; and
- a named use-case-defined section, such as all open failures.

The normal runtime is bounded threaded execution. Serial execution remains a
debugging option. Separate-process execution is deferred unless isolation is
shown to solve a real failure.

An interrupted run may resume only its missing units. An interruption means the
run process stopped before its selected work finished, whether by `Ctrl-C`,
terminal or machine shutdown, authentication loss, or an external failure.
Completed unit results remain durable during the run. This is distinct from
deleted-run recovery, which is not required.

Every eval records token and cost summaries. Required statistics include input,
output, and total tokens; total cost; average cost per unit; P5 and P95 cost per
unit; and cost-coverage information. The model configuration experience must
support input and output prices, and the eval must retain the pricing snapshot
used for its estimates.

The repository already contains project-owned model pricing and cost-estimation
contracts in `model_catalog.py` and `src/evals/eval_orchestration.py`. The
identified product gap is that the model configuration selector does not
collect or maintain those prices, and the current aggregate cost summary does
not expose all required per-unit percentile statistics.

### Required Alignment

- Keep full-benchmark, explicit-unit, and named use-case section selection.
- Do not expose the generic predicate language as a required FDE concept.
- Make threaded execution the standard path and serial execution the debugging
  path.
- Remove, hide, or leave unsupported separate-process execution unless evidence
  justifies it.
- Preserve the simplest missing-unit resume path; do not expand it into
  generalized recovery generations or rerun policy machinery without a
  demonstrated need.
- Keep review and comparison downstream of completed eval execution.
- Add model pricing to the configuration experience and produce the decided
  token and per-unit cost summaries.
- Classify materialization-only operations, selective failure reruns, and other
  advanced orchestration contracts as unsupported or maintenance-only unless
  a concrete FDE failure requires them.

## 3. Experiment Provenance Versus Agent-Version Promotion

**Status:** Resolved at the product-scope level. Implementation alignment
remains.

### Observation

Every eval currently resolves an exact candidate agent version before model
execution. Resolution scans and hashes the pipeline graph, component source,
dirty overlay, declared assets, prompts, schemas, contracts, dependency state,
and model override policy. Promotion then copies the manifest and required
objects into a local content-addressed store.

Relevant evidence:

- `src/agent_versions/resolver.py`
- `src/agent_versions/store.py`
- `agent_version_configs/*.agent.yaml`
- candidate resolution in `src/evals/eval_orchestration.py`

The product job says meaningful agent versions should be saved over time so the
team can demonstrate progress and roll back. That wording suggests a distinction
between ordinary experiment provenance and explicit version promotion.

### Product Owner Decision

Ordinary working evals and meaningful retained evals are different product
states. Working evals are disposable. An FDE explicitly retains an eval when it
represents a meaningful agent version worth future comparison or review.

This establishes explicit elevation as the meaningful-version boundary.

Every working eval records lightweight provenance: Git commit, relevant
uncommitted and untracked changes, configuration hashes, benchmark and evidence
identity, model configuration, and the frozen pricing snapshot. This is
sufficient for working and retained evals; a second copy of the full source tree
is not required.

Elevating an eval automatically retains its associated meaningful agent
version. The eval and agent version are one preservation decision and must not
become detached.

### Why This May Be Strategically Wrong

Conflating every experiment with an immutable agent version creates an internal
source and artifact-management product. It may also make the concept of a
"version" less meaningful to an FDE or customer.

Exact reproducibility remains important. The open question is whether ordinary
runs need the same artifact machinery as promoted, package-ready agents.

### Required Alignment

- Treat every new eval as a working eval.
- Record lightweight Git, patch, configuration, benchmark, model, and pricing
  provenance without copying the full source tree.
- Provide one explicit elevation operation that retains both the eval and its
  meaningful agent version.
- Compact the elevated eval into aggregate artifacts while pruning disposable
  performance detail.
- Separate working and retained evals visibly in the local folder contract and
  evaluation review app.
- Document the run, review, elevate, verify, and delete lifecycle in a
  repository skill.
- Preserve the working-versus-retained semantic boundary when retained
  artifacts move to cloud storage after MVP.

See `docs/product-strategy/mvp-scope.md`, Decision 3, for the durable target
folder and workflow contract.

## 4. Use-Case Repository Versus Framework Monorepo

**Status:** Resolved at the product-scope level. Physical reorganization remains
feature-planning work; long-term package distribution is deferred.

### Observation

The repository simultaneously contains:

- the Spirax use-case implementation;
- project bootstrap and template behavior;
- full editable `mi-core` and CLI source;
- reusable evaluation core and UI packages;
- use-case-specific frontend composition; and
- local version and lifecycle subsystems.

The root package remains named `mesh.insights.template`, while the README
describes a combined full-core and use-case repository. Repository skills direct
Codex to modify the embedded framework when behavior appears reusable.

Relevant evidence:

- `README.md`
- `pyproject.toml`
- `mi-core/`
- `agent-dev-eval-core/`
- `agent-dev-eval-ui/`
- `src/project_bootstrap/`

### Why This May Be Strategically Wrong

If this combined layout becomes the normal customer-project layout, each
engagement can create its own framework fork. That weakens cross-customer reuse,
increases review and upgrade cost, and consumes the FDE capacity the strategy
identifies as the main constraint.

The layout may be correct for central Workbench product development. It is less
clearly correct for a thin, customer-owned use-case project.

### Product Owner Decision

This repository is an internal Mesh/FDE working repository containing both the
reusable components and a complete Spirax reference use case. Each new use case
gets its own Git repository created from the Agent Workbench template, including
reusable source, the standard project structure, and root-level agent skills. It
removes the Spirax reference example and builds the new use case in the same
structural seam. Customers do not see these repositories; their eventual
handoff is the portable agent package.

For MVP, rapid iteration takes priority over a rigid package-release boundary.
Reusable libraries may remain editable local source. A coding agent must,
however, ask the user before changing reusable core code. It must explain why a
use-case-local change is insufficient and identify the exact shared paths or
contracts involved.

Reusable ownership must be explicit, but reusable code must not be collapsed
into one catch-all directory or into `mi-core/`. `mi-core/` is a distinct forked
pipeline and AI runtime library. `agent-dev-eval-core/`,
`agent-dev-eval-ui/`, and other use-case-neutral Workbench mechanics remain
separate reusable components.

The repository needs one clearly documented replaceable use-case seam
containing project identity, domain context, integrations, pipelines, prompts,
evaluation configuration, and frontend composition. Agent skills stay at the
repository root under `.agents/skills/`; reference-specific skills are removed
or rewritten there when starting a new project.

When an approved reusable fix is discovered in a use-case repository, the
coding agent may implement and test it locally but must record and upstream it
to the canonical template or reusable library source before the work is
complete. Independently published, pinned packages remain a likely long-term
option, but adopting them now would add release and migration friction while
the shared contracts are changing quickly.

### Required Alignment

- Give every use case its own Git repository created from the working template.
- Make the Spirax reference boundary explicit and replaceable without searching
  through or modifying reusable code.
- Keep one complete working reference use case in this development repository.
- Keep `mi-core/` as its own forked pipeline/runtime library; do not use it as a
  container for unrelated reusable Workbench code.
- Keep other reusable libraries and generic Workbench mechanics separately
  identifiable.
- Keep all agent skills at root under `.agents/skills/`.
- Preserve editable local reusable code during rapid MVP iteration.
- Require explicit user approval before a coding agent modifies reusable core
  behavior.
- Update repository skills and agent guidance to enforce that approval gate.
- Require approved local reusable fixes to be identified and upstreamed to the
  canonical template or reusable library source.
- Keep this repository and its source artifacts internal to Mesh/FDEs.
- Revisit pinned packages or separate shared repositories when multiple active
  projects, contract stability, or upgrade rework justifies the overhead.

See `docs/product-strategy/mvp-scope.md`, Decision 4, for the durable direction
and proposed logical boundary.

## 5. Human Inspection Versus Heavy Default Review Capture

**Status:** Resolved at the product-scope level. Implementation alignment
remains.

### Observation

Human result exploration is directly aligned with the FDE job. The current
implementation, however, defaults every eval to full review capture and stores
detailed prompt, response, tool, validation, text, and multimodal artifacts in a
transactional local content-addressed tree.

Relevant evidence:

- `src/evals/eval_orchestration.py`, `review_capture="full"`
- `agent-dev-eval-core/evaluation/review.py`
- `src/evals/inspection.py`
- `agent-dev-eval-ui/`
- `www/`

In the repository state observed during the review, two runs under one benchmark
version consumed roughly 63 MB, with most of that size in one run's review
objects. This is a point-in-time observation, not a production sizing study.

### Product Owner Decision

Rich local debugging and review are core purposes of a working eval. Every
working unit captures its exact model request, response, tool calls, and
validation detail. Working runs are disposable and may be deleted quickly.

Frozen evidence packages are not copied into either working or retained evals.
The eval retains immutable Azure Blob identity and integrity metadata, and the
review path retrieves the evidence package from Azure when needed.

Elevation applies to a complete eval run, not individual units. It preserves
full AI outputs, expected outputs, grading outcomes, accuracy calculations,
token and cost results, and critical aggregate statistics. It prunes detailed
tool, invocation, speed, latency, and other disposable performance data and
does not use a file-per-unit retained layout.

The local review app is read-only for MVP. It lets an FDE select all evals,
working/non-elevated evals, or elevated/retained evals, but it does not elevate
or delete them. Those operations belong to the documented command and Codex
skill workflow.

Retained evals may be permanently deleted through a less frequent,
exact-target, confirmed operation. They are protected from ordinary
working-run cleanup but are not immutable and are not recoverable after
deletion.

### Why This May Be Strategically Wrong

The strategy requires fast inspection of wrong examples and the raw evidence and
model behavior that explain them. It does not necessarily require complete
forensic capture for every successful attempt.

Heavy default capture increases local storage, run overhead, privacy surface,
integrity machinery, and lifecycle pressure—the same pressure that then
justifies more artifact-management features.

### Required Alignment

- Capture complete request, response, tool, and validation detail for every
  working unit.
- Retain immutable evidence-package identity and integrity metadata and load
  evidence from Azure Blob Storage during review.
- Do not duplicate frozen evidence packages in local eval storage.
- Elevate and compact only complete eval runs.
- Keep full AI outputs and grading detail while pruning disposable tool and
  performance traces from retained evals.
- Keep the local app read-only and add all, working, and retained filters.
- Perform elevation and exact confirmed deletion through the documented
  command or Codex skill workflow.

## Review Outcome And Next Step

All five findings now have an MVP product-scope decision. The next step is to
translate the required-alignment items into a sequenced feature and migration
plan.

Revisit published core packages when multiple active projects or contract
stability justify the release and migration overhead.

Revisit portable packaging, runtime translation, feedback handoff, and Azure
publication only after the eval and improvement MVP is validated.

Do not implement directly from this review document. Use
`docs/product-strategy/mvp-scope.md` as the durable product boundary and create
an explicit feature and migration plan before changing the implementation.
