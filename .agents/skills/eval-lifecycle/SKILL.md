---
name: eval-lifecycle
description: Manage the formal local lifecycle of Agent Workbench evaluation results. Use when an FDE or coding agent needs to explain working versus retained evals, list exact evals, preview or elevate one complete full run and its agent version, verify retained artifacts, or permanently delete an exact working or retained eval. Do not use for running evals, analyzing accuracy, cloud publication, recoverable deletion, or UI mutation.
---

# Eval Lifecycle

Use the supported `src.eval_lifecycle.cli` workflow. Deletion is permanent;
there is no quarantine, restore, recovery, or generalized reachability layer.

## Lifecycle Contract

- Every new run begins under `eval_results/working/` with rich per-unit
  attempts, review detail, and disposable performance observations.
- Elevation applies to one complete run, never selected units.
- An elevated eval lives under `eval_results/retained/` as a few aggregate
  artifacts and is linked to the retained meaningful agent version.
- After the retained artifacts and linked agent version verify successfully,
  elevation permanently removes the source working eval. Working and retained
  rows must never coexist for the same source occurrence.
- Retained `units.json` preserves expected outputs, full final AI outputs,
  validation, grading, usage, and cost without a file per unit.
- `evidence-references.json` preserves exact Azure account, container, object,
  size, SHA-256, source snapshot, and recipe identity. Evidence is retrieved
  and verified on demand; it is not copied locally.
- `agent-provenance.json` and optional `agent.patch` preserve Git identity,
  relevant configuration hashes, and relevant dirty or untracked agent
  content.
- Elevation prunes attempt files, performance/latency detail, tool traces, and
  intermediate review objects from the retained representation, then removes
  the complete source working directory.
- Deletion is permanent and not recoverable.

## Workflow

### 1. List or inspect exact evals

```bash
uv run python -m src.eval_lifecycle.cli list --state all --json
uv run python -m src.eval_lifecycle.cli list --state working --json
uv run python -m src.eval_lifecycle.cli list --state retained --json
uv run python -m src.eval_lifecycle.cli inspect <eval-id> --json
```

Report the exact ID, lifecycle state, benchmark/version, agent version, model,
attempt coverage, and path. Never infer lifecycle state from age or score.

### 2. Preview elevation

```bash
uv run python -m src.eval_lifecycle.cli elevate eval_<hash> --dry-run --json
```

Read the preservation and pruning lists. Refuse incomplete or inconsistent
runs. Confirm that this full run represents a meaningful agent version and
that successful elevation permanently removes its source working eval before
proceeding.

### 3. Elevate and verify

```bash
uv run python -m src.eval_lifecycle.cli elevate eval_<hash> --yes --json
uv run python -m src.eval_lifecycle.cli verify ret_<hash> --json
```

Report both the retained eval ID and agent version ID. Elevation is
non-interactive and scriptable after explicit confirmation. Confirm that the
source working eval was deleted only after retained verification. Do not add an
elevate action to the MVP review UI.

### 4. Permanently delete an exact working eval

```bash
uv run python -m src.eval_lifecycle.cli delete working eval_<hash> --yes --json
```

Confirm the exact target with the user before execution unless their request
already clearly authorizes that ID. Explain that completed data is immediately
removed and cannot be resumed or restored.

### 5. Permanently delete an exact retained eval

```bash
uv run python -m src.eval_lifecycle.cli delete retained ret_<hash> \
  --confirm-retained ret_<hash> --json
```

Retained deletion requires the exact ID twice. Report the linked agent version
and whether it was removed. If another retained eval references the same agent
version, the shared version must remain.

## Routing And Boundaries

- Use `$run-use-case-evals` to create or resume working evals.
- Use `$eval-results-analysis` to review working or retained results.
- Use `$external-runtime-setup` to configure model identity and frozen pricing.
- Use `$agent-eval-builder` for changes to lifecycle schemas or the read-only
  explorer.
- The review app may filter All, Working, and Retained and inspect both states.
  It must not elevate, delete, edit, annotate, or expose another mutation.
- Cloud publication is post-MVP. Do not add Azure retained-result writes.
- Before modifying reusable lifecycle, eval, UI, versioning, or bootstrap code,
  explain why a project-local change is insufficient, identify exact shared
  paths/contracts, and obtain explicit user approval.
