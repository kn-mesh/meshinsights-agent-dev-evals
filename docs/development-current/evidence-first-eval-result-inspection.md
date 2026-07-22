# Evidence-First Eval Result Inspection

**Status:** Implemented for coding-agent MVP

**Implementation summary:** Local-only run-scoped review capture, within-run
content addressing, immutable Benchmark Studio source references, normalized
workflow and agent interaction transcripts, pipeline-stage correlation,
bounded summary/filter/example/execution commands, comparison work-item
drill-down, compact optional diagnoses, integrity verification, and explicit
review-only purge are implemented. The optional local human explorer remains a
follow-on.

**Backlog feature:** `docs/development-backlog/features.md` → Evidence-First
Eval Result Inspection

**Related active designs:**

- `docs/development-current/schema-driven-evaluation-and-scoring.md`
- `docs/development-current/reproducible-eval-execution-and-model-comparison.md`
- `docs/development-current/immutable-agent-versions-and-benchmark-linkage.md`

## Outcome

Give an FDE or coding agent a temporary, local, queryable view of exactly what
happened during an evaluation attempt, then make the large review artifacts
safe and easy to remove.

The primary workflow is:

```text
run eval
  -> capture a run-scoped local review bundle
  -> summarize and select failures, regressions, or unstable examples
  -> let a coding agent inspect only the relevant attempts and artifacts
  -> optionally retain a small diagnosis or experiment note
  -> explicitly purge most or all review artifacts for the run
```

The finished system will:

- keep Benchmark Studio and its immutable Azure evidence read-only;
- never upload prompts, model responses, traces, generated images, tool
  activity, or other eval-review artifacts to Azure;
- capture review artifacts only on the local workstation that executes the
  eval;
- organize review data under the deterministic local run directory so deleting
  one run's review bundle is a bounded operation;
- retain compact schema-v3 scores and run identity separately from disposable
  review artifacts;
- expose exact normalized model messages, multimodal inputs, tool activity,
  outputs, validation history, and pipeline-stage context when the active
  backend makes them available;
- reference immutable Benchmark Studio source artifacts by identity, size, and
  SHA-256 instead of creating another durable copy;
- de-duplicate repeated prompts and binary artifacts within one run;
- let Codex or another coding agent query summaries and individual examples
  without loading a complete large result into context;
- support an optional local human review application over the same contract;
  and
- report review capture and purge state honestly without changing scientific
  run identity or rewriting immutable attempt records.

## Fixed Product Constraints

These constraints are decisions, not open design questions.

### No Azure publication

Agent Workbench may read the already-published benchmark and its frozen source
evidence through the existing least-privilege contracts. This feature adds no
Azure write path and no cloud artifact destination.

In particular, it must not upload:

- model request or response content;
- prompts or conversation transcripts;
- pipeline receipts or traces;
- generated charts or other derived evidence;
- tool arguments or results;
- coding-agent diagnoses; or
- local review indexes.

An Azure source-artifact reference in a review manifest means “this immutable
object was read,” not “Agent Workbench stored an eval artifact in Azure.” A
reference must exclude credentials, SAS query strings, connection strings, and
other access material.

### Review artifacts are ephemeral and run scoped

Large review artifacts are expected to live only long enough for near-term
human or coding-agent diagnosis. They belong beneath the run that produced
them, not in a global cross-run artifact repository.

De-duplication is limited to one run. This keeps cleanup simple: removing one
run's `review/` directory cannot break another run and does not require global
garbage collection or reference counting.

### Cleanup is explicit

Do not silently delete a review bundle immediately after execution; the FDE or
coding agent must have a reliable opportunity to inspect it. Do not implement
a background retention service for MVP.

Provide a non-interactive purge command with preview and structured output.
The command must resolve and validate the exact run directory before deleting
anything. It may remove only the disposable review surface by default. Whole-
run deletion remains a separate, more destructive lifecycle operation.

### Compact results remain distinct from review artifacts

The durable local run store continues to own:

