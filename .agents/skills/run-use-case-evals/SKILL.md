---
name: run-use-case-evals
description: Prepare, execute, or troubleshoot published-benchmark evaluation commands for the current Agent Workbench use case. Use when a developer or coding agent asks how to run a targeted or full benchmark eval, needs current project defaults, or needs help selecting the pipeline, model, scope, repetition, and supported runtime. Do not use for changing eval orchestration contracts, validating an agent under development on one unit, or analyzing accuracy regressions.
---

# Run Use-Case Evals

Read `EvalRunbook.md` at the repository root completely before preparing or
executing an eval command. Treat it as the source of truth for operator-facing
commands and current use-case defaults. Do not duplicate its command templates
in this skill.

## Workflow

1. Determine whether the user wants a command, a live run, or troubleshooting.
   Do not execute an eval when the user only asks for guidance.
2. Read `models.yaml` and resolve its `pricing_key` through
   `model_pricing.yaml`; confirm the requested model exists and note its `api`
   family. Catalog membership proves selectability, not runtime compatibility.
   When the user explicitly requests the default model, resolve `default_model`
   from the catalog and pass that concrete model explicitly after confirming its
   API family is supported.
   If the user did not name a model and compatibility is not already proven,
   retain the runbook's `<provider:model>` placeholder instead of inserting the
   catalog default.
3. Use the fully explicit commands from `EvalRunbook.md`. For live discovery,
   pass the evaluation profile, project key, all three Azure PostgreSQL
   identities, and both Azure Storage identities explicitly. Never use the bare
   interactive chooser when `DATABASE_URL` may be set: without complete
   `--azure-postgres-*` arguments, the repository can silently query that
   database instead of hosted Azure PostgreSQL. The CLI text
   `Retrieving published benchmarks ... from Azure` does not prove which
   connection path was selected. For execution, also supply benchmark key,
   benchmark version, model, reasoning effort, worker count, and exactly one
   supported scope: `--all-examples`, an explicit
   `--example-ids`/`--unit-ids` list, or one or more named `--section` values.
   Use threaded execution normally and `--runtime serial --max-workers 1` only
   for debugging. A run count of one and threaded execution are defaults, but
   keep them explicit in reproducible handoffs. Avoid interactive profile or
   benchmark selection unless discovery is the requested task.
4. Treat hosted benchmark availability as mutable operational state. Before a
   live run, confirm the exact key and version through the runbook's explicit
   Azure discovery workflow or a current catalog result proven to come from the
   same hosted Azure PostgreSQL environment. A value in
   `workbench.project.json`, durable documentation, a retained result, or a
   local `DATABASE_URL` catalog proves compatibility or historical/local
   identity, not current Azure publication. Require the selected live identity
   to be present in the project compatibility allow-list; stop on a genuine
   Azure catalog/configuration mismatch. For a command-only request without a
   current hosted catalog result, retain the benchmark placeholders and tell
   the user to resolve them; never present a concrete key as "currently
   available" based only on repository contents.
5. Execute the scope the user requested. Do not create a one-example eval as a
   compatibility check or prerequisite to a section or full-benchmark eval.
   Agent development must establish pipeline/model compatibility with focused
   tests and the exact-example pipeline runner before evaluation. A
   one-example or one-unit eval is valid only when that narrow evaluation is
   itself the user's requested measurement or when debugging an existing eval
   failure; never run it automatically before a wider eval.
6. When authorized to execute, monitor the run through completion and report
   the unique eval occurrence ID, deterministic `run_spec_sha256`, and exact
   `result.json` path. Starting the same command again creates a new
   occurrence. If interrupted, use the exact command printed by the runner; it
   includes `--run-id <exact-occurrence>` and reruns only missing work for that
   occurrence, whose completed work is already durable.
   Diagnose the first substantive error; do not mistake successful Blob `206`
   logs or thread-shutdown noise for the root cause.
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
8. Expect the occurrence-aware schema-v2 run bundle under
   `eval_results/working/<benchmark-key>/v<version>/<run-id>/`. Every new run
   is a rich, disposable working eval. Report the exact `result.json` and do not
   reconstruct identity from display labels. If the completed run represents a
   meaningful agent version, hand it to `$eval-lifecycle` for explicit
   full-run elevation; do not infer retention from score or age.
9. Treat comparison as review of completed evals through Codex,
   `$eval-results-analysis`, or the local read-only explorer. Do not make
   comparison a runner phase.

## Boundaries

- Use `$agent-eval-builder` to change orchestration, benchmark contracts, result
  schemas, or executor behavior.
- Use `$eval-results-analysis` to explain accuracy changes in completed result
  files.
- Use `$eval-lifecycle` to list, elevate, verify, or permanently delete an
  exact working or retained eval.
- Use `$external-runtime-setup` for provider credentials or telemetry setup.
- Do not substitute a one-example eval for the exact-example pipeline validation
  required while writing or editing an agent. Eval occurrences are measurement
  artifacts and appear in the eval explorer even when their scope is only one
  example.
- Do not teach process execution, arbitrary label filters/predicates, failure
  generation reruns, materialization-only operations, or comparison flags as
  normal eval workflow.
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
