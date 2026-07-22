# Development Bugs

This backlog records confirmed correctness and operability issues found during the July 2026 review of the schema-v1 evaluation, diagnostic-review, performance-telemetry, and eval-explorer changes. Items are grouped so one implementation task can address closely related failures together.

## P0 — Durable schema-v1 eval bundles are not retained by Git

**Status:** Confirmed

**Affected areas:** `.gitignore`, schema-v1 run storage, reproducibility and long-term eval retention

The repository describes eval results as durable evidence, but Git currently ignores most of the files required to verify and reconstruct that evidence. A committed `result.json` references `manifest.json`, `agent-version.json`, and per-attempt records, while the ignore rules exclude those referenced artifacts and the agent source objects needed for dirty-worktree candidates.

Consequently, an eval can look complete in the working copy but become unverifiable and non-reproducible in a fresh clone. Copying only the Git-eligible `result.json` causes `load_verified_result` to fail because the manifest is absent. Inputs, outputs, labels, benchmark identity, and the exact dirty candidate source may also be lost.

**Evidence**

- `.gitignore` ignores `eval_results/**/attempts/`, `eval_results/**/objects/`, `agent-version.json`, and `manifest.json` while allowing `result.json`.
- Schema-v1 `result.json` stores artifact references rather than duplicating the required evidence.
- Verification of a result-only bundle fails when resolving its missing manifest.

**Required fix**

Align source-control retention with the durable schema-v1 contract. Retain the run manifest, agent-version manifest, attempt records, and any content-addressed source objects required to reproduce the evaluated candidate. Continue excluding disposable performance telemetry and mutable diagnostic-review state.

**Acceptance criteria**

- A fresh clone can load and verify every committed durable eval result without relying on ignored local files.
- The committed bundle contains enough information to reconstruct attempt inputs, outputs, labels, benchmark identity, agent configuration, and token usage.
- A dirty-worktree candidate retains the exact source objects referenced by its agent-version manifest.
- An automated test builds or copies only Git-retained files and successfully calls the schema-v1 verifier.
- Performance telemetry and diagnostic-review artifacts remain excluded from long-term durable evidence.

## P1 — Disposable performance telemetry can fail durable evals and report inconsistent generations

**Status:** Confirmed

**Affected areas:** `src/evals/eval_orchestration.py`, `src/evals/run_store.py`, `src/apps/eval_explorer.py`

Three related defects violate the intended boundary between durable eval evidence and disposable performance diagnostics:

1. Performance writes are unguarded after durable attempt and result writes. A telemetry serialization or filesystem failure can abort the command even though valid durable evidence was already committed. This can leave committed attempts without a materialized result, or report the overall eval as failed after the durable result succeeded.
2. Run-level performance summaries aggregate records from all attempt generations, while durable result rows and explorer attempt lookup use only the latest generation. Reruns can therefore double-count superseded work, and slow-call links can point to attempts the explorer cannot open.
3. The explorer assumes nested performance fields such as `model_calls` are mappings. A malformed optional telemetry file containing `null` or a scalar can raise a `TypeError` and turn disposable-data corruption into a server error.

**Required fix**

Treat performance capture and visualization as best-effort diagnostics throughout the write, aggregation, and read paths. Define one generation policy for the primary run summary—preferably latest/current attempts only—and expose historical generations separately if they remain useful.

**Acceptance criteria**

- Injected failures in attempt-level performance capture do not prevent durable attempt commit.
- Injected failures in performance materialization do not prevent durable result completion or cause a successful eval to be reported as failed.
- Performance failures are recorded through an explicit warning or availability status with enough context to diagnose the problem.
- Primary run aggregates include only the same current attempt generations represented by the durable result.
- Every attempt or slow-call link shown in the explorer resolves successfully; historical telemetry is either separately labeled and navigable or excluded.
- Missing, malformed, or type-invalid optional telemetry renders as unavailable without blocking run, attempt, result, review, or evidence views.
- Tests cover performance write failures, rerun generations, stale telemetry, and malformed nested fields.

## P1 — A diagnostic review run with no successful captures is reported as partial

**Status:** Confirmed

**Affected area:** `agent-dev-eval-core/evaluation/review.py`

Review summary status is derived with an overly broad fallback: whenever review manifests exist but are not all complete, the run is classified as `partial`. If every review capture failed, the summary still reports `partial`, which implies that some usable review evidence exists when none does.

**Evidence**

A review store containing one failed manifest and no complete or partial captures produces a summary equivalent to:

```json
{
  "status": "partial",
  "execution_counts": {
    "complete": 0,
    "partial": 0,
    "failed": 1
  }
}
```

**Required fix**

Make the aggregate status truthful about capture outcomes. Use `complete` only when all expected captures completed, `partial` when at least one usable capture exists but the set is incomplete, and `failed` (or the established equivalent such as `capture_failed`) when none succeeded.

**Acceptance criteria**

- All-complete manifests summarize as `complete`.
- Mixed successful and failed/incomplete manifests summarize as `partial`.
- All-failed manifests summarize as `failed` or the canonical failure status.
- Empty/not-started review state remains distinguishable from capture failure.
- Unit tests assert the exact aggregate status for all-complete, mixed, all-failed, and empty cases.

## P1 — Agent-version resolution and the test suite depend on unrelated live worktree changes

**Status:** Confirmed

**Affected area:** `src/agent_versions/resolver.py` and agent/eval tests

The agent-version resolver scans the repository's live dirty paths and rejects changes outside its allowed candidate-source set. This fail-closed behavior can be appropriate when publishing a real candidate, but the tests use the same ambient Git state. An unrelated local edit can therefore invalidate broad portions of the suite without exercising the behavior under test.

During review, a full test run produced 32 failures—7 agent-version tests and 25 eval-orchestration tests—all terminating at the same dirty-runtime guard because of an unrelated modified runtime file. This makes test results dependent on developer workspace state and obscures real regressions.

**Required fix**

Make resolver tests hermetic by using an isolated repository fixture or an injected Git-state boundary. Preserve fail-closed validation for real candidate publication. For local eval operation, document or implement an explicit, auditable way to distinguish intended candidate changes from unrelated runtime changes without silently weakening provenance checks.

**Acceptance criteria**

- Agent-version and eval-orchestration tests pass or fail identically regardless of unrelated changes in the developer's surrounding worktree.
- Tests that verify dirty-source capture and forbidden-path rejection still exercise real Git semantics in an isolated fixture.
- Production candidate resolution remains fail-closed for untracked or modified source that could alter evaluated behavior.
- Any operator override is explicit, recorded in provenance, and cannot silently omit behavior-affecting source.

## Related cleanup candidates — verify before removal

These are not confirmed correctness bugs. They appear unused or stale and should be validated against external consumers before deletion:

- `src/evals/eval_orchestration.py`: `_results_from_store`, `_extract_model_name`, and `_results_filename`.
- `src/evals/comparisons.py`: `_numeric_observation_deltas`.
- `src/evals/run_store.py`: public `LocalRunStore.write_result`; confirm no external callers before removal.
- `src/processors/common/temperature_graphs_three_intervals_processor.py`: the v2-only custom-chart path, including `render_custom_combined_chart`, `_build_custom_analysis_window`, `_build_custom_temperature_chart_title`, and potentially `_format_chart_timestamp`.
- `docs/use_case/PROJECT_CONTEXT.md` and `docs/use_case/PipelineVersions.md`: stale references to the deleted `UseCase-V2.md` document.