- the resolved run manifest;
- append-only terminal attempt generations;
- compact scoring, reliability, timing, usage, cost, and failure evidence;
- exact benchmark, agent, model, profile, grader, and runtime identities; and
- the materialized schema-v3 `result.json`.

The disposable review bundle must not become the recovery source for run
completion or scoring. Purging it must not invalidate the run manifest,
attempt hashes, `result.json`, comparison identity, or promoted agent version.

## Non-Goals

This feature does not:

- create cloud storage, cloud publication, or multi-user artifact hosting;
- copy Benchmark Studio labels or benchmark truth into a new local source of
  truth;
- retain all source telemetry locally after review;
- guarantee access to provider internals that the active backend does not
  expose;
- persist raw HTTP headers, credentials, bearer tokens, connection strings, or
  complete provider SDK objects;
- make review capture part of model-quality scoring;
- make ephemeral artifacts part of deterministic `run_id` or
  `agent_version_id`;
- replace immutable attempt records with a trace database;
- create a global content-addressed store shared across runs;
- implement automatic AI diagnosis as a grader; or
- publish the optional coding-agent diagnosis as benchmark or production
  truth.

## Current Foundations And Gaps

The repository already provides the durable identities and compact result
surface required to anchor inspection:

- `src/evals/run_store.py` stores a deterministic run manifest, immutable
  attempt generations, invocation events, and materialized `result.json`;
- `src/evals/eval_orchestration.py` records per-example labels, structured
  outputs, correctness, contract errors, failure details, stage timing, usage,
  retry observations, cost availability, and agent-version identity;
- `src/evals/comparisons.py` validates comparison dimensions and calculates
  paired aggregate deltas;
- `src/benchmarks/models.py` carries immutable source-artifact identity, size,
  and content hashes;
- the retriever verifies frozen Azure Blob content before decoding it;
- pipeline processors already construct the prompts, images, tools, and
  structured output requests that the model sees; and
- `mi.ai` has a common workflow/agent backend boundary and normalized usage
  telemetry.

The remaining gaps are:

- schema-v3 results contain final/partial structured output but not the exact
  normalized message sequence supplied to each model call;
- multimodal blocks and generated evidence have no generic review-artifact
  reference contract;
- tool calls and tool results are not retained as a chronological inspection
  transcript;
- raw text before structured parsing and output-validation attempt history are
  not consistently available;
- pipeline receipts expose timing and selected metadata but not a bounded,
  stage-oriented inspection view;
- comparison output counts improvements and regressions without listing the
  aligned example/work-item identities that produced those counts;
- a coding agent must currently parse a complete result file and then inspect
  project-specific files manually;
- no command reports whether a run's disposable review bundle is complete,
  partial, absent, or already purged; and
- there is no safe, run-scoped review purge workflow.

## Core Separation: Durable Evidence And Disposable Review

The design has two local storage classes.

| Storage class | Purpose | Lifecycle |
|---|---|---|
| Durable run evidence | Resume, scoring, comparison, identity, and compact audit | Retained until the run itself is intentionally deleted |
| Disposable review bundle | Exact model-visible inputs and detailed diagnostic artifacts | Retained for review, then explicitly purged |

An immutable attempt record must not directly depend on a disposable file for
its own integrity. Review manifests correlate to attempts through `run_id`,
`work_item_id`, and `execution_id`, but their content hashes are not embedded
into the hashed attempt payload.

This separation avoids two bad outcomes:

1. purging a large image must not corrupt or require rewriting an immutable
   attempt record; and
2. retaining a compact result must not force retention of every prompt, trace,
   or generated chart.

Review availability is operational state. Inspection commands determine it by
reading the run's `review/` directory; deterministic `result.json` does not
gain a mutable `review_available` field.

## Local Storage Layout

Extend the existing run directory with a disposable `review/` subtree:

```text
eval_results/
  <pipeline-id>/
    <benchmark-key>/
      v<benchmark-version>/
        runs/
          <run-id>/
            manifest.json
            candidate-agent.json
            invocations/
            attempts/
            result.json
            review/
              capture.json
              index.json
              executions/
                <work-item-prefix>/
                  <execution-id>.json
              objects/
                sha256/
                  <hash-prefix>/
                    <content-hash>
            diagnosis/
              <diagnosis-id>.json
              <diagnosis-id>.md
```

