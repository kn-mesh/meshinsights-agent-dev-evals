# Agent Workbench Development Backlog

This backlog defines the capabilities MeshInsights Agent Workbench needs to
support an FDE developing and evaluating agents against published benchmarks.
It is an MVP checklist and feature inventory, not the implementation plan for
each feature. Active feature plans belong in `docs/development-current/`.

MeshInsights Benchmark Studio owns candidate intake, evidence review,
labeling, benchmark creation and publication, and production-feedback
conversion. Agent Workbench consumes published benchmark versions and their
frozen Azure evidence through read-only contracts. It must never recreate or
mutate Benchmark Studio workflow truth.

## MVP Boundary

The Agent Workbench MVP is complete when an FDE, working directly or through
Codex, can:

1. initialize a use-case repository from the standard workbench template;
2. point Codex at a repository containing the working Benchmark Studio
   evidence pipeline and port the relevant pipeline into the new project;
3. retrieve a named, published benchmark version and its frozen evidence;
4. build a first agent variant with a measurable structured output contract;
5. evaluate variants repeatedly across models and runtime configurations;
6. inspect aggregate results and drill into the exact evidence and model
   inputs and outputs for an individual example;
7. iterate on prompts, evidence, tools, pipeline design, and models; and
8. explicitly freeze a useful agent version and link its eval results to the
   exact published benchmark name and version.

The MVP does **not** include portable agent packaging, deployment into
Microsoft Foundry or another production runtime, or cloud publication of
selected eval results. Those remain important post-MVP features below.

## Status Definitions

- **Foundation present:** coherent code exists, but the complete FDE job is not
  yet supported.
- **Partial:** the feature works for the current use case but is not complete,
  use-case-neutral, or sufficiently usable for MVP.
- **Missing:** no complete implementation exists.
- **Post-MVP:** intentionally outside the MVP boundary.

## MVP Readiness Checklist

- [x] Repeatable project bootstrap from the Agent Workbench template
- [x] Codex-guided port of a working Benchmark Studio evidence pipeline
- [x] Use-case-neutral published benchmark and frozen-evidence contract
- [x] Repeatable first-agent and agent-variant development workflow
- [x] Schema-driven evaluation and scoring harness
- [x] Repeated, concurrent, resumable model and configuration evaluation
- [x] Complete quality, reliability, performance, token, and cost measurement
- [ ] Human result exploration with evidence-visualization parity
- [x] Codex-readable result exploration and per-example drill-down
- [ ] Fast compare-diagnose-change-rerun iteration loop
- [x] Explicit immutable agent-version promotion
- [x] Exact benchmark, agent, configuration, and eval-result linkage
- [x] Local version/result catalog with intentional retention and deletion

## Current MVP Implementation Priority

**Next:** Human result exploration with evidence-visualization parity.

The FDE/Codex path from project bootstrap through pipeline port, first agent,
evaluation, Codex inspection, and immutable versioning is complete for MVP.
The next gap is the interactive human experience for filtering results and
drilling into the same evidence views used during benchmark review.

Keep the human explorer focused on the existing result and review-artifact
contracts. Do not create a second evaluation or evidence representation.

## MVP Features

### Repeatable Project Bootstrap

**Status:** Complete for MVP; a strict non-secret specification, safe local/Git
template materialization, exact revision provenance, deterministic project
configuration, independent validation, and optional Git initialization are
implemented.

Create a repeatable flow for starting one repository per customer use case from
the Agent Workbench template. The bootstrap should establish a known project
layout, pin the workbench/core dependencies, and configure the project from the
published outputs of the labeling/readiness phase without copying customer
secrets into the repository.

The initialized project must retrieve or record:

- Azure environment and deployed Benchmark Studio application identity;
- project key, use-case identity, and published benchmark catalog;
- configured evaluation-label fields and the label/output schema they imply;
- evidence-recipe identity and immutable source-snapshot contract;
- read-only access used by standalone pipeline runs and eval orchestration;
- project-owned model catalog and runtime defaults; and
- durable locations for use-case context, pipeline variants, eval results, and
  promoted agent versions.

Use-case facts, domain terminology, prompts, output semantics, and
source-specific setup belong in the generated project, primarily under
`docs/use_case/`, project configuration, and `src/`. Shared template and core
code should remain use-case-neutral.

The detailed plan should decide the template/copy mechanism, dependency update
policy, environment discovery, credential bootstrap, and compatibility checks.

### Codex-Guided Pipeline Port From Benchmark Studio

**Priority:** Completed MVP feature.

