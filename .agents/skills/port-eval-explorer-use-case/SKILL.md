---
name: port-eval-explorer-use-case
description: Port a use case from an existing MeshInsights Benchmark Studio app into the Agent Workbench eval explorer. Use when an AI coding agent must reuse the generic run, attempt, review, and evidence-loading core while implementing the use-case-specific frozen-evidence normalization, schema, and charts.
---

# Port Eval Explorer Use Case

Port the reviewer evidence experience without copying the Benchmark Studio app.
Use `$benchmark-pipeline-port` as well when the underlying evidence pipeline has
not yet been ported.

## 1. Recover The Source Contract

Read both repositories' instructions, then inspect the Benchmark Studio use-case
config, evidence recipe, frozen-artifact decoder, normalized `EvidenceView`,
charts, and parity tests. Record the source remote, commit, relevant dirty files,
recipe ID/version, artifact kinds, cutoff semantics, and one representative
published example.

Do not copy labels, credentials, generated evidence, review workflow, auth, or
database code. Benchmark Studio remains the source of benchmark truth.

## 2. Keep The Ownership Boundary

Reuse these generic layers without adding use-case names or artifact fields:

- `agent-dev-eval-core/evaluation/`: result querying and state classification;
- `agent-dev-eval-ui/agent_eval_ui/`: local read-only API and static hosting; and
- `agent-dev-eval-ui/web/src/`: run picker, filters, attempt detail, tool trace,
  tabs, JSON views, and generic chart primitives.

Put custom behavior only in:

- `src/evidence/`: verified artifact decoding, normalization, and the project
  evidence envelope; and
- `www/src/use_case/`: schema validation and evidence composition/charts.

If a useful primitive can be configured without understanding the use case,
propose it as a reusable change and obtain explicit user approval before editing
the reusable UI or eval packages. If it contains business meaning, artifact
names, thresholds, or domain-specific layout, keep it in the
manifest-declared reference paths.

## 3. Port The Evidence Path

1. Load the exact benchmark identity and selected example's complete frozen
   source-snapshot contract from the retained eval-run manifest.
2. Retrieve only those retained frozen artifacts through `EvidenceStore`;
   preserve hash/size verification and the decision timestamp cutoff. Do not
   re-query the current publication catalog to recover a historical run.
3. Recreate Benchmark Studio's normalization and derived fields in
   `src/evidence/`. Never query a live source system or infer data from labels.
4. Return a versioned, JSON-serializable envelope containing provenance,
   example identity, normalized evidence, coverage, and known gaps.
5. Define the matching Zod schema in `www/src/use_case/` and compose core UI
   primitives into the domain views. A custom React component is the escape
   hatch; do not force every use case into one declarative chart grammar.
6. Register the project adapter in the root UI. Do not add a switch statement
   for use cases to the generic shell.

Preserve the same data, windows, derived values, markers, gaps, and context that
reviewers saw. Styling may differ unless pixel parity is requested.

## 4. Verify Before Handoff

- Unit-test decoding and normalization with safe synthetic fixtures.
- Test the generic API separately from the project adapter.
- Build and test the React app, including an evidence-render smoke test.
- Compare one real published example against Benchmark Studio semantics.
- Confirm the explorer runs without the Benchmark Studio checkout or live
  source system.
- Confirm tool calls and detailed review data degrade clearly when capture was
  disabled or purged.

The port is done when the user can select a retained eval run, inspect expected
and actual outputs plus model/tool activity, and view the verified evidence
package used for that exact benchmark version—with all use-case meaning confined
to the project-owned directories above.