`review/` is disposable as a unit. `diagnosis/` is optional, compact, and
retained when the user wants to preserve the coding agent's conclusions after
purging raw review artifacts. Whole-run deletion removes both.

### `capture.json`

`capture.json` records operational capture configuration and status, not
scientific run identity:

- review schema version;
- run ID and run-spec hash;
- capture mode;
- local-only storage policy;
- redaction-policy ID/version;
- object compression policy;
- inline-size threshold;
- capture start/completion timestamps;
- counts and byte totals by artifact kind;
- complete, partial, failed, or purged status; and
- explicit missing-capability reasons.

It must state `publication: local_only` and contain no upload destination.

### Execution review manifests

Write one manifest per actual `execution_id`. It contains:

- run, work-item, execution, example, repetition, and invocation identities;
- benchmark, source-snapshot, pipeline, model, and agent-version correlations;
- an ordered model-interaction transcript;
- pipeline-stage observations;
- typed references to local review objects or immutable external source
  artifacts;
- capture completeness and redaction observations; and
- a canonical manifest hash.

Execution manifests are append-only while present. A failed capture must still
write a small manifest with `capture_status: partial|failed` and a reason when
it is safe to do so.

### `index.json`

`index.json` is a replaceable, compact projection over execution review
manifests plus durable attempt results. It supports fast filtering by:

- example, work item, execution generation, and repetition;
- correct, incorrect, unscored, invalid, failed, or cancelled outcome;
- expected/actual field values and confidence;
- benchmark slice;
- failure type;
- model and agent version;
- duration, token, retry, and cost observations;
- stable versus flaky repeated outputs; and
- improved, regressed, or changed outcomes in a selected comparison.

The index contains references and small scalar fields only. It must not inline
large prompts, transcripts, images, telemetry, or tool results.

### Run-scoped content-addressed objects

Store only locally generated or otherwise non-durable review content under
`review/objects/sha256/`. Address the logical uncompressed bytes by SHA-256.
The reference records:

- content SHA-256;
- media type;
- logical byte length;
- stored byte length;
- optional compression encoding;
- artifact kind;
- producer stage or model interaction; and
- redaction status.

Use create-if-absent writes and validate an existing object's digest. Repeated
system prompts, tool schemas, and identical images within the same run resolve
to one local object.

Do not use a repository-global object directory. Cross-run duplication is an
accepted tradeoff for bounded deletion and short artifact lifetime.

### Immutable external source references

When the content already exists as frozen Benchmark Studio evidence, record a
reference rather than a durable local copy:

```json
{
  "storage": "benchmark_source",
  "artifact_kind": "telemetry",
  "source_snapshot_id": "...",
  "container": "...",
  "object_key": "...",
  "content_sha256": "...",
  "size_bytes": 123456,
  "media_type": "application/parquet"
}
```

The reference must be reconstructable through the existing authenticated,
read-only repository/storage configuration. It must not persist a SAS token or
connection string. Inspection may download the object into a process-scoped
temporary directory, verify its size and SHA-256, render or summarize it, and
remove the temporary copy when the command exits.

If the exact bytes sent to the model are a generated transformation rather
than the frozen source object, retain those generated bytes in the run-scoped
local object store. A derivation recipe alone is insufficient when exact
model-visible bytes are required for diagnosis.

## Review Artifact Contract

Use typed artifact references rather than arbitrary paths. Required reference
kinds are:

- `local_object` for bytes under the run's review object store;
- `benchmark_source` for immutable read-only source evidence;
- `inline` for bounded JSON scalars or very small structured payloads; and
- `unavailable` when the backend or stage did not expose the information.

Every unavailable artifact must include a stable reason. Do not substitute a
configured limit, reconstructed approximation, or newly regenerated image for
an observation that was not captured.

Paths supplied by a manifest are resolved relative to the validated run
directory. Reject absolute paths, `..` traversal, symlink escape, digest
mismatch, and files outside the run's review subtree.