**Status:** Complete for MVP through the `benchmark-pipeline-port` repository
skill, routing from `project-guide` and `pipeline-builder`, and the existing
tested Spirax reference port. The workflow assumes a clean bootstrapped target,
records the working source repository state, ports only the use-case evidence
behavior needed downstream, verifies representative evidence and visualization
semantics, and adds no port-specific runtime subsystem.

An FDE will give Codex the path to the relevant Benchmark Studio repository,
which contains a working pipeline used to build evidence packages. Codex must
be able to inspect that source and port the use-case-specific pipeline into the
new Agent Workbench project, modifying it for agent development and evaluation.

The workflow must:

- preserve traceability to the source repository, source revision, pipeline,
  and evidence-recipe version used during the port;
- identify which components are use-case logic and which are reusable runtime
  mechanics;
- bring across the relevant objects, retrieval/normalization behavior,
  processors, visualizations, dependencies, and pipeline wiring;
- replace Benchmark Studio workflow access with read-only retrieval of the
  already-published benchmark and frozen evidence where appropriate;
- preserve the `unit`, `decision_timestamp`, and example discriminator
  semantics established during readiness;
- verify evidence and visualization parity on representative examples; and
- leave a runnable control pipeline that becomes the base for agent variants.

This does not require a fully automatic importer for MVP. A documented,
Codex-operated workflow with validation and clear provenance is sufficient.

### Published Benchmark And Frozen-Evidence Consumption

**Priority:** Completed MVP feature.

**Status:** Complete for MVP. Shared benchmark and runtime metadata are
use-case-neutral, use-case pipelines declare their artifact and compatibility
requirements, standalone and eval execution share fail-closed preflight, and
Azure evidence remains content-verified before use. See
`docs/development-current/published-benchmark-and-frozen-evidence-consumption.md`.

Standalone pipeline runs and eval orchestration must consume the same named,
published benchmark version and immutable evidence contract. The benchmark is
not copied into or versioned by Agent Workbench. Agent Workbench records the
benchmark name/key, Azure-owned version identity, source-state hash, and
selected example IDs.

The complete feature must:

- discover and load published benchmark versions through least-privilege,
  read-only access;
- retrieve and integrity-check the exact Azure evidence artifacts frozen for
  each example;
- reject incompatible benchmark, evidence, label-schema, or pipeline
  contracts before expensive execution;
- keep example identity stable across standalone runs, evals, inspection, and
  agent-version promotion; and
- support use-case-defined evidence artifacts rather than hard-coding the
  current Spirax telemetry and alarm files into shared mechanics.

### First-Agent And Variant Development Workflow

**Status:** Complete for MVP through the existing pipeline and AI processor
skills, one-example runner, eval harness, inspection tools, and immutable
candidate versions. `pipeline-builder` now provides the concise FDE/Codex
workflow, and the Spirax `v1_3` and `v2` references demonstrate the supported
workflow and agent shapes without adding another subsystem. See
`docs/development-current/first-agent-and-variant-development-workflow.md`.

An FDE and Codex need a clear progression from the ported control pipeline to a
first measurable agent and then to multiple comparable variants. Each variant
must have an explicit hypothesis and a structured output aligned with the
configured benchmark evaluation fields.

The workflow must support:

- deterministic, AI workflow, and tool-using agent variants without forcing
  every use case into an agent architecture;
- versioned pipeline configuration separate from reusable components;
- prompts, model inputs, skills, tools, evidence transforms, and structured
  schemas as inspectable project assets;
- fast execution of one benchmark example before a wider eval;
- stable output and receipt contracts required by the eval harness; and
- addition of new variants without overwriting earlier useful variants.

### Schema-Driven Evaluation And Scoring

**Status:** Complete for MVP; implemented through published-contract schema v2,
versioned evaluation profiles, deterministic graders, conditional fields,
local slices, and result schema v3.

The harness must run any supported agent variant against a selected immutable
benchmark version and assess its complete structured output contract. It must
derive evaluation fields from project/benchmark configuration rather than
assuming classifications such as the current `classification` and
`root_cause` fields.

The MVP harness must support:

- exact or normalized comparison for configured structured fields;
- configurable deterministic graders;
- field-level and complete-contract correctness;
- benchmark slices and user-selected example subsets;
- aggregate metrics plus results grouped by expected label, confidence, slice,
  model, agent version, and relevant configuration;
- missing, malformed, partial, and failed outputs as explicit measurable
  outcomes; and
- a versioned result schema that both human tooling and Codex can consume.

### Reproducible Eval Execution And Model Comparison

**Status:** Complete for MVP; deterministic content-addressed runs, incremental
attempt generations, interruption recovery, selective reruns, bounded
concurrency, schema-v3 materialization, execution telemetry availability,
optional frozen pricing estimates, and dimension-validated model/configuration
comparison are implemented.

