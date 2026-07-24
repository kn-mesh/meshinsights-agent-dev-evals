# Spirax Pulse Eval Runbook

Use this runbook to execute the `v1_3` pipeline against an immutable published
benchmark version for the `spirax-pulse` project.

## Full Benchmark Command Template

The hosted Benchmark Studio catalog is mutable operational state. Do not copy a
benchmark key from this runbook, `workbench.project.json`, a retained result, or
a previous terminal session and assume that it is still published. First use
the discovery workflow below to confirm the exact key and version available in
the current environment, then substitute them into this command. This command
evaluates every example in that selected version once:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --azure-postgres-host misprx-lb-dv-pg-qdol4f5j2ozla.postgres.database.azure.com \
  --azure-postgres-database label_benchmark \
  --azure-postgres-user kurt.neuens@mesh-systems.com \
  --azure-storage-account-url https://misprxlbdvqdol4f5j2ozla.blob.core.windows.net \
  --azure-storage-container source-snapshots \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --all-examples \
  --ai-model azure:gpt-5.6-luna \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime threaded \
  --max-workers 4 \
  --review-capture full
```

This is a full 70-example model run and therefore incurs model usage. Validate
a new or edited agent first with focused tests and the exact-example pipeline
runner; do not create a one-example eval occurrence as a prerequisite to this
full eval.

## Prefer The Explicit Command

Pass the evaluation profile, benchmark, version, model, and execution settings
explicitly. This skips the slow interactive benchmark-catalog query and makes
the run reproducible.

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --azure-postgres-host <postgres-host> \
  --azure-postgres-database <postgres-database> \
  --azure-postgres-user <entra-login> \
  --azure-storage-account-url <blob-account-url> \
  --azure-storage-container <blob-container> \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --all-examples \
  --ai-model <provider:model> \
  --ai-reasoning-effort <low|medium|high> \
  --runs-per-example <count> \
  --runtime threaded \
  --max-workers <count> \
  --review-capture <full|off>
```

Replace every angle-bracket placeholder. Choose `--ai-model` from
`models.yaml`. Keep `--benchmark-version` explicit for comparable runs;
the non-interactive CLI requires it rather than silently selecting latest.

Every run automatically resolves the matching
`agent_version_configs/<pipeline-stem>.agent.yaml`, creates an immutable
candidate manifest, and writes it beside the durable run. Use
`--agent-version-id av_<hash>` or `--require-promoted-agent-version` when a run
must use content already promoted into the local catalog.

Promote a useful completed run without resolving the current checkout again:

```bash
uv run python -m src.agent_versions.cli promote \
  --from-run eval_<run-id> \
  --alias <human-readable-alias>
```

Use `src.agent_versions.cli inspect`, `verify`, and `reconstruct` to audit a
promoted version. Promotion defaults to a clean version surface; pass
`--dirty-policy capture` explicitly when promoting current dirty pipeline work.

`models.yaml` currently declares `azure:gpt-5.6-luna` as the interactive
default model and routes it through the `openai_responses` API family.
Non-interactive execution requires `--ai-model` and an explicit reasoning
setting, including `default` when provider defaults are intentional.

Do not replace `<provider:model>` with the catalog default merely because it is
listed. Confirm that the current runtime adapter supports the entry's `api`
family first. Models marked `openai_responses` are routed through Azure's
Responses API rather than Chat Completions.

List selectable models and their resolved reusable prices with:

```bash
uv run python -m src.model_configuration list
```

`models.yaml` owns project model selection; `model_pricing.yaml` owns reusable,
reviewed rates and may be referenced by multiple provider aliases. Both are
non-secret; provider credentials remain in `.env`. Prices are never fetched or
silently refreshed during an eval. The resolved pricing record is frozen into
run identity and results.

## Development Validation Is Not An Eval

When writing or editing an agent, run focused tests and one known example
through the exact-example pipeline runner before considering the agent ready
for evaluation:

```bash
uv run python -m src.pipelines.pipeline_run_from_yaml pipeline_configs/v1_3.ppln \
  --project-key spirax-pulse \
  --azure-postgres-host <postgres-host> \
  --azure-postgres-database <postgres-database> \
  --azure-postgres-user <entra-login> \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --example-id '<example-id>' \
  --ai-model <provider:model> \
  --ai-reasoning-effort medium
```

