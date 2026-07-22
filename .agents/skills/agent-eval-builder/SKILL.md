---
name: agent-eval-builder
description: Build or update MeshInsights Agent Workbench published-benchmark evaluation orchestration for AI-enabled pipelines in this repo. Use when changing Benchmark Studio published contracts, immutable Azure evidence, evaluation profiles, deterministic graders, slices, repeated-run execution, tracked eval schema v1, disposable performance schema v1, scoring, or evaluation-results apps. Do not use merely to prepare, execute, or troubleshoot an existing eval command; use run-use-case-evals for that.
---

# Agent Eval Builder

Use this skill for Agent Workbench evaluation work tied to immutable published
benchmarks and pipeline receipts.

## Sources Of Truth

- Benchmark Studio owns published benchmark membership, complete approved label
  payloads, and frozen label-schema identity.
- Agent Workbench consumes that truth read-only. It owns versioned evaluation
  profiles that map agent output fields to selected benchmark labels, choose
  deterministic graders, define applicability, and define local slices.
- Benchmark labels and agent outputs need not match one-to-one. Preserve full
  benchmark labels for inspection; grade only profile-selected targets.
- Evidence views are derived from immutable raw artifacts. They are not label
  or benchmark truth.

Never introduce local benchmark JSON, local label truth, or a write path into
Benchmark Studio data.

## Current Contracts

- `src/benchmarks/models.py` defines published benchmark, full label payload,
  frozen label schema, example, and source-artifact models.
- `src/benchmarks/postgres_repository.py` loads published-contract schema
  version 2 directly from Azure PostgreSQL with Entra authentication.
- `evaluation_configs/*.eval.yaml` contains project-owned evaluation profiles.
- `src/evals/evaluation_profile.py` validates profiles, predicates, preflight,
  and local slice membership.
- `src/evals/scoring.py` validates configured output contracts and runs
  deterministic graders.
- `src/evals/eval_orchestration.py` owns repeated execution, generic filtering,
  aggregation, tracked eval schema version 1, and disposable performance schema
  version 1.
- `src/evals/run_specs.py` and `src/evals/run_store.py` own deterministic run
  identity, source manifests, immutable attempt generations, local locking,
  resume/rerun selection, and materialization.
- `src/agent_versions/` and `agent_version_configs/*.agent.yaml` own exact
  candidate resolution, Git/dirty overlays, model override policy, local CAS,
  promotion, verification, and the immutable agent reference used by evals.
- `src/evals/comparisons.py` preflights every comparison child into an immutable
  manifest, validates declared varying dimensions, and reports paired logical-
  work-item deltas across deterministic schema-v1 runs.
- `src/evals/inspection.py`, `src/evals/inspection_cli.py`, and
  `agent-dev-eval-core/evaluation/review.py` own local-only, run-scoped,
  disposable model/evidence review, bounded coding-agent queries, optional
  compact diagnoses, integrity verification, and explicit review-only purge.
- `src/lifecycle/` owns the derived local catalog, reference graph, deletion
  previews, recoverable quarantine, restore, and permanent purge for managed
  schema-v1 runs, comparisons, and promoted agent versions.
- `agent-dev-eval-core/evaluation` owns use-case-neutral attempt states, scalar
  extraction, grader registry/built-ins, metrics, execution, and immutable JSON
  writing.
- `eval_results/<pipeline>/` contains local evaluation evidence.

Hosted published-contract loading must preserve Benchmark Studio's declared
contract version and label-schema hashes and fail closed when either a hash is
missing or the canonical schema content does not match it. Direct PostgreSQL
loading derives the same canonical hash at the trusted database boundary.

Keep generic mechanics in `agent-dev-eval-core`; keep profile selection, named
views, and use-case-specific graders in the root project.

## Required Evaluation Flow

1. Resolve or load an exact candidate agent version and validate requested
   model/reasoning overrides against its frozen policy.
2. Require a versioned evaluation profile and explicit benchmark key.
3. Resolve an explicit published benchmark version or the latest published
   version for the configured project.
4. Load every example's complete frozen label payload, label-schema reference,
   source snapshot, and raw artifact manifest.
5. Apply generic example/unit/label filters and profile-defined slices.
6. Preflight label-schema hashes, profile compatibility, paths, predicates,
   graders, expected targets, slice membership, and the pipeline's project,
   published-schema, evidence-recipe, snapshot-contract, and required-artifact
   declarations before model calls.
7. Construct benchmark metadata and verify Blob byte size and SHA-256 before
   decoding evidence.
