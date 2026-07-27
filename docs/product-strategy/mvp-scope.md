# Agent Workbench MVP Scope

## Purpose

This document records product-owner decisions about the Agent Workbench MVP.
It is a living scope and decision log, not an implementation backlog.

The MVP is focused on enabling a Mesh FDE to evaluate an agent, inspect the
results, improve the agent, and repeat. It is not intended to prove the full
Agent Launch journey or create the portable agent package.


## Strategy - at MVP scope
1. There is a `core` set of code/libraries/helpers which has zero use case specific code. These are building blocks which are not modified when creating a new project (unless there are new core features...so these are treated more as product/platform)
2. There is a standard project structure which seprates the core code from the code structure that will be modified / populated (e.g. directory of empty folders that defines the structure, configurations of selectable LLMs which evolve over time and need to be easily editable)
3. This MVP codebase has a reference use case (spirax steam trap failure classifications) which is used to test and build out functionality as well as show what this would look like for a new use case. Each use case gets it's own repo that includes the core code + template structure which is then populated with the necessary code. 


## Current MVP Boundary

### In scope

- Build and run agent variants against published benchmark truth.
- Inspect aggregate results and individual examples, including the evidence,
  model input, model output, expected output, and grading result needed to
  understand failures.
- Review high-level differences across separate eval results for useful
  variants, models, prompts, and configurations.
- Preserve enough experiment context to explain material changes in results.
- Explicitly save meaningful agent versions and their associated benchmark and
  evaluation results so progress can be demonstrated and useful states can be
  revisited.
- Support the local artifact handling necessary to keep the evaluation and
  improvement loop usable.
- Explicitly publish selected complete retained eval results to durable Azure
  storage without granting Agent Workbench permission to change Benchmark
  Studio benchmark truth.

## Out of Scope

This section makes the scope horizon explicit. A capability that is deferred
beyond the MVP is not necessarily rejected permanently. A capability excluded
from both the MVP and the near-term broader scope should not attract design or
implementation work without a new product decision.

### Deferred beyond the MVP

The following are not MVP completion criteria. Their later timing and exact
shape remain undecided:

- creating a portable agent package;
- translating or deploying an agent into Microsoft Foundry or another
  production runtime;
- proving an end-to-end Agent Launch;
- implementing a production-feedback return path; and
- automatically synchronizing, elevating, or publishing evals into cloud
  storage without an explicit FDE action.

### Excluded from the MVP and near-term broader scope

- acting as a generic agent runtime or production orchestration platform;
- recoverable deletion of local eval runs;
- application-managed quarantine and restore for deleted local artifacts;
- lifecycle transactions designed to recover interrupted deletion operations;
- distributed or multi-user local artifact coordination;
- generalized retention policies, archival tiers, storage administration, and
  content-addressed garbage collection beyond the minimum needed to protect
  explicitly retained evals and meaningful agent versions;
- retaining detailed speed or latency telemetry with meaningful eval records;
- exposing separate-process evaluation as part of the normal supported eval
  path without evidence that process isolation is needed;
- exposing an arbitrary predicate language to FDEs for benchmark selection when
  full-benchmark, explicit-unit, and named use-case sections are sufficient; and
- requiring a file-per-example storage layout for retained evals.

Existing implementations of excluded capabilities may remain under safe
maintenance, but their presence does not make them part of the supported
product scope.

## Decision 1: Local Artifact Lifecycle Versus Portable Handoff

**Status:** Decided for MVP.

### Decisions

1. The MVP is an eval and agent-improvement MVP. It is not an Agent Launch or
   portable-package MVP.
2. The portable package and a Foundry translation are not required for MVP.
   The minimum shape of a future portable package does not need to be decided
   yet.
3. A real production-feedback return path is not required for MVP.
4. Most eval runs are short-lived local working data. They exist to support
   rich debugging and review while an FDE changes and improves an agent, and
   may be deleted within minutes.
5. Some evals represent meaningful agent versions and must be explicitly
   retained for future comparison and review.
6. Deletion is permanent. Recovering a deleted run is not an MVP requirement.
7. One FDE manages the local artifacts for their project. Shared or
   multi-operator local lifecycle management is not required.
8. An FDE may explicitly publish selected complete retained eval results to
   Azure Blob Storage. The eval-results destination is logically and
   permission-wise separate from frozen benchmark evidence packages, and
   publication never changes Benchmark Studio benchmark truth.

### Two classes of eval data

#### Working evals

Working evals support immediate debugging and review. They may contain rich
detail needed to inspect individual examples, inputs, outputs, intermediate
behavior, and failures. They are disposable and should be easy to delete as the
agent evolves.

The MVP should not impose durable retention, recovery, or archival requirements
on these runs.

#### Retained evals