Example IDs can contain `|`, so quote them. This command validates one unit
without creating an eval result that appears in the explorer.

Do not run a one-example eval automatically before a section or full-benchmark
eval. A one-example or one-unit eval is appropriate only when that narrow
scope is the requested measurement or when debugging an existing eval failure.
After development validation passes, run the requested eval scope directly.

## Scope Options

Choose exactly one of the three supported scope forms:

- `--example-ids <id> [<id> ...]`: exact immutable benchmark examples.
- `--unit-ids <id> [<id> ...]`: every selected example for those units.
- `--section <key-or-label>`: examples in a named use-case section from the
  selected evaluation profile. Repeat it to select the union of named sections.
- `--all-examples`: every example in the selected benchmark version. The
  non-interactive CLI requires this flag or one of the choices above.

`--example-ids` and `--unit-ids` are the explicit-list form and must not be
combined with each other or a named section. Profile predicates remain an
internal implementation detail; operators select a named section.

For example, run every approved Open Failure example once with the catalog
default model after substituting a key and version confirmed by discovery:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --section 'Open Failure' \
  --ai-model azure:gpt-5.6-luna \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime threaded \
  --max-workers 4
```

## Benchmark Discovery And Availability

Before a new live run, or whenever the environment or catalog may have changed,
run the interactive chooser with the hosted data-plane identities explicit:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --azure-postgres-host misprx-lb-dv-pg-qdol4f5j2ozla.postgres.database.azure.com \
  --azure-postgres-database label_benchmark \
  --azure-postgres-user kurt.neuens@mesh-systems.com \
  --azure-storage-account-url https://misprxlbdvqdol4f5j2ozla.blob.core.windows.net \
  --azure-storage-container source-snapshots
```

With the complete `--azure-postgres-*` arguments above, discovery uses direct
Entra-authenticated Azure PostgreSQL. Without them, the repository falls back
to `DATABASE_URL` when it is set; this repository's normal local environment
may therefore show a local catalog instead of hosted Azure state. The message
`Retrieving published benchmarks for spirax-pulse from Azure...` is emitted
before connection-path verification and is not evidence that Azure was queried.
Do not use the bare chooser to establish hosted availability.

Record the selected benchmark key and version, then use the fully explicit
command for subsequent runs in the same environment. Repeat discovery after
publication changes or when an explicit command reports that its benchmark is
unavailable. Do not use the interactive form in automation; resolve and
validate the key/version before starting unattended work.

`workbench.project.json` is the project-owned compatibility allow-list, not a
live catalog cache. A configured benchmark identity or a retained run proves
what the project supports or historically evaluated; neither proves that the
version is currently retrievable from Benchmark Studio. A runnable selection
must be both currently published and present in that compatibility allow-list;
if there is no intersection, stop and resolve the catalog/configuration mismatch
rather than editing compatibility metadata merely to make the run start. Do not
put claims such as "the only available benchmark" in durable documentation. If
a temporary catalog snapshot is useful for an incident or handoff, record the
environment and verification timestamp outside the reusable command templates.

## Prerequisites

- Run from the repository root with dependencies installed by `uv`.
- Set `APP_PROJECT_KEY=spirax-pulse` or pass `--project-key spirax-pulse`.
- Pass the hosted PostgreSQL host, database, Entra login, Blob account URL, and
  container explicitly for both discovery and execution. These are non-secret
  resource identities. Complete `AZURE_POSTGRES_*` and Azure Storage
  environment settings are supported, but do not rely on an ambiguous
  `DATABASE_URL` fallback for hosted discovery.
- Sign in with Azure CLI so `DefaultAzureCredential` can obtain short-lived
  PostgreSQL and Blob tokens. PostgreSQL must have Entra authentication enabled,
  the login must be mapped to a database role, the local public IP must be
  allowed by the server firewall, and the identity needs container-scoped
  `Storage Blob Data Reader` for immutable evidence.
- Direct PostgreSQL retrieval starts every connection with an explicit
  read-only transaction. Do not use exported database passwords, storage keys,
  SAS tokens, or Container App exec.
- Configure credentials required by the selected model provider.
- Check `models.yaml` for the model's `api` family. Catalog membership means the
  model is selectable; the runtime adapter must also support that API family.

## Results

