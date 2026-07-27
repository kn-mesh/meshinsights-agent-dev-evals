# Core And Reference Use-Case Separation Refactor

**Status:** Proposed implementation plan

**Scope:** Current Agent Workbench core-plus-Spirax reference repository and
the future neutral template structure

**Primary job:** Make a new use-case project by preserving product code and
replacing one explicit use-case area

**Product decision:** `docs/product-strategy/mvp-scope.md`, “Strategy - at MVP
scope” and Decision 4

## Objective

Create an enforceable boundary between:

1. reusable product code that contains no use-case behavior and is not normally
   modified while creating a project;
2. fixed project configuration and conventions that an FDE is expected to use;
3. one replaceable reference-use-case implementation; and
4. template-authoring and generated-local files.

The completed refactor must let an FDE initialize a repository, preserve the
reusable Agent Workbench and `mi-core` sources unchanged, and populate one
standard `use_case/` tree without searching through or modifying reusable code.

This is a source-ownership and dependency-direction refactor. It must not change
the published Benchmark Studio contract, the Spirax decision behavior, eval
scoring semantics, working/retained lifecycle meaning, or production scope.

## Repository Roles And Migration Assumption

- This repository contains the reusable product code plus the implemented
  Spirax reference use case. Spirax remains here as the working proof and
  integration case.
- A future template repository will contain the same reusable product code and
  the fixed neutral `use_case/` directory structure, but no Spirax behavior,
  identifiers, prompts, schemas, evidence decoders, or UI.
- There are no other existing use-case repositories that this refactor must
  migrate or keep source-compatible.
- Therefore this plan does not build a general repository migration framework,
  configurable layouts, or compatibility packages for other use cases.

## Current-State Findings

The repository already has useful separation primitives:

- `mi-core/`, `agent-dev-eval-core/`, and `agent-dev-eval-ui/` are distinct
  editable reusable libraries.
- `workbench.template.json` declares reusable and reference-use-case paths.
- `src/project_bootstrap/service.py` clears declared reference paths and
  preserves reusable source when creating a project.
- The reusable React explorer receives a `UseCaseAdapter`.
- Pipeline, evaluation, and agent-version configurations are source controlled
  independently from generic evaluation mechanics.

The following gaps prevent the boundary from satisfying the new MVP strategy:

| Gap | Current evidence | Consequence |
|---|---|---|
| Use-case code is physically mixed with reusable code | `src/actions`, `src/evidence`, `src/hydrators`, `src/objects`, `src/processors`, and `src/retrievers` sit beside reusable `src/evals`, `src/benchmarks`, and lifecycle code | An FDE must understand a path inventory instead of seeing one replaceable project area |
| A reusable module statically imports a use-case module | `src/apps/eval_explorer.py` imports `src.evidence` | Dependency direction is reusable → use case |
| Project-owned grader registration is inside a reusable path | `src/evals/graders/__init__.py` defines `PROJECT_GRADERS`, while all of `src/evals` is declared reusable | Adding a custom grader requires modifying reusable-owned source and survives reference reset |
| A generic contract is misclassified as use-case code | `src/objects/pipeline_metadata.py` defines the general published-benchmark runtime metadata contract | New use cases would duplicate a contract that applies to every benchmark example |
| Reusable paths contain reference identity | `mi-core/cli/src/cli/init_project.py` hard-codes a Spirax template; `src/pipelines/pipeline_run_from_yaml.py` names Pulse in its module description | “Zero use-case-specific core” is not machine true |
| Project paths are hard-coded in reusable behavior | Eval CLI defaults, agent policy lookup, provenance globs, bootstrap required paths, skills, and runbooks name the current root folders | A physical move cannot be completed safely in one place |
| Ownership is not exhaustive | Several tracked root and `www/` files have no effective manifest owner | A path can bypass approval or leak checks |
| A declared reset field is unused | `root_skills_with_project_defaults` is modeled and populated but is not consumed by bootstrap | The manifest describes behavior that does not occur |
| Blank projects are only partly runnable | Bootstrap writes a Python evidence placeholder but leaves the frontend adapter absent | Core validation passes, but the project UI cannot build before the explorer port |
| Reusable coverage is stored under `tests/use_case` | Most orchestration, explorer-backend, candidate-version, compatibility, pricing, lifecycle, and resume tests are located in the replaceable test tree | A generated blank project discards significant reusable Workbench coverage |
| Source identity assumes the current layout | `src/evals/run_specs.py`, `src/agent_versions/resolver.py`, registry scan paths, policies, and tests enumerate current paths | Moving files changes candidate identities and can make an in-progress occurrence non-resumable |

