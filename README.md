# MeshInsights Agent Workbench

This repository combines the full `mi-core` source with a root-level use-case
Agent Workbench project for building and evaluating connected-system agents. It is Python-only,
and all Python dependencies are managed with `uv`.

The source snapshots were imported from:

- `Mesh-Systems-Eng/mesh.insights.core` `main` at commit
  `84a69611126a801975c63e9ea9d16500e3393a25`.
- `Mesh-Systems-Eng/mesh.insights.templates` `main` at commit
  `6ba259c958a4f073e52575370eaec4d4866c2e00`.

The root project uses editable path dependencies for `mi-core` and the CLI, so
changes under `mi-core/` are immediately available through the root `uv`
environment. The local Spirax operator reads published benchmark identity and
approved labels directly from Azure PostgreSQL with a short-lived Entra token,
then downloads the exact immutable raw evidence from Azure Blob Storage using
container-scoped RBAC.

Use this README as the quick on-ramp. Keep durable use-case context in `docs/use_case/`. For development guidance, ask Codex: the repo skills under `.agents/skills/` provide the project-specific playbooks, and the current codebase remains the source of truth.

## Prerequisites

1. Python `>=3.13.5` (see `pyproject.toml`).
2. `uv` installed.

## Quickstart (with `uv`)

```bash
# Create Virtual Environment
uv venv
source .venv/bin/activate

# Install project and dev dependencies into .venv
uv sync

# Create .env from the template and provide the non-secret PostgreSQL/Blob
# resource identities, model-provider, and optional Logfire credentials. Azure
# CLI supplies short-lived tokens for PostgreSQL and Blob Storage.
cp .env.example .env

# Configure LLM inference and tracing credentials interactively when useful.
## Follow terminal instructions typically choosing
### Providers: "Azure Anthropic", "Azure OpenAI", "Google Gemini", "Logfire"
#### Azure Auth: Subscription = "Olympus", Resource Group = "rg-mi-dv", Store "Resource Name"
uv run mi auth
```

`uv sync` installs both the runtime dependencies and the local development CLI tooling for this repo.
That includes `meshinsights-cli`, which provides `mi auth` in the project environment.

The committed `.env.example` contains placeholders only. Never commit real secrets.

If you use AI-enabled pipelines or evals and the repo-managed `uv run mi auth` flow is unreliable on your machine, a separately installed machine-level `mi auth` is an acceptable fallback.

If you need tracing, set up Logfire during auth as well. For deeper auth, telemetry, and `.env` conventions, use `$external-runtime-setup`.

## Daily `uv` Workflow

### Run commands in project env

Always execute project commands through `uv run`:

```bash
uv run python -m <module>
uv run pytest
uv run ruff check src/
uv run basedpyright
uv run mi auth
```

### Agent Runtime Notes

This repo assumes agents inspect and run code through the `uv`-managed project environment in `.venv`.

Do not burn time checking whether a separate system `python` on `PATH` can import repo dependencies. For this repo, the correct first move is to use `uv run`.

Common inspection commands:

```bash
# Installed package version
uv run python -c "import importlib.metadata; print(importlib.metadata.version('mi-core'))"

# Source file backing an installed symbol
uv run python -c "import inspect; from mi.core.pipeline_orchestrator import PipelineOrchestrator; print(inspect.getsourcefile(PipelineOrchestrator))"

# Inspect an installed module or class from the repo env
uv run python -c "import inspect; from mi.core.pipeline_orchestrator import PipelineOrchestrator; print(inspect.getsource(PipelineOrchestrator))"
```

Use the same pattern for `mi.ai` or any other installed dependency.

### Add dependencies

```bash
# Runtime dependency
uv add <package>

# Dev-only dependency
uv add --dev <package>
```

### Lock/sync behavior

- `uv add` updates `pyproject.toml` and lock state.
- `uv sync` installs exactly what the lock defines.
- `uv lock` refreshes lock resolution without installing.

Use `uv sync` after pulling branch changes that touch `pyproject.toml` or `uv.lock`.

## Common Entry Points

