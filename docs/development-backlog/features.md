# Agent Workbench Development Backlog

## MVP Features

### Selective Cloud Publication Of Eval Results

**Status:** local results remain the source for active
experimentation.

Add an explicit promotion workflow for publishing selected, useful eval runs
to durable cloud storage. Do not automatically retain every exploratory or
failed run.

The workflow should:

- preserve agent version, model/runtime/grader configuration, published
  benchmark identity, benchmark source-state hash, selected example IDs, and result payload integrity;
- support comparison and audit of promoted runs without treating them as
  benchmark truth;
- define retention, naming, deduplication, annotation, supersession, and
  redaction rules; and
- use a least-privilege write destination that cannot update Benchmark Studio



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


### Production Runtime Adapters

**Status:** Post-MVP.

Validate translation of the portable package into Microsoft Foundry first,
followed by other approved customer runtimes as required. Adapters should map
the package's trigger, evidence, model, tool, output, action, and feedback
contracts into the target environment without requiring Agent Workbench or the
full MeshInsights runtime to become the production host.


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