## Architectural Decisions

### AD-01: Keep The Existing Ownership Vocabulary

Use the existing manifest owner types rather than inventing a more elaborate
ownership system:

- `reusable_library`: `mi-core`, eval core, and eval UI packages.
- `reusable_workbench`: benchmark, orchestration, runner, lifecycle,
  publication, storage, bootstrap, versioning, and explorer-backend mechanics.
- `reference_use_case`: everything below the fixed `use_case/` root.
- `root_infrastructure`: non-secret project identity/configuration, dependency
  files, generated on-ramps, repository skills, and template-authoring files.
- `generated_local`: local outputs.

The plan and documentation should still explain the practical difference
between reusable product code, project-editable root configuration, and
use-case behavior, but the manifest does not need a new owner type for each
concept.

### AD-02: Consolidate reference behavior under one top-level `use_case/`

The MVP will adopt one physical replaceable root instead of preserving the
current scattered reference paths. Reusable Workbench Python remains under
`src/`; this refactor does not rename or repackage all reusable modules.

Target layout:

```text
mi-core/                         # reusable library
agent-dev-eval-core/             # reusable library
agent-dev-eval-ui/               # reusable library and React shell
src/                             # reusable Workbench Python only
  agent_versions/
  apps/
  benchmarks/
  evals/
  eval_lifecycle/
  eval_publication/
  pipelines/
  project_bootstrap/
  storage/
use_case/                        # one replaceable project implementation
  __init__.py
  docs/
  pipeline_configs/
  evaluation_configs/
  agent_version_configs/
  apps/
  actions/
  evidence/
  hydrators/
  objects/
  processors/
  retrievers/
  graders/
  explorer/
  tests/
www/                             # project frontend build/composition harness
workbench.project.json           # project configuration
models.yaml                      # project configuration
model_pricing.yaml               # reusable Workbench data
EvalRunbook.md                   # generated project configuration/runbook
```

`www/src/main.tsx` is a project composition root and may import both the
reusable UI shell and `use_case/explorer`. It is not reusable UI library code.

### AD-03: Enforce one-way dependencies

Allowed dependency direction:

```text
project composition → use_case → reusable Workbench → reusable libraries
project composition → reusable Workbench
```

Reusable libraries and reusable Workbench modules must not statically import
`use_case`. A fixed project-owned composition module may import both sides.

### AD-04: Use Fixed Paths And Simple Conventions

Do not make use-case paths configurable in `workbench.project.json`. Every
project uses the same `use_case/` structure. Define the fixed path conventions
once in a small reusable layout module and consume those constants from
bootstrap, CLIs, provenance, tests, skills, and documentation.

The fixed conventions are:

- `use_case/docs/`
- `use_case/pipeline_configs/`
- `use_case/evaluation_configs/`
- `use_case/agent_version_configs/`
- `use_case/apps/`
- `use_case/{actions,evidence,hydrators,objects,processors,retrievers}/`
- `use_case/graders/`
- `use_case/explorer/`
- `use_case/tests/`

Use a fixed project composition module, such as
`use_case/apps/eval_explorer.py`, to inject the use-case evidence adapter into
the reusable explorer backend. Do not build configurable extension import
paths. The current product has no custom grader, so use core graders only and
defer a custom-grader extension contract until a real use case requires one.