The command prints the exact result file when it completes. For `v1_3`, files
are written under:

```text
eval_results/working/<benchmark-key>/v<version>/<run-id>/
  manifest.json
  agent-version.json
  attempts/<prefix>/<work-item-id>.<generation>.json  # detailed, local, Git-ignored
  result.json
  performance/                     # disposable and ignored by Git
    attempts/<prefix>/<work-item-id>.<generation>.json
    invocations/<invocation-id>.<event>.json
    summary.json
  review/
    capture.json
    index.json
    executions/<prefix>/<execution-id>.json
    objects/sha256/<prefix>/<content-hash>
  diagnosis/                       # optional compact retained review notes
```

Every new run is a working eval with a unique occurrence ID. The separate
`run_spec_sha256` deterministically hashes the resolved source-content
manifest, pipeline, benchmark, profile/graders, model, reasoning, scope,
repetitions, runtime, worker limit, error policy, and configuration dimensions.
Running the identical command again starts a new occurrence. Resume requires
the exact existing occurrence through `--run-id eval_<occurrence>`.

Working `manifest.json`, `agent-version.json`, immutable attempts,
`result.json`, review, and performance detail support immediate debugging and
resume. A meaningful complete run is preserved through `$eval-lifecycle`,
which creates compact aggregate retained artifacts and the linked meaningful
agent version. The working manifest retains every selected example's complete
frozen source-snapshot window, Azure storage identity, recipe, known gaps, and
raw artifact object key, byte size, and SHA-256 contract.

Result schema version 2 separates durable evaluation evidence from disposable
performance diagnostics. Its summary contains `accuracy`, `reliability`,
`scoring_coverage`, `usage`, `cost`, `nondeterminism`,
`execution_recovery`, and aggregate active evaluation wall time. Accuracy
includes only runs with a valid configured output contract whose deterministic
graders all completed.
Provider, pipeline, timeout, cancellation, identity, missing, malformed,
partial-output, and grader failures remain fully recorded but are excluded from
accuracy denominators. `scoring_coverage` shows how many planned attempts
reached grading, while `reliability` reports execution and output-contract
status counts.

`summary.execution_recovery` records logical slots, missing work, total
execution generations, and selected reruns. `summary.usage` and `summary.cost`
retain availability explicitly. Current receipts preserve
model requests, input/output/cache/reasoning tokens, tool calls, and direct
workflow output attempts when reported.

The CLI reports total input, output, cached-input, reasoning, and overall
tokens. Cost summary preserves actual, complete-estimate, partial-estimate, and
unavailable status. For each currency it reports total, average per completed
unit, P5, and P95 calculated from complete per-unit observations, plus counts
of units with complete, partial, or unusable cost information.

Estimated model costs use the conservative `assume_uncached` input-pricing
policy: every provider-reported input token is priced at the ordinary input
rate. Provider-reported cache reads and writes remain available in usage
diagnostics, but they do not reduce estimated cost or create partial pricing
coverage. Each new run freezes this policy in its model identity.

`performance/summary.json` contains short-lived wall time, throughput, stage
timings, retry telemetry, and model/API-call durations, including the exact
work item and execution for the slowest calls. Primary aggregates contain only
the latest durable generation for each logical work item; superseded telemetry
is not mixed into the current run view. Adapter-owned HTTP observations
include attempt duration, terminal status, retry category, configured request
timeout, and available provider/client request IDs. HTTP transport-attempt
counts remain `unavailable` when the backend does not expose them; configured
limits are never presented as observations. A
`duration_exceeded_configured_timeout` value is a duration-boundary signal, not
proof that the provider raised a timeout. The complete `performance/`
directory may be deleted without invalidating or reducing the durable
evaluation result. The explorer reports this deletion as performance
`unavailable` while keeping quality, attempts, and evidence usable. Capture,
materialization, filesystem, or malformed-data failures are likewise nonfatal
to durable attempts and results and are surfaced as warnings or unavailable
diagnostics.

`review/` is a disposable, local-only inspection bundle. It is not part of
`run_id`, attempt integrity, scoring, resume, or `result.json`. Benchmark source
evidence remains in immutable Azure storage and is represented locally by a
credential-free identity/hash reference. Exact generated images, long prompts,
model transcripts, tool activity, and validation history are content-addressed
and de-duplicated only within the run. No review artifact is uploaded to Azure.

