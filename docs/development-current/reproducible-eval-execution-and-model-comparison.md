# Reproducible Eval Execution And Model Comparison

**Status:** Implemented for MVP

**Implementation summary:** Deterministic run/work/comparison identity,
append-only attempt generations, local coordinator locking, incremental
checkpointing, interruption recovery, selective failed-work reruns, stable
schema-v3 materialization, explicit CLI preflight, source-content manifests,
usage/retry/cost availability, optional frozen pricing estimates, and
dimension-validated comparisons are implemented. Provider-dependent transport
attempts and billed cost remain explicitly unavailable when the active backend
does not expose them; configured limits are never reported as observations.

**Backlog feature:** `docs/development-backlog/features.md` → Reproducible Eval
Execution And Model Comparison

**Related active design:**
`docs/development-current/schema-driven-evaluation-and-scoring.md`

## Outcome

Make an evaluation run a durable, resumable, and reproducible execution record
rather than one in-memory CLI operation that produces one timestamped JSON file.
An FDE or Codex should be able to define a model/configuration comparison,
interrupt it, resume only unfinished work, selectively retry failed work, and
compare the results without losing or conflating the conditions that produced
them.

The finished workflow will:

- resolve every execution and scoring input before the first model call;
- give identical resolved run specifications the same deterministic run ID;
- give every example/repetition slot a stable work-item ID;
- persist terminal work incrementally and never overwrite completed evidence;
- resume missing work and retry failed work without rerunning completed slots;
- preserve every retry generation and distinguish harness retries from model
  transport, output-validation, and tool retries;
- capture latency, stage timing, model usage, cost, provider diagnostics, and
  output-contract reliability per work item;
- materialize a stable result-schema-v3 document from durable attempt records;
- create comparison sets whose varied and held-constant dimensions are
  explicit; and
- remain usable through one primary non-interactive CLI, with interactive
  selection as a convenience rather than a source of hidden defaults.

## Non-Goals

This feature does not include:

- defining benchmark labels, schemas, graders, or scoring semantics;
- AI or nondeterministic graders;
- an interactive result-inspection application;
- cloud publication or multi-machine distributed scheduling;
- reconstructing provider billing when a provider does not expose actual cost;
- treating wall-clock timestamps, worker count, or invocation history as model
  quality dimensions; or
- automatically promoting an evaluation result to an immutable agent version.

The result and run contracts must nevertheless carry the identities required by
future inspection, catalog, and agent-version features.

## Relationship To Schema-Driven Evaluation And Scoring

The schema-driven scoring design owns:

- published label-schema consumption;
- evaluation-profile models and hashes;
- output extraction and contract validation;
- grader resolution and field grades;
- benchmark slices;
- accuracy, reliability, and scoring-coverage semantics; and
- the semantic contents of evaluation result schema v3.

This design consumes the resolved outputs of that preflight and owns:

- run, comparison, work-item, execution-generation, and invocation identity;
- durable scheduling, locking, checkpointing, resume, and rerun behavior;
- execution telemetry and cost accounting;
- immutable local storage and result materialization;
- explicit execution/configuration dimensions; and
- cross-result comparison validation and aggregation.

Implement the shared result-schema-v3 models once. Do not create a parallel
result schema for resumability. In particular, `resolved_scoring_contract_hash`,
evaluation-profile identity, grader-set identity, output-contract status, and
scoring status come from the scoring design and are inputs to this run design.

## Current Foundations And Gaps

The current repository already provides:

- explicit pipeline, benchmark, model, reasoning, scope, repetition, runtime,
  worker, error-action, and progress settings;
- immutable published benchmark and frozen Blob evidence identity;
- serial, threaded, and process execution with bounded workers;
- repeated work-item planning in deterministic example/run order;
- continued execution after partial failure and stop-on-error cancellation;
- useful completion and slow-work heartbeats;
- pipeline/stage duration capture;
- normalized provider, transport, timeout, pipeline, receipt, executor, and
  cancellation failure categories;
- correlation-safe structured failure details; and
- atomic, collision-safe whole-result JSON writing.

The important gaps are:

- `run_eval` retains all terminal attempts in memory and writes only after the
  full invocation returns;
- interruption loses all completed work from that invocation;
- a timestamped filename is an occurrence label, not deterministic run
  identity;
- no durable work-item state exists from which to calculate missing or failed
  work;