```bash
# Initialize or validate a new use-case Agent Workbench repository
uv run python -m src.project_bootstrap.cli --help

# YAML pipeline runner CLI
uv run python -m src.pipelines.pipeline_run_from_yaml --help
uv run python -m src.pipelines.pipeline_run_from_yaml pipeline_configs/v1_3.ppln \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --example-id '<unit-id>|<decision-timestamp>'

# Eval orchestration CLI
uv run python -m src.evals.eval_orchestration --help

# Local-only ephemeral eval review CLI
uv run python -m src.evals.inspection_cli --help

# Local human eval-results explorer (after building www/)
APP_PROJECT_KEY=<benchmark-studio-project-key> \
  uv run python -m src.apps.eval_explorer

# Derived local catalog and recoverable lifecycle operations
uv run python -m src.lifecycle.cli --help
```

See [`EvalRunbook.md`](EvalRunbook.md) for the explicit, reproducible eval
command shape. Prefer it over the slower interactive benchmark chooser.

The explorer keeps reusable run/attempt/review mechanics in
`agent-dev-eval-core/` and `agent-dev-eval-ui/`. This project's immutable
Spirax evidence projection lives in `src/evidence/`, while its evidence charts
live in `www/src/use_case/`; a new use case replaces those project-owned
adapters without rebuilding the shell.

## Current Spirax Reference Pipeline

- `pipeline_configs/v1_3.ppln` is the one-shot structured AI workflow example.

It uses the benchmark-aligned terminal output contract. It is an example, not
a mandatory design for every use case: keep deterministic logic when it works
and prefer one workflow call when prepared evidence is sufficient. See
[`docs/use_case/PipelineVersions.md`](docs/use_case/PipelineVersions.md) for the
short hypothesis and lineage.

## Initialize A New Use-Case Project

Use the bootstrap CLI to create a separate repository from an exact standard
template revision. Start by copying and reviewing
[`bootstrap_configs/example.project.json`](bootstrap_configs/example.project.json).
The specification records project identity, the read-only Benchmark Studio
surface, published benchmark contracts, label/evidence identities, and the
project model catalog. It must not contain credentials.

```bash
uv run python -m src.project_bootstrap.cli --json init ../customer-agent-workbench \
  --spec bootstrap_configs/customer.project.json \
  --template-source https://github.com/Mesh-Systems-Eng/mesh.insights.templates.git \
  --template-ref <branch-tag-or-commit>

uv run python -m src.project_bootstrap.cli --json validate \
  ../customer-agent-workbench
```

For offline development, `--template-source` may point to a local Git checkout.
A non-Git local directory requires an explicit `--template-revision` value.
Initialization refuses to overlay a non-empty destination and excludes source
Git state, `.env`, credentials, virtual environments, caches, local eval
results, and promoted agent-version data.

After initialization, enter the new repository, run `uv sync`, then configure
credentials with `uv run mi auth` or a local `.env`. The generated
`.env.example` contains placeholders only. Populate
`docs/use_case/PROJECT_CONTEXT.md` before using the separate Codex-guided
pipeline-port workflow.

## Immutable Agent Versions

Every new eval resolves a content-addressed candidate agent version before the
first model call. The manifest freezes the resolved pipeline graph, source and
dirty overlay, prompts, skills, tools, schemas, evidence/action contracts,
dependency lock, and the model override policy in
`agent_version_configs/<pipeline>.agent.yaml`.

Resolve or promote explicitly:

```bash
uv run python -m src.agent_versions.cli --json resolve \
  --pipeline pipeline_configs/v1_3.ppln \
  --dirty-policy capture

uv run python -m src.agent_versions.cli promote \
  --from-run eval_<run-id> \
  --alias pulse-v1-3-1
```

Clean promotion uses the Git revision without copying tracked source. Dirty
promotion must use `--dirty-policy capture` and retains exact changed bytes in
the local content-addressed store. Global `agent_versions/` remains local-only;
run-local candidate manifests and required objects are durable evaluation
evidence and can be retained with their run in Git.

## Local Version And Result Lifecycle

The lifecycle catalog is rebuilt from managed schema-v1 run manifests,
run-local candidates, comparisons, promoted manifests, aliases, and promotion
events. It does not create a mutable catalog database and does not read legacy
standalone result JSON.