An FDE may explicitly retain an eval when it represents a meaningful agent
version worth comparing or reviewing later. A retained eval must preserve the
critical evidence needed to understand and reproduce the measured result,
including:

- the exact benchmark identity and published version;
- the exact meaningful agent version;
- the relevant model, prompt, runtime, grader, and evaluation configuration;
- the full AI outputs for the evaluated units;
- the expected outputs and grading outcomes needed to review correctness;
- the calculations and aggregate statistics used to report accuracy; and
- enough identity and configuration information to compare the retained eval
  with later meaningful versions.

A retained eval does not need detailed performance telemetry such as per-unit
speed or latency measurements. It also does not require one file per evaluated
example. A small number of aggregate JSON artifacts containing the unit results,
full outputs, grading details, and summaries is simpler and sufficient.

### MVP local lifecycle scope

The local lifecycle should serve this working-versus-retained distinction, not
become a general artifact-management product. The MVP needs:

- a clear way to list and inspect local eval runs;
- explicit promotion or retention of an eval associated with a meaningful
  agent version;
- visible linkage among retained evals, agent versions, benchmark versions, and
  configurations;
- simple permanent deletion of disposable runs;
- protection against casually deleting a retained eval or meaningful agent
  version as part of working-run cleanup; and
- a compact retained representation built from aggregate JSON artifacts rather
  than a file-per-unit layout.

The MVP does not need:

- quarantine or restore;
- recoverable deletion;
- lifecycle transactions designed to recover interrupted delete operations;
- distributed locking or multi-user coordination;
- generalized artifact reachability or garbage collection beyond what is
  strictly necessary to protect retained evals and agent versions;
- retention policies, archival tiers, or other storage-administration
  machinery beyond the selected retained-eval publication contract.

The current implementation already provides some capabilities beyond this
boundary. Those features need not be removed immediately, but they should be
frozen at safe maintenance rather than treated as required product behavior.

## Decision 2: Protected Evaluation Path

**Status:** Decided for MVP.

### Standard workflow

The protected eval workflow is:

1. choose the published benchmark and version;
2. choose the agent candidate and AI model configuration;
3. choose the evaluation scope;
4. run the agent with bounded threaded concurrency;
5. produce the completed eval result; and
6. review the result through Codex, the local evaluation review app, or both.

Each completed eval remains a separate result. The local app displays
high-level result, model, and configuration differences and supports drill-down
into one run at a time; Codex may review multiple independent results when
deeper analysis is useful. The MVP does not create direct-comparison artifacts,
paired-delta reports, comparison APIs, or multi-model comparison orchestration.

### Evaluation scope

An FDE must be able to run:

- the full published benchmark;
- an explicit hand-selected list of units or examples; or
- a named section defined by the use case, such as all open failures in the
  Spirax use case.

Named sections are project-owned evaluation concepts. The underlying
configuration may use simple rules to define their membership, but an arbitrary
predicate language does not need to be exposed as part of the normal FDE
workflow.

### Execution modes

- Bounded threaded execution is the normal eval path.
- Serial execution is retained as a debugging option.
- Separate-process execution is not part of the normal supported MVP path and
  should be deferred unless process isolation solves an observed failure.

### Interruption and resume

An interrupted eval is a run whose process stops before all selected units
finish—for example, because the FDE presses `Ctrl-C`, closes the terminal, the
machine or process stops, authentication expires, or an external service makes
continued execution impossible.

Completed unit results should be written durably as the eval progresses. Every
new start creates a unique eval occurrence, even when its configuration matches
another run. To resume, the FDE supplies that exact occurrence ID; the runner
verifies the resolved configuration and executes only missing units. This
avoids repeating model calls and cost. It is execution resumability, not
recoverable deletion: once the eval run is deleted, it cannot be resumed or
restored.

### Token and cost measurement

Every eval run should measure and summarize token usage and model cost. The
result should include:

- total input, output, and overall token usage;
- total estimated cost for the selected benchmark scope;
- average cost per unit;
- P5 and P95 cost per unit; and
- the number of units with complete, partial, or unavailable cost information.

Cost estimates require a pricing snapshot for the selected model, including at
least input-token and output-token rates. Vendor pricing is reusable Workbench
configuration, not use-case configuration: `models.yaml` selects models and
references billing identities, while reviewed rates live in
`model-pricing.yaml` and can be shared by multiple provider aliases. The run
must retain the resolved pricing snapshot so later price changes do not rewrite
the historical estimate.

The read-only eval-results app displays the stored overall eval cost, mean cost
per unit, P5/P95 per-unit cost, currency, and complete/partial/unavailable
pricing coverage. It does not recalculate or refresh historical costs.

## Decision 3: Eval Provenance, Elevation, And Preservation