- a rerun produces another whole result and may silently duplicate successful
  attempts;
- concurrent invocations can execute the same logical run independently;
- the pipeline file path is recorded, but its canonical contents and resolved
  runtime configuration are not hashed;
- prompts embedded in Python, tools, evidence transformations, model-catalog
  entries, source revision, and dirty source state are not identified;
- attached AI usage remains in process artifacts and is not carried into eval
  attempts;
- usage exposes request/input/output counts but not detailed retry history,
  cached/reasoning tokens, tool usage, or provider-reported cost;
- configured retry limits are recorded, but actual attempts are not;
- there is no versioned pricing snapshot or explicit unknown-cost state; and
- result files can be inspected side by side, but there is no comparison
  contract proving which dimensions changed and which stayed fixed.

## Identity Model

Use five distinct identities. They solve different problems and must not be
collapsed into one timestamp or filename.

### Resolved run specification and `run_id`

A **resolved run specification** is the complete, canonical, immutable input to
one logical evaluation run. Hash canonical JSON with SHA-256 and derive:

```text
run_id = eval_<first 24 lowercase hex characters of sha256(canonical_run_spec)>
```

Persist the full hash as `run_spec_sha256`; the short ID is only a path and UI
token. On opening an existing run directory, compare the full canonical spec
and hash and fail closed on any mismatch or truncated-hash collision.

The canonical run specification includes semantic conditions:

- project key;
- benchmark key, immutable version ID/number, source-state hash, published
  contract version, and referenced label-schema hashes;
- sorted selected example IDs and a canonical scope definition;
- pipeline/agent identity, canonical pipeline source hash, and resolved runtime
  pipeline hash after model/reasoning overrides but before example metadata;
- source revision and a content manifest for execution-relevant local files;
- resolved model provider, model/deployment ID, API family, model-catalog entry,
  and provider/backend options with secrets removed;
- effective reasoning configuration;
- evaluation-profile identity/hash, resolved scoring-contract hash, grader-set
  hash, and slice-definition hash from scoring preflight;
- repetition count;
- semantic AI policies such as timeout, transport attempts, output retries,
  tool retries, turn/tool/token limits, and output schema;
- execution runtime, worker/in-flight concurrency limits, and error policy;
- evidence-recipe/transform/tool/capability/skill identities or content hashes;
- harness result-schema version and execution-contract version; and
- declared project-owned grouping dimensions.

The specification excludes operational or incidental values that should not
create a new scientific comparison point:

- start/completion timestamps;
- invocation ID;
- output directory;
- logging verbosity and progress interval;
- rerun selection such as `missing` or `failed`.

Persist those values as invocation metadata. Runtime and concurrency remain run
dimensions because they affect timing, provider pressure, and potentially
failure behavior even when model-quality semantics are otherwise unchanged.

Never infer reproducibility from Git cleanliness alone. Record the Git commit
when available, but hash the actual execution-relevant content. A dirty checkout
can therefore be reproduced from the stored content manifest/artifact hashes;
the manifest explicitly records `source_tree_state: clean|dirty|unavailable`.

### `comparison_id`

A **comparison specification** contains an ordered set of child run IDs plus
its declared varying and invariant dimensions. Its canonical hash produces:

```text
comparison_id = cmp_<first 24 hex characters of sha256(canonical_comparison_spec)>
```

A comparison is immutable. Adding a model/configuration creates a new
comparison ID without changing prior evidence.

### `work_item_id`

One repetition slot for one selected example is a logical work item:

```text
work_item_id = sha256(run_id + "\n" + example_id + "\n" + repetition_index)
```

`repetition_index` is one-based and bounded by `runs_per_example`. A valid but
incorrect answer is completed work. A contract-invalid, provider-failed,
timed-out, or cancelled answer is terminal evidence but is eligible for an
explicit failed-work rerun policy.

### `execution_id`

Every actual execution of a work item has an immutable generation:

```text
execution_id = <work_item_id>.<generation>
```

Generation 1 is the initial execution. Selectively rerunning a failed or
cancelled work item creates generation 2, and so on. Never overwrite or discard
an earlier generation. The materialized result projects the latest terminal
generation for each work item into accuracy/reliability metrics and retains an
`execution_history` summary or references so the recovery path is auditable.

