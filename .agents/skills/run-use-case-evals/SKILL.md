---
name: run-use-case-evals
description: Prepare, execute, or troubleshoot published-benchmark evals for this Agent Workbench use case. Use to select an explicit pipeline, benchmark version, model, scope, repetitions, and runtime or to monitor a requested run. Do not change orchestration contracts, validate a developing agent on one unit, or analyze regressions with this skill.
---

# Run Use-Case Evals

Read `EvalRunbook.md` completely; it owns commands and project defaults. If it
contains `agent-workbench-eval-runbook-status: bootstrap-placeholder`, do not infer or
execute an eval. Route control-path completion to
`$benchmark-pipeline-port` and eval/runbook completion to
`$agent-eval-builder`.

## Workflow

1. Determine whether the user wants guidance, troubleshooting, or one live
   occurrence. Do not execute for a command-only request.
2. Resolve a concrete selectable model from `models.yaml`, its pricing record
   from `model_pricing.yaml`, and its API-family compatibility. Use the
   catalog default only when explicitly requested and supported; otherwise
   retain the runbook placeholder.
3. Resolve the exact currently published benchmark key/version through the
   runbook's explicit hosted discovery path. Repository defaults and historical
   results prove compatibility, not current availability. For command-only
   guidance without live discovery, retain placeholders.
4. Use the runbook's fully explicit command: profile, project/hosted identities,
   benchmark version, model, reasoning, repetitions, worker/runtime settings,
   and exactly one requested scope. Before a paid run, report selected examples
   × repetitions, model/reasoning, concurrency, and the available frozen
   pricing basis. Request direction only when the user has not already
   authorized that concrete run.
5. Run exactly the requested measurement. Do not create a one-example eval as a
   compatibility check before a wider eval; agent development uses focused
   tests and the exact-example pipeline runner.
6. Eval `--dry-run` is stateful: it allocates one working occurrence and writes
   its manifest and candidate without executing attempts. Continue that exact
   occurrence with the emitted `--run-id` command; never remove `--dry-run` and
   start a second occurrence.
7. When authorized, monitor to completion. Report the unique occurrence ID,
   `run_spec_sha256`, and exact `result.json`. For interruption, use the exact
   resume command emitted by the runner.
8. One request authorizes at most one new occurrence of the requested scope
   unless the user explicitly asks for more. Never silently duplicate or
   replace a run; explain downstream ineligibility and estimated rerun cost
   before requesting authorization.
9. Verify durable artifacts separately from optional diagnostics:
   - integrity-check `result.json` and confirm `run` matches the requested
     profile, benchmark, model, reasoning, scope, and repetitions;
   - confirm frozen evidence identities and hashes for selected examples;
   - confirm `run.dimensions` records agent, pipeline, model, grader, and
     project configuration;
   - check inspection capture state without treating absent review as failure;
   - inspect `performance/summary.json` only when present and never treat its
     absence as missing durable evidence.
10. Report the working bundle path. Route explicit elevation or deletion to
   `$eval-lifecycle` and completed-result explanation to
   `$eval-results-analysis`.

## Boundaries

- Use `$agent-eval-builder` for orchestration, schema, grader, or executor
  changes and `$external-runtime-setup` for credentials or telemetry.
- Do not expose secrets, rely on ambiguous interactive selection, infer a
  benchmark/model, or let local database configuration masquerade as hosted
  discovery.
- Diagnose the first substantive failure; successful Blob range logs and
  shutdown noise are not root causes.
- Treat working attempts/review/performance as disposable diagnostics and the
  occurrence's compact result/identity as durable.
- Compare completed evals through `$eval-results-analysis` or the read-only
  explorer, not as a runner phase.
