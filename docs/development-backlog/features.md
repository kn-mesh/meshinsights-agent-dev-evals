# Development Backlog

This backlog covers deferred capabilities for MeshInsights Agent Workbench.
The separate MeshInsights Benchmark Studio product owns candidate
intake, evidence review, labeling, benchmark creation and publication, and
production-feedback conversion. Features here may consume its published Azure
artifacts but must not recreate or mutate those workflows.

## Project Bootstrap From Published Readiness Artifacts

**Status:** Missing; define before the next use-case project is initialized.

Create a repeatable bootstrap flow that configures a new Agent Workbench project
from the outputs of the use case's labeling/readiness phase.

The flow should retrieve or record, without copying customer secrets into the
repository:

- Azure environment and deployed Benchmark Studio application identity;
- project key, use-case identity, and published benchmark catalog;
- configured evaluation-label fields and the label/output schema they imply;
- evidence-recipe identity and immutable source-snapshot contract;
- the read-only identity and access method used by standalone pipeline runs and
  eval orchestration.

The generated project configuration should be use-case-neutral. Use-case facts,
domain terminology, output semantics, and any source-specific setup belong in
`docs/use_case/` and project configuration, not in shared skills.

Initial standalone pipeline runs and the primary eval workflow should consume
the same published benchmark and evidence contracts. Access to benchmark truth
and frozen evidence must remain read-only from this repository.

Open design questions:

- Whether the handoff is an exported manifest, a read-only API contract, or a
  combination of both.
- How Azure environment discovery works for local users and unattended
  automation without distributing database or storage-owner credentials.
- Which schema/version compatibility checks block project initialization or an
  eval run.

## Selective Cloud Publication Of Eval Results

**Status:** Deferred; local JSON remains the source for active experimentation.

Add a promotion workflow that publishes selected, useful eval runs to durable
cloud storage. Do not automatically retain every exploratory or failed run.

The workflow should:

- keep normal eval output local by default;
- let an FDE explicitly select runs for publication;
- preserve pipeline version, model/runtime configuration, published benchmark
  identity, benchmark source-state hash, selected example IDs, and result
  payload integrity;
- support comparison and audit of promoted runs without treating them as
  benchmark truth;
- define retention, naming, deduplication, and redaction rules;
- use a dedicated least-privilege write destination that cannot update the
  Benchmark Studio PostgreSQL tables or immutable source-snapshot objects.

Open design questions:

- Storage service and result catalog/query model.
- Promotion criteria and whether a run can be superseded or only annotated.
- Customer tenancy, access control, sensitive model-output handling, and
  retention policy.
- Whether promoted eval results are referenced by portable agent packages or
  copied into them.

## Portable Agent Package

**Status:** TBD; strategic handoff artifact with no implemented manifest yet.

Define a versioned, inspectable package that promotes a validated agent variant
from Agent Workbench into a customer-owned pilot or production runtime.
The package is a deployment handoff contract, not a new generic production
runtime or hosting platform.

At minimum, the package should identify:

- package and agent-variant version;
- trigger contract, unit identity, decision-timestamp semantics, and any extra
  example discriminator;
- evidence recipe and source/tool assumptions;
- prompt, skill, tool, and other agent assets with integrity hashes;
- model and runtime configuration, including supported override boundaries;
- structured output schema aligned with the labeling project's configured
  evaluation fields;
- action policy, confidence/escalation behavior, and safety constraints;
- supporting published benchmark version and selected promoted eval results;
- known limitations and supported benchmark or operating slices;
- production feedback schema and routing contract for the Benchmark Studio
  product to ingest through its own feedback workflow.

The package should be portable across Microsoft Foundry and other approved
customer runtimes where practical. Runtime-specific adapters may translate the
package, but they must not become the source of truth for the agent design.

Open design questions:

- Manifest format, artifact layout, signing, provenance, and compatibility
  rules.
- Which assets are embedded versus referenced by immutable URI and hash.
- Promotion gates, approval history, rollback linkage, and update-package
  semantics.
- Minimum adapter contract for Microsoft Foundry and customer-developed
  runtimes.

## Link the frozen benchmark version to a frozen agent version
- Need to have a mechanism to version agents (similar to benchmark versioning)
- Eval results need to reference each benchmark and agent version (along with the other configs such as model). Both the benchmark and agent version will evolve over time, so we need to keep frozen copies for as long as needed (FDE will selectively delete old eval results and agent versions as the agents and benchmarks improve)