Execution generations are harness-level reruns. Provider transport attempts,
output-validation retries, tool retries, and individual model requests remain
nested telemetry within one execution generation and do not consume additional
repetition slots.

### `invocation_id`

Every CLI process that starts, resumes, or retries a run receives a random
UUIDv7/ULID-like `invocation_id`. It records operator/session history and may be
timestamp-sortable, but it is never used as scientific run identity or a
comparison dimension.

## Durable Local Run Store

Replace one timestamp-named evidence file with one content-addressed run
directory and immutable attempt records:

```text
eval_results/
  <pipeline-id>/
    <benchmark-key>/
      v<benchmark-version>/
        runs/
          <run-id>/
            manifest.json
            invocations/
              <invocation-id>.json
            attempts/
              <work-item-prefix>/
                <work-item-id>.1.json
                <work-item-id>.2.json
            artifacts/
              sha256/<prefix>/<content-hash>
            result.json
        comparisons/
          <comparison-id>.json
```

### `manifest.json`

Create `manifest.json` before scheduling. It contains:

- run ID and full run-spec hash;
- canonical resolved run specification;
- deterministic ordered work-item plan;
- creation timestamp as metadata only;
- storage/result/telemetry schema versions; and
- redaction policy and content-addressed artifact references.

Write it with atomic create-if-absent semantics. If it exists, validate exact
identity rather than replacing it.

### Attempt records

Write one terminal attempt generation immediately after it completes. Use a
temporary file, `fsync`, and exclusive hard-link/create semantics as the current
writer does. If an identical `execution_id` already exists:

- accept it only when the canonical payload hash is identical; and
- otherwise fail with a storage-integrity error.

Do not use a mutable shared JSON checkpoint as the source of truth. Immutable
per-attempt files make interruption recovery and parallel completion safe. An
interruption during a pipeline call leaves no terminal file for that generation;
on resume it is missing and can run again.

### Run lock

Hold an advisory local lock for the run directory while one coordinator plans
and executes work. A second local invocation for the same run fails with the
active invocation identity and start time. OS-managed advisory locking releases
on process death, avoiding a permanent stale lock. Exclusive attempt commits
remain the final duplicate-execution safeguard.

Multi-host execution against a shared filesystem is outside MVP. The manifest
must declare `coordinator_scope: local_single_host` so the limit is explicit.

### `result.json`

`result.json` is a deterministic materialized view, not the recovery source of
truth. Rebuild it atomically from the manifest plus immutable attempt records:

- after each terminal completion, with a short debounce for large concurrent
  runs;
- at clean invocation completion; and
- on `eval status`, `eval resume`, or `eval materialize` when stale/missing.

Its semantic arrays follow manifest work-item order, not completion order.
Exclude materialization timestamp from the canonical evidence hash. It uses
result schema v3 from the scoring design and adds only execution-owned fields
agreed there, including run/work/execution identity, usage, cost, retries, and
invocation provenance.

Historical schema-v2 JSON files remain immutable and readable. They cannot be
made resumable because they have no durable work-item identity. A catalog
adapter may expose them as `legacy_non_resumable`; never infer missing hashes or
retry history.

## Run State And Resume Semantics

Derive state by scanning the manifest and terminal attempt generations:

- `missing`: no terminal generation exists for the work item;
- `completed`: latest generation is execution-completed, output-valid, and has
  a terminal scoring state of `scored` or `no_applicable_targets`;
- `failed`: latest generation has failed execution, invalid/not-produced
  output, `grader_error`, or another retry-eligible failure category;
- `cancelled`: latest generation was not run because stop-on-error or operator
  cancellation prevented execution; and
- `superseded`: an older generation exists behind a newer generation.

The scoring design decides which terminal states contribute to accuracy. The
execution design decides which states are eligible for operator-requested
rerun. By default, a grader error is failed harness work and eligible for rerun;
a valid but incorrect model output is completed model work and is never retried
under the same run.

Support these explicit selections:

- new run: execute `missing` work (all slots are initially missing);
- `--resume missing`: execute only work with no terminal generation;
- `--resume missing-or-cancelled`: include cancellations caused by an
  interrupted/stop-on-error invocation;
- `--rerun failed`: create a new generation only for retry-eligible failed
  work;
- `--rerun <failure-type>`: retry only matching normalized failures; and
- `--work-item-id` / `--example-id`: narrow any allowed resume/rerun selection.

