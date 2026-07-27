---
name: benchmark-pipeline-port
description: Port an initial Benchmark Studio evidence pipeline into Agent Workbench. Use for frozen-evidence retrieval, decoding, normalization, control wiring, receipts, and tests. For later variants use pipeline-builder; for explorer-only work use port-eval-explorer-use-case.
---

# Benchmark Pipeline Port

Port the smallest working evidence pipeline into a freshly initialized,
validated Agent Workbench project. This is guided engineering, not an importer
or runtime subsystem.

Use `$pipeline-builder` for the target shape,
`$port-eval-explorer-use-case` for explorer evidence UI, and
`$external-runtime-setup` for read-only Azure credentials.

## Preconditions And Boundaries

- Record the source repository remote, commit, relevant entry points, and dirty
  source files.
- Confirm the target has no customer code that would be overwritten. Ask before
  proceeding when source changes or target ownership overlap is ambiguous.
- Read both repositories' instructions, target `use_case/docs/`, source recipe,
  label schema, pipeline, visualization, dependencies, and focused tests.
- Benchmark Studio owns benchmark, label, review, and publication truth. The
  target consumes published versions and frozen evidence read-only.
- Keep use-case decoding and business rules in manifest-declared reference
  paths.

Do not port Studio routes, databases, workflow UI, authorization, live
source-system retrieval, mutable labels, secrets, generated evidence, or AI
prompts/tools unless the user explicitly includes agent development.

## Establish The Handoff

Resolve from source and published contracts:

- decision and `unit_id` meaning;
- `decision_timestamp` cutoff semantics;
- `example_id` and discriminator;
- evidence recipe/version and lookback;
- artifact kinds, formats, hashes, sizes, and capture windows;
- normalized/derived evidence shown to reviewers;
- measurable label fields; and
- exact published benchmark version and validation example.

Ask only for facts unavailable from those sources.

## Ordered Port

1. **Retrieve frozen evidence.** Load the explicit benchmark/example through
   existing read-only Azure contracts. Verify artifact identity, size, hash,
   window, and known gaps; reject post-decision evidence.
2. **Create the typed boundary.** Decode formats in a use-case retriever or
   adapter, hydrate typed datasets and identity, and preserve source meaning
   without copying accidental framework structure.
3. **Reproduce reviewer evidence.** Port transformations and visual semantics
   needed to inspect the same data, cutoff, windows, gaps, derived values, and
   markers. Styling may differ unless screenshot parity is requested.
4. **Build the control pipeline.** Add the minimum deterministic processor,
   typed objects/hydrators/actions, and `.ppln`. Declare published schema,
   evidence recipe, snapshot contract, and required artifact kinds in
   `benchmark_contract`; keep large evidence out of the final receipt.
5. **Add the candidate policy.** Create
   `use_case/agent_version_configs/<pipeline-stem>.agent.yaml` with the matching source
   pipeline, receipt contracts, action policy, evidence recipe, and permitted
   model/reasoning overrides.
6. **Wire exact execution.** Require explicit project, benchmark key/version,
   and example ID. The target must run without the Studio checkout or live
   source system.
7. **Update operator handoff.** Replace the control-pipeline portion of
   `EVAL_RUNBOOK.md` with validated pipeline/policy paths and the exact-example
   command. Leave
   `agent-workbench-eval-runbook-status: bootstrap-placeholder` until
   `$agent-eval-builder` adds the first complete eval command.

Stop after the control path is sound. Continue with the first-agent workflow in
`$pipeline-builder`; use `$ai-processor-builder` for implementation details.

## Acceptance Checks

Use the
[repository verification matrix](../project-guide/references/verification-matrix.md)
for the Python, pipeline, reusable, and frontend layers changed by the port.

- Source repository, commit, pipeline/config paths, recipe, and meaningful
  adaptations are recorded in existing project provenance documentation.
- Stable `example_id`, `unit_id`, and `decision_timestamp` flow into the
  receipt; the timestamp remains a hard no-hindsight cutoff.
- Frozen source artifacts are integrity-checked before decoding.
- Reviewer-evidence semantics match; approved differences are documented.
- YAML builds through the real registry and produces a compact stable receipt.
- The matching policy validates and resolves a candidate `agent_version_id`.
- Focused decoding, cutoff, hydration, visualization, and receipt tests pass.
- One published representative example runs from Azure evidence.
- Tests and runtime succeed with the source checkout unavailable.

Use normal Git history and tests as the record. Do not add a port manifest,
database, or content-addressed port subsystem.