## Model Interaction Capture

Capture at the shared `mi.ai` backend boundary so workflows and tool-using
agents produce one use-case-neutral transcript contract. Do not add bespoke
prompt-dumping code to each Spirax processor.

For each model interaction, retain when available:

- chronological interaction and turn index;
- provider/model/deployment identity and effective reasoning configuration;
- normalized system, developer, user, assistant, and tool messages;
- text blocks and references to image/file/binary blocks;
- tool definitions or capability manifests made available to the model;
- tool call name, stable call ID, validated arguments, result content, and
  error state;
- raw model text before structured parsing;
- parsed structured output;
- output-validation failures and retry sequence;
- provider response/request correlation IDs that contain no credentials;
- finish/stop reason when exposed;
- usage and retry observations already supported by execution telemetry; and
- backend capability gaps.

“Exact” means exact normalized semantic content used by `mi.ai`, plus exact
bytes for referenced multimodal blocks. It does not mean serializing opaque
provider SDK objects, HTTP authorization headers, transport buffers, or hidden
provider chain-of-thought.

The capture hook must be observational:

- it cannot change prompts, message ordering, tool availability, model
  configuration, validation behavior, or returned output;
- object hashing and disk persistence occur outside measured model and
  pipeline-stage durations where practical;
- capture overhead is measured separately as operational telemetry; and
- a review-storage failure cannot turn a successful agent attempt into an
  inaccurate result. It produces partial review status and an operator warning.

## Pipeline And Evidence Capture

Provide a small generic pipeline inspection hook for stage boundaries. Each
stage may expose a bounded, serializable review view containing:

- stage name, component identity, status, and correlation IDs;
- input/output schema identity;
- relevant compact structured inputs or outputs;
- references to generated images and files;
- source-artifact identities and integrity observations;
- stage failure details; and
- links to model interactions produced during that stage.

The hook is not a request to serialize entire arbitrary Python process objects.
Use explicit adapters/providers for review-bearing components. Project-owned
adapters may present Spirax telemetry windows, alarms, and chart semantics;
generic storage, identity, and safety mechanics remain use-case-neutral.

Evidence-package visual parity requires that inspection show the same derived
image bytes that were sent to the model whenever those bytes were captured. If
the human view also offers an interactive re-render, label it as a derived view
and retain the exact captured image separately.

## Capture Modes And Failure Semantics

Support two MVP modes:

- `full`: capture the complete supported local review surface; and
- `off`: retain only the existing durable compact run evidence.

The primary eval workflow defaults to `full` because near-term coding-agent
review is the normal use case. An explicit flag or project setting can disable
capture for storage-constrained runs. Dry-run, status, comparison-only, and
materialize-only invocations do not create review artifacts.

Capture mode is invocation metadata rather than a scientific run dimension.
Resuming an existing run may therefore execute missing work with capture on or
off. Inspection must report coverage by execution generation and never imply
that uncaptured historical work can be reconstructed exactly.

Capture outcomes are:

- `complete`: every artifact required by the supported contract was captured;
- `partial`: the attempt is inspectable but one or more artifacts are
  unavailable, redacted, oversized, or failed to persist;
- `failed`: no useful detailed review manifest could be produced; and
- `purged`: a tombstone or purge event records that review content was
  intentionally removed.

Disk-space or configured-size limits must be checked before and during capture.
Never silently omit an artifact. Mark the affected execution partial with its
reason and continue durable eval execution when safe.

## Coding-Agent Inspection Workflow

The coding agent should use progressive disclosure rather than ingesting an
entire run.

### 1. Summarize

Return a bounded JSON summary containing:

- run identity and configuration;
- aggregate quality, reliability, performance, usage, and cost;
- review capture status and size;
- counts of incorrect, invalid, failed, flaky, and unreviewed attempts; and
- available filters and comparisons.

### 2. Select

List compact example/work-item rows for a filter such as:

- complete-evaluation incorrect;
- one field incorrect;
- output-contract invalid;
- provider or pipeline failure;
- highest latency or token use;
- repeated outputs disagree;
- comparison regression or improvement; or
- benchmark slice membership.

Rows include identity, labels, outputs, correctness, confidence, failure type,
and artifact availability, but no large content.

### 3. Drill down

Retrieve one execution manifest with resolved text and optionally materialize
selected binary artifacts into a validated temporary/output directory. The
coding agent can request only messages, tools, output history, pipeline stages,
or evidence references when the complete manifest would be too large.

### 4. Record diagnosis

Optionally write a compact diagnosis document containing:

- reviewed run/comparison and execution identities;
- selected representative examples;
- observed failure clusters;
- evidence-based hypothesis;
- recommended prompt, evidence, tool, pipeline, model, or grader change;
- proposed smoke scope; and
- author/model identity and timestamp as metadata.

A diagnosis is local experiment context, not a score, benchmark label, or
agent-version mutation.

### 5. Purge

Preview and explicitly remove the run's disposable review bundle. The coding
agent or FDE can retain the compact diagnosis and durable result, or separately
request whole-run deletion through the later lifecycle feature.

## CLI Contract

Expose stable, non-interactive commands with `--json` output. Exact command
packaging may follow the existing eval entry point, but the capabilities are:

```text
eval inspect summary   --run <run-id> --json
eval inspect list      --run <run-id> --filter <predicate> --json
eval inspect example   --run <run-id> --example <id> [--repetition N] --json
eval inspect execution --run <run-id> --execution <id> [--section ...] --json
eval inspect verify    --run <run-id> --json
eval inspect size      --run <run-id> --json
eval inspect purge     --run <run-id> --review-only --dry-run --json
eval inspect purge     --run <run-id> --review-only --yes --json
```

Requirements:

- `--run` resolves to exactly one run beneath `eval_results/`;
- ambiguous or missing IDs fail without mutation;
- all list commands support deterministic ordering and explicit limits;
- JSON output is bounded unless the caller explicitly requests one detailed
  execution;
- binary artifacts are never printed into terminal JSON as base64 by default;
- materialization writes only beneath an explicit validated destination;
- purge dry-run reports exact paths, file counts, and bytes;
- purge requires explicit confirmation in non-interactive mode;
- purge refuses a broad root, symlink escape, or path that does not validate as
  the requested run's `review/` directory; and
- purge reports whether a compact diagnosis and durable result remain.

Update `.agents/skills/eval-results-analysis/SKILL.md` after implementation so
coding agents use these commands instead of reading large result and artifact
files directly.

## Comparison Integration

Extend the comparison result with bounded identity lists, not duplicated
artifact content. For each baseline/candidate pair, include:

- improved work-item identities;
- regressed work-item identities;
- changed but jointly incorrect work-item identities;
- newly failed/recovered work-item identities; and
- repeated-output disagreement identities.

Each item links the baseline and candidate `execution_id` values. Inspection
commands can then resolve both run-scoped review manifests and present a paired
drill-down.

Large identity sets may use a separately referenced compact comparison index,
but must remain local and must not copy binary review artifacts between runs.

## Optional Local Human Review Application

After the coding-agent CLI and contract are stable, add a local, read-only
review application over the same inspection APIs. It may provide:

- run and comparison selection;
- filters by correctness, field, label, confidence, slice, failure, model,
  agent version, latency, tokens, and cost;
- sortable example and attempt tables;
- baseline/candidate regression views;
- exact prompt/message and tool transcript panels;
- model output and validation-history panels;
- chart/image/file viewers; and
- side-by-side Benchmark Studio evidence-parity views.

The application must not create a second result schema or persistence layer.
It runs locally, reads one workstation's run directories, and performs no
artifact upload. It must tolerate already-purged review bundles by showing
compact results with explicit artifact-unavailable states.

## Purge And Retention Semantics

### Review-only purge

The default purge operation removes only:

- `review/executions/`;
- `review/objects/`;
- the materialized review `index.json`; and
- other files declared disposable by the review schema.