### AD-05: Move the generic benchmark runtime metadata contract into core

`BenchmarkExamplePipelineMetadata` represents the strategy-wide
unit/decision-timestamp/frozen-evidence contract, not Spirax behavior. Move it
from `src/objects/pipeline_metadata.py` into the reusable benchmark surface,
for example `src/benchmarks/pipeline_metadata.py`.

Do not generalize Spirax artifact formats, temperature normalization, charting,
or alarm projection. Those remain use-case code.

### AD-06: Keep Manifest Schema Version 1 And Simplify Reset

Do not introduce a manifest schema version 2 or per-path bootstrap action
language. Keep schema version 1 and make two focused improvements:

1. every tracked template file must resolve through longest-prefix matching to
   one effective existing owner; and
2. `reference_reset.clear_directories` contains only `use_case/`.

The existing explicit remove/render behavior is sufficient for the small set
of template-authoring and generated root files. Remove
`root_skills_with_project_defaults` because bootstrap does not use it and the
skills should discover the fixed conventions rather than be rendered per
project.

### AD-07: Use a hard source-layout cutover, not compatibility wrappers

Do not retain forwarding modules under the old use-case paths. They would:

- leave use-case names in reusable `src`;
- create duplicate registry discoveries;
- weaken import-boundary tests; and
- make the old layout appear supported indefinitely.

Update imports, YAML registry paths, scripts, tests, skills, and documentation
atomically. Historical eval artifacts remain immutable and are not rewritten.

### AD-08: Treat the source move as a new candidate-agent identity

Agent-version identity includes source paths, the resolved component graph, and
source hashes. Moving the reference implementation must therefore create a new
`agent_version_id`, even when behavior is unchanged.

Do not alias the new candidate to the old identity. Retained historical evals
continue to point to their original agent identity. Completed historical runs
must remain inspectable, but resuming an occurrence created against the old
source layout is not guaranteed.

### AD-09: A blank generated project must be independently valid

After bootstrap and before a use-case port:

- reusable Python imports and CLI `--help` commands work;
- reusable tests run without reference code;
- the project validator passes;
- the neutral use-case skeleton contains import-safe placeholders;
- the frontend builds with a small neutral “use case not configured” adapter;
  and
- attempting evidence display or eval execution fails with a precise
  configuration error rather than an import error.

### AD-10: Keep editable co-located core for MVP

Do not introduce package publication, independent repositories, or automatic
upgrade propagation in this refactor. The existing editable dependency model
remains. Approved reusable changes still require an explicit canonical
upstream handoff.

## Ordered Development Activities

These activities are ordered for implementation. Complete the exit criteria
for one activity before starting the next. The only deliberately large step is
Activity 3: because this plan uses a hard source-layout cutover, all consumers
of the moved paths must switch in the same changeset.

### Skill synchronization rule

Repository skills under `.agents/skills/` are part of the implementation
contract, not end-of-project documentation. At the end of every activity:

1. search skill instructions, skill references, `agents/openai.yaml` files, and
   skill-routing fixtures for paths, commands, ownership rules, or behavior
   changed by that activity;
2. update every affected skill in the same changeset as the code or contract
   change;
3. validate each changed skill with the installed `skill-creator`
   `quick_validate.py`;
4. run `uv run pytest tests/test_repository_skills.py -q`; and
5. record an explicit “no skill impact” result when the review finds no needed
   change.

Do not update a skill to describe a future layout before that layout is active.
Do not defer stale operational instructions until the final documentation
activity.

## 1. Establish The Baseline And Cutover Inventory

**Goal:** Decide what must move and preserve before changing any production
path.

### Work

1. Record the currently passing focused and broad Python/frontend checks,
   including the real Spirax pipeline construction test.
2. Capture behavior invariants for:
   - Spirax pipeline construction and structured outputs;
   - evaluation profile fields, applicability, slices, and scoring;
   - explorer evidence decoding and charts;
   - candidate identity and declared assets; and
   - working and retained eval listing, inspection, and deletion.
