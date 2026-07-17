---
name: project-guide
description: Orient developers in this repository and give codebase-grounded development guidance. Use when a developer asks how the project fits together, where a change belongs, how to customize the template, what development sequence to follow, whether behavior belongs in the use-case project or mi-core, which source files explain current behavior, or which specialized repo skill should handle a task.
---

# Project Guide

Use this skill to answer developer questions with current repository evidence and to route implementation work. Do not make developers reconstruct an implementation from prose when Codex can inspect and change the code directly.

## Ground Answers In The Repository

Use this source order:

1. Read the user's request and any explicitly named files.
2. Read the relevant durable context in `docs/use_case/` without editing it unless asked.
3. Inspect current source, pipeline configs, tests, and runnable entry points.
4. Load the specialized repo skill for the task.
5. Inspect repository-local framework source and docs under `mi-core/` when framework behavior matters.
6. Use `README.md` for setup and entry-point orientation.

Distinguish current behavior from recommended direction. Existing coherent code is the source of truth unless the user asks to migrate it. When a skill and the implementation differ, explain the difference and follow the implementation for local behavior.

Run repository commands with `uv run ...`. Treat `mi-core/` and `mi.ai` as editable local source under `mi-core/core/src/mi/`, not as opaque installed dependencies.

## Repository Ownership Boundaries

| Layer | Owns |
|---|---|
| `mi-core/` | Reusable runtime mechanics, component APIs, registry behavior, pipeline orchestration, and general framework docs |
| This root project | Use-case implementation, data integrations, pipeline variants, prompts, business rules, evals, and operator/debug tooling |
| `docs/use_case/` | Durable business context, input/output meaning, benchmark semantics, and domain terminology |
| `.agents/skills/` | Concise Codex playbooks for repository-specific development and analysis workflows |

Modify `mi-core/` directly when requested behavior is generally reusable framework behavior. Keep use-case-specific rules, data shaping, prompts, and source-system knowledge in the root project. Do not add a root-project workaround solely because framework code was once external.

Do not modify `src/experimental_core/` without explicit user permission.

## Repository Layout

Use these locations by default:

| Path | Purpose |
|---|---|
| `data/` | Non-secret local development assets; published benchmarks and eval evidence live in Azure |
| `pipeline_configs/` | Declarative `.ppln` component wiring |
| `src/retrievers/` | Source-system data acquisition |
| `src/objects/` | Typed process, action, and metadata contracts |
| `src/hydrators/` | Stage-boundary normalization, decision handoff, and receipt stamping |
| `src/processors/` | Deterministic and AI analysis logic, organized by variant when useful |
| `src/actions/` | Final side effects or intentionally no-op terminal actions |
| `src/pipelines/` | Runnable pipeline entry points and runner CLIs |
| `src/evals/` | Evaluation orchestration and result handling |

Treat example files as starting patterns, not required production behavior.

## Route To Specialized Skills

Load the narrowest applicable skill before answering in depth or implementing:

| Question or task | Skill |
|---|---|
| Pipeline components, YAML, variants, runners, or receipts | `$pipeline-builder` |
| Structured AI processors, workflows, agents, tools, capabilities, or Agent Skills | `$ai-processor-builder` |
| Eval orchestration, benchmark contracts, repeated runs, or result apps | `$agent-eval-builder` |
| Existing eval regressions, comparisons, or error analysis | `$eval-results-analysis` |
| `.env`, `mi auth`, provider credentials, runtime overrides, or Logfire | `$external-runtime-setup` |

Use multiple skills only when the request genuinely spans their domains.

## Guide Template Customization

When turning the template into a consumer project, recommend and, when asked, perform this sequence:

1. Capture durable domain context in `docs/use_case/`.
2. Update `pyproject.toml` with the real project identity and dependencies.
3. Rewrite `README.md` around the real application, boundaries, entry points, supported variants, and navigation.
4. Configure the published benchmark repository and immutable evidence source.
5. Replace example metadata, objects, retrievers, hydrators, processors, and actions under `src/`.
6. Replace example `.ppln` files with project-specific pipeline variants.
7. Add eval and operator tooling after the output contract is stable enough to compare.

Keep application prompts, business rules, source-system joins, domain labels, and operational guidance in the consumer project. Keep framework mechanics generic in `mi-core/`.

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

## Answer Developer Questions

For guidance-only requests:

1. Answer the question directly.
2. Cite the relevant repo-relative files or symbols.
3. State whether the answer describes current behavior, a skill recommendation, or both.
4. Identify the narrowest next action or specialized skill when useful.

For implementation requests, inspect the same evidence, load the specialized skill, make the requested change, and verify it in proportion to risk.
