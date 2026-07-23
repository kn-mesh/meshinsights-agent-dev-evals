# Template And Reference Use-Case Separation Plan

## Status

Proposed feature and skill plan.

## FDE Outcome

An FDE can create a separate Git repository from the Agent Workbench template,
replace the complete Spirax reference use case without disturbing reusable
libraries or generic Workbench mechanics, and safely request shared changes
when the use case reveals a genuine core gap.

## Current State

The repository currently combines:

- the forked `mi-core/` pipeline and AI runtime library;
- `agent-dev-eval-core/`;
- `agent-dev-eval-ui/`;
- generic Workbench behavior under root `src/`;
- use-case behavior under root `src/`;
- root pipeline, evaluation, agent-version, and project configuration;
- generic and Spirax-specific frontend composition;
- root-level repository skills; and
- project bootstrap/template behavior.

The root project uses editable path dependencies, which is appropriate for rapid
MVP co-development. The problem is not editability itself; it is that the
replaceable Spirax surface is distributed across several paths and coding-agent
skills currently instruct agents to change reusable code without the newly
required approval gate.

## Target Repository Model

Each use case receives its own Git repository created from the working template.
The template contains:

- all reusable libraries and generic Workbench source;
- the standard project structure;
- root-level `.agents/skills/`; and
- one complete, runnable Spirax reference use case.

The new project replaces the reference content in one documented operation.
Customers do not receive the source repository.

Reusable components remain distinct:

- `mi-core/` is the forked pipeline and AI runtime library;
- `agent-dev-eval-core/` is the reusable evaluation library;
- `agent-dev-eval-ui/` is the reusable explorer library and UI shell; and
- other use-case-neutral Workbench mechanics remain separately identifiable.

Do not create a catch-all `mi-core` or move unrelated Workbench code into the
forked library.

## Feature 1: Ownership Inventory

Create a versioned ownership manifest that classifies every project path as:

- reusable library;
- reusable Workbench mechanics;
- replaceable reference-use-case content;
- root project or skill infrastructure; or
- generated/local state.

The inventory must cover at least:

- `mi-core/`;
- `agent-dev-eval-core/`;
- `agent-dev-eval-ui/`;
- `.agents/skills/`;
- `src/`;
- `docs/use_case/`;
- `pipeline_configs/`;
- `evaluation_configs/`;
- `agent_version_configs/`;
- `www/`;
- `models.yaml`;
- `workbench.project.json`;
- `bootstrap_configs/`;
- `eval_results/`; and
- `agent_versions/`.

For mixed paths such as `src/` and `www/`, identify the exact subpaths or
symbols that must move or become explicit extension points.

## Feature 2: Replaceable Use-Case Seam

Create one manifest-driven reference seam containing:

- project and Benchmark Studio identity;
- use-case documentation;
- objects and domain contracts;
- retrievers and evidence decoding;
- hydrators, processors, and actions;
- pipeline configurations;
- evaluation fields, graders, and named sections;
- agent-version configurations and prompts;
- use-case-specific frontend schema, charts, and composition; and
- reference-specific model or dependency additions.

The physical directory may be `use_case/` or another name selected during the
inventory. The key requirement is that bootstrap and validation know the exact
replaceable paths; an FDE should not discover them through search-and-delete.

Skills remain at `.agents/skills/`. The seam manifest separately identifies
which root skills are generic and which files contain reference-specific
defaults that must be rewritten for the new use case.

## Feature 3: Template Initialization And Validation

Extend `src/project_bootstrap/` so initialization can:

1. copy one exact template revision into a new, empty Git repository;
2. preserve reusable libraries, generic Workbench mechanics, and generic root
   skills;
3. remove or reset the manifest-declared Spirax reference paths;
4. write the new project, benchmark, evidence, and model identities;
5. leave clear placeholders for new use-case code and UI composition;
6. exclude local evals, retained versions, credentials, caches, and generated
   build outputs; and