3. Produce an exhaustive inventory of production code, configuration, tests,
   scripts, skills, and documentation that reference the old paths.
4. Resolve every tracked file through the current ownership manifest and list
   uncovered or contradictory entries. Do not switch ownership to `use_case/`
   yet.
5. Reclassify the current `tests/use_case` suite before moving it:
   - move generic orchestration, lifecycle, versioning, explorer-backend,
     compatibility, pricing, model-catalog, and CLI coverage into reusable test
     paths;
   - create neutral test-only components where reusable integration tests need
     a pipeline or evidence adapter; and
   - leave only Spirax behavior tests marked for the future
     `use_case/tests/` tree.
6. Split mixed files such as `test_eval_orchestration.py` and
   `test_eval_explorer.py` by ownership instead of moving them wholesale.
7. Inspect local incomplete working evals before the cutover. Finish, delete,
   or explicitly accept each one as non-resumable. Do not rewrite working or
   retained artifacts.
8. Build the affected-skill inventory for `.agents/skills/`, including skill
   references, discovery metadata, agent metadata, and routing fixtures.

### Exit criteria

- Current behavior has a recorded green baseline or each pre-existing failure
  is documented.
- Every old path consumer is assigned to a later activity.
- Reusable tests no longer depend on being stored in a replaceable test tree.
- The local incomplete-eval cutover decision is complete.
- The skill impact review and required skill validation for this activity pass.

## 2. Prepare Reusable Foundations Without Switching Layouts

**Goal:** Create the reusable seams needed by the cutover while the existing
Spirax layout remains operational.

### Work

1. Keep `workbench.template.json`, `TemplateOwnershipManifest`,
   `workbench.project.json`, and bootstrap specifications at schema version 1.
2. Implement one shared longest-prefix ownership resolver and test it against
   the current manifest. Make current tracked-file ownership exhaustive without
   changing the reference reset root to `use_case/`.
3. Add one small reusable layout module that defines the future fixed
   `use_case/` paths. Test path safety and non-overlap, but do not activate the
   new defaults in production consumers yet.
4. Move `BenchmarkExamplePipelineMetadata` from the use-case-shaped
   `src/objects/pipeline_metadata.py` location to the reusable benchmark
   surface and update its imports atomically.
5. Remove `src/evals/graders/PROJECT_GRADERS` and use the reusable built-in
   grader registry directly. Preserve grader IDs and scoring contracts.
6. Extract the reusable explorer evidence-adapter protocol and constructor
   injection seam while keeping the current composition operational until
   Activity 3.
7. Add and test the neutral evidence and frontend placeholder implementations
   needed by generated blank projects. They must report “use case not
   configured” rather than failing during import.
8. Remove the hard-coded Spirax template from
   `mi-core/cli/src/cli/init_project.py` and make generic runner descriptions
   use-case neutral.
9. Keep `mi-core` changes limited to reference leakage and seams directly
   required by this refactor.

### Exit criteria

- The current old-layout Spirax pipeline, explorer, and eval profile still
  work.
- Reusable explorer and grader mechanics no longer require a project-owned
  registry or evidence implementation.
- The fixed target layout is defined once but has not prematurely changed a
  production default.
- Reusable `mi-core` production code contains no Spirax default.
- The skill impact review and required skill validation for this activity pass.

## 3. Perform The Atomic Source-Layout Cutover

**Goal:** Move every reference artifact and switch every path consumer in one
coherent, green changeset.

### Move map

