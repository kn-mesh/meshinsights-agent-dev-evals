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

- [ ] Repeatable project bootstrap from the Agent Workbench template
- [ ] Codex-guided port of a working Benchmark Studio evidence pipeline
- [ ] Use-case-neutral published benchmark and frozen-evidence contract
- [ ] Repeatable first-agent and agent-variant development workflow
- [ ] Schema-driven evaluation and scoring harness
- [ ] Repeated, concurrent, resumable model and configuration evaluation
- [ ] Complete quality, reliability, performance, token, and cost measurement
- [ ] Human result exploration with evidence-visualization parity
- [ ] Codex-readable result exploration and per-example drill-down
- [ ] Fast compare-diagnose-change-rerun iteration loop
- [ ] Explicit immutable agent-version promotion
- [ ] Exact benchmark, agent, configuration, and eval-result linkage
- [ ] Local version/result catalog with intentional retention and deletion

## MVP Features

### Repeatable Project Bootstrap

**Status:** Missing; define before the next use-case project is initialized.

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

**Status:** Missing as a repeatable workflow; a working Spirax pipeline is
already present in this repository.

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

**Status:** Foundation present for the current Spirax contracts; generalization
and initialization integration remain.

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

**Status:** Foundation present through the current YAML pipelines, structured
outputs, workflows, agent processors, tools, and skills; the workflow is not
yet a use-case-neutral MVP path.

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

**Status:** Partial; repeated execution and several classification metrics
exist, but scoring remains coupled to the current output fields and use case.

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

**Status:** Partial; repeated runs, scoped execution, concurrency, progress,
failure capture, timing, and local JSON output are present.

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

**Status:** Missing as an integrated experience; local structured result files
and pipeline-generated evidence images provide foundations.

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

**Status:** Missing; pipeline filenames currently identify variants but are not
complete immutable agent versions.

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

**Status:** Partial; eval results are written to structured local paths, but
there is no complete catalog or referential-integrity workflow.

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
