---
name: run-use-case-evals
description: Prepare, execute, or troubleshoot published-benchmark evaluation commands for the Spirax Pulse use case in this repository. Use when a developer or coding agent asks how to run an eval, wants a smoke or full benchmark run, needs to avoid the slow interactive benchmark lookup, or needs help selecting explicit pipeline, benchmark, model, scope, repetition, and runtime flags. Do not use for changing eval orchestration contracts or analyzing accuracy regressions.
---

# Run Use-Case Evals

Read `EvalRunbook.md` at the repository root completely before preparing or
executing an eval command. Treat it as the source of truth for operator-facing
commands and current use-case defaults. Do not duplicate its command templates
in this skill.

## Workflow

1. Determine whether the user wants a command, a live run, or troubleshooting.
   Do not execute an eval when the user only asks for guidance.
2. Read `models.yaml`; confirm the requested model exists and note its `api`
   family. Catalog membership proves selectability, not runtime compatibility.
   When the user explicitly requests the default model, resolve `default_model`
   from the catalog and pass that concrete model explicitly after confirming its
   API family is supported.
   If the user did not name a model and compatibility is not already proven,
   retain the runbook's `<provider:model>` placeholder instead of inserting the
   catalog default.
3. Prefer the fully explicit command from `EvalRunbook.md`. Supply evaluation
   profile, benchmark key, benchmark version, model, reasoning effort, run
   count, runtime, worker count, error action, and an explicit scope. Use
   `--all-examples` for a full benchmark; absence of filters no longer implies
   all examples in unattended execution. Include `--agent-version` and
   repeatable `--dimension KEY=JSON_VALUE` flags whenever those stable
   comparison identities are known. Avoid interactive profile or benchmark
   selection unless discovery is the requested task.
4. Start with the runbook's one-example serial smoke run when pipeline/model
   compatibility has not already been established.
5. When authorized to execute, monitor the run through completion and report
   the deterministic run ID and exact `result.json` path. If interrupted,
   rerun the identical explicit command with `--resume-mode missing`; completed
   work is already durable. Diagnose the first substantive error; do not
   mistake successful Blob `206` logs or thread-shutdown noise for the root
   cause.
6. Verify the resulting JSON `run_config` matches the requested evaluation
   profile identity/hash, benchmark, model, reasoning effort, scope, and
   repetition settings. Verify `run_config.dimensions` captures agent, pipeline,
   model, grader-set, and project-declared configuration identities.
7. Expect persisted results under
   `eval_results/<pipeline>/<benchmark-key>/v<version>/runs/<run-id>/`. Report
   the exact `result.json` and do not reconstruct identity from display labels.
8. Use `--compare-model` for multiple models under identical conditions. For
   existing results, use `--compare-result` plus every allowed
   `--varying-dimension`; undeclared differences intentionally fail closed.

## Boundaries

- Use `$agent-eval-builder` to change orchestration, benchmark contracts, result
  schemas, or executor behavior.
- Use `$eval-results-analysis` to explain accuracy changes in completed result
  files.
- Use `$external-runtime-setup` for provider credentials or telemetry setup.
- Never print secrets or commit `.env` values.
- Never infer a benchmark key for a real run. Discover it interactively or
  obtain it from the user or a prior result.
- Never infer a concrete model for a command-only request. Use a user-selected
  model or one whose catalog API family is known to be supported by the current
  runtime adapter.
