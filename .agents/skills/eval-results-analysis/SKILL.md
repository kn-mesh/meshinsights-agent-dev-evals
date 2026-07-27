---
name: eval-results-analysis
description: Analyze completed eval results for a pipeline, prompt, model, tool, grader, configuration, or evidence change. Use to explain accuracy shifts, regressions, reliability failures, and likely next changes. Do not run evals or edit behavior without explicit authorization.
---

# Eval Results Analysis

Explain what changed and why from concrete unit evidence without overfitting.
Treat current repository outputs and inspection code as authoritative.

## Workflow

1. Confirm the exact eval IDs, variants, or revisions in scope. Do not diff
   every result by default.
2. Resolve lifecycle state:

   ```bash
   uv run python -m src.eval_lifecycle.cli inspect <eval-id> --json
   ```

   Working evals may retain attempts, review, and performance. Retained evals
   contain compact aggregates and intentionally prune tool/intermediate traces.
   Before reading retained artifacts directly, verify the bundle:

   ```bash
   uv run python -m src.eval_lifecycle.cli verify <retained-id> --json
   ```

   The explorer also satisfies this gate because its retained backend verifies
   the selected bundle before returning retained content.
3. For a working eval, start with bounded inspection:

   ```bash
   uv run python -m src.evals.inspection_cli summary --run <run-id>
   uv run python -m src.evals.inspection_cli list \
     --run <run-id> --filter incorrect --limit 20
   ```

   Use `incorrect`, `invalid`, `failed`, `flaky`, `unscored`, or
   `review-unavailable` as relevant. For retained evals, use the verified
   explorer or bounded rows from `units.json` only after lifecycle verification.
4. Inspect only representative units:

   ```bash
   uv run python -m src.evals.inspection_cli example \
     --run <run-id> --example '<example-id>'
   uv run python -m src.evals.inspection_cli execution \
     --run <run-id> --execution '<execution-id>' \
     --section model_interactions --resolve-text
   ```

5. Separate repeated quality errors from execution, output-contract, grader,
   review-capture, and evidence-integrity failures.
6. Propose targeted changes with evidence and overfitting risk before editing.
7. Preserve a working-eval diagnosis with
   `src.evals.inspection_cli diagnose` only when requested. That command resolves
   working evals only. For a retained eval, keep its bundle immutable: return
   the analysis or write an explicitly requested note outside the retained bundle,
   keyed by exact retained ID.

## Evidence Rules

- Use `run` and `run.dimensions` to confirm benchmark, pipeline, model,
  reasoning, agent, grader, configuration, and source-snapshot identity.
- Use accuracy only for valid scored attempts. Analyze reliability and scoring
  coverage separately.
- For working detail, use bounded commands or
  `LocalRunStore.evaluation_rows()`. Attempts supply `agent_output`,
  `evaluations`, contract errors, usage, cost, and failures; missing attempts
  make detailed analysis unavailable, not invalid.
- Retained `units.json` preserves final outputs and grading. Verify its bundle
  before direct reads, and state when a question requires traces that elevation
  pruned.
- Resolve evidence through the working manifest or retained
  `evidence-references.json`; verify exact snapshot and artifact hashes. Never
  substitute current membership or an unverified local copy.
- Use chart-specific analysis only when the selected use-case adapter supplies charts.
- Treat `performance/summary.json` and review artifacts as optional disposable
  diagnostics. Access review objects only through the inspection CLI.
- Report unavailable review by its typed reason, such as `capture_failed`,
  rather than calling the durable attempt failed.

Read
[the current evaluation contracts](../agent-eval-builder/references/current-evaluation-contracts.md)
only when exact result fields, layouts, capture states, or lifecycle mechanics
matter; otherwise inspect the selected result and source directly.

## Guardrails And Output

- Do not run evals, edit prompts, publish artifacts, or mutate lifecycle state
  without explicit authorization.
- Do not reconstruct missing traces, infer retry counts, or treat disposable
  diagnostics as benchmark truth.
- Prefer repeated patterns over anecdotes; distinguish model interpretation,
  prompt framing, evidence preparation, pipeline handoff, grader behavior, and
  uncertain labels.
- Give the reviewed identity, main changes/clusters, representative unit IDs
  with evidence-grounded explanations, recommended next changes and risks, and
  a clear statement of whether anything was rerun or edited.