Review capture defaults to `full` for executed attempts. Use
`--review-capture off` when detailed local review is not needed. Dry-run and
status operations do not capture new review content.

Each execution capture is journaled before local objects are promoted. Startup
recovers interrupted transactions, retaining objects only when the exact
committed execution manifest exists. The derived schema-v2 `review/index.json`
fingerprints result, attempt-generation, capture, manifest, object, and staging
state and is rebuilt automatically when any input changes. Capture status and
bundle integrity are reported separately; an integrity-invalid review bundle
does not invalidate the durable eval result.

Capture state is evidence-based: `in_progress` while executions are being
recorded, then `complete`, `partial`, or `failed` after reconciliation with the
durable attempt IDs. A capture failure is nonfatal to the durable eval result.
The inspection CLI and explorer identify unavailable detail as `disabled`,
`capture_failed`, `capture_partial`, `pruned`, or `absent`, so missing
diagnostics are not confused with a failed or low-quality agent output.

`run.dimensions.evaluation_profile` records the profile ID, version, and
content hash.
`manifest.json` preserves each example's complete published `benchmark_labels`,
even when the profile grades only a subset. Immutable attempts preserve
canonical `agent_output`, `evaluations`, usage, cost, contract errors, and
failure details. Detailed rows are reconstructed on demand through the
inspection CLI or `LocalRunStore.evaluation_rows()`; they are not repeated in
`result.json`.

Verify the three evidence classes independently after a run:

```bash
# Durable run/result integrity and terminal work state
uv run python -m src.evals.eval_orchestration --status-run-id eval_<hash>

# Disposable review status/counts; this remains useful when detail is absent
uv run python -m src.evals.inspection_cli summary --run eval_<hash>

# Optional disposable performance observations
eval_run_dir='eval_results/working/<benchmark>/v<version>/eval_<hash>'
if test -f "$eval_run_dir/performance/summary.json"; then
  uv run python -m json.tool "$eval_run_dir/performance/summary.json" >/dev/null
else
  echo "Performance diagnostics unavailable; durable eval remains valid."
fi
```

Absence of `performance/summary.json` means timing and retry diagnosis is
unavailable; it does not invalidate the durable result. Review capture may
independently be `in_progress`, `complete`, `partial`, or `failed`; elevated
retained evals report detailed review as `pruned`.

CLI exit codes are `0` for a fully scored completion, `2` for argument/preflight
errors, `3` when durable execution completes with terminal unscored work, `4`
for storage-integrity failure, and `130` for operator interruption.

## Explore Results Locally

Build the local UI once after installing its dependencies, then launch the
read-only explorer from the repository root:

```bash
cd www
pnpm install
pnpm build
cd ..
APP_PROJECT_KEY=spirax-pulse uv run python -m src.apps.eval_explorer
```

Open `http://127.0.0.1:8765`. Select a working run to filter attempts and
inspect expected/actual outputs, grading, model interactions, pipeline/tool
activity, and raw review data. Select a retained eval to inspect its compact
full outputs and grading; tool traces and performance detail are intentionally
unavailable. The Evidence package tab reads the selected eval's exact Azure
artifact references, verifies the immutable objects, and renders the normalized
Spirax charts used by Benchmark Studio. Every supported run is required to
contain the current frozen evidence and published review-context contracts.
If review capture was off, failed, partial, pruned, or absent, compact result
rows remain available and the detailed tabs state the specific reason the
review is unavailable.

The server deliberately binds only to `127.0.0.1`; this MVP has no remote auth
or write endpoints. Re-run `pnpm build` after frontend changes.

## Reliability And Transient Failures

AI processor `transport_retries` values are total HTTP attempts, including the
initial request. A value of `3` therefore allows two retries after transient
timeouts, connection failures, rate limits, and retryable server responses.
The v1_3 pipeline keeps a 120-second timeout per attempt and uses three
transport attempts.

Persisted `run.dimensions.execution.ai_execution_policies` records the
configured timeout and retry policy for every AI processor. Observed request
counts, retry availability,
model/API durations, and timeout overruns belong to optional
`performance/summary.json`; configured limits are not observations. Failed
runs also include
`failure_details`, with the failed stage, pipeline and stage correlation IDs,
and a bounded exception chain. Use `summary.reliability.failures_by_type` to
separate `timeout`, `transport_error`, `provider_error`, pipeline,
`receipt_identity_error`, `output_missing`, `output_malformed`,
`output_partial`, and `grader_error` outcomes. All remain excluded from
valid-run accuracy.

