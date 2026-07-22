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
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --all-examples \
  --ai-model <provider:model> \
  --ai-reasoning-effort <low|medium|high> \
  --runs-per-example <count> \
  --runtime threaded \
  --max-workers <count> \
  --error-action continue
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
remove `--example-ids` and use repeated threaded runs for the full benchmark.

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
- `--agent-version <version>`: persist the stable agent/package revision used
  for cross-result grouping when one exists.
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

`Retrieving published benchmarks for spirax-pulse from Azure...` launches a
remote Azure Container App query and can take a while. Record the selected
benchmark key and version, then use the explicit command for subsequent runs.
Do not use the interactive form in automation.

## Prerequisites

- Run from the repository root with dependencies installed by `uv`.
- Set `APP_PROJECT_KEY=spirax-pulse` or pass `--project-key spirax-pulse`.
- Sign in with Azure CLI. The CLI reads the benchmark through the deployed
  `label-benchmark` Container App and obtains read-only Blob configuration from
  the hosted environment.
- Configure credentials required by the selected model provider.
- Check `models.yaml` for the model's `api` family. Catalog membership means the
  model is selectable; the runtime adapter must also support that API family.

## Results

The command prints the exact result file when it completes. For `v1_3`, files
are written under:

```text
eval_results/v1_3/<benchmark-key>/v<version>/runs/<run-id>/
  manifest.json
  attempts/<prefix>/<work-item-id>.<generation>.json
  invocations/<invocation-id>.<event>.json
  result.json
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

`manifest.json` and immutable attempt generations are the recovery source of
truth. `result.json` is an atomically rebuilt schema-v3 view. Confirm
`run_config` records the intended run ID and conditions before comparison.

Result schema version 3 separates the summary into `accuracy`, `reliability`,
`scoring_coverage`, and `performance`. Accuracy includes only runs with a valid
configured output contract whose deterministic graders all completed.
Provider, pipeline, timeout, cancellation, identity, missing, malformed,
partial-output, and grader failures remain fully recorded but are excluded from
accuracy denominators. `scoring_coverage` shows how many planned attempts
reached grading, while `reliability` reports execution and output-contract
status counts. `performance` records wall time, throughput, run-duration
statistics, and available stage timings.

`summary.execution_recovery` records logical slots, missing work, total
execution generations, and selected reruns. `summary.usage`, `summary.retries`,
and `summary.cost` retain availability explicitly. Current receipts preserve
model requests, input/output/cache/reasoning tokens, tool calls, and direct
workflow output attempts when reported. HTTP transport-attempt counts and
provider-billed cost remain `unavailable` when the backend does not expose
them; configured limits are never presented as observations.

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

`run_config.evaluation_profile` records the profile ID, version, and content
hash. Each result preserves the complete published `benchmark_labels`, even
when the profile grades only a subset. Per-attempt `fields` record
applicability, expected and actual values, confidence, grader identity,
normalization, and correctness.

CLI exit codes are `0` for a fully scored completion, `2` for argument/preflight
errors, `3` when durable execution completes with terminal unscored work, `4`
for storage-integrity failure, and `130` for operator interruption.

## Reliability And Transient Failures

AI processor `transport_retries` values are total HTTP attempts, including the
initial request. A value of `3` therefore allows two retries after transient
timeouts, connection failures, rate limits, and retryable server responses.
The v1_3 pipeline keeps a 120-second timeout per attempt and uses three
transport attempts.

Persisted `run_config.ai_execution_policies` records the effective timeout and
retry policy for every AI processor. Failed runs also include
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

## Fast Diagnosis

- Azure Blob status `206` is a successful ranged download.
- `Retrieving published benchmarks...` means `--benchmark-key` was omitted.
- A `400` mentioning `/v1/responses` means the chosen model requires the
  Responses API but the runtime sent Chat Completions.
- Interrupting a run can produce worker and tracing shutdown output. Completed
  attempts are already durable; rerun the identical command for missing slots.

Use `uv run python -m src.evals.eval_orchestration --help` to verify the current
CLI flags if code and this runbook diverge.
