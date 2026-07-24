# MeshInsights Agent Workbench

This repository combines the full `mi-core` source with a root-level use-case
Agent Workbench project for building and evaluating connected-system agents.
The runtime and operator tooling are Python, with dependencies managed by `uv`;
the local eval-results explorer also includes a TypeScript/React frontend managed
by `pnpm`.

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
3. Node.js `>=22.13.0` for the eval-results explorer frontend.
4. pnpm `>=11.9.0` (the exact package-manager version is recorded in
   `www/package.json`).

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

# Model selection and frozen-pricing configuration
uv run python -m src.model_configuration list
uv run python -m src.model_configuration upsert --help

# Local-only ephemeral eval review CLI
uv run python -m src.evals.inspection_cli --help

# Local human eval-results explorer (after building www/)
APP_PROJECT_KEY=<benchmark-studio-project-key> \
  uv run python -m src.apps.eval_explorer

# Working/retained elevation, verification, and permanent deletion
uv run python -m src.eval_lifecycle.cli --help

# Explicit publication of eligible retained evals
uv run python -m src.eval_publication.cli --help
```

See [`EvalRunbook.md`](EvalRunbook.md) for the explicit, reproducible eval
command shape. Prefer it over the slower interactive benchmark chooser.

The explorer has two UI layers:

- `agent-dev-eval-ui/web/` is the reusable React shell for run, attempt, review,
  and evidence navigation.
- `www/` is the project frontend that composes that shell with the Spirax-owned
  evidence schema and charts in `www/src/use_case/`.

Evidence inspection uses the exact selected-example source snapshot and raw
artifact hashes retained in each current run manifest; it does not re-query the
current published benchmark catalog. Runs created before that retained evidence
contract must be rerun before their Evidence package can be rendered.

Install, test, and build the frontend from `www/` before starting the Python
explorer backend:

```bash
cd www
pnpm install --frozen-lockfile
pnpm test
pnpm build
cd ..
APP_PROJECT_KEY=<benchmark-studio-project-key> \
  uv run python -m src.apps.eval_explorer
```

A new use case replaces the project-owned `www/src/use_case/` adapters without
rebuilding the reusable shell.

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

`workbench.template.json` is the versioned ownership and reference-reset
contract. It keeps `mi-core/`, the reusable eval packages, and generic Workbench
mechanics distinct while declaring the exact reference-use-case paths that are
cleared in a new repository. Root skills remain under `.agents/skills/`.
Validation rejects reference identifiers in generated project-facing paths.

Reusable source remains editable during MVP development, but coding agents must
explain the shared change and obtain user approval before modifying it. An
approved reusable fix made in a use-case repository must include an upstream
template or library handoff before it is considered complete.

After initialization, enter the new repository, run `uv sync`, then configure
credentials with `uv run mi auth` or a local `.env`. The generated
`.env.example` contains placeholders only. Populate
`docs/use_case/PROJECT_CONTEXT.md` before using the separate Codex-guided
pipeline-port workflow.

## Agent Candidate Provenance

Every new eval resolves a lightweight candidate before the first model call.
The run-local manifest freezes Git revision, relevant dirty/untracked overlay,
the resolved pipeline graph, prompts, skills, tools, schemas, evidence/action
contracts, dependency lock, and the model override policy in
`agent_version_configs/<pipeline>.agent.yaml`.

Resolve explicitly when diagnosing provenance:

```bash
uv run python -m src.agent_versions.cli --json resolve \
  --pipeline pipeline_configs/v1_3.ppln \
  --dirty-policy capture
```

The supported meaningful-version workflow is full-run elevation through
`src.eval_lifecycle.cli`. It retains the candidate's Git identity,
configuration hashes, and relevant patch together with the compact retained
eval; it does not copy the complete source tree.

## Local Version And Result Lifecycle

Every new eval is a rich, disposable working eval. Elevation is an explicit
full-run operation for a meaningful result and agent version. Retained evals
use aggregate artifacts, prune performance/tool-trace detail, and keep exact
Azure evidence references rather than local evidence copies. After the retained
eval verifies successfully, elevation permanently removes its source working
eval so the explorer shows only the retained row for that occurrence.

```bash
uv run python -m src.eval_lifecycle.cli list --state all --json
uv run python -m src.eval_lifecycle.cli elevate eval_<run-id> --dry-run --json
uv run python -m src.eval_lifecycle.cli elevate eval_<run-id> --yes --json
uv run python -m src.eval_lifecycle.cli verify ret_<retained-id> --json
uv run python -m src.eval_lifecycle.cli delete working eval_<run-id> --yes --json
uv run python -m src.eval_lifecycle.cli delete retained ret_<retained-id> \
  --confirm-retained ret_<retained-id> --json