Completed work is never duplicated within a run. There is intentionally no
`--rerun all` under the same run ID. To collect more nondeterminism samples,
create a new run specification with a larger repetition count or an explicit
new trial dimension. To change model, prompt, evidence, tool, grader, timeout,
or another semantic condition, create a new run ID.

Before scheduling, print a plan containing selected, completed, missing,
failed, cancelled, and ineligible counts. `--dry-run` performs full preflight,
identity resolution, and plan calculation without acquiring provider capacity.

## Execution Coordinator And Concurrency

Retain `RepeatedEvalExecutor`'s bounded serial/thread/process mechanics, but
split planning from execution:

1. preflight produces the immutable ordered work-item plan;
2. the run store filters it to the requested missing/failed selection;
3. the executor receives explicit `RepeatedEvalWorkItem`s instead of rebuilding
   every repetition internally;
4. the coordinator commits each terminal record through an `on_completed`
   callback as soon as it finishes; and
5. summary materialization reads the durable store, not only returned memory.

Evolve the reusable core API to accept:

- explicit work items with stable IDs;
- a terminal-record callback;
- lifecycle callbacks for queued/started/completed state and progress;
- cooperative cancellation on SIGINT/SIGTERM;
- a configurable maximum number of in-flight tasks separate from worker count
  if process memory requires it; and
- deterministic returned ordering independent of completion order.

The initial signal stops new submissions, lets in-flight work finish for a
bounded grace period, commits their results, materializes state, and exits with
an interrupted status. A second signal may terminate immediately. Work without
a terminal record remains missing and is safe to resume.

Process execution must receive only serializable resolved inputs and must not
write the shared store directly. The parent coordinator owns commits and
materialization. Preserve `max_workers >= 1`, bounded pending work, and existing
stop/continue behavior.

## Execution Telemetry Contract

### Per pipeline attempt

Every execution generation records:

- wall-clock start/end and monotonic duration;
- pipeline and retrieve/process/act stage durations;
- pipeline/stage correlation IDs;
- execution, output-contract, and scoring statuses;
- normalized failure category and bounded exception chain;
- provider status/request IDs where safely available;
- usage and cost totals plus per-model-call breakdown;
- configured retry limits and observed attempts/retries;
- tool calls and tool failures/timeouts at count level;
- output-validation attempt count;
- resolved model/reasoning/backend identity; and
- content-addressed references to inspectable request/response evidence when
  that later inspection contract is enabled.

Failures preserve telemetry accumulated before failure. Missing telemetry is
represented as `null`/`unavailable` with a reason, never as zero.

### Required `mi.ai` changes

The current `AIUsage` contract and attached process artifacts are insufficient
for complete measurement. Introduce a backend-neutral execution telemetry
contract in `mi-core` and carry it through process-to-action receipt metadata or
a stable pipeline receipt artifact channel.

At minimum, extend usage to support:

- requests;
- input, output, total, cached-input, and reasoning tokens where providers
  expose them;
- observed transport attempts/retries;
- output-validation attempts/retries;
- tool calls, tool retries, and tool failures;
- per-call model/provider/request identity and latency;
- provider-reported actual cost and currency when available; and
- explicit availability/source fields for every provider-dependent measure.

Backend adapters must populate observations from real provider/backend events,
not infer actual retries from configured limits. Aggregate multi-processor v2
usage by processor and model before computing attempt/run totals. Keep bounded
provider error payloads redacted; never persist credentials, authorization
headers, connection strings, or unrestricted request bodies.

If modifying `mi-core` is not immediately possible, implement run identity and
resume first and mark detailed retry/cost telemetry as unavailable. Do not
fabricate the missing values in the project evaluator.

## Cost Accounting

Extend the project-owned model catalog with optional versioned pricing entries
or references. A pricing record contains:

- model/deployment match key;
- effective date/version;
- currency;
- per-million input, cached-input, output, and reasoning-token rates when
  applicable;
- request/tool/image rates when applicable;
- source label/URL and retrieval date; and
- canonical pricing-record hash.

Preflight freezes the selected pricing snapshot into the resolved run
specification. Cost output separates:

- `actual`: provider-reported billed cost, when exposed;
- `estimated`: computed from observed usage and the frozen pricing snapshot;
- `unpriced_usage`: observed usage categories without a configured rate; and
- `status`: `actual`, `estimated_complete`, `estimated_partial`, or
  `unavailable`.

