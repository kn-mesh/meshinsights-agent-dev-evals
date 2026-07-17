# Spirax Pulse Eval Runbook

Use this runbook to execute the `v1_3` pipeline against an immutable published
benchmark version for the `spirax-pulse` project.

## Current Full Benchmark Command

As verified from the published Azure catalog on July 17, 2026, the only
available benchmark is `phase-1-benchmark-3fb7f544`, version `1`, containing 70
examples. This command evaluates every example once:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --project-key spirax-pulse \
  --benchmark-key phase-1-benchmark-3fb7f544 \
  --benchmark-version 1 \
  --ai-model azure:gpt-5.6-luna \
  --ai-reasoning-effort medium \
  --runs-per-example 1 \
  --runtime threaded \
  --max-workers 4 \
  --error-action continue
```

This is a full 70-example model run and therefore incurs model usage. Use the
smoke-run pattern below when validating a new pipeline or model configuration.

## Prefer The Explicit Command

Pass the benchmark, version, model, and execution settings explicitly. This
skips the slow interactive benchmark-catalog query and makes the run
reproducible.

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --project-key spirax-pulse \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --ai-model <provider:model> \
  --ai-reasoning-effort <low|medium|high> \
  --runs-per-example <count> \
  --runtime threaded \
  --max-workers <count> \
  --error-action continue
```

Replace every angle-bracket placeholder. Choose `--ai-model` from
`models.yaml`. Keep `--benchmark-version` explicit for comparable runs;
omitting it selects the latest published version.

Do not replace `<provider:model>` with the catalog default merely because it is
listed. Confirm that the current runtime adapter supports the entry's `api`
family first. Models marked `openai_responses` are routed through Azure's
Responses API rather than Chat Completions.

## Recommended First Run

Run one known example serially before evaluating the full benchmark:

```bash
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
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
- `--classifications <label> [<label> ...]`: examples with those approved
  classification labels.
- No scope flag: every example in the selected benchmark version.

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
src/evals/eval_results_v1_3/<benchmark-key>/v<version>/<scope>/*.json
```

Confirm `run_config` records the intended benchmark version, model, reasoning
effort, runtime, worker count, and run count before comparing results.

## Fast Diagnosis

- Azure Blob status `206` is a successful ranged download.
- `Retrieving published benchmarks...` means `--benchmark-key` was omitted.
- A `400` mentioning `/v1/responses` means the chosen model requires the
  Responses API but the runtime sent Chat Completions.
- Interrupting a threaded run can produce worker and tracing shutdown output;
  that output is secondary to the first pipeline or model error above it.

Use `uv run python -m src.evals.eval_orchestration --help` to verify the current
CLI flags if code and this runbook diverge.