7. validate that no undeclared Spirax identifiers remain outside explicitly
   allowed reference documentation.

Keep a separate mode that validates the untouched template can still run the
complete Spirax reference example.

## Feature 4: Reusable-Code Approval Gate

Update root-level coding-agent guidance so an agent may inspect reusable code
but must ask before editing it.

Before proposing a reusable change, the agent must:

- show why a correct use-case-local implementation is insufficient;
- identify the reusable owner and exact paths or contracts;
- explain the cross-use-case meaning;
- state focused validation; and
- receive explicit user approval.

Apply the gate to:

- `mi-core/`;
- reusable eval code;
- reusable UI code;
- generic orchestration;
- project bootstrap;
- agent-version mechanics; and
- generic lifecycle mechanics.

Approval to change one reusable component does not imply approval to reorganize
other reusable packages.

## Feature 5: Shared-Fix Upstream Handoff

When an approved reusable fix is made in a use-case repository:

- implement and test it locally;
- mark it as reusable in the work handoff;
- identify the canonical template or library target;
- record the local commit or patch and focused tests;
- record the upstream issue, PR, commit, or explicitly pending action; and
- do not call the shared fix complete without that upstream reference.

Do not add package publishing, submodules, or automatic cross-repository sync
for MVP.

## Agent Skill Deliverables

### Update `project-guide`

- Describe the ownership manifest and replaceable seam.
- Preserve `mi-core/` as a distinct forked library.
- Require approval before reusable changes.
- Route new-project work to the port and bootstrap skills.
- Explain the shared-fix upstream handoff.

### Update `benchmark-pipeline-port`

- Start from the empty use-case seam produced by bootstrap.
- Refuse to overwrite reusable paths.
- Populate only manifest-declared use-case locations.
- Rewrite reference-specific root skill defaults when required.

### Update `pipeline-builder`, `ai-processor-builder`, and
`external-runtime-setup`

Replace instructions to modify `mi-core/` or other reusable source directly with
the approval workflow. Update all paths after the seam migration.

### Update `port-eval-explorer-use-case`

Use the reusable UI shell and populate only the declared use-case evidence
schema and composition paths.

### Update `run-use-case-evals`

Remove hard-coded Spirax identity from the generic template portion. Keep named
sections and operational defaults project-owned so a new repository can rewrite
them without moving the skill from `.agents/skills/`.

### Add or extend a bootstrap skill

Provide one root-level workflow for:

- creating the new Git repository from an exact template revision;
- clearing the reference seam;
- capturing durable use-case context;
- configuring Benchmark Studio and model identities;
- validating that reusable code was not changed; and
- handing off to the benchmark pipeline and explorer port skills.

Prefer extending an existing project/bootstrap skill if one already owns the
workflow; add a new `create-use-case-project` skill only if no existing skill
has a clear trigger and complete sequence.

## Validation

- Untouched template still runs the Spirax reference smoke path.
- New-project initialization produces a separate Git repository.
- Reusable package contents match the selected template revision.
- No local eval, retained version, credential, cache, or build output is copied.
- Reference reset removes all manifest-declared Spirax content.
- Validation detects undeclared Spirax leakage.
- New use-case placeholders and root skills remain usable.
- Porting populates only replaceable paths.
- Tests cover the approval-routing language in relevant skills.
- One representative approved shared fix produces a complete upstream handoff
  record.

## Non-Goals

- publishing reusable packages;
- automatic upgrades across use-case repositories;
- Git submodules;
- merging all reusable code into `mi-core/`;
- moving `.agents/skills/` under the use-case directory;
- customer access to source repositories; and
- portable agent packaging.

## Completion Criteria

An FDE can identify every replaceable reference path before changing files,
bootstrap a clean separate repository, port a new use case without editing
reusable code, and follow an explicit approval and upstream process when a
genuine shared gap is found.