| Current path | Target path |
|---|---|
| `docs/use_case/` | `use_case/docs/` |
| `pipeline_configs/` | `use_case/pipeline_configs/` |
| `evaluation_configs/` | `use_case/evaluation_configs/` |
| `agent_version_configs/` | `use_case/agent_version_configs/` |
| `src/actions/` | `use_case/actions/` |
| `src/evidence/` use-case implementation | `use_case/evidence/` |
| `src/hydrators/` | `use_case/hydrators/` |
| `src/objects/` remaining domain objects | `use_case/objects/` |
| `src/processors/` | `use_case/processors/` |
| `src/retrievers/` | `use_case/retrievers/` |
| `www/src/use_case/` | `use_case/explorer/` |
| `tests/use_case/` remaining Spirax tests | `use_case/tests/` |

### Work

1. Create `use_case/` as an importable package with the fixed `apps`, `docs`,
   configuration, component, `graders`, `explorer`, and test directories.
2. Move reference files rather than copying them. Never leave old and new
   component modules visible to the registry at the same time.
3. Activate the fixed layout module across bootstrap, eval chooser defaults,
   agent-policy lookup, validation, and other conventional path consumers.
   Preserve explicit positional CLI paths.
4. Update Python imports, pipeline YAML, evaluation profiles, agent policies,
   declared assets, documentation assets, and non-execution exclusions.
5. Switch registry scanning to `use_case/**/*.py`, continue excluding tests,
   and verify the Spirax pipeline builds through the real registry.
6. Switch provenance and candidate identity together with the source move:
   - include reusable `src`, reusable libraries, and fixed use-case
     source/configuration paths;
   - include reachable use-case and `mi-core` execution dependencies;
   - exclude unrelated reusable Workbench management code as intended; and
   - fail closed for traversal or missing declared assets.
7. Add `use_case/apps/eval_explorer.py` as the fixed backend composition root.
   It constructs the Spirax evidence adapter and injects it into the reusable
   explorer.
8. Move the Spirax frontend schema, labels, evidence display, and charts into
   `use_case/explorer/`. Keep `www/src/main.tsx` as the composition root and
   use the same fixed `use_case/explorer/adapter.tsx` import in every project.
9. Switch the schema-v1 manifest to one `reference_use_case` owner for
   `use_case/`, set `reference_reset.clear_directories` to only `use_case/`,
   and remove the unused `root_skills_with_project_defaults` field.
10. Update bootstrap in the same changeset so clearing `use_case/` immediately
    produces:
    - an import-safe package and standard empty directories;
    - durable context prompts under `use_case/docs/`;
    - neutral evidence/backend and frontend adapters;
    - an empty `use_case/graders/` package without discovery or a plugin
      contract;
    - project contract and model placeholders; and
    - `.env.example`, README, and EvalRunbook placeholders.
11. Update `pyproject.toml`, pytest/type-check settings, Vite, and TypeScript
    aliases for the new package and frontend location.
12. Move only the remaining Spirax tests identified in Activity 1 into
    `use_case/tests/`.
13. Remove every obsolete reference directory after all consumers have
    switched.
14. Update affected `.agents/skills/` paths, commands, examples, agent
    metadata, references, and routing cases as part of this same cutover.

### Atomicity rule

Activity 3 may be developed in local substeps, but it is one review and merge
unit. Do not hand off or merge a state with:

- both old and new registry components;
- ownership pointing at a directory that has not moved;
- provenance scanning a different layout from runtime discovery;
- bootstrap generating an unimportable repository;
- explorer composition importing a removed evidence path; or
- skills directing an agent to the old layout.

### Exit criteria

- `src/` contains no reference pipeline component, evidence decoder,
  domain-output schema, prompt, or domain object.
- Every reference behavior and configuration artifact is beneath `use_case/`,
  apart from designated project composition and root configuration.
- Ownership is exhaustive and reset has exactly one clear root.
- The Spirax Python and frontend composition paths work from the new layout.
- Bootstrap generates an importable neutral project immediately after the
  cutover.
- Repository skills describe the active layout, and their validation passes.

## 4. Verify Behavior, Provenance, And Historical Results

**Goal:** Prove the cutover preserved semantics while intentionally changing
source identity.

### Work