Never label an estimate as actual. Never use the current catalog price to
retroactively recompute a historical result without displaying that it is a
new analysis. Retry token usage is included when the provider reports it; if
the backend cannot observe failed-attempt usage, disclose that limitation.

## Configuration Provenance And Comparison Dimensions

Use a typed dimension map rather than filenames or free-form labels. Each
dimension has a stable key, canonical value, value hash, provenance, and role:

- `benchmark.*`: benchmark/version/source/label-schema identity;
- `agent.*`: pipeline or promoted agent identity;
- `pipeline.*`: pipeline YAML and resolved configuration hashes;
- `model.*`: provider, deployment/model, API, reasoning, and backend options;
- `prompt.*`: static source/template hashes and per-attempt resolved message
  artifact hashes;
- `evidence.*`: source snapshot, recipe, transform/config, and selected evidence
  hashes;
- `tools.*`: tool, toolset, capability, skill, limit, and implementation hashes;
- `scoring.*`: profile, grader set/config, slices, and resolved contract hashes;
- `harness.*`: result/execution schema, eval-core version, and relevant policy;
  and
- `project.*`: explicitly registered use-case dimensions.

Do not require a promoted agent-version feature for MVP. Until it exists, the
pipeline hash plus execution-relevant source manifest is the agent identity.
When agent versions arrive, record both the promoted version and verified
content hashes.

Dynamic prompt and tool inputs vary naturally by example and attempt. Keep
their actual content hashes in attempt evidence; compare the template/tool
implementation and policy identities at run level. A comparison must not claim
that per-example model inputs are identical merely because the same prompt
template was used.

## Comparison Sets

Add an orchestration layer that expands a comparison specification into one
resolved child run per configuration variant. Example conceptual YAML:

```yaml
schema_version: 1
comparison_id_hint: v2-model-reasoning

base:
  pipeline: pipeline_configs/v2.ppln
  benchmark_key: phase-1-benchmark-3fb7f544
  benchmark_version: 1
  evaluation_profile: evaluation_configs/spirax-failure-evaluation.eval.yaml
  scope:
    all: true
  runs_per_example: 3

matrix:
  - model: azure:gpt-5.6-terra
    reasoning: high
  - model: azure:gpt-5.6-sol
    reasoning: medium

varying_dimensions:
  - model.id
  - model.reasoning
```

Resolve every child completely before executing any child. Write the comparison
manifest with:

- comparison ID/spec hash;
- ordered child run IDs and human labels;
- explicitly varying dimensions;
- computed invariant dimensions and hashes;
- scope alignment (same example IDs and repetition plan);
- preflight warnings/errors; and
- aggregate execution status.

Fail preflight when an undeclared dimension differs between children. Warn and
require an explicit override when scopes, repetition counts, benchmark versions,
evaluation profiles, or grader configurations differ because paired metrics
would otherwise be misleading.

Comparison aggregation reads child result-v3 documents and:

- reports quality, reliability, scoring coverage, latency, tokens, and cost
  together;
- includes numerator/denominator counts for every rate;
- computes paired per-example deltas only for aligned work-item populations;
- reports instability across repetitions separately from mean accuracy;
- retains missing/failed counts instead of silently dropping them;
- groups only by declared dimensions; and
- labels comparisons with scoring differences as different evaluation regimes,
  not model-only comparisons.

For nondeterminism, report per-example outcome distribution, unanimous/unstable
counts, and agreement rate across completed scored repetitions. Do not treat
harness rerun generations as additional samples.

## Primary CLI Workflow

Keep a single discoverable evaluator entry point, even if implementation
remains in `src.evals.eval_orchestration` initially:

```text
python -m src.evals.eval_orchestration <explicit run settings> ...
python -m src.evals.eval_orchestration <same settings> --resume-mode missing
python -m src.evals.eval_orchestration --status-run-id <run-id>
python -m src.evals.eval_orchestration --compare-result <path> ...
python -m src.evals.eval_orchestration <same settings> --materialize-only
```

For unattended `run`, require explicit:

- pipeline/agent path or identity;
- benchmark key and exact published version;
- evaluation profile/grader configuration;
- one or more model variants;
- reasoning setting, including an explicit `default` token if desired;
- scope (`all`, example IDs, unit IDs, or a resolved named slice/filter);
- repetitions;
- runtime and worker limit; and
- error policy.

