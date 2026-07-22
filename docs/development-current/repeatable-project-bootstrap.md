# Repeatable Project Bootstrap

**Status:** Implemented for MVP

**Implementation summary:** Strict versioned bootstrap specifications, isolated
local/Git template materialization, exact revision provenance, safe tracked-file
copying, atomic destination creation, project/configuration rendering,
independent structural validation, optional Git initialization, machine-readable
CLI output, and operator documentation are implemented.

**Backlog feature:** `docs/development-backlog/features.md` → Repeatable Project
Bootstrap

## Outcome

Give an FDE or coding agent one non-interactive command that creates a new,
use-case-specific Agent Workbench repository from an exact standard-template
revision and a reviewed, non-secret initialization specification.

The generated repository must be ready for the next workflow—Codex-guided port
of the Benchmark Studio evidence pipeline—without carrying example customer
logic, local credentials, virtual environments, result data, or other mutable
state from the machine that performed initialization.

## Product Boundary

Bootstrap owns:

- materializing a standard template from a local checkout or Git source;
- recording template source and exact revision;
- assigning project and use-case identity;
- recording the deployed Benchmark Studio read surface;
- recording a published benchmark catalog and default benchmark;
- recording label, evidence-recipe, and immutable source-snapshot contracts;
- creating the project-owned model catalog and runtime default;
- creating non-secret environment placeholders and durable project paths;
- initializing an independent Git repository; and
- validating the generated repository before reporting success.

Bootstrap does not:

- copy or port a customer evidence pipeline;
- infer source-system semantics;
- contact Benchmark Studio, Azure, or model providers;
- retrieve or write credentials;
- copy benchmark labels or evidence into the repository;
- run a benchmark example before the control pipeline has been ported; or
- create an agent variant, evaluation profile, or promoted agent version.

Those boundaries keep initialization deterministic and safe to run before
external credentials are configured. Hosted-contract compatibility and a
one-example control-pipeline smoke test belong to the pipeline-port workflow.

## Operator Contract

The primary command is:

```bash
uv run python -m src.project_bootstrap.cli --json init <destination> \
  --spec <bootstrap-spec.json> \
  --template-source <local-path-or-git-url> \
  --template-ref <branch-tag-or-commit>
```

`--template-source` defaults to the canonical Agent Workbench template Git
repository. A local checkout is supported for offline development and testing.
For a Git source, `--template-ref` is resolved to an exact commit before files
are copied. A non-Git local directory is allowed only with an explicit
`--template-revision` provenance value.

Validation is independently repeatable:

```bash
uv run python -m src.project_bootstrap.cli --json validate <project>
```

Initialization fails if the destination is non-empty. It never overlays an
existing project.

## Bootstrap Specification

The input is versioned JSON so it is easy for Codex, CI, and operators to
generate, review, and diff without embedding credentials.

Schema version 1 records:

- project key, display name, Python distribution name, and use-case key;
- Azure environment, deployed Benchmark Studio application identity, project
  key, and supported read-access mode;
- one or more named published benchmark versions;
- the default benchmark selection;
- published-contract schema version, evaluation-label fields,
  evidence-recipe identity, and immutable source-snapshot contract for each
  benchmark;
- project-supported `provider:model` entries and one default model; and
- optional project description.

The schema rejects unknown fields, duplicate benchmark/model identities,
invalid package/model identifiers, empty label fields, and a default that is
not present in its catalog.

It intentionally contains no database URL, connection string, SAS token,
provider key, or other credential value.

## Generated Contract

Every initialized project contains:

- `workbench.project.json`, the normalized non-secret project contract plus
  exact template provenance and fixed durable-path locations;
- a rewritten `[project]` identity in `pyproject.toml`;
- a project-specific README heading and bootstrap notice;
- `models.yaml`, containing only the configured project model catalog;
- `.env.example`, containing identity values and credential placeholders only;
- `docs/use_case/PROJECT_CONTEXT.md`, with prompts for durable business context;
- empty durable directories when the template does not already provide them:
  `pipeline_configs/`, `evaluation_configs/`, `agent_version_configs/`,
  `eval_results/`, and the standard `src/` component directories; and
- a new Git repository unless the operator explicitly selects `--no-git`.

The initializer copies only Git-tracked files from a Git template. It excludes
source Git metadata, `.env`, virtual environments, caches, telemetry state,
local eval results, promoted-version stores, and common secret-bearing paths
even if they are accidentally tracked. Symlinks are rejected.

## Validation

Successful validation proves:

- the normalized project contract is schema-valid;
- the generated project identity matches `pyproject.toml`;
- the configured model default exists in `models.yaml` with the expected API
  family;
- the default benchmark exists in the published catalog;
- required durable locations and generated files exist;
- exact template revision provenance is present; and
- no root `.env` was copied.

Validation is local and structural. It does not claim that credentials work or
that the remote published benchmark is currently reachable.

## Implementation Shape

Keep this project-owned operator workflow under `src/project_bootstrap/`:

- `models.py` owns the strict versioned input and generated contracts;
- `service.py` materializes a template, renders project files, initializes Git,
  and validates the result; and
- `cli.py` exposes stable `init` and `validate` commands with JSON output.

Do not add this to `mi-core`: repository initialization and Benchmark Studio
project metadata are Agent Workbench product behavior, not generic pipeline
runtime mechanics.

## Implementation Sequence

1. Define and test the strict bootstrap specification and invariants.
2. Implement safe local/Git template materialization and provenance capture.
3. Render the project contract, package metadata, README, model catalog,
   environment template, context prompt, and durable directories.
4. Add independent structural validation and fail initialization unless it
   passes.
5. Add CLI coverage for machine-readable success and actionable failures.
6. Document the operator command and update the MVP backlog only after all
   acceptance criteria pass.

## Acceptance Criteria

- [x] A local Git template initializes a separate project at its exact commit.
- [x] A Git URL/ref can be materialized without depending on ambient checkout
  state.
- [x] A non-Git source requires explicit revision provenance.
- [x] A non-empty destination is rejected without modifying its contents.
- [x] No credential, `.env`, cache, result, telemetry, or source-repository Git
  state is copied.
- [x] Project, Benchmark Studio, benchmark, label/evidence, model, path, and
  template identities are present in `workbench.project.json`.
- [x] `pyproject.toml`, README, `models.yaml`, `.env.example`, and use-case
  context are rendered from the reviewed specification.
- [x] The generated repository is independently validated before init reports
  success.
- [x] The default command creates a new Git repository; `--no-git` is available
  for controlled embedding and tests.
- [x] Unit and CLI tests cover success, schema rejection, secret exclusion,
  provenance, destination safety, and post-generation validation.
- [x] README documents the complete non-interactive workflow and makes clear
  that credentials are configured afterward with `uv run mi auth` or `.env`.
