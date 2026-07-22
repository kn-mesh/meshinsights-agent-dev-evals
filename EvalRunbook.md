# Spirax Pulse Eval Runbook

Use this runbook to execute the `v1_3` pipeline against an immutable published
benchmark version for the `spirax-pulse` project.

## Current Full Benchmark Command

As verified from the published Azure catalog on July 17, 2026, the only
available benchmark is `phase-1-benchmark-3fb7f544`, version `1`, containing 70
examples. This command evaluates every example once:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --azure-postgres-host misprx-lb-dv-pg-qdol4f5j2ozla.postgres.database.azure.com \
  --azure-postgres-database label_benchmark \
  --azure-postgres-user kurt.neuens@mesh-systems.com \
  --azure-storage-account-url https://misprxlbdvqdol4f5j2ozla.blob.core.windows.net \
  --azure-storage-container source-snapshots \
  --benchmark-key phase-1-benchmark-3fb7f544 \
  --benchmark-version 1 \
  --all-examples \
  --ai-model azure:gpt-5.6-luna \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime threaded \
  --max-workers 4 \
  --error-action continue \
  --review-capture full
```

This is a full 70-example model run and therefore incurs model usage. Use the
smoke-run pattern below when validating a new pipeline or model configuration.

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
  --error-action continue \
  --review-capture <full|off>
```

Replace every angle-bracket placeholder. Choose `--ai-model` from
`models.yaml`. Keep `--benchmark-version` explicit for comparable runs;
the non-interactive CLI requires it rather than silently selecting latest.

Every run automatically resolves the matching
`agent_version_configs/<pipeline-stem>.agent.yaml`, creates an immutable
candidate manifest, and writes it beside the durable run. Use
`--agent-version-id av_<hash>` or `--require-promoted-agent-version` when a run
must use content already promoted into the local catalog. `--agent-version` is
retained only as a deprecated display label and is not identity.

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
Non-interactive execution requires `--ai-model` (or `--compare-model`) and an
explicit reasoning setting, including `default` when provider defaults are
intentional.

Do not replace `<provider:model>` with the catalog default merely because it is
listed. Confirm that the current runtime adapter supports the entry's `api`
family first. Models marked `openai_responses` are routed through Azure's
Responses API rather than Chat Completions.

## Recommended First Run

Run one known example serially before evaluating the full benchmark:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --example-ids '<example-id>' \
  --ai-model <provider:model> \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime serial \
  --max-workers 1 \
  --error-action stop
```

Example IDs can contain `|`, so quote them. After the smoke run succeeds,
replace `--example-ids` with `--all-examples` and use repeated threaded runs
for the full benchmark.

## Scope Options

Use only the filters needed for the intended scope. Multiple filter types are
combined as an intersection.

- `--example-ids <id> [<id> ...]`: exact immutable benchmark examples.
- `--unit-ids <id> [<id> ...]`: every selected example for those units.
- `--label-filter 'path=<json-scalar>'`: examples whose immutable benchmark
  label at `path` matches the JSON value. Repeat it to accept multiple values
  for one path. Quote string values, for example
  `--label-filter 'root_cause="Open Failure"'`.
- `--slice <slice-key>`: examples in a named slice from the selected evaluation
  profile. Repeat it to select the union of multiple slices.
- `--agent-version-id av_<hash>`: require an exact resolved candidate identity.
  `--agent-version` is only a deprecated display label and is not identity.
- `--dimension 'key=<json-scalar>'`: persist a project-relevant configuration
  dimension such as `--dimension 'prompt_revision=7'`. Repeat for additional
  grouping dimensions; keys must be unique.
- `--all-examples`: every example in the selected benchmark version. The
  non-interactive CLI requires this flag or one of the filters above.

For example, run every approved Open Failure example once with the catalog
default model:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --benchmark-key phase-1-benchmark-3fb7f544 \
  --benchmark-version 1 \
  --slice open-failure \
  --ai-model azure:gpt-5.6-luna \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime threaded \
  --max-workers 4 \
  --error-action continue
```

## One-Time Benchmark Discovery

