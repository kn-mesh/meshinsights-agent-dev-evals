# Local Version And Result Lifecycle

**Status:** Implemented and verified for MVP on 2026-07-22.

## Outcome

Complete the Agent Workbench MVP lifecycle feature with one local, derived
catalog for immutable agent versions, schema-v3 evaluation runs, and
comparisons, plus an intentional and recoverable deletion workflow.

The catalog is not a second source of truth. It is rebuilt from existing
immutable manifests, promotion and alias records, run-local candidates,
comparison records, and retained diagnoses. Benchmark Studio remains the
read-only owner of published benchmark and frozen-evidence truth.

This feature makes a clean break from historical standalone eval JSON. The
tracked legacy files under `eval_results/` are deleted, the directory becomes
local-only, and no compatibility reader, migration command, or legacy catalog
state is added.

## Decisions

- Deletion first moves data into a recoverable project-local quarantine.
- Runs, comparisons, and promoted versions use the same preview, confirmation,
  restore, and permanent-purge flow.
- Promoted versions require no special force flag. Their manifest, aliases,
  promotion events, and newly unreachable global CAS objects are one owned
  deletion unit.
- References are exposed as warnings in the deletion plan. Explicit `--yes`
  confirms the exact warned operation; there is no implicit cascade.
- A candidate that exists only inside retained runs is not an independently
  deletable global version. Delete its owning runs instead.
- Review-only purge remains separate from whole-run lifecycle deletion.
- Quarantine and lifecycle operation receipts are local-only and ignored by
  Git.

## Existing Sources Of Truth

| Entity | Durable source |
|---|---|
| Promoted agent version | `agent_versions/manifests/av_*.json` |
| Promotion/alias state | `agent_versions/catalog/{promotions,aliases}/` |
| Global dirty-version bytes | `agent_versions/objects/sha256/` |
| Eval run | `eval_results/**/runs/<run-id>/manifest.json` |
| Run-local candidate | `<run-dir>/agent-version.json` and local objects |
| Materialized result | `<run-dir>/result.json`, verified through `LocalRunStore` |
| Comparison | `eval_results/**/comparisons/cmp_*.{manifest.json,json}` |
| Diagnosis/review | Run-local `diagnosis/` and `review/` |

## Catalog Contract

Add `src/lifecycle/` with typed, versioned JSON views for:

- agent versions, including candidate/promoted state and associated runs;
- evaluation runs, including pipeline, benchmark, model, configuration,
  completion, review, size, and agent identity;
- comparisons and their ordered child-run identities;
- directed references between catalog entities;
- integrity findings for malformed, duplicate, or dangling managed records;
  and
- quarantine operation plans and receipts.

Discovery is deterministic and read-only. A corrupt managed record is reported
as an integrity finding and is not silently downgraded to a legacy record.

## Reference Graph

The catalog derives these relationships:

```text
comparison -> eval run -> agent version
promotion  -> source eval run
alias      -> promoted agent version
agent version -> global CAS object
eval run   -> run-local diagnosis and review state
```

References are classified as relationships and deletion warnings. The catalog
does not require a promoted global copy to keep a run reproducible because each
run retains its exact candidate manifest and required local CAS bytes.

## Commands

Provide stable non-interactive commands with JSON output:

```text
python -m src.lifecycle.cli catalog --json
python -m src.lifecycle.cli inspect <run|version|comparison> <id> --json
python -m src.lifecycle.cli verify --json
python -m src.lifecycle.cli delete <run|version|comparison> <id> --dry-run --json
python -m src.lifecycle.cli delete <run|version|comparison> <id> --yes --json
python -m src.lifecycle.cli restore <operation-id> --dry-run --json
python -m src.lifecycle.cli restore <operation-id> --yes --json
python -m src.lifecycle.cli purge <operation-id> --dry-run --json
python -m src.lifecycle.cli purge <operation-id> --yes --json
```

The deletion preview includes resolved paths, file and byte counts, owned
metadata, newly unreachable CAS objects, and every retained relationship that
will become dangling. IDs must resolve exactly once.

## Quarantine Contract

Use a project-local ignored root:

```text
.workbench/lifecycle/
  operations/<operation-id>.json
  quarantine/<operation-id>/payload/<original-project-relative-path>
```

Confirmed deletion:

1. rebuilds and validates the catalog;
2. verifies the target and plan hash;
3. refuses broad roots, ambiguous IDs, symlinks, or active run locks;
4. moves the exact paths atomically into operation-scoped quarantine;
5. writes a receipt with identities, warnings, paths, sizes, and timestamps;
6. leaves unrelated and shared CAS objects untouched.

Restore refuses to overwrite any recreated path. Permanent purge requires a
second explicit confirmation and removes only the exact operation quarantine.
Interrupted operations are detected from the receipt and filesystem state and
fail closed rather than guessing.

## Implementation Sequence

1. Delete tracked standalone result JSON and ignore `eval_results/` and local
   lifecycle state.
2. Add catalog models and deterministic managed-artifact discovery.
3. Add reference-graph derivation and integrity findings.
4. Add deletion planning, active-run and path-safety checks, and CAS reachability.
5. Add quarantine execution, restore, and permanent purge.
6. Add the lifecycle CLI with stable JSON and concise human output.
7. Add unit and integration tests for discovery, references, clean-break
   behavior, promoted-version deletion, shared CAS, quarantine, restore,
   purge, corruption, symlinks, and active locks.
8. Update the README, eval runbook, repository skill, and feature checklist.

## Verification And Acceptance

- Catalog output lists all managed schema-v3 runs and candidate/promoted agent
  versions with exact benchmark, model, configuration, and relationship data.
- No legacy standalone result reader or migration support exists.
- Deleting a run, comparison, or promoted version uses the same dry-run and
  confirmed quarantine flow.
- A quarantined entity can be restored without loss before permanent purge.
- Shared CAS objects survive; only objects unreachable from retained promoted
  manifests are quarantined with a deleted version.
- Active runs, ambiguous identities, corrupt managed records, broad paths, and
  symlinks fail closed.
- Deletion is local-only and performs no Azure or Benchmark Studio write.
- Relevant unit tests and the full repository test suite pass.

## Implementation Verification

- `src/lifecycle/` implements typed catalog, reference, deletion-plan, and
  operation contracts plus managed discovery and the lifecycle CLI.
- Runs, comparisons, and promoted versions share the same dry-run and confirmed
  quarantine flow; candidate-only versions remain owned by their runs.
- Restore verifies content-addressed tree evidence before moving data back.
- Operation states make interrupted staging, restore, and purge work detectable
  and recoverable without guessing.
- Promoted-version deletion includes aliases and promotion events and moves only
  CAS objects that no retained promoted manifest references.
- The agent-version resolver classifies `src/lifecycle/**` as operator-only so
  lifecycle changes do not alter execution-bearing agent identity.
- Twelve tracked standalone legacy eval JSON files were removed and
  `eval_results/` is now ignored local state.
- Verification completed with `311 passed, 6 skipped`, Ruff, and basedpyright.