The primary eval workflow must make it straightforward to compare selected
models and configurations without losing the exact conditions of a run.

MVP execution requirements are:

- explicit agent/pipeline, benchmark name and version, model, reasoning,
  runtime, scope, repetition count, and grader configuration;
- repeated runs to measure nondeterminism;
- safe concurrency with configurable limits;
- resumability after interruption and selective rerun of missing or failed
  work without duplicating completed attempts;
- partial-failure handling and useful progress reporting;
- deterministic run identity and collision-safe result writing;
- captured latency, stage timing, token usage, estimated/actual model cost,
  provider errors, retries, and output-contract reliability; and
- comparison across models, prompts, evidence choices, tools, and harness
  configurations without conflating those dimensions.

### Evidence-First Eval Result Inspection

**Status:** Implemented for MVP; local-only, run-scoped review capture now feeds
both bounded coding-agent inspection and a locally hosted human explorer. The
explorer provides run selection, attempt filters, expected/actual outputs,
grading, model/tool traces, raw review data, and a verified frozen-evidence view
whose use-case-specific Spirax normalization and charts preserve Benchmark
Studio semantics. Richer cross-run comparison navigation remains in the
variant-comparison feature below.

Both a human developer and Codex must be able to start from an eval run, find a
wrong or unstable example, and understand what the agent actually saw before
judging its output. Aggregate accuracy without exact input visibility is not
sufficient.

For every example and attempt, inspection must expose:

- example identity, expected labels, actual labels, correctness, confidence,
  errors, timing, token usage, and cost;
- the exact system/developer/user prompts or messages sent to the model;
- all structured data, images, files, tool inputs/results, and other evidence
  supplied to or generated for the model;
- the raw and parsed model output, validation/retry history, and final
  structured decision;
- pipeline and stage traces needed to explain how the inputs were produced;
  and
- the agent version, benchmark version, model, grader, and runtime
  configuration that produced the attempt.

Human inspection needs an interactive visual experience for filtering,
comparison, and per-example drill-down. Evidence-package visuals must match
what the FDE/SME sees in Benchmark Studio so the same evidence can be reasoned
about consistently across labeling and evaluation.

Codex inspection needs a stable, documented, queryable result/artifact format
that supports summary, filtering, comparison, and retrieval of one example's
complete input/output bundle without requiring it to parse an entire large run
into context.

Large or sensitive artifacts should be referenced by stable local or immutable
Azure identity and integrity hash rather than duplicated indiscriminately.

### Variant Comparison And Iteration Loop

**Status:** Partial; variants and evals can be run, but there is no complete
comparison and failure-analysis workflow.

The workbench must shorten the loop from result inspection to a justified agent
change. An FDE or Codex should be able to compare runs, identify regressions and
failure clusters, drill into representative examples, record a hypothesis,
change one or more agent dimensions, and rerun the appropriate scope.

The feature must support:

- comparisons at overall, field, slice, confidence, and example level;
- separation of model, prompt, evidence, tool, pipeline, grader, and runtime
  changes;
- identification of regressions, improvements, flaky examples, and systematic
  failure modes;
- direct navigation from a comparison to the full evidence/input/output view;
- small smoke scopes before full benchmark execution; and
- retention of enough experiment context to explain why a useful variant was
  promoted.

### Immutable Agent Versions And Benchmark Linkage

**Status:** Implemented for MVP; every new eval resolves an exact candidate
agent version, and useful candidates can be promoted without copying source.

An FDE must be able to explicitly promote a useful working variant into an
immutable, inspectable agent version. Promotion should be efficient and should
not require manually copying every contributing file.

An agent-version manifest should freeze or content-address:

- source revision and dirty-state policy;
- pipeline wiring and component configuration;
- use-case code, prompts, skills, tool definitions, and agent assets;
- structured input/output schemas and action-policy assumptions;
- dependency lock and relevant runtime/core versions;
- default model configuration and permitted runtime overrides;
- source-pipeline provenance and evidence-recipe identity; and
- integrity hashes for the complete resolved version.

The benchmark remains owned and stored in Azure. Every eval result must link
the exact agent version to the benchmark name/key and published version,
benchmark source-state hash, selected examples, model/runtime configuration,
grader configuration, and result-schema version.

The detailed feature plan should choose the efficient mechanism—for example, a
small content-addressed manifest over a clean Git revision plus hashes for
resolved assets—along with promotion rules, validation, and dirty-worktree
handling.

### Local Version And Result Lifecycle