8. Run the pipeline and validate the generic act-receipt identity fields.
9. Extract the profile-configured JSON scalar outputs from receipt metadata.
10. Validate required, optional, and conditional output fields.
11. Grade only valid outputs with explicit deterministic graders.
12. Aggregate valid-run accuracy separately from reliability and scoring
    coverage.
13. Persist the exact agent manifest, benchmark, schema, profile, grader, slice,
    model, runtime, aggregate outputs, usage, and attempt identities in eval
    schema v1. Retain the compact result, run manifest, and agent manifest in
    Git; keep detailed attempt generations local by default. Persist durations,
    retries, and backend-call timing only in disposable performance schema v1.

Preflight must resolve the final structured output schema declared by the
pipeline. Every configured `receipt_metadata_path` begins at `agent_output`,
must exist in that schema, and must agree with the configured scalar type.
Selected benchmark target values must also be type-compatible before execution.

The local coordinator translates the first `SIGINT` or `SIGTERM` into
cooperative cancellation: stop submitting work, allow active terminal records
to commit within the bounded grace period, preserve unsubmitted work as
missing, and record an `interrupted` invocation event. A second signal requests
immediate interruption.

Invocation audit history must not mutate execution performance: no-op resumes
and materialization-only invocations contribute zero execution wall time.

## Receipt Contract

The act receipt must carry these generic identity fields:

- `example_id`
- `benchmark_key`
- `benchmark_version_id`
- `benchmark_version_number`
- `source_snapshot_id`

The agent's structured output lives under `agent_output`. Evaluation profiles
resolve nested paths inside that payload. Do not require or add flat
use-case-specific receipt keys such as `classification` or `root_cause`.

The retrieve receipt should preserve frozen source-snapshot hash, evidence row
counts, and artifact integrity details.

Process objects may expose bounded `execution_telemetry`; the pipeline persists
it on the process receipt in `finally` so usage and retry observations survive
processor, hydrator, or action failure. Evaluation merges available stage
telemetry and marks only genuinely absent observations unavailable.

## Attempt And Accuracy Rules

Keep these states orthogonal:

- execution: `completed`, `failed`, `cancelled`;
- output contract: `valid`, `invalid`, `not_produced`; and
- scoring: `scored`, `not_scored`, `grader_error`,
  `no_applicable_targets`.

Only `valid` + `scored` attempts enter accuracy denominators. Missing,
malformed, partial, identity-mismatched, operationally failed, cancelled, and
grader-failed attempts remain fully persisted but affect reliability/coverage,
not valid-run accuracy.

Every ratio must include numerator and denominator counts. Report complete
evaluation accuracy, per-field accuracy, expected-value and confidence views,
profile slice views, output-contract validity, scoring coverage, failure types,
and performance.

## Deterministic Graders And Predicates

Use built-ins from the explicit registry:

- `core.exact@1`
- `core.normalized_string@1`
- `core.numeric_tolerance@1`

Normalization must be explicit in profile configuration and recorded in
results. Register project graders by stable ID/version; evaluation YAML never
imports arbitrary code.

Use the small declarative predicate language for conditional applicability and
slices. Never execute Python, templates, or arbitrary expressions from a
profile. Slices may use immutable benchmark labels, metadata, identity, and
decision timestamps; do not derive slice membership from model output.

## Retained Eval, Local Detail, And Disposable Performance Contracts

Keep `result.json` compact with top-level keys in this order:

1. `schema_version`
2. `summary`
3. `run`
4. `artifacts`

Eval schema v1 is split by retention policy:

- `manifest.json`, `agent-version.json`, and compact `result.json` are retained
  in Git for important runs;
- immutable `attempts/` are detailed local evidence, ignored by Git by default,
  and may be removed after initial analysis; and
- `performance/` and `review/` are disposable local diagnostics.

Together, while the local detail is present, these files preserve:

- published benchmark and source-state identity;
- each selected example's frozen source-snapshot identity, window, known gaps,
  and complete hash/size-verified raw artifact manifest;
- frozen label-schema identities and hashes;
- evaluation profile ID/version/hash, grader set, and slices;
- complete benchmark labels for every example;
- per-attempt execution/contract/scoring states;
- applicable fields, expected/actual values, grader details, confidence, and
  correctness;
- raw/partial agent output and contract errors;
- structured failure/correlation details; and
- effective AI execution policies and token/cost observations.

Do not persist duplicated per-example rows in `result.json`. Complete benchmark
labels live once in the retained manifest eval contract; canonical agent output,
grades, usage, and failures live in local immutable attempt generations.
Detailed rows are reconstructed on demand through
`LocalRunStore.evaluation_rows()` while those attempts are retained locally.
Deleting attempts intentionally gives up resume, rematerialization, detailed
inspection, and per-attempt verification while preserving the committed compact
summary and exact run/agent identity.

