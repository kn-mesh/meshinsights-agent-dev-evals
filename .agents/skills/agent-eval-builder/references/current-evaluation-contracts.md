# Current Evaluation Contracts

This reference describes the current repository implementation. Read only the
sections relevant to a task that changes or diagnoses these contracts. The
presence of a feature here does not justify preserving, expanding, or copying
it into another use case.

## Contents

- [Ownership Map](#ownership-map)
- [Current Execution Path](#current-execution-path)
- [Receipt And Scoring Contracts](#receipt-and-scoring-contracts)
- [Run And Retention Layout](#run-and-retention-layout)
- [Review Capture](#review-capture)
- [Candidate Versions](#candidate-versions)
- [Local Lifecycle Maintenance](#local-lifecycle-maintenance)
- [Hosted Inputs](#hosted-inputs)
- [Focused Validation Map](#focused-validation-map)

## Ownership Map

- `src/benchmarks/models.py` defines published benchmark, full label payload,
  frozen label schema, example, and source-artifact models.
- `src/benchmarks/postgres_repository.py` loads published-contract schema
  version 2 directly from Azure PostgreSQL with Entra authentication.
- `evaluation_configs/*.eval.yaml` contains project-owned evaluation profiles.
- `src/evals/evaluation_profile.py` validates profiles, predicates, preflight,
  and local slice membership.
- `src/evals/scoring.py` validates configured outputs and invokes graders.
- `src/evals/eval_orchestration.py` coordinates selection, execution,
  aggregation, result materialization, and current CLI options.
- `src/evals/run_specs.py` and `src/evals/run_store.py` implement deterministic
  run-spec identity, unique eval occurrences, attempts, locking, exact-ID
  resume/rerun selection, and materialization.
- `agent-dev-eval-core/evaluation/` contains shared attempt, grader, metric,
  execution, serialization, review, and explorer-query mechanics.
- `src/agent_versions/` resolves and promotes content-addressed candidate
  versions using Git/source state, policies, contracts, assets, and a local CAS.
- `src/evals/inspection.py`, `src/evals/inspection_cli.py`, and
  `agent-dev-eval-core/evaluation/review.py` implement local review capture and
  inspection.
- `src/apps/eval_explorer.py`, `agent-dev-eval-ui/`, and `www/` implement the
  local human explorer.
- `src/eval_lifecycle/` implements the supported working/retained lifecycle,
  compact elevation, retained verification, and permanent exact deletion.
- `src/eval_publication/` implements retained-eval publication preflight, the
  versioned cloud subset, dry run, Azure conditional creation, and verification.

## Current Execution Path

The current orchestrator can:

1. resolve a candidate agent version and validate model overrides;
2. load a versioned evaluation profile and published benchmark version;
3. load complete labels, label-schema identity, source snapshots, and artifact
   manifests;
4. select examples using identities, label filters, and profile slices;
5. preflight pipeline, project, schema, evidence, grader, and output contracts;
6. verify Blob size and SHA-256 before evidence decoding;
7. execute the pipeline serially or in bounded threads;
8. validate receipt identity and structured output;
9. grade applicable valid outputs;
10. aggregate accuracy, reliability, coverage, slice, usage, and performance
    observations;
11. persist attempts plus compact result and manifest files; and
12. start a unique occurrence by default and explicitly resume, selectively
    rerun, or rematerialize it.

The coordinator also contains cooperative signal handling and invocation audit
history. Treat these as current compatibility constraints only when a change
touches interruption, resume, or performance accounting.

## Receipt And Scoring Contracts

The current act receipt includes:

- `example_id`
- `benchmark_key`
- `benchmark_version_id`
- `benchmark_version_number`
- `source_snapshot_id`

The structured decision lives under `agent_output`. Evaluation profiles resolve
nested scalar paths inside that payload. The retrieve receipt preserves source
snapshot and artifact-integrity observations.

Attempt state currently separates:

- execution: `completed`, `failed`, `cancelled`;
- output contract: `valid`, `invalid`, `not_produced`; and
- scoring: `scored`, `not_scored`, `grader_error`,
  `no_applicable_targets`.

Only valid, scored attempts enter accuracy denominators. Other attempts
contribute to reliability and coverage. Ratios include numerator and denominator
counts.

Built-in deterministic graders are registered as:

- `core.exact@1`
- `core.normalized_string@1`
- `core.numeric_tolerance@1`

Evaluation profiles also support a small declarative predicate language for
conditional applicability and benchmark-derived slices.

## Run And Retention Layout

New evals use occurrence-aware schema version 2 and retain compact top-level
`result.json` keys:

1. `schema_version`
2. `summary`
3. `run`
4. `artifacts`

Every new run begins under:

- `eval_results/working/<benchmark>/v<version>/<run-id>/`

The rich working layout separates:

- `manifest.json`, `agent-version.json`, and `result.json` as durable identity
  and summary artifacts;
- `attempts/` as immutable detailed local execution evidence;
- `performance/` as disposable invocation and timing observations; and
- `review/` as disposable prompt, model-response, tool, and multimodal detail.

`eval_run_id` uniquely identifies one start, while `run_spec_sha256`
deterministically identifies the resolved configuration. Repeating an identical
command starts a new occurrence. Resume requires the exact existing
`eval_run_id` and verifies the supplied resolved specification.

`LocalRunStore.evaluation_rows()` reconstructs detailed rows from the manifest
and selected immutable attempt-generation files in the working bundle.
Removing attempts gives up resume, rematerialization, detailed inspection, and
attempt verification while leaving the compact result.

Lifecycle discovery and elevation support occurrence-aware schema-v2 working
bundles only. Legacy schema-v1 working bundles are rejected rather than
migrated or elevated. A selected schema-v2 occurrence may be elevated when it
is complete: zero planned work items are missing and every planned work item
has a latest recorded attempt. Its scope may be all examples, named sections,
or explicit units/examples. Complete selected occurrences may be elevated to:

- `eval_results/retained/<benchmark>/v<version>/<retained-eval-id>/`

Elevation always creates a schema-v2 retained eval with a non-circular identity
seed bound to the occurrence, benchmark, source state, and agent version. It is
a compact aggregate containing `manifest.json`,
`result.json`, `units.json`, `agent-provenance.json`,
`evidence-references.json`, and an optional `agent.patch`. Retained evals never
contain per-unit files, performance detail, review objects, or local copies of
Azure evidence. Shared meaningful agent-version records live under
`eval_results/retained/agent_versions/`. After retained verification succeeds,
elevation permanently removes the source working occurrence so one eval is not
listed in both lifecycle states.

The explorer reconstructs evidence from each working run manifest or retained
eval's exact Azure storage references. It does not re-query the current
publication catalog for a historical run.

## Review Capture

The current review subsystem stores detailed model interactions in a local
content-addressed object tree. It stages objects, writes recovery state,
publishes per-execution manifests, finalizes capture status, verifies counts and
object integrity, and builds an inspection index.

Review capture is outside scientific run identity and failures are intended to
remain nonfatal to attempt scoring. Changes to this subsystem should preserve
that separation. New eval features do not need to use or extend transactional
capture unless their requested inspection outcome depends on it.

## Candidate Versions

The current candidate resolver scans the pipeline graph, source, dirty overlay,
declared assets, prompts, schemas, action/evidence contracts, dependency lock,
and model override policy. It hashes those inputs into an immutable candidate
manifest. Promotion copies the selected manifest and required objects into the
local agent-version store and may attach an alias.

Treat candidate provenance and promoted-version lifecycle as separate concepts
when modifying these contracts. Do not add another identity or catalog merely
to solve a presentation or filtering task.

## Local Lifecycle Maintenance

`src/eval_lifecycle/` is the supported MVP lifecycle. It lists explicit working
and retained evals, previews and elevates complete selected occurrences,
verifies compact retained artifacts, and permanently deletes an exact working
or retained eval.
Elevation preserves the benchmark and agent identities, aggregate results,
full final AI outputs, grading, usage/cost, relevant Git provenance, and exact
Azure evidence references while pruning disposable detail. It verifies the
retained artifacts before permanently deleting the source working occurrence.

Deletion is immediate and unrecoverable. Retained deletion requires the exact
retained ID twice, and a shared agent version remains until its last retained
eval reference is deleted. The read-only explorer may filter and inspect both
lifecycle states but must not elevate, delete, edit, or annotate them.

Publication accepts schema-v2 retained evals only. An explicitly selected
retained eval may be published when every canonical unit completed and its
recorded agent surface is clean. Each publish creates a new event. Payloads are
downloaded and hash-verified before `publication-manifest.json` is created last
as the discovery marker. Publication does not alter the local lifecycle or
Benchmark Studio truth.

## Hosted Inputs

The current operator path uses direct Microsoft Entra access:

- `APP_PROJECT_KEY`
- `AZURE_POSTGRES_HOST`
- `AZURE_POSTGRES_DATABASE`
- `AZURE_POSTGRES_USER`
- `AZURE_STORAGE_ACCOUNT_URL`
- `AZURE_STORAGE_CONTAINER`
- `AZURE_EVAL_RESULTS_ACCOUNT_URL`
- `AZURE_EVAL_RESULTS_CONTAINER`

PostgreSQL transactions are set read-only. Blob access uses an identity with
container-scoped `Storage Blob Data Reader`. Programmatic tests may inject
`DATABASE_URL`. The operator path does not use Container App exec, runtime
secret discovery, SAS tokens, or shared storage keys.

Operator CLI/env connection inputs must match the non-secret project,
PostgreSQL, and Blob identities in `workbench.project.json` before catalog
queries, evidence reads, or eval run-state writes.

The eval-results variables identify a separate Entra-authenticated publication
destination. They are used only by the explicit publication command; evidence
retrieval continues to use the read-only source-snapshot variables.

## Focused Validation Map

Select tests based on the contract being changed:

- Published input: project/version selection, schema hashes, complete labels,
  immutable artifact identity, read-only access.
- Evaluation profile: stable loading, path/type compatibility, relevant
  predicates, graders, applicability, and slices.
- Scoring: valid/invalid/partial output and relevant grader behavior.
- Execution: only the runtimes, failure classes, cancellation, or resume behavior
  touched by the change.
- Results: compact summary, attempt materialization, and integrity fields changed
  by the task.
- Review: only capture, attempt-write recovery, or object-integrity behavior
  touched by the task.
- Lifecycle: working/retained discovery, complete-selected-occurrence
  elevation, compact artifact integrity, exact evidence references, permanent
  deletion, shared agent references, active-run locks, and path safety.
- Use case: the current reference pipeline's `agent_output` handoff when shared
  changes could affect project-owned behavior.