Interactive prompts may fill these values, but the CLI must print and persist
the same resolved preflight specification before confirmation. Never resolve
“latest benchmark” after run creation; the exact immutable version is frozen in
the manifest.

`status` reports planned/current-generation counts, execution/reliability/
scoring states, active invocation if locked, slowest recorded attempts, token
and cost totals, and the result path. Progress during execution uses the same
durable counters so resumed runs report cumulative and invocation-local counts.

Exit codes distinguish complete success, complete-with-terminal-failures,
interrupted/resumable, preflight/configuration failure, and storage-integrity
failure. Document them in `EvalRunbook.md`.

## Result Contract Additions

Coordinate these additions with result schema v3 rather than defining a v4:

### `run_config`

- `run_id` and `run_spec_sha256`;
- canonical resolved semantic dimensions and hashes;
- source revision/tree/content-manifest identity;
- execution-contract and telemetry schema versions;
- pricing snapshot/hash;
- latest materialized invocation ID; and
- runtime operational settings, clearly separated from semantic dimensions.

### Per attempt

- `work_item_id`, `repetition_index`, current `execution_id`, and generation;
- execution-history references/summary;
- invocation ID;
- start/end/duration and stage timings;
- structured usage, retries, tool counts, and cost;
- request/provider/correlation identifiers;
- telemetry availability/limitations; and
- exact prompt/evidence/output artifact references when available.

### Summary

- duration/throughput distributions;
- usage and cost totals/distributions by processor/model;
- observed retry and provider-failure counts;
- resume/rerun generation counts; and
- nondeterminism/agreement metrics over logical repetition slots.

Keep secrets and large binary/request artifacts out of inline result JSON.
Store permitted artifacts content-addressed and reference their hash, media
type, byte size, role, and redaction status.

## Code Ownership And Expected Changes

### `agent-dev-eval-core/evaluation/`

- Add canonical JSON hashing and typed run/work/execution identity primitives.
- Change repeated execution to accept explicit work items and terminal/lifecycle
  callbacks.
- Add filesystem-independent run-store protocols and typed terminal records.
- Add generic usage, cost, retry, and nondeterminism aggregation.
- Keep this package independent of `src`, Spirax, Azure benchmark models, and
  project pricing files.

### `src/evals/`

- Add resolved run/comparison specification models and preflight composition.
- Implement the local filesystem run store, advisory coordinator lock,
  incremental commits, scan/recovery, and result materializer.
- Add resume/rerun selection and signal-aware orchestration.
- Resolve project dimensions, source manifests, model catalog, pricing, and
  comparison matrices.
- Integrate the evaluation-profile/grader preflight from the scoring design.
- Replace filename-based model comparison with comparison manifests and generic
  aggregation.

Suggested modules after decomposing the current large orchestration file:

```text
src/evals/
  cli.py
  preflight.py
  run_specs.py
  run_store.py
  coordinator.py
  telemetry.py
  materialize.py
  comparisons.py
  eval_orchestration.py  # compatibility facade during migration
```

### `mi-core/core/src/mi/ai/` and pipeline receipts

- Evolve `AIUsage` into a detailed, backend-neutral telemetry contract while
  preserving a compatibility view for existing callers.
- Instrument backends with actual per-request/retry observations.
- Carry accumulated processor telemetry through a stable receipt/artifact
  channel even when later stages fail.
- Verify process and action receipts can safely reference content-addressed
  prompt/evidence/output artifacts.

### Project configuration

- Add optional versioned pricing metadata to `models.yaml` or a dedicated
  `model_pricing.yaml` referenced by it.
- Add comparison specification examples under `evaluation_configs/` or a
  distinct `evaluation_comparisons/` directory.
- Register execution-relevant source/config paths for content manifests when
  they cannot be discovered from resolved pipeline components.

## Implementation Sequence

Implement after or alongside scoring phases 1–4, with shared contracts agreed
before either feature writes result schema v3.

### Phase 1: Freeze shared contracts and golden fixtures

- Reconcile result-schema-v3 attempt/run fields with the scoring design.
- Finalize canonicalization, semantic-dimension, run-spec, work-item, terminal
  attempt, telemetry-availability, and comparison-spec schemas.
