# Core And Use-Case Separation Migration

**Implemented:** 2026-07-27

The repository now has one fixed replaceable use-case root. Reusable product
code remains in `mi-core/`, `agent-dev-eval-core/`, `agent-dev-eval-ui/`, and
use-case-neutral `src/` modules. Root identity, model, environment, runbook, and
frontend composition files remain project configuration.

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

`BenchmarkExamplePipelineMetadata` moved separately into reusable
`src/benchmarks/` ownership.

## Identity And Existing Evals

The source layout is part of candidate provenance. A candidate resolved from
the new tree is behavior-equivalent to the pre-cutover Spirax candidate but has
a deliberately different `agent_version_id`; it must not be aliased to an old
identity.

Existing working and retained eval artifacts are not rewritten. Their recorded
`pipeline_configs/v1_3.ppln` path and original agent-version identity remain
historical facts. At cutover, every discovered local working eval was already
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