## Interruption And Resume

Every terminal attempt is committed immediately. On `Ctrl-C` or another
cooperative interruption, the runner reports the incomplete run ID, current
state counts, manifest path, and an exact shell-safe resume command. Run that
command unchanged. It includes `--run-id` for the exact occurrence; completed
units keep their durable results and only missing units execute.

Failed, invalid, and incorrect terminal results remain inspectable completed
work. Selective failure reruns are not part of the supported MVP workflow.
Deleted runs cannot be resumed.

Inspect local durable state without Azure or provider bootstrap:

```bash
uv run python -m src.evals.eval_orchestration \
  --status-run-id eval_<hash>
```

## Compare Completed Results

Comparison happens after evals complete. Use Codex with
`$eval-results-analysis` or select retained runs in the local read-only
explorer. Keep execution focused on producing one durable result per explicit
agent/model/scope configuration.

## Ephemeral Coding-Agent Review

Use progressive disclosure instead of loading an entire result and every
binary artifact into context:

```bash
# Bounded run summary and review size/status
uv run python -m src.evals.inspection_cli summary --run eval_<hash>

# Select compact rows
uv run python -m src.evals.inspection_cli list \
  --run eval_<hash> \
  --filter incorrect \
  --limit 20

# Drill into one example or exact execution; large text resolves only on request
uv run python -m src.evals.inspection_cli example \
  --run eval_<hash> \
  --example '<example-id>'

uv run python -m src.evals.inspection_cli execution \
  --run eval_<hash> \
  --execution '<work-item-id>.<generation>' \
  --section model_interactions \
  --resolve-text

# Verify hashes and inspect local storage cost
uv run python -m src.evals.inspection_cli verify --run eval_<hash>
uv run python -m src.evals.inspection_cli size --run eval_<hash>
```

Optionally retain a compact coding-agent diagnosis from a JSON object, with an
additional Markdown note when useful:

```bash
uv run python -m src.evals.inspection_cli diagnose \
  --run eval_<hash> \
  --input diagnosis.json \
  --markdown diagnosis.md
```

## Working And Retained Lifecycle

List explicit lifecycle state:

```bash
uv run python -m src.eval_lifecycle.cli list --state all --json
uv run python -m src.eval_lifecycle.cli inspect eval_<hash> --json
```

Preview and explicitly elevate a meaningful complete full run:

```bash
uv run python -m src.eval_lifecycle.cli elevate eval_<hash> --dry-run --json
uv run python -m src.eval_lifecycle.cli elevate eval_<hash> --yes --json
uv run python -m src.eval_lifecycle.cli verify ret_<hash> --json
```

The retained folder contains `manifest.json`, `result.json`, aggregate
`units.json`, `agent-provenance.json`, `evidence-references.json`, and optional
`agent.patch`. It preserves full final AI outputs, expected outputs, validation,
grading, accuracy, usage, and cost. It prunes performance, invocation, tool,
and intermediate review detail and never copies Azure evidence locally.

Permanently delete exact evals only after explicit confirmation:

```bash
uv run python -m src.eval_lifecycle.cli delete working eval_<hash> --yes --json
uv run python -m src.eval_lifecycle.cli delete retained ret_<hash> \
  --confirm-retained ret_<hash> --json
```

Deletion is immediate and not recoverable. A deleted working run cannot resume.
Retained deletion preserves a shared agent version until no retained eval
references it. The local app only filters and reviews All, Working, and
Retained; it has no elevate or delete actions.

## Fast Diagnosis

- Azure Blob status `206` is a successful ranged download.
- `Retrieving published benchmarks...` means `--benchmark-key` was omitted; it
  does not prove that the repository selected the Azure connection path.
- A `400` mentioning `/v1/responses` means the chosen model requires the
  Responses API but the runtime sent Chat Completions.
- Interrupting a run can produce worker and tracing shutdown output. Completed
  attempts are already durable; rerun the identical command for missing slots.

Use `uv run python -m src.evals.eval_orchestration --help` to verify the current
CLI flags if code and this runbook diverge.
