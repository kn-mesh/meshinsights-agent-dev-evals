---
name: project-guide
description: Orient developers in the MeshInsights Agent Workbench repository and give codebase-grounded development guidance. Use when a developer asks how the project fits together, where a change belongs, how to customize the template, what development sequence to follow, whether behavior belongs in the use-case project or mi-core, which source files explain current behavior, or which specialized repo skill should handle a task.
---

# Project Guide

Use this skill to answer developer questions with current repository evidence and to route implementation work. Do not make developers reconstruct an implementation from prose when Codex can inspect and change the code directly.

This repository is a use-case implementation of **MeshInsights Agent
Workbench**. It consumes published benchmark versions and frozen evidence from
**MeshInsights Benchmark Studio** through read-only contracts, then develops,
compares, evaluates, and packages agent variants. It does not own Benchmark
Studio workflow truth or the production agent runtime.

## Ground Answers In The Repository

Use this source order:

1. Read the user's request and any explicitly named files.
2. Read the relevant durable context in `docs/use_case/` without editing it unless asked.
3. Inspect current source, pipeline configs, tests, and runnable entry points.
4. Load the specialized repo skill for the task.
5. Inspect repository-local framework source and docs under `mi-core/` when framework behavior matters.
6. Use `README.md` for setup and entry-point orientation.

Distinguish current behavior from recommended direction. Existing coherent code is the source of truth unless the user asks to migrate it. When a skill and the implementation differ, explain the difference and follow the implementation for local behavior.

Do not turn current behavior into a product requirement merely because it is
coherent. For architecture, prioritization, or new-feature guidance, first test
the request against `docs/product-strategy/` and the FDE job. Describe existing
mechanics as compatibility constraints only when the requested change touches
them.

Run repository commands with `uv run ...`. Treat `mi-core/` and `mi.ai` as
inspectable editable local source under `mi-core/core/src/mi/`, not as opaque
installed dependencies. Editable does not imply authority to change it.

## Repository Ownership Boundaries

| Layer | Owns |
|---|---|
| `mi-core/` | Reusable runtime mechanics, component APIs, registry behavior, pipeline orchestration, and general framework docs |
| Reusable Workbench paths | Eval mechanics, review shell, bootstrap, versioning, generic orchestration, and operator tooling |
| Reference use-case paths | Use-case implementation, data integrations, pipeline variants, prompts, business rules, and UI composition |
| `docs/use_case/` | Durable business context, input/output meaning, benchmark semantics, and domain terminology |
| `.agents/skills/` | Concise Codex playbooks for repository-specific development and analysis workflows |

Use `workbench.template.json` as the versioned ownership and replaceable-reference
map. Keep use-case-specific rules, data shaping, prompts, and source-system
knowledge in manifest-declared reference paths.

Before modifying `mi-core/`, reusable eval or UI packages, bootstrap,
agent-version mechanics, generic orchestration, or lifecycle code:

1. show why a correct use-case-local change is insufficient;
2. identify the exact reusable paths and contracts;
3. explain the cross-use-case meaning and focused tests; and
4. obtain explicit user approval.

When an approved reusable fix is made in a use-case repository, record the
canonical template or library target and upstream issue, PR, commit, or pending
action before calling the work complete.

Do not modify `src/experimental_core/` without explicit user permission.

## Repository Layout

Use these locations by default:

| Path | Purpose |
|---|---|
| `data/` | Non-secret local development assets; published benchmarks and eval evidence live in Azure |
| `pipeline_configs/` | Declarative `.ppln` component wiring |
| `evaluation_configs/` | Versioned project evaluation profiles, graders, applicability, and slices |
| `src/retrievers/` | Source-system data acquisition |
| `src/objects/` | Typed process, action, and metadata contracts |
| `src/hydrators/` | Stage-boundary normalization, decision handoff, and receipt stamping |
| `src/processors/` | Deterministic and AI analysis logic, organized by variant when useful |
| `src/actions/` | Final side effects or intentionally no-op terminal actions |
| `src/pipelines/` | Runnable pipeline entry points and runner CLIs |
| `src/evals/` | Evaluation orchestration and result handling |
| `model_catalog.py`, `src/model_configuration.py` | Reusable model identity and frozen-pricing configuration |
| `agent-dev-eval-core/` | Reusable eval execution, result, review, and explorer-query mechanics |
| `agent-dev-eval-ui/` | Reusable local explorer API and React shell |
| `src/evidence/` | Project-owned frozen-evidence normalization and explorer envelope |
| `www/src/use_case/` | Project-owned evidence schema and visual composition |
| `src/project_bootstrap/`, `bootstrap_configs/` | Reusable initialization and project bootstrap inputs |
| `src/eval_lifecycle/` | Supported working/retained elevation, verification, and exact permanent deletion |
| `src/lifecycle/` | Frozen legacy quarantine/recovery implementation; not a supported product workflow |