It writes a small run-local purge event outside the deleted tree or retains a
minimal `review/capture.json` tombstone containing:

- run ID;
- prior review schema version;
- purge timestamp;
- purged file/object counts and bytes;
- command/invocation identity; and
- `status: purged`.

The tombstone contains no artifact content and is not part of run identity.

### Diagnosis retention

`diagnosis/` is not removed by review-only purge unless explicitly requested.
This allows the costly raw inputs to be deleted while retaining a small record
of why a subsequent agent variant was attempted.

### Whole-run deletion

Deleting `manifest.json`, attempt generations, `result.json`, candidate-agent
linkage, diagnoses, and review content is outside this feature's default purge
path. It belongs to Local Version And Result Lifecycle, which must check
references from comparisons, promoted versions, and retained diagnoses.

## Redaction And Safety

Review capture is local but still sensitive. Apply an explicit redaction policy
before persistence:

- remove credentials, authorization headers, connection strings, SAS query
  parameters, and secret environment values;
- preserve model-visible customer evidence unless project policy explicitly
  forbids local capture, because removing it would make review misleading;
- record redaction occurrences without storing the removed value;
- bound arbitrary exception representations and stack traces;
- validate media types and byte sizes;
- never execute or render active file content merely to index it; and
- treat tool results as untrusted data.

If required model-visible content matches a forbidden-secret rule, mark capture
partial and explain that exact review is unavailable. Do not persist the secret
for the sake of completeness.

## Code Ownership And Expected Changes

### `mi-core/core/src/mi/ai/`

Own reusable, provider-neutral capture hooks and normalized model-interaction
events:

- message and content-block serialization;
- model request/response correlation;
- tool-call and tool-result chronology;
- raw-text and structured-output observations;
- output-validation attempt observations;
- provider capability availability; and
- secret-safe correlation metadata.

The backend emits observations to an injected sink. It does not choose the
run-directory layout or write project eval files directly.

### `mi-core/core/src/mi/core/`

Own an optional generic pipeline stage-inspection hook and bounded review-view
provider contract. Normal pipeline execution remains independent of whether a
sink is present.

### `agent-dev-eval-core/evaluation/`

Own use-case-neutral review contracts and local storage mechanics where they
are reusable:

- typed artifact references;
- canonical review-manifest serialization and hashing;
- safe run-scoped content-addressed object writes;
- compression metadata;
- redaction interfaces;
- bounded index models; and
- capture completeness states.

Do not put Benchmark Studio or Spirax knowledge in this package.

### `src/evals/`

Own orchestration and operator behavior:

- create and inject one run-scoped review sink per execution;
- correlate capture events with run/work/execution/example identity;
- join durable attempts to review manifests;
- materialize the review index;
- implement summary, filtering, drill-down, verification, size, and purge
  commands;
- extend comparison output with aligned work-item identity lists; and
- optionally record compact coding-agent diagnoses.

### Use-case components

Spirax retrievers, processors, and hydrators may expose named review views for
domain-specific evidence and visuals. They must use generic artifact/reference
contracts and must not implement their own storage directories or Azure writes.

### Documentation and skills

Update:

- `EvalRunbook.md` with capture, inspection, diagnosis, and purge commands;
- `README.md` with the disposable review layout and local-only boundary;
- `.agents/skills/eval-results-analysis/SKILL.md` to use progressive inspection;
  and
- `docs/development-backlog/features.md` only when implementation status
  materially changes.

## Implementation Sequence

### Phase 1: Freeze contracts and golden fixtures

1. Define review schema version 1, typed artifact references, capture states,
   execution manifest, index row, purge event, and diagnosis contracts.
2. Create small golden fixtures for a workflow attempt, a tool-using agent
   attempt, a partial capture, and a purged run.
3. Prove that review presence or absence does not change `run_id`, attempt
   record hashes, scoring, or `result.json` semantics.
4. Define the redaction policy and safe path-resolution rules.

### Phase 2: Run-scoped local review store

1. Implement create-if-absent object writes, hash verification, optional
   compression, and within-run de-duplication.