1. Re-run the Activity 1 behavior invariants for the Spirax pipeline,
   structured outputs, evaluation profile, explorer, and lifecycle behavior.
2. Add regression tests showing:
   - deterministic candidate identity within the new layout;
   - dirty reachable use-case and `mi-core` files are captured;
   - unrelated Workbench changes are excluded as designed;
   - declared prompt, schema, evidence, action, and operator-document assets
     resolve; and
   - traversal and missing assets fail closed.
3. Verify completed old-layout working and retained fixture bundles remain
   listable, inspectable, verifiable, and deletable without mutation.
4. Confirm the first post-cutover Spirax candidate has a new
   `agent_version_id`; do not alias it to the old identity.
5. Describe the new candidate as behavior-equivalent but
   source-layout-distinct. Accuracy comparison remains valid; identity equality
   is neither expected nor desired.
6. Verify the Spirax profile produces identical field, applicability, slice,
   and accuracy behavior.
7. Verify current and retained explorer storage identities use the same
   injected evidence-factory contract.

### Exit criteria

- Spirax behavior is unchanged within the captured invariants.
- New candidate identity is stable and complete.
- Historical results retain their original identity and remain reviewable.
- The skill impact review and required skill validation for this activity pass.

## 5. Enforce Boundaries And Validate A Neutral Project

**Goal:** Turn the architectural boundary into continuous tests and prove the
future neutral template shape.

### Work

1. Add a Python AST boundary test:
   - reusable owners may not import `use_case`;
   - `use_case` may import reusable modules; and
   - designated project composition roots may import both.
2. Add equivalent TypeScript import-boundary checks.
3. Scan reusable production owners for canonical reference terms. Isolated
   reusable unit tests may use Spirax as self-contained test data, but may not
   create a production dependency or default.
4. Require every Git-tracked template file to resolve to an effective existing
   owner and fail CI when an unowned file is added.
5. Continue rejecting unsafe reset paths and contradictory clear/remove
   declarations before changing a destination.
6. Verify all use-case structured outputs, prompts, schemas, evidence recipes,
   source fields, and UI labels resolve beneath `use_case/`.
7. Create a temporary generated repository and:
   - validate its project structure and identities;
   - confirm no Spirax/reference terms remain;
   - import reusable packages and run supported CLIs with `--help`;
   - run the reusable Python tests without reference code;
   - run frontend tests/build using the neutral adapter; and
   - confirm pipeline/eval execution reports “use case not configured” before
     external access or run-state creation.
8. Verify clearing or removing `use_case/` leaves meaningful reusable
   orchestration, explorer, lifecycle, versioning, and bootstrap coverage.
9. Verify built-in graders work in the neutral project; do not add custom
   grader discovery.

### Exit criteria

- Adding a forbidden reference import or identifier to reusable production
  source fails locally and in CI.
- An unowned tracked file fails CI.
- A blank generated project validates, imports, tests, and builds without
  Spirax.
- Removing the reference tree does not remove reusable product coverage.
- The skill impact review and required skill validation for this activity pass.

## 6. Complete Documentation, Skill Sweep, And Operator Handoff

**Goal:** Finish the explanatory material and prove no operational guidance is
stale.

Path- and command-sensitive skill changes must already have been made during
Activities 1–5. This activity is a final repository-wide consistency sweep, not
the first skill update.

### Work

1. Update `README.md`, `EvalRunbook.md`, `.env.example`, and `AGENTS.md` for the
   consolidated `use_case/` root and current commands.
2. Update `workbench.template.json` and generated README text to explain the
   three practical editing zones: reusable product, project configuration, and
   use-case implementation.
3. Update `docs/product-strategy/mvp-scope.md` only if the implementation
   decisions need to replace the now-resolved physical-migration statement.
4. Add a migration note recording:
   - the old-to-new path map;
   - the agent-identity impact;
   - the incomplete-working-run cutover policy; and
   - the canonical upstream destination for reusable changes.
5. Record the narrow reusable `mi-core` cleanup for upstreaming to the
   canonical `mesh.insights.core` source.
