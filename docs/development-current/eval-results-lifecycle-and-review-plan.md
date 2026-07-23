# Eval Results Lifecycle And Review Plan

## Status

Implemented and validated on 2026-07-23. New working results use the explicit
working root; complete runs can be elevated to compact retained artifacts; exact
permanent deletion, immutable Azure evidence references, formal lifecycle
skills, and read-only Working/Retained explorer filters are in place.

## FDE Outcome

An FDE can use rich local evals for immediate debugging, explicitly elevate a
meaningful full run and its agent version for longer-term comparison, review
both states in a read-only app, and permanently remove obsolete results without
operating a local artifact-management platform.

## Current State

The current schema-v1 run layout already separates:

- compact `manifest.json`, `agent-version.json`, and `result.json`;
- immutable detailed `attempts/`;
- disposable `performance/`; and
- detailed `review/` content-addressed model artifacts.

`src/agent_versions/` resolves every run into a content-addressed candidate and
promotes selected candidates into a separate local store. `src/eval_lifecycle/`
owns the complete working-versus-retained lifecycle. The explorer reads both
states without exposing mutations.

## Target Lifecycle

### Working eval

Every new run starts as a working eval. It contains:

- run, benchmark, model, pricing, grader, and candidate provenance;
- durable per-unit execution and grading results;
- exact model request and response for every unit;
- tool calls and output-validation detail for every unit;
- disposable speed, latency, retry, and invocation observations; and
- immutable Azure evidence-package references and integrity metadata.

Working evals may be deleted minutes after creation.

### Elevated retained eval

Elevation applies to one complete eval run. It:

- retains the associated meaningful agent version in the same operation;
- verifies benchmark, evidence, agent, model, pricing, grader, and result
  identity;
- produces compact aggregate retained artifacts;
- preserves full AI outputs, expected outputs, validation and grading outcomes,
  accuracy, reliability, token, and cost information;
- preserves lightweight Git commit, relevant patch/untracked content, and
  configuration hashes;
- prunes detailed tool traces and disposable performance observations; and
- protects the retained eval from ordinary working-run cleanup.

Elevation is not inferred from age or score.

## Feature 1: Schema And Folder Contract

Implement the product-level separation:

```text
eval_results/
  working/
    <benchmark-key>/
      <benchmark-version>/
        <run-id>/
          manifest.json
          result.json
          agent-provenance.json
          evidence-references.json
          attempts/
          review/
          performance/
  retained/
    <benchmark-key>/
      <benchmark-version>/
        <retained-eval-id>/
          manifest.json
          result.json
          units.json
          agent-provenance.json
          evidence-references.json
          agent.patch
```

The implementation may refine names, but must preserve:

- distinct working and retained roots;
- a small number of aggregate retained files;
- no file-per-unit retained layout;
- no copied evidence packages; and
- an explicit lifecycle state readable without scanning content-addressed
  object reachability.

Before changing the schema, inventory existing local runs and promoted versions.
Decide explicitly whether any existing run is meaningful enough to migrate.
Disposable historical runs may be deleted rather than supporting a generalized
migration framework.

## Feature 2: Lightweight Candidate Provenance

Replace full source-store behavior in the supported path with:

- Git commit;
- relevant dirty patch;
- relevant untracked agent files or their captured patch content;
- hashes of pipeline, prompt, output schema, evaluation profile, model, and
  project configuration;
- benchmark and evidence identity; and
- pricing snapshot.

Do not copy the complete source tree into every run. The retained patch must
contain enough content to reconstruct relevant uncommitted changes, not merely
their hash.

## Feature 3: Full-Run Elevation Command

Provide one non-interactive, scriptable command that:

1. accepts an exact working run ID;
2. refuses incomplete or internally inconsistent runs;
3. previews the retained artifacts and pruned categories;
4. requires explicit confirmation;
5. retains the eval and meaningful agent version atomically enough that they
   cannot become detached;
6. writes compact retained artifacts;
7. verifies their hashes and references; and
8. reports the retained eval ID and paths.

Do not expose elevation in the review UI.

