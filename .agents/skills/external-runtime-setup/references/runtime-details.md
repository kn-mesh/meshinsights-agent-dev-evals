# Runtime Details

Read this reference only while configuring or diagnosing external runtime
integration. Confirm fast-moving names against current runner and `mi-core`
source before changing code.

## Hosted Benchmark And Evidence Identity

| Input | Purpose |
|---|---|
| `APP_PROJECT_KEY` | Scope benchmark queries to the configured project |
| `AZURE_POSTGRES_HOST`, `AZURE_POSTGRES_DATABASE`, `AZURE_POSTGRES_USER` | Hosted publication database and Entra-mapped login |
| `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_STORAGE_CONTAINER` | Immutable evidence location |
| Azure identity | Short-lived PostgreSQL and Blob tokens through `DefaultAzureCredential` |

`workbench.project.json` is the compatibility allow-list; CLI arguments and
environment variables are connection inputs. Operator commands must fail before
querying or writing run state when the effective project, PostgreSQL host and
database, Blob account, or container differs from that contract.

`DATABASE_URL` is permitted for test injection only. Hosted operator execution
must not depend on passwords, Container App exec, secret extraction, shared
keys, SAS tokens, local benchmark JSON, or filesystem snapshots.

## `mi auth`

Prefer the project CLI:

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

A machine-level `mi auth` is an acceptable fallback when the repo-managed
`meshinsights-cli` install is unavailable. Templates may be named
`.env.template`, `.env.example`, `env.template`, or `env.example`; include
placeholders only.

## Provider Credential Mapping

| Catalog API/provider | Required environment |
|---|---|
| `openai_chat_completions` with `azure:*` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION` |
| `openai_responses` with `azure:*` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` |
| `anthropic_messages` with `azure:*` | `ANTHROPIC_FOUNDRY_API_KEY` and either `ANTHROPIC_FOUNDRY_RESOURCE` or `ANTHROPIC_FOUNDRY_BASE_URL` |
| `anthropic_messages` with `anthropic:*` | `ANTHROPIC_API_KEY` |
| `google_generate_content` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `openai_chat_completions` with `openrouter:*` | `OPENROUTER_API_KEY` |

The Responses backend normalizes the Azure endpoint to `/openai/v1` and does
not send the dated API version. `anthropic:*` may use `ANTHROPIC_BASE_URL` for
compatible hosted routing. Keep provider-option overrides centralized.

## Logfire

After environment and telemetry bootstrap, instrument pydantic-ai only when
content capture is allowed:

```python
logfire.instrument_pydantic_ai(
    include_content=True,
    include_binary_content=True,
)
```

Authenticate with `uv run mi auth --provider logfire`, local `logfire auth`
plus project selection, or `LOGFIRE_TOKEN` in managed environments. An
environment token takes precedence over stored CLI credentials.

## Troubleshooting

- Provider validation: check catalog prefix, API family, and mapped variables.
- Model rejection: require canonical `provider:model` from `models.yaml`.
- Missing traces: verify Logfire auth, telemetry bootstrap, and instrumentation.
- Unexpected auth: inspect higher-precedence environment variables.
- Provider discovery: add a placeholder-only env template.
- Azure identity failure: verify local Azure login or workload identity.
- Evidence `403`: verify container-scoped `Storage Blob Data Reader` for the
  same principal.