The local explorer reconstructs reviewer evidence from the selected example's
retained frozen-artifact manifest and reads those exact objects from Blob. It
must not re-query the current publication catalog to recover historical run
evidence. A legacy run that lacks the retained artifact manifest fails closed
and must be rerun with the current writer.

Performance schema v1 lives under ignored `<run-dir>/performance/`. It owns
invocation events, attempt/stage durations, retry observations, backend-call
durations, configured-timeout duration-boundary observations, and its aggregate
summary. Record HTTP attempt counts and retry categories only when the active
adapter observed them; never convert configured retry limits into observations
or label aggregate duration as a confirmed provider timeout. Performance is
not part of tracked eval integrity and may be deleted without affecting
scoring, resume, comparisons, inspection, lifecycle, or promotion. Explorer
APIs and views must represent missing performance as unavailable. Do not add
readers, writers, migrations, or compatibility paths for any older eval schema.

Detailed prompts, multimodal bytes, tool transcripts, and validation history
belong in the disposable run-local `review/` subtree, not inline in immutable
attempt records or schema-v1 `result.json`. Review capture never writes to
Azure, is excluded from scientific run identity, and may be purged without
invalidating scoring, resume, comparisons, or agent-version linkage.

Treat each execution review as a transaction. Normalize only explicitly
supported binary encodings, stage and hash the complete manifest/object set,
write a recovery journal before promotion, publish the manifest as the commit
point, and remove staged or newly promoted objects on failure or interrupted
transaction recovery. Capture begins `in_progress` and is finalized against
the durable execution IDs as `complete`, `partial`, or `failed`; purge produces
`purged`. Persist bounded redacted failure observations, verify orphan/missing
objects plus manifest/count mismatches, and derive lifecycle/explorer status
from one evidence-backed review-state projection rather than trusting the
descriptor string. The disposable schema-v2 inspection index fingerprints the
compact result, current attempt generations, capture descriptor, execution
manifests, objects, and staging state and is rebuilt whenever those sources
change. Review failure must remain nonfatal to durable attempt, scoring, and
performance persistence.

## Hosted Inputs

The local operator CLI defaults to direct Microsoft Entra access. It uses
`APP_PROJECT_KEY`, `AZURE_POSTGRES_HOST`, `AZURE_POSTGRES_DATABASE`, and
`AZURE_POSTGRES_USER` to obtain a short-lived Azure PostgreSQL token through
`DefaultAzureCredential`, immediately sets the transaction read-only, and uses
`AZURE_STORAGE_ACCOUNT_URL` plus `AZURE_STORAGE_CONTAINER` to read frozen
evidence with `Storage Blob Data Reader`.

Password-based programmatic tests may still inject `DATABASE_URL`, but the
operator path must use Entra for PostgreSQL and Blob. Never restore Container
App exec, runtime secret discovery, SAS tokens, or shared storage keys.

## Operator Commands

Do not duplicate commands here. Read `EvalRunbook.md` and use
`$run-use-case-evals` for live run preparation or troubleshooting.

When a schema-v1 contract changes, update the run and analysis skills plus
operator documentation in the same change. Keep the repository contract-drift
test passing so removed result fields cannot reappear in active instructions.

## Tests

At minimum cover:

- exact/latest published-version selection and project scoping;
- full label payload and frozen label-schema hash loading through the direct
  repository adapter;
- profile validation, stable hashing, invalid paths/predicates/graders, and
  multi-schema compatibility;
- exact, normalized-string, numeric-tolerance, and project grader behavior;
- required, optional, conditional, missing, malformed, and partial outputs;
- generic label filters and deterministic slice membership, including empty
  slices;
- valid-run field/complete accuracy and separate reliability/coverage;
- provider, transport, timeout, pipeline, identity, output, grader, executor,
  and cancellation failures;
- retained schema-v1 run/agent identity, compact summaries, and local detailed
  attempt evidence;
- disposable performance schema v1 separation and backend-call timing;
- URL-safe Pydantic AI binary capture, malformed-artifact rollback, CAS
  deduplication, truthful capture finalization, and orphan/count integrity;
- repeated serial/thread/process equivalence; and
- deterministic run/work identity, interruption recovery, selective failure
  generations, idempotent resume, and dimension-safe comparison; and
- derived lifecycle discovery, reference warnings, shared-CAS reachability,
  quarantine/restore/purge, active-lock rejection, and path/symlink safety; and
- Spirax nested `agent_output` receipt handoff without flat output aliases.

Use injected repositories, pipeline receipts, Blob clients, and grader
registries for deterministic tests. Live Azure smoke checks are useful when
credentials are available but are not required unit tests.
