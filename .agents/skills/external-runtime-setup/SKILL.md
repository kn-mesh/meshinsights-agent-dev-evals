---
name: external-runtime-setup
description: Configure external auth, environment bootstrap, provider credentials, telemetry, and runtime AI overrides for this repo. Use this skill when a request involves `.env` setup, `mi auth`, provider:model validation, Logfire setup, bootstrap startup order, or troubleshooting AI-enabled pipeline and eval runs.
---

# External Runtime Setup

Use this skill for project-level setup that depends on external systems rather than pipeline business logic. It covers provider credentials, `.env` conventions, telemetry, and runtime override behavior for AI-enabled runners.

## Scope Of This Skill

This skill defines recommended runtime-setup patterns for an AI coding agent working in an `mi-core` style repo.

Treat it as default guidance for auth, telemetry, and runtime override structure, not as a guarantee that every existing runner in the repo already implements every recommendation exactly as written.

Rules:
- Prefer these patterns by default when adding or cleaning up runtime setup.
- If the repo already has a different but coherent setup path, treat the local implementation as the source of truth unless the user asks to migrate it.
- Keep concrete CLI usage, env-var names, and startup-order references accurate.
- When this skill describes centralized validation or setup structure, read that as the preferred architecture for agent-built work unless the repo deliberately differs.

Use this skill alongside:
- `$pipeline-builder` when building pipeline runners.
- `$ai-processor-builder` when AI processors need provider-backed execution.
- `$agent-eval-builder` when eval orchestration depends on hosted models or tracing.

## Repository-local mi-core

- Treat `mi-core/` as editable source in this repository, not as a static imported package.
- Its current checkout path is `/Users/kurt.neuens/Desktop/Code - Product/meshinsights-agent-dev-evals-mvp/mi-core`; use the repo-relative `mi-core/` path in code and documentation.
- Runtime source lives under `mi-core/core/src/mi/`, and CLI source lives under `mi-core/cli/src/cli/`.
- The root `uv` environment installs both as editable local sources. Inspect or modify that source when runtime or CLI behavior itself must change, then run the relevant `mi-core` tests.

## What Belongs Here

Use this skill when the user asks you to:
- configure `.env` or `.env` templates,
- set up or troubleshoot `mi auth`,
- validate `provider:model` identifiers,
- wire provider credential checks into a runner,
- configure Logfire or AI tracing,
- debug AI startup failures caused by missing auth, env bootstrap, or telemetry setup.

Do not put auth or telemetry setup logic inside processors.

## Environment Bootstrap

On current `mi-core`, pipeline and orchestrator execution bootstraps environment variables from `.env` automatically by default.

Use that default for normal pipeline and eval runs.

If a top-level script, app, or runner validates providers, initializes telemetry, or constructs AI backends before calling `pipeline.run()` or `orchestrator.run()`, call `bootstrap_environment()` explicitly at startup:

```python
from mi.core import bootstrap_environment

bootstrap_environment()
```

Rules:
- Never commit secrets.
- Keep secret values in `.env` or CI secret stores.
- Keep bootstrap logic in runners or app startup, not in processors.
- Fail fast with explicit auth and validation errors.

## Published Benchmark And Evidence Access

The active Spirax operator CLI uses hosted data access as follows:

| Input | Purpose |
|---|---|
| `APP_PROJECT_KEY` | Scopes every benchmark query to the configured Benchmark Studio project |
| `AZURE_POSTGRES_HOST`, `AZURE_POSTGRES_DATABASE`, `AZURE_POSTGRES_USER` | Select the hosted publication database and Entra-mapped login without a password |
| `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_CONTAINER` | Select immutable evidence without a connection string |
| Azure identity | Supplies short-lived PostgreSQL and Blob tokens through `DefaultAzureCredential` |

Password-based test injection may use `DATABASE_URL`, but hosted operator
execution must not depend on database
passwords, Container App exec, secret extraction, shared keys, or SAS tokens.
There is no MongoDB, local benchmark JSON, or filesystem snapshot fallback.

## `.env` And Template Files

Create a `.env` file at repo root for local development.

If you want `mi auth` to detect the relevant providers more reliably, keep a template file in one of these supported names:
- `.env.template`
- `.env.example`
- `env.template`
- `env.example`

Template files should contain variable names and placeholders only, never real secrets.

`mi auth` uses the template to:
- detect which providers are relevant,
- preserve comments and grouping,
- seed a new `.env` from the template structure.

## `mi auth`

Prefer `uv run mi auth` so the CLI comes from the project environment.

`mi auth` is provided by `meshinsights-cli`, not `mi-core` itself. If the repo-managed install is unreliable on a machine, a separately installed machine-level `mi auth` is an acceptable fallback.

Common commands:

```bash
uv run mi auth
uv run mi auth --provider azure_openai
uv run mi auth --provider azure_foundry
uv run mi auth --provider anthropic
uv run mi auth --provider google-gemini
uv run mi auth --provider openrouter
uv run mi auth --provider logfire
uv run mi auth --env-file .env.local
```

Fallback:

```bash
mi auth
mi auth --provider azure_openai
mi auth --provider logfire
```

What it does:
1. Scans `.env.template` or `.env.example` when present.
2. Lets you choose providers.
3. Retrieves credentials automatically where possible.
4. Writes or updates `.env`.

## Model Identifier Rules

Use canonical `provider:model` format and choose project-supported models from
the root `models.yaml`. That catalog owns the fast-moving identifiers and each
model's required API family.

Examples:
- `azure:gpt-5.6-luna`
- `azure:claude-sonnet-4-6`
- `google:gemini-3.5-flash`
- `openrouter:google/gemini-3.5-flash`

Rules:
- Keep provider support and credential mapping in runner validation, not in processor business logic.
- Do not use unsupported `openai:*` identifiers.

## Provider Credential Mapping

Use centralized runner-side validation to map catalog API families and model
providers to required environment variables.

Current mapping:

| Catalog API/provider | Required env vars |
|---|---|
| `openai_chat_completions` with `azure:*` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION` |
| `openai_responses` with `azure:*` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`; the backend normalizes the endpoint to `/openai/v1` and does not send the dated API version |
| `anthropic_messages` with `azure:*` | `ANTHROPIC_FOUNDRY_API_KEY`, plus `ANTHROPIC_FOUNDRY_RESOURCE` or `ANTHROPIC_FOUNDRY_BASE_URL` |
| `anthropic_messages` with `anthropic:*` | `ANTHROPIC_API_KEY` |
| `google_generate_content` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `openai_chat_completions` with `openrouter:*` | `OPENROUTER_API_KEY` |

Notes:
- `anthropic:*` may also use `ANTHROPIC_BASE_URL` for Anthropic-compatible Azure-hosted routing.
- `azure:claude-*` should resolve credentials from environment variables directly; do not require explicit `provider_options` for the standard path.
- If runner code supports provider option overrides such as Azure deployment overrides, keep that logic centralized there.

## Runtime AI Overrides

Prefer runtime overrides when comparing models or reasoning effort without editing source YAML:
- `--ai-model <provider:model>`
- `--ai-reasoning-effort <low|medium|high>`

Recommended runner behavior:
1. Create a temporary runtime YAML with overrides applied only to AI processor entries.
2. Execute using the temporary YAML.
3. Delete the temporary file after the run.

Never modify the source YAML in place.

## Telemetry And Tracing

For normal pipeline and orchestrator runs on current `mi-core`, telemetry bootstrap is also automatic by default.

For top-level apps or custom runners that initialize observability before pipeline execution, use this startup order:
1. `bootstrap_environment()`
2. `bootstrap_telemetry()`
3. `logfire.instrument_pydantic_ai(include_content=True, include_binary_content=True)`

If you skip pydantic-ai instrumentation, you will usually get pipeline spans but not full prompt and response payloads.

### Logfire authentication options

Option A with `mi auth`:
- `uv run mi auth --provider logfire`
- or `mi auth --provider logfire` if the CLI is installed separately

Option B for local manual setup:

```bash
uv run logfire auth
uv run logfire projects use <project-name>
```

Option C for CI or shared environments:
- set `LOGFIRE_TOKEN` in the environment or secret store

If `LOGFIRE_TOKEN` is set, it takes precedence over stored CLI credentials and project selection.

## Data Sensitivity

`include_content=True` captures prompt and response text. If policy requires metadata-only traces, set `include_content=False`.

## Troubleshooting Checklist

1. Provider validation fails:
   verify the model prefix and required environment variables.
2. Model identifier is rejected:
   confirm `provider:model` format and avoid unsupported `openai:*` names.
3. No telemetry appears:
   verify auth or token setup, then confirm both telemetry bootstrap and pydantic-ai instrumentation are happening.
4. Auth behaves unexpectedly:
   check for conflicting environment variables that override CLI credentials, especially `LOGFIRE_TOKEN`.
5. `mi auth` does not detect the right providers:
   add or update an `.env.template` or `.env.example` file.
6. Azure identity retrieval fails:
   verify Azure CLI is installed and logged in for local development, or that
   the hosted workload identity is configured.
7. Evidence returns `403`:
   verify the same principal has container-scoped `Storage Blob Data Reader` on
   the Benchmark Studio evidence container.

## Expected Behavior When Using This Skill

When using this skill:
- keep setup and validation in runners or app startup,
- keep secrets out of the repo,
- centralize provider-to-credential mapping,
- use runtime overrides for comparisons instead of editing source YAML,
- separate auth and tracing concerns from processor business logic.