2. Implement append-only execution review manifests and replaceable
   `index.json` materialization.
3. Add storage-size accounting, disk-space checks, partial-capture reporting,
   and integrity verification.
4. Keep all review files beneath the exact validated run directory.

### Phase 3: `mi.ai` model interaction capture

1. Add an optional observational capture sink to workflow and agent execution.
2. Serialize normalized messages, multimodal blocks, tool definitions, tool
   calls/results, raw text, structured output, and validation attempts.
3. Emit explicit unavailable reasons for provider/backend gaps.
4. Verify that capture does not alter prompts, outputs, retry behavior, or
   measured model duration.

### Phase 4: Pipeline and orchestration integration

1. Add the bounded stage-inspection hook and connect relevant current pipeline
   stages.
2. Correlate model and stage observations with deterministic execution IDs.
3. Store exact generated model-input images locally and immutable source
   evidence as read-only references.
4. Expose full/off capture mode through the primary eval workflow.
5. Preserve successful eval attempts when review capture is partial or fails.

### Phase 5: Coding-agent query workflow

1. Implement summary, list/filter, example, execution-section, verify, and size
   commands with bounded JSON.
2. Extend comparisons with improved, regressed, changed, recovered, and failed
   work-item identities.
3. Implement paired comparison drill-down.
4. Add optional compact diagnosis recording.
5. Update the eval-results-analysis skill to use progressive disclosure.

### Phase 6: Safe purge

1. Implement exact run resolution and review-only dry-run output.
2. Implement confirmed review-only deletion with path, symlink, and identity
   validation.
3. Retain a minimal purge tombstone and optional diagnosis by default.
4. Test interrupted purge recovery and idempotent repeated purge.
5. Document the boundary between review-only purge and whole-run lifecycle
   deletion.

### Phase 7: Optional local human explorer

1. Build a local read-only application over the inspection APIs.
2. Add run, comparison, filtering, transcript, evidence, and paired regression
   views.
3. Verify Benchmark Studio visual parity for representative Spirax examples.
4. Verify useful degraded behavior after review artifacts have been purged.

## Testing Strategy

### Contract and integrity

- canonical review-manifest and reference hashing;
- exact run/work/execution correlation;
- local-object digest and byte-length verification;
- immutable source-reference validation;
- compression round trips;
- duplicate object writes; and
- schema rejection for unknown or unsafe references.

### Separation from durable run evidence

- identical scientific run and attempt identity with capture full versus off;
- identical scoring and comparison metrics with review present or absent;
- review purge leaves manifest, attempts, result, and candidate agent valid;
- stale or missing review index can be rebuilt from remaining review manifests;
  and
- purged content is never required for resume or materialization.

### AI and tool capture

- workflow messages and multimodal blocks in chronological order;
- tool-using agent calls and results with stable call correlation;
- raw text, parsed output, and validation retries;
- provider capability gaps reported as unavailable;
- capture sink failure does not change agent output; and
- no credentials or authorization metadata persist.

### Evidence and pipeline capture

- frozen Azure evidence is referenced without a local durable duplicate;
- generated chart bytes are stored and hash-verified;
- stage/component correlations are correct;
- failed stages retain available partial observations; and
- interactive re-renders are distinguished from exact captured model inputs.

### Queries and comparisons

- bounded summaries and deterministic pagination/order;
- filters for incorrect, invalid, failed, flaky, slice, field, confidence,
  latency, tokens, and cost;
- per-execution section selection avoids loading unrelated artifacts;
- comparison identity lists match aggregate improved/regressed counts; and
- paired baseline/candidate drill-down resolves the correct generations.

### Purge safety

- dry-run reports exact file and byte counts;
- confirmation is required for mutation;
- ambiguous/missing run IDs fail closed;
- absolute, parent-traversal, symlink-escape, root, and wrong-run targets are
  rejected;
- purge is idempotent;
- a purge interruption can be completed safely;
- diagnosis retention is honored; and
- no Azure API write is invoked in capture, inspection, or purge tests.

### End-to-end

Run representative v1_3 workflow and v2 tool-using agent smoke evaluations and
prove:

1. compact schema-v3 results remain correct;
2. the review index finds an incorrect or failed example;
3. the exact supported messages, image bytes, tool activity, and output history
   can be inspected;
4. a comparison links a regression to both executions;
5. a compact diagnosis can be retained; and
6. review-only purge removes the large artifacts without breaking run
   verification or comparison.

## Acceptance Criteria

The MVP coding-agent inspection slice is complete when:

- [x] Review capture writes only beneath the local run directory and performs
      no Azure writes.
- [x] Existing frozen Azure evidence is represented by safe immutable
      references rather than another durable local copy.
- [x] Generated model-input images and other non-durable exact inputs are
      stored in a run-scoped, content-addressed local object store.
- [x] Repeated content is de-duplicated within a run.
- [x] Each captured execution has a typed, hash-verified review manifest linked
      to its durable execution ID.
- [x] Workflow and agent attempts expose normalized messages, multimodal
      inputs, tool activity, raw/parsed output, and validation history when
      available.
- [x] Missing observations are explicit; the system never invents or silently
      reconstructs them.
- [x] Coding agents can summarize, filter, and retrieve one attempt without
      parsing the complete result or loading unrelated binaries.
- [x] Comparisons list the example/work-item identities behind improvements,
      regressions, failures, and recoveries.
- [x] Review capture can be disabled without changing scientific run identity
      or result semantics.
- [x] Review-only purge previews and then safely removes one exact run's large
      disposable artifacts.
- [x] Purge leaves compact results, immutable attempts, agent/benchmark
      linkage, and an optional diagnosis valid.
- [x] Capture, inspection, and purge persist no credentials or signed Azure
      access URLs.
- [x] The runbook and eval-results-analysis skill document the complete
      run-review-diagnose-purge workflow.

The optional human-inspection slice is complete when a local read-only app can
filter runs and comparisons, drill into the same execution manifests, display
exact captured evidence, and degrade honestly after purge without creating a
second persistence contract.

## Risks And Mitigations

### Full capture can still consume substantial local disk

Use within-run content addressing, optional compression, size accounting, disk
preflight, bounded source references, and an explicit review-only purge
command. Report partial capture instead of silently dropping content.

### Disposable references can be mistaken for durable audit evidence

Keep review files outside immutable attempts, label the capture policy and
status explicitly, and make compact durable results sufficient for scoring,
resume, comparison, and version linkage.

### Backend abstractions may not expose every interaction

Capture at the common `mi.ai` boundary, add capability states, and report
unavailable observations. Never claim exact provider internals that were not
exposed.

### Capture instrumentation can perturb performance

Keep hooks observational, defer persistence outside measured model calls where
possible, separately measure capture overhead, and test full versus off
behavior.

### Tool results and traces can contain secrets

Apply redaction before persistence, exclude transport headers and credentials,
bound exceptions, and mark required redacted content partial.

### Purge can delete the wrong data

Resolve one deterministic run, constrain deletion to its validated `review/`
subtree, reject symlink/path escapes and broad roots, preview exact effects,
and require explicit confirmation.

### A coding agent can overload its context with a full bundle

Make summary, selection, and section-scoped drill-down the primary interface.
Do not emit binary base64 or every transcript in list commands.

### Azure source evidence may later be unavailable

That is an accepted consequence of the local-only, short-lived review policy.
During the active review window, resolve and integrity-check the immutable
source reference on demand. Do not create a new durable cloud or local archive
to mask source-retention policy.

## Decisions To Revisit After MVP

- Whether project policy should default capture to `full` or require an
  explicit flag once storage usage is measured across several use cases.
- Whether compact diagnoses should be a first-class input to agent promotion
  or remain informal local experiment notes.
- Whether the local human explorer is required for MVP completion or can follow
  the coding-agent inspection slice.
- Whether automatic age/size-based cleanup is useful after explicit purge has
  proven safe; no background cleanup is included initially.
- Whether review bundles need an optional export format for user-controlled
  offline transfer. Such export must remain explicit and must not imply Azure
  publication.
