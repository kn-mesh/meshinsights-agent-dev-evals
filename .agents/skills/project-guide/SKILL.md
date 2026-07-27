---
name: project-guide
description: Orient developers in a MeshInsights Agent Workbench repository. Use to explain how the project fits together, where a change belongs, how to customize the template, whether behavior is use-case-specific or reusable, which files define current behavior, and which specialized repo skill should handle a task.
---

# Project Guide

Ground guidance in current repository evidence and route implementation to the
narrowest skill. This use-case project consumes published Benchmark Studio
benchmarks and frozen evidence read-only; it does not own Studio workflow truth
or the production agent runtime.

## Ground Answers

Read, in order:

1. The request and named files.
2. Durable `docs/use_case/` context.
3. Current source, configs, tests, and runnable entry points.
4. The specialized repo skill.
5. Editable `mi-core/` source when framework behavior matters.
6. `README.md` for on-ramp context.

Current coherent code defines local behavior. For architecture or product
choices, use `docs/product-strategy/` when that template-repository directory
exists; generated projects instead use `workbench.project.json`,
`docs/use_case/`, and this skill's boundaries.

Use `uv run` for Python commands. Use the package manager declared by each
non-Python workspace. Treat `mi-core/` as editable reusable source, not
automatic scope.

## Ownership And Approval

- `mi-core/`: reusable pipeline/AI runtime mechanics.
- Reusable Workbench paths: eval, explorer shell, bootstrap, versioning,
  orchestration, lifecycle, and operator mechanics.
- Manifest-declared reference paths: use-case data, rules, prompts, variants,
  evidence projection, and UI composition.
- `.agents/skills/`: concise repository workflows.

Use `workbench.template.json` as the ownership map. If the request explicitly
authorizes the named reusable scope, proceed after stating its ownership and
focused tests. Otherwise, identify the exact reusable paths/contracts and pause
once for approval. Record the canonical upstream target or pending action for
an approved shared fix.

## Repository Layout

Use `workbench.template.json` as the authoritative path inventory. Its
`ownership` entries distinguish reusable, reference-use-case, root, and
generated-local paths. Common project paths are `pipeline_configs/`,
`evaluation_configs/`, `agent_version_configs/`, `src/{retrievers,objects,hydrators,processors,actions,evidence}/`,
and `www/src/use_case/`. Treat examples as starting patterns.

## Gate New Work

Identify the FDE job—create, port, build, evaluate, inspect, improve, package,
or hand off—the current blocker, and the simplest existing path. Make reusable
only behavior supported by cross-use-case evidence; name adjacent work to defer.

## Route To Specialized Skills

| Task | Skill |
|---|---|
| Bootstrap a separate project | `$create-use-case-project` |
| Initial Studio evidence-pipeline port | `$benchmark-pipeline-port` |
| Port explorer evidence/schema/charts | `$port-eval-explorer-use-case` |
| Pipeline components, variants, runners, receipts | `$pipeline-builder` |
| Structured AI workflows or agents | `$ai-processor-builder` |
| Prepare, run, or troubleshoot evals | `$run-use-case-evals` |
| Change eval contracts, graders, or apps | `$agent-eval-builder` |
| Analyze completed eval results | `$eval-results-analysis` |
| Elevate, verify, or permanently delete evals | `$eval-lifecycle` |
| Publish one retained eval | `$publish-retained-eval` |
| Models, pricing, auth, runtime, telemetry | `$external-runtime-setup` |

Use multiple skills only when the request truly spans them.

## Guide Template Customization

Use `$create-use-case-project`, then capture `docs/use_case/`, set project and
benchmark identities, configure models, replace manifest-declared reference
paths, and validate one control pipeline. Keep reusable Workbench and
`mi-core/` mechanics distinct from use-case rules.

## Development Sequence

1. Durable use-case context.
2. Evidence inspection and visualization.
3. Runnable YAML control pipeline.
4. Deterministic baseline.
5. One-shot AI only when needed.
6. Tool-using agent only when targeted investigation helps.
7. Eval loop and operator handoff after outputs stabilize.

## Completion Verification

For implementation work, read the
[repository verification matrix](references/verification-matrix.md), select
every row touched by the change, and report any required check that could not
run. Do not substitute one layer's green tests for another affected layer.

For guidance, answer directly, cite exact files/symbols, distinguish current
behavior from recommendations, and give the narrowest next action. For
implementation, load the routed skill, change the owning layer, and verify in
proportion to risk.
