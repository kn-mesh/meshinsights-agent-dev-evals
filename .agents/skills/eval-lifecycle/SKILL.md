---
name: eval-lifecycle
description: Manage local working and retained evals. Use to list or inspect exact IDs, preview or elevate one complete occurrence, verify retained artifacts, or permanently delete an exact eval. Do not run, analyze, publish, or perform recoverable deletion.
---

# Eval Lifecycle

Use `workbench.eval_lifecycle.cli`. Deletion and post-elevation source removal are
permanent; there is no quarantine, restore, or recovery layer.

## Contract

- New runs are rich working evals with attempts and optional review/performance.
- Elevation accepts one complete selected occurrence: every planned work item
  has a recorded terminal attempt and none are missing. It preserves compact
  aggregates, final outputs, grading, usage/cost, exact evidence references,
  and meaningful agent provenance, then prunes execution/review detail.
- Retained verification must succeed before the source working directory is
  removed. One occurrence must not coexist in both states.
- Evidence stays in Azure and is hash-verified on demand.
- Exact deletion is immediate and not recoverable.

## Workflow

1. List or inspect; report exact ID, state, benchmark/version, agent/model,
   coverage, and path:

   ```bash
   uv run python -m workbench.eval_lifecycle.cli list --state all --json
   uv run python -m workbench.eval_lifecycle.cli inspect <eval-id> --json
   ```

2. Preview elevation and review preservation/pruning. Refuse incomplete or
   inconsistent runs:

   ```bash
   uv run python -m workbench.eval_lifecycle.cli elevate eval_<hash> --dry-run --json
   ```

3. After explicit confirmation, elevate and verify. Report retained eval and
   agent-version IDs, and confirm source removal happened only after verify:

   ```bash
   uv run python -m workbench.eval_lifecycle.cli elevate eval_<hash> --yes --json
   uv run python -m workbench.eval_lifecycle.cli verify ret_<hash> --json
   ```

4. Confirm the exact target before permanent deletion unless the request
   already authorizes that ID:

   ```bash
   uv run python -m workbench.eval_lifecycle.cli delete working eval_<hash> --yes --json
   uv run python -m workbench.eval_lifecycle.cli delete retained ret_<hash> \
     --confirm-retained ret_<hash> --json
   ```

   Retained deletion requires the ID twice. Report whether its agent version
   remained because another retained eval references it.

## Routing And Boundaries

- `$run-use-case-evals`: create or resume working evals.
- `$eval-results-analysis`: inspect quality.
- `$publish-retained-eval`: explicitly create an immutable Azure publication
  event from one verified retained eval.
- `$agent-eval-builder`: change lifecycle schemas or explorer behavior.
- The explorer is read-only for All/Working/Retained. Never add elevation,
  deletion, annotation, automatic sync, or Benchmark Studio writes.
- For implementation changes, select every affected layer in the
  [repository verification matrix](../project-guide/references/verification-matrix.md).