Treat example files as starting patterns, not required production behavior.

## Gate New Work By FDE Outcome

Before routing or recommending a change, answer:

1. Which FDE job does it complete: create, port, build, evaluate, inspect,
   improve, package, or hand off?
2. What is blocked or materially slow in the current path?
3. What is the simplest existing path that completes the job?
4. Does it help launch or improve a decision about a unit at a decision point?
5. What evidence supports making it reusable across use cases?
6. What adjacent feature should be deferred?

If the request is implementation-specific maintenance, answer from current code.
If it is a product or architecture choice, prefer the strategy and the smallest
validated capability over preservation or expansion of current machinery.

## Route To Specialized Skills

Load the narrowest applicable skill before answering in depth or implementing:

| Question or task | Skill |
|---|---|
| Create a separate use-case repository from the template | `$create-use-case-project` |
| Initial port of a Benchmark Studio evidence pipeline into a clean project | `$benchmark-pipeline-port` |
| Port Benchmark Studio evidence into the local eval explorer | `$port-eval-explorer-use-case` |
| Pipeline components, YAML, variants, runners, or receipts | `$pipeline-builder` |
| Structured AI processors, workflows, agents, tools, capabilities, or Agent Skills | `$ai-processor-builder` |
| Prepare, execute, or troubleshoot a use-case eval command | `$run-use-case-evals` |
| Minimum eval capability, benchmark contracts, scoring, comparison, or result apps | `$agent-eval-builder` |
| Project model catalog, frozen pricing, credentials, or provider compatibility | `$external-runtime-setup` |
| Elevate, verify, or permanently delete an exact working/retained eval | `$eval-lifecycle` |
| Existing eval regressions, comparisons, or error analysis | `$eval-results-analysis` |
| `.env`, `mi auth`, provider credentials, runtime overrides, or Logfire | `$external-runtime-setup` |

Use multiple skills only when the request genuinely spans their domains.

## Guide Template Customization

When turning the template into a new use-case repository, use
`$create-use-case-project`, then perform this sequence:

1. Capture durable domain context in `docs/use_case/`.
2. Update `pyproject.toml` with the real project identity and dependencies.
3. Rewrite `README.md` around the real application, boundaries, entry points, supported variants, and navigation.
4. Configure the published benchmark repository and immutable evidence source.
5. Declare pipeline compatibility with the generated `workbench.project.json`;
   keep benchmark/runtime metadata generic and put artifact requirements and
   decoding in the use-case retriever.
6. Replace example metadata, objects, retrievers, hydrators, processors, and actions under `src/`.
7. Replace example `.ppln` files with project-specific pipeline variants.
8. Add eval and operator tooling after the output contract is stable enough to compare.

Keep application prompts, business rules, source-system joins, domain labels,
and operational guidance in manifest-declared use-case paths. Keep `mi-core/`
as the distinct forked pipeline/runtime library; do not use it as a catch-all
for unrelated reusable Workbench mechanics.

## Recommend The Development Sequence

Use this default progression unless evidence or the user's scope supports skipping a stage:

1. Durable use-case context.
2. Data inspection and visualization.
3. Runnable YAML control pipeline.
4. Compute-only baseline.
5. AI workflow only when deterministic logic is insufficient or brittle.
6. Agent variant only when targeted tool use materially helps.
7. Eval loop and operator tooling after outputs stabilize.

Prefer workflow over agent when one structured model call is enough. Compare variants with eval evidence rather than intuition.

For the first measurable agent or a new comparable variant, use the **Build The
First Agent Or Next Variant** workflow in `$pipeline-builder`. It connects the
existing pipeline, AI processor, one-example runner, eval, and immutable
candidate-version capabilities without adding another subsystem.

## Answer Developer Questions

For guidance-only requests:

1. Answer the question directly.
2. Cite the relevant repo-relative files or symbols.
3. State whether the answer describes current behavior, a skill recommendation, or both.
4. Identify the FDE outcome and current stage gate when the question affects
   product direction or architecture.
5. Identify the narrowest next action or specialized skill when useful.

For implementation requests, inspect the same evidence, load the specialized skill, make the requested change, and verify it in proportion to risk.
