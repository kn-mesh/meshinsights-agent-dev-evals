# MVP Codebase Alignment Plan

## Status

Proposed implementation program derived from
`docs/product-strategy/mvp-scope.md`.

This plan is self-contained implementation guidance. The durable product
authority is `docs/product-strategy/mvp-scope.md`; no temporary review document
is required to understand or execute this program.

## Outcome

Align the current Agent Workbench implementation with the decided MVP:

- optimize for the FDE evaluation and agent-improvement loop;
- make the normal eval path easy to understand and operate;
- separate disposable working evals from elevated retained evals;
- keep the local review app rich but read-only;
- make the Spirax reference use case safely replaceable;
- preserve rapid editing of reusable source while requiring approval before a
  coding agent changes it; and
- stop treating already-built generic lifecycle and orchestration machinery as
  mandatory product behavior.

## Program Structure

Implement the work through three bounded plans:

1. [`template-reference-separation-plan.md`](template-reference-separation-plan.md)
   establishes reusable-versus-use-case ownership, the replaceable reference
   seam, root-level skill rules, and the shared-code approval gate.
2. [`evaluation-workflow-simplification-plan.md`](evaluation-workflow-simplification-plan.md)
   protects the standard benchmark-selection, execution, resume, token, and
   cost path while hiding or freezing unsupported orchestration options.
3. [`eval-results-lifecycle-and-review-plan.md`](eval-results-lifecycle-and-review-plan.md)
   implements working versus retained results, full-run elevation, compact
   preservation, permanent deletion, Azure evidence references, and read-only
   explorer filters.

## Recommended Sequence

### Phase 1: Establish ownership before moving behavior

Complete the ownership inventory, replaceable-path manifest, and coding-agent
approval rules from the template/reference plan. Do not begin with a broad
directory move. First make every current path classifiable as:

- reusable library;
- reusable Workbench mechanics;
- replaceable use-case content;
- root-level project or skill infrastructure; or
- local generated state.

This prevents later eval changes from being implemented in the wrong layer.

### Phase 2: Protect the minimum eval path

Simplify the operator-facing eval workflow and complete pricing and cost
summaries. Keep existing compatible internals when they are inexpensive, but do
not expose process execution, arbitrary predicates, selective failure
generations, or materialization-only operations as part of the supported path.

### Phase 3: Replace the result lifecycle

Introduce the working/retained result contract only after the minimum run
identity, selection, cost, and resume behavior is stable. Make elevation the one
boundary that retains both the eval and its meaningful agent version.

### Phase 4: Align the read-only app and skills

Finish explorer support for working and retained results, then validate every
root skill against the implemented commands and paths. Skills must describe the
real workflow; they must not preserve deprecated flags or lifecycle concepts.

## Cross-Plan Product Rules

1. `docs/product-strategy/mvp-scope.md` is the durable product authority.
2. Benchmark Studio remains the read-only owner of published benchmarks,
   labels, frozen schemas, and evidence packages.
3. Evidence is retrieved from Azure Blob Storage by immutable identity and is
   not copied into retained eval artifacts.
4. The review app remains read-only for MVP.
5. Deletion is permanent. Do not build quarantine or restore.
6. Elevation and deletion operate on complete eval runs, not individual units.
7. Coding agents must ask before changing any reusable component, including
   `mi-core/`, reusable eval code, reusable UI code, bootstrap, versioning, or
   generic lifecycle mechanics.
8. `mi-core/` remains a distinct forked pipeline/runtime library. Do not use it
   as a catch-all location for other reusable Workbench code.
9. All repository skills remain under `.agents/skills/`.

## Shared Delivery Requirements

Each implementation plan must produce:

- a current-to-target contract map;
- focused tests for changed supported behavior;
- a compatibility or removal decision for superseded behavior;
- updated operator documentation;
- updated root-level skills;
- a list of reusable paths changed with evidence of user approval; and
- a concise record of any reusable fix that still needs to be upstreamed to the
  canonical template or library source.

## Explicitly Deferred

- portable agent packaging;
- Microsoft Foundry or other production-runtime translation;
- production-feedback ingestion;
- cloud preservation of elevated evals;
- published versioned core packages;
- automatic updates across use-case repositories;
- generic local artifact administration;
- multi-user local coordination; and
- any new eval runtime or recovery mode not required by the protected workflow.

## Program Completion

The program is complete when a new FDE can:

1. create a separate use-case repository from the working template;
2. replace the documented Spirax reference seam without changing reusable code;
3. configure a model and its pricing;
4. run the full benchmark, selected units, or a named use-case section;
5. interrupt and resume missing work;
6. inspect a rich working result in Codex or the read-only app;
7. elevate a meaningful full eval and its agent version;
8. review retained full outputs, grading, accuracy, tokens, and cost without
   retained performance clutter;
9. distinguish working and retained evals in the app; and
10. permanently delete either state through the appropriate confirmed command.