```

Deletion is permanent and not recoverable. Retained deletion preserves a
shared meaningful agent version while another retained eval still references
it. The local review app remains read-only and offers All, Working, and Retained
filters; elevation and deletion are command/skill workflows only.

Eligible retained evals can be explicitly published to a dedicated Azure Blob
container. Publication requires occurrence-aware retained schema v2, clean
recorded agent provenance, and `execution_status: completed` for every
canonical selected unit. A dry run validates and previews the payload without
allocating a publication ID or accessing Azure:

```bash
uv run python -m src.eval_publication.cli publish ret_<retained-id> \
  --dry-run --json

AZURE_EVAL_RESULTS_ACCOUNT_URL=https://<account>.blob.core.windows.net \
AZURE_EVAL_RESULTS_CONTAINER=eval-results \
  uv run python -m src.eval_publication.cli publish ret_<retained-id> \
  --yes --json
```

Each publish action creates a new immutable event under
`projects/<project-key>/benchmarks/<benchmark-key>/v<version>/publications/`.
Payload blobs are downloaded and hash-verified before
`publication-manifest.json` is created as the discovery commit marker.

## AI Model Catalog

The project-owned [`models.yaml`](models.yaml) enumerates selectable model
identifiers, declares the interactive default and API family, and references
reusable billing identities. Reviewed non-secret rates live separately in the
Workbench-owned [`model_pricing.yaml`](model_pricing.yaml), so vendor pricing is
not re-entered for every use case. Eval runs resolve and freeze the selected
pricing snapshot; they never fetch or silently refresh prices. `mi-core`
validates generic `provider:model` identifiers without owning either catalog.

## Working With Codex

Describe the outcome or ask the development question directly. Codex should inspect the relevant skill and verify its answer against the current code and tests instead of expecting you to translate guidance into code by hand.

Use `$project-guide` for repository orientation, architecture, customization, lifecycle, ownership boundaries, and help choosing a more specialized skill.

| Need | Skill |
|---|---|
| Port the initial Benchmark Studio evidence pipeline | `$benchmark-pipeline-port` |
| Build or evolve a staged pipeline | `$pipeline-builder` |
| Build an `mi.ai` workflow, agent, toolset, capability, or skill | `$ai-processor-builder` |
| Prepare, run, or troubleshoot a use-case eval | `$run-use-case-evals` |
| Elevate, verify, or permanently delete exact evals | `$eval-lifecycle` |
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
  working/<benchmark>/v<version>/<run-id>/
    manifest.json
    agent-version.json
    attempts/                  # rich local per-unit results
    result.json
    performance/               # disposable timings/retries
    review/                    # local prompts/tools/traces
  retained/<benchmark>/v<version>/<retained-eval-id>/
    manifest.json
    result.json
    units.json
    agent-provenance.json
    evidence-references.json
    agent.patch                # only for relevant dirty/untracked content
  retained/agent_versions/<agent-version-id>/
agent_version_configs/
  v1_3.agent.yaml
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
  eval_lifecycle/
  eval_publication/
```

Working evals retain rich debugging detail through the active improvement loop.
Retained evals keep a small number of aggregate files with full final AI
outputs, expected outputs, grading, usage, cost, provenance, and immutable
evidence references. Use `EvalRunbook.md` for execution and `$eval-lifecycle`
for formal preservation or deletion.

## Notes

- Keep `README.md` focused on setup and navigation.
- Put durable business and domain context in `docs/use_case/` and project-specific development guidance in `.agents/skills/`.
- Keep skills concise and procedural. When guidance depends on current behavior, have Codex inspect the implementation and tests rather than duplicating them in prose.
