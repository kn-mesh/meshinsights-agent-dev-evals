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
environment. Spirax pipeline code is intentionally not included yet.

Use this README as the quick on-ramp. Use `docs/use_case/` for durable use-case context, `docs/human_dev_guidance/` for human-oriented development guidance, and the repo skills under `.agents/skills/` for coding-agent implementation guidance.

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

# Create .env file with access to external systems (LLM inference APIs, Logfire)
## Follow terminal instructions typically choosing
### Providers: "Azure Anthropic", "Azure OpenAI", "Google Gemini", "Logfire"
#### Azure Auth: Subscription = "Olympus", Resource Group = "rg-mi-dv", Store "Resource Name"
uv run mi auth
```

`uv sync` installs both the runtime dependencies and the local development CLI tooling for this repo.
That includes `meshinsights-cli`, which provides `mi auth` in the project environment.

If you want `mi auth` to detect the right providers reliably, add a repo-root `.env.template` or `.env.example` with variable names and placeholders only. Never commit real secrets.

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
uv run python -m src.pipelines.pipeline_run_from_yaml pipeline_configs/v1.ppln --unit-id LOC-008

# Eval orchestration CLI
uv run python -m src.evals.eval_orchestration --help
uv run python -m src.evals.eval_orchestration pipeline_configs/v1.ppln --units all --runs 1

# Streamlit apps
uv run python -m streamlit run src/streamlit_apps/data_visualization_app.py
uv run python -m streamlit run src/streamlit_apps/evaluation_results_app.py
```

## Documentation Map

Start here, in order:

1. `docs/use_case/`
2. `docs/human_dev_guidance/` for human developer guidance about template structure, customization, and lifecycle
3. `.agents/skills/pipeline-builder/SKILL.md` or use `$pipeline-builder`
4. `.agents/skills/agent-eval-builder/SKILL.md` or use `$agent-eval-builder` (only for AI output evaluation)
5. `.agents/skills/external-runtime-setup/SKILL.md` or use `$external-runtime-setup` (only for AI/auth/telemetry setup)
6. `.agents/skills/streamlit-app-builder/SKILL.md` or use `$streamlit-app-builder`
7. `.agents/skills/ai-processor-builder/SKILL.md` or use `$ai-processor-builder` (only for AI processors)

## Repository Layout

```text
.agents/
data/
docs/
  current-dev/
  human_dev_guidance/
  product-strategy/
  use_case/
mi-core/
  core/
  cli/
pipeline_configs/
  data_viz.ppln
  v1.ppln
src/
  actions/
  hydrators/
  objects/
  processors/
    common/
    v1/
  retrievers/
  pipelines/
  evals/
  streamlit_apps/
  experimental_core/
```

## Notes

- Keep `README.md` focused on setup and navigation.
- Put durable business and domain context in `docs/use_case/UseCaseContext.md`, broader human developer guidance in `docs/human_dev_guidance/`, and coding-agent implementation patterns in `.agents/skills/`.
