# MeshInsights Agent Development and Evals MVP

This repository combines the full `mi-core` source with a root-level use-case
template for building and evaluating connected-system agents. It is Python-only,
and all Python dependencies are managed with `uv`.

The source snapshots were imported from:

- `Mesh-Systems-Eng/mesh.insights.core` `main` at commit
  `84a69611126a801975c63e9ea9d16500e3393a25`.
- `Mesh-Systems-Eng/mesh.insights.templates` `main` at commit
  `6ba259c958a4f073e52575370eaec4d4866c2e00`.

The root project uses editable path dependencies for `mi-core` and the CLI, so
changes under `mi-core/` are immediately available through the root `uv`
environment. The Spirax v1_3 agent reads published benchmark identity and
approved labels from Azure PostgreSQL, then downloads the exact immutable raw
evidence frozen by that benchmark version from Azure Blob Storage.

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

# Create .env from the template and provide Azure PostgreSQL, Blob Storage,
# model-provider, and optional Logfire credentials.
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
# Visualization pipeline CLI
uv run python -m src.pipelines.data_visualization_pipeline --help

# YAML pipeline runner CLI
uv run python -m src.pipelines.pipeline_run_from_yaml --help
uv run python -m src.pipelines.pipeline_run_from_yaml pipeline_configs/v1_3.ppln \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --example-id '<unit-id>|<decision-timestamp>'

# Eval orchestration CLI
uv run python -m src.evals.eval_orchestration --help
uv run python -m src.evals.eval_orchestration pipeline_configs/v1_3.ppln \
  --benchmark-key <published-benchmark-key> \
  --benchmark-version <version-number> \
  --runs-per-example 1

# Streamlit apps
uv run python -m streamlit run src/streamlit_apps/data_visualization_app.py
uv run python -m streamlit run src/streamlit_apps/evaluation_results_app.py
```

## Working With Codex

Describe the outcome or ask the development question directly. Codex should inspect the relevant skill and verify its answer against the current code and tests instead of expecting you to translate guidance into code by hand.

Use `$project-guide` for repository orientation, architecture, customization, lifecycle, ownership boundaries, and help choosing a more specialized skill.

| Need | Skill |
|---|---|
| Build or evolve a staged pipeline | `$pipeline-builder` |
| Build an `mi.ai` workflow, agent, toolset, capability, or skill | `$ai-processor-builder` |
| Build evaluation orchestration or result contracts | `$agent-eval-builder` |
| Analyze existing evaluation results | `$eval-results-analysis` |
| Build or fix a Streamlit review/debug app | `$streamlit-app-builder` |
| Configure auth, providers, runtime overrides, or tracing | `$external-runtime-setup` |

Example questions:

- “Use `$project-guide` to explain where this feature belongs and which existing code is the closest pattern.”
- “Use `$pipeline-builder` to add the next pipeline stage and verify the relevant tests.”
- “Which layer should own this behavior: the use-case project or `mi-core`?”

Before implementation, populate the relevant files in `docs/use_case/` with durable business context. Do not use those files as implementation logs, and do not update them unless the user explicitly asks.

## Repository Layout

```text
.agents/
data/
docs/
  current-dev/
  product-strategy/
  use_case/
mi-core/
  core/
  cli/
pipeline_configs/
  v1_3.ppln
src/
  actions/
  hydrators/
  objects/
  processors/
    common/
    v1/
    v1_3/
  retrievers/
  pipelines/
  evals/
  streamlit_apps/
  experimental_core/
```

## Notes

- Keep `README.md` focused on setup and navigation.
- Put durable business and domain context in `docs/use_case/` and project-specific development guidance in `.agents/skills/`.
- Keep skills concise and procedural. When guidance depends on current behavior, have Codex inspect the implementation and tests rather than duplicating them in prose.
