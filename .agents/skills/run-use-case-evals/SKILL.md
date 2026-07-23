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
   all examples in unattended execution. Include `--agent-version-id` and
   repeatable `--dimension KEY=JSON_VALUE` flags whenever those stable
   comparison identities are known. Avoid interactive profile or benchmark
   selection unless discovery is the requested task.
4. Treat hosted benchmark availability as mutable operational state. Before a
   live run, confirm the exact key and version through the runbook's discovery
   workflow or a current catalog result from the same environment. A value in
   `workbench.project.json`, durable documentation, or a retained result proves
   compatibility or historical identity, not current publication. Require the
   selected live identity to be present in the project compatibility allow-list;
   stop on a catalog/configuration mismatch. For a command-only request without
   a current catalog result, retain the benchmark placeholders and tell the user
   to resolve them; never present a concrete key as "currently available" based
   only on repository contents.
5. Start with the runbook's one-example serial smoke run when pipeline/model
   compatibility has not already been established.
6. When authorized to execute, monitor the run through completion and report
   the deterministic run ID and exact `result.json` path. If interrupted,
   rerun the identical explicit command with `--resume-mode missing`; completed
   work is already durable. Diagnose the first substantive error; do not
   mistake successful Blob `206` logs or thread-shutdown noise for the root
   cause.
7. Verify durable and optional artifacts separately:
   - load and integrity-check `result.json`; confirm `run` matches the requested
     evaluation profile identity/hash, benchmark, model, reasoning effort,
     scope, and repetitions;
   - confirm the retained manifest contains each selected example's frozen
     source-snapshot window, known gaps, and complete raw artifact hashes;
   - confirm `run.dimensions` captures agent, pipeline, model, grader-set, and
     project-declared configuration identities;
   - use the inspection summary to verify diagnostic review capture state,
     integrity, and counts; its disposable index refreshes from current attempt,
     capture, manifest, object, and staging evidence;
     and
   - inspect `performance/summary.json` only when present. Its latency, retry,
     and throughput observations cover current/latest attempt generations and
     are disposable; absence or invalid telemetry is supported and must not be
     described as missing durable eval evidence or a failed eval.
8. Expect the schema-v1 run bundle under
   `eval_results/<pipeline>/<benchmark-key>/v<version>/runs/<run-id>/`. Report
   the exact `result.json` and do not reconstruct identity from display labels.
9. Use `--compare-model` for multiple models under identical conditions. For
   existing results, use `--compare-result` plus every allowed
   `--varying-dimension`; undeclared differences intentionally fail closed.

## Boundaries

- Use `$agent-eval-builder` to change orchestration, benchmark contracts, result
  schemas, or executor behavior.
- Use `$eval-results-analysis` to explain accuracy changes in completed result
  files.
- Use `$external-runtime-setup` for provider credentials or telemetry setup.
- Never print secrets or commit `.env` values.
- Never infer a benchmark key for a real run. Discover it in the current
  environment or obtain an exact identity from the user. A prior result may be
  used to reproduce historical conditions only after current availability is
  verified.
- Never infer a concrete model for a command-only request. Use a user-selected
  model or one whose catalog API family is known to be supported by the current
  runtime adapter.
- Never read latency or retry observations from durable `result.json`, and
  never treat unavailable review or performance data as an eval failure.