6. Describe the future template repository as reusable product source plus the
   fixed neutral `use_case/` skeleton, with no Spirax content.
7. Search all active documentation, scripts, configuration, tests, and
   `.agents/skills/` for obsolete paths or instructions. Remove obsolete
   guidance rather than documenting both layouts.
8. Review every repository skill for:
   - durable context paths;
   - pipeline, evaluation, and agent-version configuration paths;
   - Python component and explorer paths;
   - CLI commands and entrypoints;
   - ownership and reusable/use-case boundaries;
   - routing to specialized skills; and
   - generated-project behavior.
9. Update skill `SKILL.md` files, linked references, `agents/openai.yaml`
   metadata, and routing fixtures together wherever any one of them changes.
10. Validate every changed skill with `quick_validate.py`, then run the
    repository skill test suite.

### Exit criteria

- Repository search finds no active command, skill, or on-ramp using an old
  reference path.
- A coding agent can identify ownership and the correct specialized skill
  without inspecting implementation history.
- All changed skills and skill-routing tests pass.

## 7. Run The Completion Gate

**Goal:** Prove the refactor is ready for development handoff and release.

### Required local checks

1. Run focused bootstrap, manifest-coverage, fixed-layout, benchmark,
   agent-version, evaluation, lifecycle, publication, and explorer tests.
2. Run the full reusable package and root Python suite:

   ```bash
   uv run pytest -q
   ```

3. Run Python lint and type checks:

   ```bash
   uv run ruff check src use_case
   uv run basedpyright
   ```

4. Run frontend checks:

   ```bash
   cd www
   pnpm test
   pnpm build
   ```

5. Validate all changed repository skills with the installed validator and
   run:

   ```bash
   uv run pytest tests/test_repository_skills.py -q
   ```

6. Build the Spirax reference pipeline through the real registry and run its
   focused pipeline contract and exact-example runner tests.
7. Generate a temporary neutral repository and repeat the complete
   generated-project acceptance test from Activity 5.
8. Run `git diff --check`.

### Authorized external integration gate

Because pipeline locations, registry discovery, evidence loading, and candidate
identity change, final completion also requires one exact, explicitly versioned
published Spirax example using `EvalRunbook.md`. This may require credentials
and a model call, so run it only with explicit authorization. Record the exact
benchmark, example, model, and resulting candidate identity.

Do not substitute a one-example eval occurrence for exact-example pipeline
validation.

### Final definition of done

- Reusable product code contains no reference-use-case imports or behavior.
- Every tracked template file has one effective existing owner.
- The fixed `use_case/` layout is defined once and used consistently.
- All reference behavior lives under `use_case/`, apart from designated root
  composition and configuration files.
- A blank generated project validates, imports, and builds its neutral
  frontend without reference content.
- The Spirax reference pipeline, eval profile, explorer, and lifecycle still
  work from the new layout.
- Reusable coverage remains after the reference tree is cleared.
- New agent provenance is deterministic and historical results remain
  inspectable without mutation.
- Skills were updated alongside the changes that affected them and the final
  skill sweep finds no stale operational guidance.

## Handoff Rule

The numbered activities above are the delivery sequence. Do not create a
second, cross-cutting implementation order. A developer should start at
Activity 1 and proceed one activity at a time through Activity 7, using each
activity’s exit criteria as the handoff gate.

## Explicitly Deferred

- Publishing reusable Workbench packages.
- Splitting reusable libraries into separate repositories.
- Automatic propagation of core upgrades to use-case repositories.
- Configurable use-case directory layouts or extension import paths.
- A custom-grader plugin system before a concrete use case requires it.
- A general migration framework for other use-case repositories.
- Portable agent package design.
- Production runtime adapters or production hosting.
- Benchmark Studio write paths or benchmark-truth changes.
- Changes to eval result schemas, lifecycle semantics, or retained artifact
  layout that are not required by the source move.