**Status:** Decided for MVP.

### Provenance

Every working eval must record enough lightweight provenance to identify the
agent candidate that produced it:

- the Git commit;
- the relevant uncommitted patch, including relevant untracked agent files;
- hashes of the selected pipeline, prompt, schema, and configuration inputs;
- the selected benchmark and immutable evidence identities; and
- the selected model, model configuration, and pricing snapshot.

This is sufficient for ordinary evals and retained agent versions. The MVP does
not need a second content-addressed copy of the entire source tree.

### Elevation boundary

Every completed eval begins as a **working eval**. An FDE may explicitly
**elevate** it when the result represents a meaningful agent version worth
long-term comparison or review.

Elevation applies to a complete selected occurrence—zero missing planned work
items with one latest recorded attempt per planned item. The selected scope may
be all examples, named sections, or explicit units/examples; elevation never
extracts only part of that occurrence. It is one operation that:

1. marks the eval as retained;
2. retains its associated meaningful agent version;
3. verifies that the benchmark, evidence, agent, model, pricing, grading, and
   result identities are complete;
4. creates the compact retained artifacts;
5. preserves the full AI outputs, expected outputs, grading outcomes, accuracy,
   token, and cost information required for later review;
6. removes detailed speed, latency, invocation, and other disposable
   performance data from the retained representation; and
7. verifies the retained eval and linked agent artifacts;
8. permanently removes the source working eval; and
9. leaves the retained eval protected from ordinary working-run cleanup.

A retained eval and its retained agent version must not become detached. If one
is retained, the other is retained through the same elevation operation.

### Target local folder contract

The product-level target is a visible separation between working and retained
evals:

```text
.workbench/evals/
  working/
    <benchmark-key>/
      <benchmark-version>/
        <run-id>/
          manifest.json
          result.json
          agent-provenance.json
          evidence-references.json
          attempts/
          review/
          performance/
  retained/
    <benchmark-key>/
      <benchmark-version>/
        <retained-eval-id>/
          manifest.json
          result.json
          units.json
          agent-provenance.json
          evidence-references.json
          agent.patch
```

The names may be refined during feature planning, but the semantic boundary is
required:

- `working/` contains complete, immediately reviewable, disposable run detail;
- `retained/` contains a small number of durable aggregate artifacts;
- a successfully elevated occurrence exists only under `retained/`, never in
  both lifecycle roots;
- `units.json` contains per-unit expected outputs, full AI outputs, validation,
  grading outcomes, and review-critical metadata without requiring one file per
  unit;
- `agent-provenance.json` records the Git, configuration, benchmark, model, and
  pricing identities; and
- `evidence-references.json` records immutable Azure Blob evidence-package
  identities and integrity metadata without copying the evidence locally; and
- `agent.patch` preserves relevant changes not represented by the recorded Git
  commit and is omitted when the working tree is clean.

Working and retained evals load the frozen evidence package from Azure Blob
Storage when it is needed for review. Neither state creates a durable local
copy of the evidence package.

The later feature plan must reconcile this target with the current schema-v1
layout. The current folder layout is an implementation constraint, not the
product requirement.

### Required documented skill workflow

The MVP must include a repository skill that documents and guides the formal
eval lifecycle:

1. configure model identity and pricing;
2. select a benchmark scope;
3. run or resume an eval;
4. inspect the working eval through Codex or the local app;
5. elevate a meaningful eval and its agent version;
6. verify the retained artifacts and remove the source working eval as one
   elevation transaction; and
7. permanently delete non-elevated disposable working evals or, less frequently, an exact
   retained eval.

The skill must explain the folder contract, the difference between working and
retained evals, what elevation preserves and prunes, and which operations are
not recoverable. Deleting a retained eval must be an intentional, exact-target,
confirmed operation distinct from ordinary working-run cleanup. Feature
planning will decide whether this extends the existing eval-running skill or
becomes a narrower dedicated lifecycle skill.

### Evaluation review app

The local evaluation review app must make preservation state visible. At a
minimum, the FDE can view:

- all evals;
- working, non-elevated evals; or
- elevated, retained evals.

Each eval shows its preservation state, and elevation is represented as an
explicit state rather than inferred from age, accuracy, or filesystem location.
The app is read-only for MVP: it does not elevate, delete, or otherwise mutate
evals. Elevation and deletion are performed through the documented command or
Codex skill workflow. The app must continue to support detailed working-run
review and compact retained-run review.

An FDE may explicitly publish a complete local retained eval to Azure Blob
Storage. Publication does not replace elevation, automatically synchronize
local retained evals, or change the working-versus-retained lifecycle and
artifact meaning.

## Decision 4: Reusable Core Versus Reference Use Case

**Status:** Decided and physically implemented for MVP.

