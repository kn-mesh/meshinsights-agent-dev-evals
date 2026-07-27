# Core And Use-Case Separation Migration

**Implemented:** 2026-07-27

The repository now has one fixed replaceable use-case root. Reusable product
code lives in the independently packaged libraries under `packages/` and the
use-case-neutral `workbench/` Python package. Fixed application composition
roots live under `apps/`; root identity, model, environment, and runbook files
remain project configuration.

## Path Cutover

| Previous path | Current path |
|---|---|
| `docs/use_case/` | `use_case/docs/` |
| `pipeline_configs/` | `use_case/pipeline_configs/` |
| `evaluation_configs/` | `use_case/evaluation_configs/` |
| `agent_version_configs/` | `use_case/agent_version_configs/` |
| `src/actions/` | `use_case/actions/` |
| `src/evidence/` | `use_case/evidence/` |
| `src/hydrators/` | `use_case/hydrators/` |
| `src/objects/` reference objects | `use_case/objects/` |
| `src/processors/` | `use_case/processors/` |
| `src/retrievers/` | `use_case/retrievers/` |
| `www/src/use_case/` | `use_case/explorer/` |
| `tests/use_case/` reference tests | `use_case/tests/` |
| `mi-core/` | `packages/mi-core/` |
| `agent-dev-eval-core/` | `packages/eval-core/` |
| `agent-dev-eval-ui/` | `packages/eval-ui/` |
| reusable `src/` modules | `workbench/` |
| root `model_catalog.py` | `workbench/models/catalog.py` |
| `src/model_configuration.py` | `workbench/models/configuration.py` |
| `www/` | `apps/eval_explorer/web/` |
| `use_case/apps/eval_explorer.py` | `apps/eval_explorer/server.py` |
| `bootstrap_configs/example.project.json` | `examples/project-bootstrap.json` |
| `eval_results/` | `.workbench/evals/` |
| root `agent_versions/` | `.workbench/agent-versions/` |
| `EvalRunbook.md` | `EVAL_RUNBOOK.md` |
| `model_pricing.yaml` | `model-pricing.yaml` |
| reusable root tests | `tests/workbench/` |
| boundary and repository tests | `tests/architecture/` |

`BenchmarkExamplePipelineMetadata` moved separately into reusable
`workbench/benchmarks/` ownership.

## Identity And Existing Evals

The source layout is part of candidate provenance. A candidate resolved from
the new tree is behavior-equivalent to the pre-cutover Spirax candidate but has
a deliberately different `agent_version_id`; it must not be aliased to an old
identity.

Existing working and retained eval artifact contents are not rewritten. Their recorded
`pipeline_configs/v1_3.ppln` path and original agent-version identity remain
historical facts; only the enclosing generated-output root moved from
`eval_results/` to `.workbench/evals/`. At cutover, every discovered local working eval was already
fully materialized, so no incomplete occurrence needed resumption or deletion.
All seven recorded evals remain listable and inspectable, and retained eval
`ret_0c04da94528c80d073856724` verifies with all 210 unit records.

## New-Project Shape

The future template repository contains reusable product source, root project
configuration, generic skills, and the fixed neutral `use_case/` skeleton. It
contains no Spirax prompts, identifiers, schemas, evidence decoder, pipeline,
evaluation profile, model policy, or UI. Before a use case is ported, pipeline
and eval commands fail with “Use case not configured” before external access
or local run creation, while the neutral explorer still imports, tests, and
builds.

## Reusable Upstream Work

This refactor made one narrow reusable-library cleanup: the `mi-core` project
initializer no longer offers a hard-coded Spirax template. That change and its
CLI regression test should be upstreamed to the canonical
`mesh.insights.core` source. Reusable Workbench changes should likewise land in
the canonical Agent Workbench template before they are copied into another
use-case repository.

## Root-Level Naming Decision

The root names now answer different questions:

- `packages/` means independently packaged, reusable libraries;
- `workbench/` means reusable Python behavior supplied by the template;
- `use_case/` means the one replaceable project implementation;
- `apps/` means stable composition and executable entry points;
- `tests/` mirrors reusable and cross-boundary ownership; and
- `.workbench/` means generated local state, never source.

There is no generic `src/` root because it hid this ownership distinction.
There is no `use_case/apps/` root because the application itself is stable:
only the adapter it imports is replaceable.

## Completion Validation

The authorized external gate passed on 2026-07-27 with:

- benchmark `phase-1-benchmark-3fb7f544`, version `1`;
- example `250000101|2024-11-03T14:00:32`;
- model `azure:gpt-5.6-luna`, reasoning effort `medium`;
- pipeline `use_case/pipeline_configs/v1_3.ppln`; and
- cutover candidate `av_34dfa80839c2141dd533183f`.

The exact-example runner completed retrieve, process, and act successfully
without creating an eval occurrence. The recorded candidate is the dirty
cutover-worktree identity; a later source commit correctly produces a new clean
identity because Git revision and tree state are part of provenance.

The root-layout cutover was revalidated the same day against the same published
example and model after the final package, Workbench, application, generated
state, and file-name moves. Retrieve, process, and act again completed
successfully without creating an eval occurrence. The final dirty-worktree
candidate exercised by that live gate was `av_087bfb3a0fe3f922bf4272f2`.
The subsequent removal of unnecessary root-package installation changed
`pyproject.toml` and `uv.lock` without changing runtime behavior; the completed
dirty-worktree candidate is therefore `av_9c8ad884c5c6adeb3201985e`. These
identities differ from the earlier cutover because source paths and dependency
identities are intentionally part of candidate provenance.
