---
name: publish-retained-eval
description: Preview and explicitly publish one eligible retained Agent Workbench eval as a new immutable Azure Blob event. Use when an FDE asks to publish, upload, or durably share an exact retained eval. Do not use for elevation, deletion, automatic synchronization, working evals, or Benchmark Studio writes.
---

# Publish Retained Eval

Use `src.eval_publication.cli`. Publication is a create-only handoff from one
verified local retained eval to the separate eval-results container. It never
changes local lifecycle state or Benchmark Studio truth.

## Workflow

1. Resolve and verify the exact retained eval:

   ```bash
   uv run python -m src.eval_lifecycle.cli inspect ret_<hash> --json
   uv run python -m src.eval_lifecycle.cli verify ret_<hash> --json
   ```

2. Run the storage-free preview:

   ```bash
   uv run python -m src.eval_publication.cli publish ret_<hash> \
     --dry-run --json
   ```

   Dry run must allocate no publication ID and make no Azure request. Review
   the retained/eval/benchmark/agent identities, destination parent, payload
   hashes and sizes, unit counts, and excluded categories.

3. Confirm the exact retained eval and destination. Publication requires:

   - retained schema version 2;
   - every canonical selected unit completed;
   - clean recorded agent provenance with no `agent.patch`;
   - complete benchmark, evidence, model, grader, and run identities; and
   - a dedicated HTTPS account/container supplied by
     `AZURE_EVAL_RESULTS_ACCOUNT_URL` and
     `AZURE_EVAL_RESULTS_CONTAINER`, or the matching CLI flags.

4. Publish only after the user's request clearly authorizes that exact target:

   ```bash
   uv run python -m src.eval_publication.cli publish ret_<hash> \
     --yes --json
   ```

5. Report `publication_id`, prefix, manifest blob, payload identities, and
   `verified`. The publisher uploads payloads with create-only writes,
   downloads and hash-verifies them, and creates
   `publication-manifest.json` last as the discovery marker.

## Boundaries

- Each confirmed publish creates a new immutable event, even for the same
  retained eval. Never repeat it silently after success or an ambiguous
  client-side interruption.
- Never overwrite a blob, copy local evidence, include `agent.patch`, or upload
  attempts, retries, tool traces, intermediate responses, or detailed timing.
- Use `$eval-lifecycle` to elevate, verify, or delete local evals.
- Use `$external-runtime-setup` for Azure identity troubleshooting.
- If the request explicitly authorizes the named reusable scope, proceed after
  stating its ownership and focused tests. Otherwise, identify the exact
  reusable paths/contracts and pause once for approval.
- For implementation changes, select every affected layer in the
  [repository verification matrix](../project-guide/references/verification-matrix.md).