**Status:** Complete for MVP through the derived schema-v3 catalog and reference
graph, uniform deletion previews, recoverable local quarantine, restore and
permanent purge, active-run/path/integrity safety, and reachability-aware CAS
cleanup. Historical standalone result JSON has been removed and is unsupported.

During active experimentation, local project data remains the primary record.
The FDE needs a catalog that can answer which agent versions and eval runs
exist, how they relate, and which are safe to delete.

The MVP must:

- list agent versions and eval runs with their benchmark/model/configuration
  identities;
- distinguish exploratory variants from explicitly promoted agent versions;
- preserve immutable manifests and results until the FDE intentionally removes
  them;
- make deletion selective and explicit;
- warn when deleting an agent version or result would break a retained
  reference; and
- avoid treating local copies as benchmark truth.

## Cross-Cutting MVP Requirements

All MVP features should be:

- operable by both an FDE at the command line and Codex through stable,
  non-interactive commands and structured outputs;
- use-case-neutral in shared code while allowing project-owned domain logic;
- reproducible from explicit versions and configuration rather than ambient
  state;
- secure by default, with read-only Benchmark Studio access and no committed
  customer secrets;
- testable at component, pipeline-contract, and end-to-end smoke levels; and
- documented through short runbooks and repository skills that point to the
  current implementation rather than duplicating it.

## Post-MVP Features

### Benchmark Studio Integration API

**Status:** Optional Consideration.

The first-class benchmark retrieval path is direct Microsoft Entra access from
Agent Workbench to Azure PostgreSQL and Blob Storage. Workbench uses a
least-privilege published-data reader, forces database transactions read-only,
uses container-scoped `Storage Blob Data Reader`, and verifies frozen artifact
size and SHA-256 before decoding evidence. This path requires no database
password, storage key, SAS URL, client secret, or Benchmark Studio application
deployment.

A dedicated Benchmark Studio integration API may be considered later if hosted
multi-consumer access, consumer-specific authorization, centralized policy, or
network isolation makes direct data-plane access unsuitable. That option would
need a versioned project-scoped read contract, Entra audience and permission
validation, caller allowlists, immutable artifact identity, and independent
Blob data-plane authorization. Do not add or maintain this API until one of
those requirements is adopted.

### Selective Cloud Publication Of Eval Results

**Status:** Post-MVP; local results remain the source for active
experimentation.

Add an explicit promotion workflow for publishing selected, useful eval runs
to durable cloud storage. Do not automatically retain every exploratory or
failed run.

The workflow should:

- preserve agent version, model/runtime/grader configuration, published
  benchmark identity, benchmark source-state hash, selected example IDs, and
  result payload integrity;
- support comparison and audit of promoted runs without treating them as
  benchmark truth;
- define retention, naming, deduplication, annotation, supersession, and
  redaction rules; and
- use a least-privilege write destination that cannot update Benchmark Studio
  PostgreSQL tables or immutable evidence objects.

The detailed plan must resolve the storage/catalog model, customer tenancy and
access control, sensitive-output policy, retention, and relationship to future
portable agent packages.

### Portable Agent Package

**Status:** Post-MVP; strategic handoff artifact with no implemented manifest.

Define a versioned, inspectable package that promotes a validated agent version
from Agent Workbench into a customer-owned pilot or production runtime. The
package is a deployment handoff contract, not a generic production runtime or
hosting platform.

At minimum, it should identify:

- package and agent-version identity;
- trigger contract, unit identity, decision-timestamp semantics, and example
  discriminator;
- evidence recipe and source/tool assumptions;
- prompt, skill, tool, and other agent assets with integrity hashes;
- model/runtime configuration and supported override boundaries;
- structured output schema aligned with configured evaluation fields;
- action policy, confidence/escalation behavior, and safety constraints;
- supporting published benchmark version and selected promoted eval results;
- known limitations and supported benchmark or operating slices; and
- production-feedback schema and routing contract for Benchmark Studio's
  feedback workflow.

The package should be portable across Microsoft Foundry and other approved
customer runtimes where practical. Runtime adapters may translate the package,
but must not become the source of truth for agent design.

The detailed plan must resolve manifest format, artifact layout, signing,
provenance, compatibility, embedded versus referenced assets, promotion gates,
approval history, rollback linkage, and update-package semantics.

### Production Runtime Adapters

**Status:** Post-MVP.

Validate translation of the portable package into Microsoft Foundry first,
followed by other approved customer runtimes as required. Adapters should map
the package's trigger, evidence, model, tool, output, action, and feedback
contracts into the target environment without requiring Agent Workbench or the
full MeshInsights runtime to become the production host.