- Create golden canonical JSON/hash fixtures and a representative result-v3
  fixture with succeeded, incorrect, contract-invalid, provider-failed,
  cancelled, grader-failed, and rerun generations.
- Decide the exact execution-relevant source manifest for current v1_3 and v2
  pipelines and fail preflight when identity cannot be resolved.

### Phase 2: Durable identity and run store

- Implement run/work/execution/invocation identity.
- Implement manifest create/validate, attempt exclusive commit, scanning,
  advisory locking, and atomic materialization.
- Adapt current eval output to a run directory while retaining a schema-v2
  compatibility reader.
- Prove crash recovery by terminating after selected completions and resuming
  without rerunning them.

### Phase 3: Resumable coordinator and CLI

- Let the executor accept explicit filtered work items and completion callbacks.
- Add resume/rerun selection, signal handling, durable cumulative progress,
  dry-run/status/materialize commands, and documented exit codes.
- Preserve serial/thread/process equivalence and parent-owned filesystem writes.
- Update `EvalRunbook.md` and `$run-use-case-evals` only after flags stabilize.

### Phase 4: Usage, retry, and cost telemetry

- Add detailed `mi.ai` telemetry and receipt propagation for successful and
  failed processors.
- Aggregate multi-processor/model usage into eval attempts.
- Add frozen pricing records, estimated/actual/partial/unavailable cost states,
  and performance/usage/cost summaries.
- Confirm provider failures and retry counts come from observations, not string
  parsing or configured maxima where structured data exists.

### Phase 5: Comparison specifications and aggregation

- Implement comparison matrix expansion and all-child preflight.
- Enforce declared varying/invariant dimensions and scope alignment.
- Run/resume child runs independently under one comparison manifest.
- Add paired quality/reliability/performance/token/cost views and repetition
  agreement metrics.

### Phase 6: Migration and hardening

- Preserve historical schema-v2 files and expose them as non-resumable legacy
  results.
- Add storage integrity audit and deterministic rematerialization commands.
- Test large-run directory scanning and debounce/checkpoint performance.
- Verify redaction and bounded artifact retention before enabling detailed
  request/response artifact capture.

## Testing Strategy

### Identity and canonicalization

- identical resolved semantic specs produce identical full hashes and IDs;
- YAML formatting, mapping order, timestamps, output paths, logging verbosity,
  and progress intervals do not change run ID;
- model, reasoning, prompt/tool/evidence/pipeline/scoring hashes, retries,
  timeout, runtime, worker limit, error policy, scope, repetition count, or
  benchmark version do change run ID;
- truncated-ID collisions fail by comparing full hashes/specs;
- dirty source content changes identity even at the same Git commit; and
- secrets are excluded/redacted before canonical persistence.

### Durable execution and recovery

- every terminal work item is readable immediately after completion;
- simulated termination after N completions resumes only remaining slots;
- interrupted in-flight work without a terminal record is safely missing;
- failed rerun creates the next generation and preserves prior evidence;
- valid incorrect outputs are never selected by `--rerun failed`;
- repeated resume commands are idempotent;
- a second coordinator cannot acquire an active local run lock;
- identical exclusive commits are accepted and conflicting commits fail;
- process workers never write shared state directly; and
- rematerialization is byte-stable for semantic content and manifest order.

### Concurrency and progress

- serial, threaded, and process modes plan equivalent work and materialize the
  same logical ordering;
- worker/in-flight limits are never exceeded;
- stop-on-error marks unscheduled work cancelled and leaves resumable evidence;
- cumulative and invocation-local progress remain correct after resume; and
- signal handling commits completed in-flight work within the grace period.

### Telemetry and cost

- successful and failed calls preserve observed usage and retry telemetry;
- configured retry limits are distinct from actual attempts;
- multi-processor and multi-call totals equal their detailed observations;
- unavailable provider fields remain null with reasons, not zero;
- pricing hashes and effective versions are persisted;
- estimates cover cached/reasoning/request/image categories correctly;
- partially priced usage yields `estimated_partial`; and
- provider actual cost is never replaced or mislabeled by an estimate.

### Comparison behavior

- matrix expansion is deterministic;
- undeclared differing dimensions fail preflight;
- differing scope, benchmark, scoring, or grader identities cannot be presented
  as a paired model-only comparison;
- paired deltas use only aligned logical work-item populations and expose
  denominators;
