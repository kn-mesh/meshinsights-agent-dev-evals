---
name: port-eval-explorer-use-case
description: Port a Benchmark Studio use case into the Agent Workbench eval explorer. Use for project-specific frozen-evidence normalization, schema, and charts while reusing the generic explorer core. Do not use for pipeline or agent behavior changes.
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

- `use_case/evidence/`: verified artifact decoding, normalization, and the project
  evidence envelope; and
- `use_case/explorer/`: schema validation and evidence composition/charts.

Keep business meaning, artifact names, thresholds, and domain-specific layout
in manifest-declared reference paths.

## 3. Port The Evidence Path

1. Resolve and verify one immutable evidence-input contract:
   - working occurrence: `manifest.json` with schema-v2 `eval_contract` and
     complete frozen example contracts;
   - retained occurrence: lifecycle-verified bundle plus exact
     `evidence-references.json`.
2. Retrieve only the artifacts referenced by that selected occurrence through
   `EvidenceStore`; preserve hash/size verification and the decision timestamp
   cutoff. Do not re-query the current publication catalog for historical runs.
3. Recreate Benchmark Studio's normalization and derived fields in
   `use_case/evidence/`. Never query a live source system or infer data from labels.
4. Return a versioned, JSON-serializable envelope containing provenance,
   example identity, normalized evidence, coverage, and known gaps.
5. Define the matching Zod schema in `use_case/explorer/` and compose core UI
   primitives into the domain views. A custom React component is the escape
   hatch; do not force every use case into one declarative chart grammar.
6. Register the project adapter in the root UI. Do not add a switch statement
   for use cases to the generic shell.

Preserve the same data, windows, derived values, markers, gaps, and context that
reviewers saw. Styling may differ unless pixel parity is requested.

## 4. Verify Before Handoff

Select the Python, reusable, and frontend rows in the
[repository verification matrix](../project-guide/references/verification-matrix.md).

- Unit-test decoding and normalization with safe synthetic fixtures.
- Test the generic API separately from the project adapter.
- Build and test the React app, including an evidence-render smoke test.
- Compare one real published example against Benchmark Studio semantics.
- Assert equivalent working and retained inputs render the same evidence
  semantics through one adapter.
- Confirm the explorer runs without the Benchmark Studio checkout or live
  source system.
- Confirm tool calls and detailed review data degrade clearly when capture was
  disabled or unavailable.

The port is done when the user can select a working or retained occurrence,
inspect its available outputs and activity, and view the verified evidence
package used for that exact benchmark version—with all use-case meaning
confined to the project-owned directories above.