## Feature 4: Simple Permanent Deletion

Provide exact-target deletion for:

- disposable working evals; and
- less-frequently deleted retained evals.

Working deletion may use a concise confirmation. Retained deletion must clearly
identify the associated retained agent version and require stronger explicit
confirmation. If another retained eval references the same meaningful agent
version, preserve the shared version until no retained eval needs it.

Deletion is permanent. Do not quarantine, restore, archive, or build deletion
transaction recovery as a product feature.

Keep only the path, active-run, and exact-reference safety necessary to avoid
deleting the wrong target.

## Feature 5: Azure Evidence References

Both working and retained artifacts store:

- storage account and container identity;
- immutable blob or artifact identity;
- size and SHA-256;
- source snapshot identity; and
- the evidence recipe or schema identity required for decoding.

The review backend retrieves and verifies the frozen package from Azure Blob
Storage on demand. It must not silently fall back to current benchmark
membership or an unverified local copy.

## Feature 6: Read-Only Review App

Extend the explorer run list with:

- All;
- Working; and
- Retained

filters. Show lifecycle state on each run. The app must:

- inspect full working request, response, tool, validation, grading, and
  evidence detail;
- inspect retained full AI outputs, expected outputs, grading, accuracy, tokens,
  and cost;
- retrieve evidence from Azure using retained immutable references;
- support downstream review and comparison of completed runs; and
- remain read-only.

Do not add elevate, delete, edit, annotate, or lifecycle mutation actions to the
MVP UI.

## Feature 7: Remove Excess Lifecycle Machinery

Completed. The quarantine, restore, purge-recovery, and generalized catalog
subsystem was removed after current working/retained discovery, comparison
reads, and exact permanent deletion were covered by focused tests.

## Agent Skill Deliverables

### Add `eval-lifecycle`

Create a root-level skill for:

- explaining working versus retained evals;
- finding exact runs;
- previewing and elevating a complete run;
- verifying retained artifacts;
- permanently deleting working or retained runs;
- explaining what elevation preserves and prunes;
- refusing UI mutation work for MVP; and
- stating that deletion is not recoverable.

This is the formal lifecycle process required by the MVP scope.

### Update `run-use-case-evals`

Make every successful run land in `working/`, explain resume versus deletion,
and hand meaningful completed runs to `$eval-lifecycle`.

### Update `eval-results-analysis`

Teach it to analyze working and retained schemas, fetch evidence by immutable
Azure reference, and state when pruned retained detail prevents a particular
analysis.

### Update `agent-eval-builder`

Use the implemented working/retained contract as the only supported lifecycle.
Keep generalized lifecycle additions behind explicit product approval.

### Update `project-guide`

Route run, analysis, elevation, deletion, and explorer questions to the correct
skills. Require user approval before changes to reusable eval, UI, versioning,
or lifecycle code.

## Validation

- Working-run creation and complete per-unit review capture.
- Lightweight provenance for clean, dirty, and relevant-untracked states.
- Full-run-only elevation.
- Incomplete-run elevation refusal.
- Compact retained artifact content and no file-per-unit output.
- Tool/performance pruning with full AI output and grading preservation.
- Eval and meaningful agent-version linkage.
- Working and retained exact permanent deletion.
- Shared retained agent-version reference safety.
- No quarantine or restore in the supported workflow.
- Azure evidence retrieval, hash verification, missing evidence, and access
  failure behavior.
- Read-only app filters and state rendering.
- Existing schema-v1 compatibility or intentional one-time migration behavior
  selected during the inventory gate.

## Non-Goals

- individual-unit elevation;
- UI elevation or deletion;
- recoverable deletion;
- local evidence-package preservation;
- cloud retention;
- storage tiers or retention policy engines;
- multi-user coordination;
- background garbage collection; and
- a generalized migration platform.

## Completion Criteria

An FDE can run, inspect, elevate, verify, filter, and permanently delete evals
through one documented lifecycle, while the app remains read-only and retained
artifacts contain exactly the durable agent-improvement evidence defined in the
MVP scope.