- failed/missing work remains visible in reliability and coverage;
- agreement metrics use repetition slots, not rerun generations; and
- adding a child produces a new comparison ID without altering old manifests.

### End-to-end

- run a small injected benchmark, interrupt, resume, rerun one provider failure,
  and verify each completed model call occurs exactly once except the selected
  failed generation;
- compare two models on the same frozen scope and prove all non-model dimensions
  are invariant;
- compare prompt/evidence/tool variants and verify each changed axis is named;
- materialize a schema-v3 result that the scoring metrics can recompute exactly;
  and
- run a live Azure smoke test when credentials exist without making it a unit
  test requirement.

## Acceptance Criteria

- Every non-interactive run records explicit agent/pipeline, exact benchmark
  version, model, reasoning, runtime, scope, repetitions, and resolved grader
  configuration before execution.
- Identical resolved semantic conditions produce the same deterministic run ID;
  differing material conditions produce a different run ID.
- Killing an eval after completed attempts have committed and resuming it does
  not repeat those completed work items.
- Missing, cancelled, failed, and failure-type-specific work can be selected for
  recovery without duplicating completed attempts.
- Failed reruns preserve generation history; valid incorrect outputs remain
  immutable nondeterminism samples.
- Concurrency is bounded, progress is cumulative and useful, and partial
  failures do not prevent durable evidence for other attempts.
- Result materialization is deterministic, atomic, collision-safe, and
  reconstructible solely from the manifest and immutable attempt records.
- Per-attempt and aggregate results expose latency/stage timing, structured
  provider failures, observed retries, token usage, and honest actual/estimated/
  partial/unavailable cost states.
- Model, prompt, evidence, tool, pipeline, scoring, and harness dimensions are
  independently identified and hashed.
- A comparison declares varied dimensions, validates invariants, exposes
  reliability/coverage beside accuracy, and never presents changed scoring or
  scope as a model-only result.
- Result schema v3 is shared with the schema-driven scoring work; no competing
  execution-specific result format is introduced.
- Historical schema-v2 output is left untouched and explicitly identified as
  non-resumable.

## Risks And Mitigations

### Content hashing may miss dynamically imported execution logic

Mitigation: hash resolved pipeline config plus a registered execution-relevant
content manifest; fail preflight when a component cannot supply identity. Add
promoted agent-version identity later, but continue verifying content hashes.

### The same deterministic run could be started concurrently

Mitigation: one OS-managed local coordinator lock, parent-owned commits, and
exclusive immutable attempt creation. Declare multi-host scheduling unsupported
for MVP.

### Reruns can bias nondeterminism metrics

Mitigation: retain logical repetition slots separately from execution
generations. Only the latest generation represents a slot; disclose generation
counts and never count generations as extra samples.

### Detailed telemetry depends on provider capabilities

Mitigation: use typed availability/source fields, preserve partial observations,
and never infer actual retry or billing data from configured limits. Land
resume/identity independently if `mi-core` telemetry takes longer.

### Pricing changes over time

Mitigation: freeze and hash a versioned pricing record at preflight. Historical
cost remains tied to that snapshot; later repricing is a separately labeled
analysis.

### Incremental files can become numerous

Mitigation: shard attempt paths by work-item prefix, debounce materialization,
and treat the immutable attempt set as an append-only local evidence store.
Optimize scanning only after measuring benchmark-scale behavior.

### Shared schema work can diverge

Mitigation: complete phase 1 jointly with
`schema-driven-evaluation-and-scoring.md`, keep a single result-schema-v3 model,
and make execution preflight consume the resolved scoring contract rather than
reimplementing graders or output-state semantics.

## Assumptions To Validate During Phase 1

No assumption below blocks this design, but each must be confirmed before its
dependent implementation phase:

- Local single-host execution and local filesystem evidence are sufficient for
  MVP; distributed/cloud scheduling remains post-MVP.
- The scoring work will expose stable evaluation-profile,
  resolved-scoring-contract, grader-set, and slice hashes during preflight.
- The pipeline builder can expose a resolved component/config manifest, or the
  use-case project can register all execution-relevant source paths explicitly.
- `mi-core` may change to propagate detailed usage/retry telemetry through
  failed as well as successful pipeline executions.
- Provider-reported actual cost will often be unavailable; a frozen project
  pricing catalog and explicit estimated/partial/unavailable states are
  acceptable for MVP.