If the benchmark key or version is unknown, run the interactive chooser once:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln
```

`Retrieving published benchmarks for spirax-pulse from Azure...` uses direct
Entra-authenticated PostgreSQL. Record the selected benchmark key and version,
then use the explicit command for subsequent runs. Do not use the interactive
form in automation.

## Prerequisites

- Run from the repository root with dependencies installed by `uv`.
- Set `APP_PROJECT_KEY=spirax-pulse` or pass `--project-key spirax-pulse`.
- Pass the hosted PostgreSQL host, database, Entra login, Blob account URL, and
  container. These are non-secret resource identities and may instead be set in
  `.env`.
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
eval_results/v1_3/<benchmark-key>/v<version>/runs/<run-id>/
  manifest.json
  agent-version.json
  attempts/<prefix>/<work-item-id>.<generation>.json
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

The run ID deterministically hashes the resolved source-content manifest,
pipeline, benchmark, profile/graders, model, reasoning, scope, repetitions,
runtime, worker limit, error policy, and configuration dimensions. Running the
identical command again resumes that run and does not duplicate completed work.

`manifest.json`, `agent-version.json`, immutable attempt generations, and the
atomically rebuilt `result.json` are durable schema-v1 evaluation evidence.
They are intended to be retained in Git. Confirm `run` records the intended
run ID and conditions and use `run.dimensions` for exact comparison identities.

Result schema version 1 separates durable evaluation evidence from disposable
performance diagnostics. Its summary contains `accuracy`, `reliability`,
`scoring_coverage`, `usage`, `cost`, `nondeterminism`, and
`execution_recovery`. Accuracy includes only runs with a valid configured
output contract whose deterministic graders all completed.
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
`--review-capture off` when detailed local review is not needed. Dry-run,
status, comparison-only, and materialize-only operations do not capture new
review content.

Capture state is evidence-based: `in_progress` while executions are being
recorded, then `complete`, `partial`, or `failed` after reconciliation with the
durable attempt IDs; explicit deletion records `purged`. A capture failure is
nonfatal to the durable eval result. The inspection CLI and explorer identify
unavailable detail as `disabled`, `capture_failed`, `capture_partial`,
`purged`, or `absent`, so missing diagnostics are not confused with a failed
or low-quality agent output.

`run.evaluation_profile` records the profile ID, version, and content hash.
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
eval_run_dir='eval_results/<pipeline>/<benchmark>/v<version>/runs/eval_<hash>'
if test -f "$eval_run_dir/performance/summary.json"; then
  uv run python -m json.tool "$eval_run_dir/performance/summary.json" >/dev/null
else
  echo "Performance diagnostics unavailable; durable eval remains valid."
fi
```

Absence of `performance/summary.json` means timing and retry diagnosis is
unavailable; it does not invalidate the durable result. Review capture may
independently be `in_progress`, `complete`, `partial`, `failed`, or `purged`.

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

Open `http://127.0.0.1:8765`. Select a retained run to filter attempts and
inspect expected/actual outputs, grading, model interactions, pipeline/tool
activity, and raw review data. The Evidence package tab retrieves the exact
published benchmark version recorded by that run, verifies its immutable Azure
artifacts, and renders the normalized Spirax charts used by Benchmark Studio.
If review capture was off, failed, partial, purged, or absent, compact result
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

Persisted `run.ai_execution_policies` records the configured timeout and retry
policy for every AI processor. Observed request counts, retry availability,
model/API durations, and timeout overruns belong to optional
`performance/summary.json`; configured limits are not observations. Failed
runs also include
`failure_details`, with the failed stage, pipeline and stage correlation IDs,
and a bounded exception chain. Use `summary.reliability.failures_by_type` to
separate `timeout`, `transport_error`, `provider_error`, pipeline,
`receipt_identity_error`, `output_missing`, `output_malformed`,
`output_partial`, and `grader_error` outcomes. All remain excluded from
valid-run accuracy.

## Resume And Selective Rerun

Every terminal attempt is committed immediately. After interruption, rerun the
same explicit command: default `--resume-mode missing` executes only logical
slots without a terminal generation.

- `--resume-mode missing-or-cancelled` includes stop-on-error cancellations.
- `--resume-mode failed` creates a new immutable generation only for failed or
  cancelled slots.
- `--resume-mode missing-or-failed` recovers all unhealthy/incomplete slots.
- `--rerun-failure-type provider_error` narrows a failed mode to one category.
- `--run-id eval_<hash>` fails if resolved conditions do not match that run.

A valid but incorrect answer is completed model work and is never selected by a
failed rerun. Earlier generations remain immutable; only the latest generation
represents that logical repetition in result metrics.

Use `--dry-run` for full identity/preflight/work selection without model
execution. Use the original explicit settings plus `--materialize-only` to
rebuild `result.json` without executing work.

Inspect local durable state without Azure or provider bootstrap:

```bash
uv run python -m src.evals.eval_orchestration \
  --status-run-id eval_<hash>
```