### Repository role

This repository is a working Agent Workbench development repository containing:

- the reusable core libraries and use-case-neutral Workbench capabilities; and
- one complete Spirax reference use case proving that the system works.

It is an internal Mesh/FDE development asset. Customers do not receive or work
in this repository. Customer handoff begins later through a portable agent
package, which is outside the MVP.

Each use case has its own Git repository, not a branch within a shared use-case
repository. A new repository starts from the Agent Workbench template, including
the reusable libraries and source, standard directory structure, and root-level
agent skills. The FDE removes the Spirax reference content and populates the
same replaceable use-case area with the new project.

### MVP dependency approach

During rapid MVP iteration, reusable libraries may remain editable local source
in the same repository. This allows an FDE and coding agent to change a use case
and a necessary core contract together and verify the complete working system
without first publishing and upgrading packages.

Pinned external package dependencies are a likely later direction, but are not
required for MVP:

- **Editable local core** makes cross-layer changes fast and atomic, but copied
  project repositories can diverge and shared fixes require deliberate
  upstreaming.
- **Pinned published packages** give projects a stable, explicit upgrade
  boundary and reduce accidental framework forks, but every shared change
  requires package release, version selection, and migration discipline.

The project should not adopt the second model until the reusable contracts are
stable enough that its release overhead costs less than continued co-development.

### Required replaceable boundary

Reusable ownership must be clear, but it does not require one physical `core/`
directory. In particular, `packages/mi-core/` is an actual forked library with its own
pipeline-runtime purpose. Other reusable Workbench code must not be moved into
or conflated with `mi-core`.

The target logical layout is:

```text
.agents/skills/
  root-level generic and use-case development skills

packages/
  mi-core/       forked reusable pipeline and AI runtime library
  eval-core/     reusable evaluation library
  eval-ui/       reusable review application library and UI shell

workbench/
  reusable orchestration, bootstrap, versioning, model, lifecycle, publication,
  storage, and shared operator mechanics

use_case/
  project identity and Benchmark Studio connection
  durable use-case documentation
  objects, retrievers, evidence adapters, hydrators, processors, and actions
  pipeline, evaluation, and agent-version configurations
  use-case-specific review UI schema and adapters

apps/
  fixed application composition roots that connect workbench and use_case

tests/
  architecture/  cross-boundary, ownership, bootstrap, and skill contracts
  workbench/     use-case-neutral reusable Workbench behavior

.workbench/
  ignored generated eval and promoted-agent-version artifacts
```

Agent skills remain under the root-level `.agents/skills/` convention. Generic
skills ship with every template. Any Spirax-specific skills are removed or
rewritten from that root directory when creating the new use case; they are not
buried inside the use-case folder.

The fixed replaceable root is `use_case/`. Reference documentation,
configurations, pipeline components, evidence adapters, explorer UI, and
behavior tests live beneath it. Bootstrap clears exactly that directory and
immediately creates the neutral standard skeleton; reusable product and project
configuration remain in place.

Repository-level environment bootstrap, dependency management, eval lifecycle
commands, generic skills, and local result folders may remain outside the
replaceable use-case area when they are shared by every project.

### Coding-agent authority

For MVP, coding agents may inspect all reusable code but must obtain explicit
user approval before modifying reusable core behavior. This applies to
`mi-core`, reusable evaluation mechanics, the reusable review UI, and any other
code designated as use-case-neutral.

The agent must:

1. explain why the requested outcome cannot be completed correctly in the
   use-case layer;
2. identify the exact reusable paths or contracts it proposes to change;
3. ask the user for approval before editing them; and
4. keep use-case-specific behavior out of the reusable layer.

This approval boundary preserves rapid core iteration without silently turning
each use-case project into a framework fork. The relevant repository skills and
agent guidance must be updated during feature implementation to enforce it.

When an approved shared fix is discovered within a use-case repository, the
coding agent may implement and test it locally. The work must identify the
change as reusable and record that the same fix needs to be upstreamed into the
canonical template or reusable library source before the project is considered
complete. Automatic package release or cross-repository synchronization is not
required for MVP.

### Deferred distribution decision

The long-term split into independently versioned repositories or published
packages remains open. Revisit it when at least one of these occurs:

- multiple active use-case repositories need the same core upgrades;
- core changes become less frequent and contracts stabilize;
- copying fixes among projects creates material rework; or
- a non-FDE consumer needs a supported upgrade path.

## Deferred Decisions

All strategic deviations reviewed for the MVP now have a product-scope
decision. The following implementation or longer-horizon decisions remain
deferred:

- the eventual split into independently versioned repositories or published
  packages;
- automatic upgrade propagation among use-case repositories;
- portable agent packaging and production-runtime translation.
