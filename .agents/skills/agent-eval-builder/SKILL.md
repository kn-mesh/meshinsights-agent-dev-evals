---
name: agent-eval-builder
description: Build or update MeshInsights Agent Workbench published-benchmark evaluation orchestration for AI-enabled pipelines in this repo. Use when changing Benchmark Studio published contracts, immutable Azure evidence, evaluation profiles, deterministic graders, slices, repeated-run execution, result schema v3, scoring, or evaluation-results apps. Do not use merely to prepare, execute, or troubleshoot an existing eval command; use run-use-case-evals for that.
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
- `src/benchmarks/postgres_repository.py` and
  `src/benchmarks/azure_container_app_repository.py` load published-contract
  schema version 2.
- `evaluation_configs/*.eval.yaml` contains project-owned evaluation profiles.
- `src/evals/evaluation_profile.py` validates profiles, predicates, preflight,
  and local slice membership.
- `src/evals/scoring.py` validates configured output contracts and runs
  deterministic graders.
- `src/evals/eval_orchestration.py` owns repeated execution, generic filtering,
  aggregation, and result schema version 3.
- `src/evals/run_specs.py` and `src/evals/run_store.py` own deterministic run
  identity, source manifests, immutable attempt generations, local locking,
  resume/rerun selection, and materialization.
- `src/agent_versions/` and `agent_version_configs/*.agent.yaml` own exact
  candidate resolution, Git/dirty overlays, model override policy, local CAS,
  promotion, verification, and the immutable agent reference used by evals.
- `src/evals/comparisons.py` preflights every comparison child into an immutable
  manifest, validates declared varying dimensions, and reports paired logical-
  work-item deltas across deterministic schema-v3 runs.
- `src/evals/inspection.py`, `src/evals/inspection_cli.py`, and
  `agent-dev-eval-core/evaluation/review.py` own local-only, run-scoped,
  disposable model/evidence review, bounded coding-agent queries, optional
  compact diagnoses, integrity verification, and explicit review-only purge.
- `src/lifecycle/` owns the derived local catalog, reference graph, deletion
  previews, recoverable quarantine, restore, and permanent purge for managed
  schema-v3 runs, comparisons, and promoted agent versions.
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
13. Persist exact agent manifest, benchmark, schema, profile, grader, slice,
    model, runtime, and attempt identities in result schema v3.

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

## Result JSON Contract

Keep top-level keys in this order:

1. `summary`
2. `run_config`
3. `selected_example_ids`
4. `results`

Result schema v3 must preserve:

- published benchmark and source-state identity;
- frozen label-schema identities and hashes;
- evaluation profile ID/version/hash, grader set, and slices;
- complete benchmark labels for every example;
- per-attempt execution/contract/scoring states;
- applicable fields, expected/actual values, grader details, confidence, and
  correctness;
- raw/partial agent output and contract errors;
- structured failure/correlation details; and
- timing and effective AI execution policies.

Historical standalone schema-v2 result files are unsupported. Do not add them
to `eval_results/`, rewrite them, migrate them, or add compatibility shims that
continue producing or cataloging them.

Detailed prompts, multimodal bytes, tool transcripts, and validation history
belong in the disposable run-local `review/` subtree, not inline in immutable
attempt records or schema-v3 `result.json`. Review capture never writes to
Azure, is excluded from scientific run identity, and may be purged without
invalidating scoring, resume, comparisons, or agent-version linkage.

## Hosted Inputs

The operator CLI uses `APP_PROJECT_KEY` plus Azure CLI authentication. Hosted
benchmark discovery executes the deployed Benchmark Studio repository contract
through its Container App and retrieves read-only Blob configuration.

Direct programmatic execution may use `DATABASE_URL`,
`AZURE_STORAGE_CONNECTION_STRING`, and `AZURE_STORAGE_CONTAINER`. Use
least-privilege read identities and never commit credentials.

## Operator Commands

Do not duplicate commands here. Read `EvalRunbook.md` and use
`$run-use-case-evals` for live run preparation or troubleshooting.

## Tests

At minimum cover:

- exact/latest published-version selection and project scoping;
- full label payload and frozen label-schema hash loading through both hosted
  and direct repository adapters;
- profile validation, stable hashing, invalid paths/predicates/graders, and
  multi-schema compatibility;
- exact, normalized-string, numeric-tolerance, and project grader behavior;
- required, optional, conditional, missing, malformed, and partial outputs;
- generic label filters and deterministic slice membership, including empty
  slices;
- valid-run field/complete accuracy and separate reliability/coverage;
- provider, transport, timeout, pipeline, identity, output, grader, executor,
  and cancellation failures;
- result schema v3 identities and debugging evidence;
- repeated serial/thread/process equivalence; and
- deterministic run/work identity, interruption recovery, selective failure
  generations, idempotent resume, and dimension-safe comparison; and
- derived lifecycle discovery, reference warnings, shared-CAS reachability,
  quarantine/restore/purge, active-lock rejection, and path/symlink safety; and
- Spirax nested `agent_output` receipt handoff without flat output aliases.

Use injected repositories, pipeline receipts, Blob clients, and grader
registries for deterministic tests. Live Azure smoke checks are useful when
credentials are available but are not required unit tests.