## Model And Configuration Comparison

Add one or more `--compare-model` flags to an explicit command to execute child
runs with identical non-model conditions and create a comparison manifest:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --evaluation-profile evaluation_configs/spirax-failure-evaluation.eval.yaml \
  --project-key spirax-pulse \
  --benchmark-key phase-1-benchmark-3fb7f544 \
  --benchmark-version 1 \
  --all-examples \
  --ai-model azure:gpt-5.6-luna \
  --compare-model azure:gpt-5.6-terra \
  --compare-model azure:gpt-5.6-sol \
  --ai-reasoning-effort high \
  --runs-per-example 3 \
  --runtime threaded \
  --max-workers 4 \
  --error-action continue
```

Comparisons are written under `v<version>/comparisons/`. Undeclared dimension
changes, mismatched scope, and mismatched repetition counts fail closed.

Compare existing deterministic results with explicitly allowed differences:

```bash
uv run python -m src.evals.eval_orchestration \
  --compare-result <first-result.json> \
  --compare-result <second-result.json> \
  --varying-dimension model.id
```

Declare every allowed difference, such as `model.provider`,
`model.reasoning_effort`, `pipeline.content_sha256`, or
`configuration.<key>`. This prevents prompt, evidence, tool, scoring, runtime,
or harness changes from being presented as model-only comparisons.

Comparison results include the aligned example, work-item, and execution IDs
behind improvements, regressions, changed incorrect outputs, new failures, and
recoveries. Use those execution IDs for paired review drill-down.

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

After review, preview and explicitly purge only the disposable review bundle:

```bash
uv run python -m src.evals.inspection_cli purge \
  --run eval_<hash> \
  --dry-run

uv run python -m src.evals.inspection_cli purge \
  --run eval_<hash> \
  --yes
```

Review-only purge retains `manifest.json`, immutable attempts, `result.json`,
candidate agent linkage, comparisons, and `diagnosis/`. Whole-run deletion is a
separate lifecycle operation. Purge validates one exact run and refuses broad,
ambiguous, or path-escaping targets.

## Local Catalog And Whole-Entity Deletion

List and verify managed schema-v1 runs, comparisons, and candidate/promoted
agent versions without contacting Azure:

```bash
uv run python -m src.lifecycle.cli catalog --json
uv run python -m src.lifecycle.cli verify --json
uv run python -m src.lifecycle.cli inspect run eval_<hash> --json
uv run python -m src.lifecycle.cli inspect version av_<hash> --json
```

The catalog is derived from immutable local records. Historical standalone
result JSON is unsupported; `eval_results/` contains only the managed
`runs/<run-id>/` and `comparisons/` layouts.

Use one flow for runs, comparisons, and promoted versions. Always inspect the
reference warnings in the preview before confirmation:

```bash
uv run python -m src.lifecycle.cli delete run eval_<hash> --dry-run --json
uv run python -m src.lifecycle.cli delete run eval_<hash> --yes --json
uv run python -m src.lifecycle.cli delete comparison cmp_<hash> --dry-run --json
uv run python -m src.lifecycle.cli delete version av_<hash> --dry-run --json
```

Confirmed deletion moves the exact paths into recoverable, Git-ignored local
quarantine. Restore while the original paths remain absent, or permanently
purge the quarantine with a second explicit confirmation:

```bash
uv run python -m src.lifecycle.cli restore del_<operation-id> --dry-run --json
uv run python -m src.lifecycle.cli restore del_<operation-id> --yes --json
uv run python -m src.lifecycle.cli purge del_<operation-id> --dry-run --json
uv run python -m src.lifecycle.cli purge del_<operation-id> --yes --json
```

Candidate-only versions live inside their eval runs and are removed by deleting
those runs. Deleting a promoted version includes its global manifest, aliases,
promotion events, and only CAS objects no retained promoted manifest uses.
Active runs, corrupt managed records, symlinks, ambiguous IDs, and broad paths
fail closed. Lifecycle operations never write to Azure or Benchmark Studio.

## Fast Diagnosis

- Azure Blob status `206` is a successful ranged download.
- `Retrieving published benchmarks...` means `--benchmark-key` was omitted.
- A `400` mentioning `/v1/responses` means the chosen model requires the
  Responses API but the runtime sent Chat Completions.
- Interrupting a run can produce worker and tracing shutdown output. Completed
  attempts are already durable; rerun the identical command for missing slots.

Use `uv run python -m src.evals.eval_orchestration --help` to verify the current
CLI flags if code and this runbook diverge.
