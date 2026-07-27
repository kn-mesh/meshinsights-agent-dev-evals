---
name: project-guide
description: Orient work in an Agent Workbench repository. Use to explain architecture, ownership, template customization, current behavior, route to specialized repo skills, or coordinate a multi-skill agent improvement loop.
---

# Project Guide

Ground guidance in current repository evidence and route implementation to the
narrowest skill. This use-case project consumes published Benchmark Studio
benchmarks and frozen evidence read-only; it does not own Studio workflow truth
or the production agent runtime.

## Ground Answers

Read, in order:

1. The request and named files.
2. Durable `use_case/docs/` context.
3. Current source, configs, tests, and runnable entry points.
4. The specialized repo skill.
5. Editable `packages/mi-core/` source when framework behavior matters.
6. `README.md` for on-ramp context.

Current coherent code defines local behavior. For architecture or product
choices, use `docs/product-strategy/` when that template-repository directory
exists; generated projects instead use `workbench.project.json`,
`use_case/docs/`, and this skill's boundaries.

Follow root `AGENTS.md` for commands, ownership, authorization, and verification.
Treat `packages/mi-core/` as editable reusable source, not automatic scope.

## Repository Layout

Use `workbench.template.json` as the authoritative path inventory. Its
`ownership` entries distinguish reusable, reference-use-case, root, and
generated-local paths. Common project paths are `use_case/pipeline_configs/`,
`use_case/evaluation_configs/`, `use_case/agent_version_configs/`,
`use_case/{retrievers,objects,hydrators,processors,actions,evidence}/`, and
`use_case/{graders,explorer,tests}/`. The fixed application composition roots
live under `apps/`. Treat examples as starting patterns.

## Gate New Work

Identify the FDE job—create, port, build, evaluate, inspect, improve, package,
or hand off—the current blocker, and the simplest existing path. Make reusable
only behavior supported by cross-use-case evidence; name adjacent work to defer.

## Route To Specialized Skills

| Task | Skill |
|---|---|
| Repository orientation or multi-skill coordination | `$project-guide` |
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

## Improve An Agent Variant

For requests to improve agent accuracy, reliability, coverage, or cost, treat
the work as one measured candidate loop:

1. **Establish the baseline.** Select exact completed eval IDs or revisions and
   use `$eval-results-analysis` to identify repeated failure patterns. If no
   suitable completed eval exists, use `$run-use-case-evals` only for an
   explicitly requested and authorized baseline measurement.
2. **State one hypothesis.** Name the behavior expected to improve, the metric
   or failure cluster that will measure it, and the benchmark, evidence,
   grader, model, and other dimensions to hold constant.
3. **Check measurability.** Use `$agent-eval-builder` only when the existing
   profile, grader, orchestration, result, or explorer path cannot measure or
   inspect the hypothesis. Do not change eval infrastructure by default.
4. **Build an isolated candidate.** Use `$pipeline-builder` for the measurable
   variant and `$ai-processor-builder` only for AI internals. Preserve the
   baseline identity, resolve a new candidate `agent_version_id`, and do not
   treat the candidate as a retained or long-lived version yet.
5. **Validate one exact example.** Run focused tests and the explicitly
   versioned exact-example pipeline runner. Do not create a one-example eval
   occurrence as a development check.
6. **Measure once.** Use `$run-use-case-evals` for the requested scope and one
   authorized occurrence. Keep the hypothesis and held-constant dimensions in
   the handoff.
7. **Compare exact results.** Use `$eval-results-analysis` with the baseline and
   candidate occurrence IDs. Separate decision quality, reliability, coverage,
   usage, and cost; do not declare success from a single anecdote.
8. **Decide explicitly.** Revise the candidate and repeat from the hypothesis,
   stop with the evidence, or use `$eval-lifecycle` to elevate a complete
   selected occurrence that represents meaningful progress. Use
   `$publish-retained-eval` only when the user explicitly requests publication
   of that exact retained eval.

Do not silently broaden the benchmark scope, create duplicate occurrences,
overwrite the baseline, retain a candidate, or publish results as part of an
ordinary improvement request.

## Guide Template Customization

Use `$create-use-case-project`, then capture `use_case/docs/`, set project and
benchmark identities, configure models, replace manifest-declared reference
paths, and validate one control pipeline. Keep reusable Workbench and
`packages/mi-core/` mechanics distinct from use-case rules.

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
