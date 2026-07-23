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
| Critical | Local artifact lifecycle is ahead of portable handoff and feedback | Rebalance the roadmap or explicitly reaffirm the MVP boundary |
| High | Evaluation orchestration has grown into a generic local platform | Define the protected minimum eval path and criteria for advanced features |
| High | Experiment provenance and meaningful agent-version promotion are conflated | Decide the minimum provenance required for ordinary runs and the promotion boundary |
| High | One repository is acting as use-case project, template, and framework monorepo | Decide the long-term customer-project and shared-framework distribution model |
| Medium-high | Human inspection is strategically correct, but default review capture is heavy | Define the minimum default inspection payload and on-demand capture policy |

## 1. Local Artifact Lifecycle Versus Portable Handoff

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

### Why This May Be Strategically Wrong

Local lifecycle sophistication protects developer artifacts, but it does not
complete Agent Launch or establish the Agent Improvement feedback loop. The
portable package and a validated customer-runtime translation are the artifacts
that connect Workbench output to the commercial offer.

The risk is a polished readiness environment that cannot yet prove the full
readiness-to-launch-to-feedback journey.

### Questions For Product Owner

1. Is the current MVP intended only to prove the internal FDE R&D loop, or must
   it prove one end-to-end Agent Launch?
2. What customer or FDE failure justified building recoverable local lifecycle
   management before portable packaging?
3. What is the smallest acceptable portable package: manifest only, or manifest
   plus one Foundry translation?
4. Is a real production-feedback return path required before calling the
   Workbench strategically validated?

### Candidate Direction, Not Yet Approved

- Freeze local lifecycle feature development at safe maintenance.
- Generate a minimal portable manifest from one promoted agent version.
- Validate one Spirax translation into Microsoft Foundry Hosted Agents.
- Define one feedback envelope and route a representative case back toward
  Benchmark Studio review.

## 2. Evaluation Harness Becoming A Generic Platform

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

### Questions For Product Owner

1. What is the protected 80/20 eval path every FDE should understand?
2. Which runtime modes have been used in real work, and which exist for
   completeness?
3. Which resume, materialization, and failure-generation cases have prevented
   material rework or model cost?
4. Does the profile predicate language support current benchmark needs, or a
   hypothetical generic evaluator?
5. Which result fields are required to make the next agent decision, rather
   than to preserve theoretical audit completeness?

### Candidate Direction, Not Yet Approved

Define a minimal path with:

1. explicit benchmark/version/example selection;
2. serial plus one bounded-concurrency mode;
3. expected output, actual output, validity, correctness, errors, model/config,
   usage, and immutable evidence identity;
4. aggregate, field, slice, reliability, and cost summaries;
5. two-run comparison; and
6. wrong-example inspection.

Classify other capabilities as optional extensions with an evidence threshold
for continued investment.

## 3. Experiment Provenance Versus Agent-Version Promotion

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

### Why This May Be Strategically Wrong

Conflating every experiment with an immutable agent version creates an internal
source and artifact-management product. It may also make the concept of a
"version" less meaningful to an FDE or customer.

Exact reproducibility remains important. The open question is whether ordinary
runs need the same artifact machinery as promoted, package-ready agents.

### Questions For Product Owner

1. What failures must ordinary run provenance protect against: changed prompt,
   changed code, dependency drift, deleted branch, or full repository loss?
2. Is Git revision plus dirty patch/config hashes sufficient for exploratory
   runs?
3. Should "agent version" mean every content-addressed candidate, or only an
   explicit milestone selected for comparison, packaging, or deployment?
4. Should portable-package promotion become the durable version boundary?

### Candidate Direction, Not Yet Approved

- Record lightweight experiment provenance on every run.
- Make meaningful version promotion explicit.
- Perform complete asset capture and package validation at promotion time.
- Use Git and conventional artifact storage unless real reconstruction failures
  demonstrate the need for a second source store.

## 4. Use-Case Repository Versus Framework Monorepo

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

### Questions For Product Owner

1. Is this repository the Workbench product monorepo, a customer use-case repo,
   the project template, or intentionally all three?
2. Will generated customer repositories contain editable framework source or
   versioned package dependencies?
3. Who owns upstreaming reusable changes discovered during an engagement?
4. How are customer projects upgraded without copying or merging framework
   history?
5. Which parts must be inspectable to customers versus independently editable?

### Candidate Direction, Not Yet Approved

- Keep a central Workbench/framework development repository.
- Generate thin use-case repositories containing context, evidence adapters,
  pipelines, prompts, profiles, and results.
- Consume shared mechanics as pinned, upgradeable dependencies.
- Provide an explicit escape hatch and upstream contribution path for genuine
  framework changes.

## 5. Human Inspection Versus Heavy Default Review Capture

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

### Why This May Be Strategically Wrong

The strategy requires fast inspection of wrong examples and the raw evidence and
model behavior that explain them. It does not necessarily require complete
forensic capture for every successful attempt.

Heavy default capture increases local storage, run overhead, privacy surface,
integrity machinery, and lifecycle pressure—the same pressure that then
justifies more artifact-management features.

### Questions For Product Owner

1. What is the minimum information required to explain an incorrect result?
2. Which large inputs can be reconstructed from immutable evidence identity?
3. Should detailed review capture be failure-only, sampled, explicit, or
   promotion-only?
4. Which tool and validation traces have changed an agent-development decision?
5. What information must survive after local attempt detail is deleted?

### Candidate Direction, Not Yet Approved

- Retain structured request/output metadata and immutable evidence references by
  default.
- Load evidence from its frozen source when inspected.
- Capture large or detailed model artifacts on failure, explicit selection,
  sampling, or promotion.
- Optimize the explorer first for wrong-example triage and use-case evidence
  parity.

## Suggested Review Order

1. Decide whether the next strategic proof is internal MVP completion or one
   end-to-end Agent Launch.
2. Define the minimum portable package and feedback handoff implied by that
   decision.
3. Define the protected minimum eval path.
4. Decide ordinary-run versus promoted-version provenance.
5. Decide the central-framework versus thin-customer-repository model.
6. Set the default review-capture policy.

Do not begin implementation from this document until the relevant questions
have product-owner answers and explicit scope.
