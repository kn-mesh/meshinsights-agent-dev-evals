---
name: external-runtime-setup
description: "Configure Agent Workbench external runtime integration: auth, environment bootstrap, provider credentials, hosted benchmark access, telemetry, model catalogs, pricing, and AI overrides. Use for `.env`, `mi auth`, provider:model validation, Logfire, or runtime failures."
---

# External Runtime Setup

Keep external-system setup in runners or application startup, separate from
pipeline business logic. Preserve a coherent local setup unless the user asks
to migrate it.

Use `$pipeline-builder` for runner integration, `$ai-processor-builder` for
processor behavior, and `$run-use-case-evals` for eval execution.

## Boundaries

- Never commit secrets; use `.env`, CI secrets, or workload identity.
- Keep provider validation, telemetry, and runtime overrides out of processors.
- Treat `models.yaml` as the project model/API catalog and
  `model-pricing.yaml` as reviewed reusable non-secret pricing.
- Inspect current runners and editable `packages/mi-core/` source when behavior
  matters.

## Startup Order

Normal pipeline and orchestrator runs bootstrap `.env` and telemetry through
current `packages/mi-core/` defaults. A top-level app or runner that validates providers
or initializes observability before execution must call:

```python
from mi.core import bootstrap_environment, bootstrap_telemetry

bootstrap_environment()
bootstrap_telemetry()
```

Instrument pydantic-ai afterward when prompt/response tracing is authorized.
Content capture may contain sensitive data; disable it when policy requires
metadata-only traces.

## Configure The Runtime

1. Create a root `.env` for local secrets. Keep a placeholder-only
   `.env.template` or `.env.example` when provider discovery is useful.
2. Prefer `uv run mi auth`; select only the providers the project needs.
3. Treat `workbench.project.json` as the compatibility allow-list and CLI/env
   values as connection inputs. Require the effective project, PostgreSQL host
   and database, Blob account, and container to match that contract before any
   query or run-state write. Use Entra/workload identity only; do not add
   password, shared-key, SAS, local JSON, or filesystem fallbacks.
4. Select a canonical `provider:model` from `models.yaml` and validate its
   declared API family against available credentials before starting work.
5. Use runtime `--ai-model` and `--ai-reasoning-effort` overrides for
   experiments. Apply them only to AI entries in a temporary YAML and never
   rewrite source pipeline config.
6. Fail fast with the missing provider, API family, and credential names; do
   not let auth failures surface deep inside a processor.

Read [references/runtime-details.md](references/runtime-details.md) only when
you need the current provider/env mapping, `mi auth` variants, hosted identity
variables, Logfire alternatives, or focused troubleshooting.

## Model Catalog And Pricing

Use the existing configuration workflow:

```bash
uv run python -m workbench.models.configuration list
uv run python -m workbench.models.configuration set-default <provider:model>
```

Add reusable reviewed vendor rates to `model-pricing.yaml`, then reference
their key from `models.yaml`. Rates must be non-negative. Never fetch or refresh
prices during an eval. The selected pricing record must be frozen into run
identity so historical cost estimates remain stable.

## Acceptance Checks

Select changed layers from the
[repository verification matrix](../project-guide/references/verification-matrix.md).

- Secrets remain outside tracked files.
- Environment bootstrap precedes provider checks and telemetry.
- Hosted publication/evidence access uses configured non-secret identities and
  least-privilege Azure identity.
- The selected model exists in `models.yaml`; its API family and credentials
  validate centrally.
- Runtime overrides leave source YAML unchanged.
- Telemetry content capture matches data policy.
- A focused startup or exact-example run proves the configured path.