```bash
uv run python -m src.lifecycle.cli catalog --json
uv run python -m src.lifecycle.cli verify --json

# Preview, then quarantine one exact entity
uv run python -m src.lifecycle.cli delete run eval_<run-id> --dry-run --json
uv run python -m src.lifecycle.cli delete run eval_<run-id> --yes --json

# The same flow applies to promoted versions and comparisons
uv run python -m src.lifecycle.cli delete version av_<version-id> --dry-run --json
uv run python -m src.lifecycle.cli delete comparison cmp_<id> --dry-run --json

# Recover or permanently remove a quarantined operation
uv run python -m src.lifecycle.cli restore del_<operation-id> --yes --json
uv run python -m src.lifecycle.cli purge del_<operation-id> --yes --json
```

Deletion previews report exact paths, bytes, and retained references. Confirmed
deletion first moves data into ignored local quarantine under
`.workbench/lifecycle/`; permanent removal is a separate confirmed purge.
Review-only purge remains available through `src.evals.inspection_cli` and does
not delete the durable run.

## AI Model Catalog

The project-owned model catalog is [`models.yaml`](models.yaml). It is the only
place this project enumerates selectable model identifiers and declares the
default used by non-interactive runs. Each entry also declares the API family
required to invoke it. Update that root file as provider models evolve;
`mi-core` validates generic `provider:model` identifiers without owning an
application model list.

## Working With Codex

Describe the outcome or ask the development question directly. Codex should inspect the relevant skill and verify its answer against the current code and tests instead of expecting you to translate guidance into code by hand.

Use `$project-guide` for repository orientation, architecture, customization, lifecycle, ownership boundaries, and help choosing a more specialized skill.

| Need | Skill |
|---|---|
| Port the initial Benchmark Studio evidence pipeline | `$benchmark-pipeline-port` |
| Build or evolve a staged pipeline | `$pipeline-builder` |
| Build an `mi.ai` workflow, agent, toolset, capability, or skill | `$ai-processor-builder` |
| Prepare, run, or troubleshoot a use-case eval | `$run-use-case-evals` |
| Build evaluation orchestration or result contracts | `$agent-eval-builder` |
| Analyze existing evaluation results | `$eval-results-analysis` |
| Configure auth, providers, runtime overrides, or tracing | `$external-runtime-setup` |

Example questions:

- “Use `$project-guide` to explain where this feature belongs and which existing code is the closest pattern.”
- “Use `$pipeline-builder` to add the next pipeline stage and verify the relevant tests.”
- “Which layer should own this behavior: the use-case project or `mi-core`?”

Before implementation, populate the relevant files in `docs/use_case/` with durable business context. Do not use those files as implementation logs, and do not update them unless the user explicitly asks.

## Repository Layout

```text
.agents/
agent-dev-eval-core/
  evaluation/
  tests/
data/
eval_results/
  <pipeline>/<benchmark>/v<version>/runs/<run-id>/
    manifest.json
    attempts/
    result.json
    performance/               # disposable timings/retries, optional
    review/                    # disposable local prompts/images/traces
    diagnosis/                 # optional compact retained analysis
agent_version_configs/
  v1_3.agent.yaml
agent_versions/               # local promoted manifests and CAS (gitignored)
.workbench/lifecycle/         # local quarantine and operation receipts
docs/
  development-current/
  product-strategy/
  use_case/
mi-core/
  core/
  cli/
pipeline_configs/
  v1_3.ppln
evaluation_configs/
  spirax-failure-evaluation.eval.yaml
src/
  actions/
  hydrators/
  objects/
  processors/
    common/
    v1_3/
  retrievers/
  pipelines/
  evals/
  lifecycle/
```

Schema-v1 keeps three evidence classes separate: `manifest.json`, immutable
`attempts/`, `agent-version.json`, and compact `result.json` are durable eval
evidence; `performance/` contains optional short-lived timing and retry
observations; `review/` contains optional local diagnostic prompts, images, and
traces. Deleting either disposable tree does not invalidate scoring, resume,
comparison, or promotion. Use `EvalRunbook.md` for exact execution and
verification commands.

## Notes

- Keep `README.md` focused on setup and navigation.
- Put durable business and domain context in `docs/use_case/` and project-specific development guidance in `.agents/skills/`.
- Keep skills concise and procedural. When guidance depends on current behavior, have Codex inspect the implementation and tests rather than duplicating them in prose.
