---
name: benchmark-pipeline-port
description: Port a working use-case evidence pipeline from a MeshInsights Benchmark Studio repository into a clean Agent Workbench project. Use when an FDE gives Codex a Benchmark Studio repo or pipeline path and wants the relevant retrieval, normalization, visualization, objects, processors, dependencies, and pipeline wiring adapted into the new project as the base for agent development. Do not use for ordinary pipeline evolution after the initial port; use pipeline-builder instead.
---

# Benchmark Pipeline Port

Port the smallest working evidence pipeline needed to start agent development.
Treat this as guided engineering in a clean project, not an importer or a new
runtime subsystem.

Use `$pipeline-builder` for the target pipeline shape. Use
`$external-runtime-setup` only when configuring read-only Azure access or local
credentials.

## Assumptions

- The target is a freshly initialized Agent Workbench repository with no
  customer-specific pipeline code to preserve.
- The developer supplies the relevant Benchmark Studio repository or pipeline
  path.
- Record the source repository remote, commit, and whether relevant pipeline
  files have uncommitted changes.
- Benchmark Studio already has a working lightweight pipeline that creates the
  evidence packages used during review and labeling.
- Agent Workbench consumes published benchmarks and frozen evidence read-only;
  it never owns or mutates Benchmark Studio workflow truth.

If the target already contains overlapping use-case code, stop and ask how to
treat it. If relevant source files are dirty, show the developer that scope and
ask whether those working changes are part of the pipeline to port.

## Read Before Editing

1. Read instructions and relevant skills in both repositories.
2. Read the target's `docs/use_case/` context without editing it unless the user
   asks.
3. Read the source project/use-case configuration, evidence recipe, label
   schema, adapter, evidence pipeline, visualization code, dependencies, and
   tests.
4. Inspect the target's existing benchmark loader, Azure evidence access,
   pipeline runner, component registry, and nearest pipeline tests.
5. Confirm the exact published benchmark version and representative example to
   use for validation.

## Establish The Handoff Contract

Before copying code, state these facts from repository evidence:

- decision being supported;
- `unit_id` meaning;
- source of `decision_timestamp` and its evidence-cutoff semantics;
- `example_id` format and any extra discriminator;
- evidence-recipe key/version and lookback rules;
- frozen artifact kinds, formats, and integrity metadata;
- normalized and derived evidence shown to reviewers;
- label fields that the later agent output must make measurable; and
- source repository remote, commit, and relevant entry points.

Ask the user only when these facts cannot be resolved from the source repo or
published contract.

## Decide What To Port

Port or adapt use-case behavior needed downstream:

- typed process, action, and metadata objects;
- frozen-artifact decoding and normalization;
- retrieve/process/action hydrators;
- deterministic evidence processors and derived features;
- evidence visualization logic;
- source-controlled pipeline YAML;
- the benchmark-aware runner shape;
- use-case dependencies; and
- focused tests and safe synthetic fixtures.

Reuse target or `mi-core` components when they already own the behavior. Keep
use-case-specific artifact names, decoding, transforms, and business rules in
the target project rather than generalizing them prematurely.

Do not port:

- Benchmark Studio review, labeling, disagreement, or publication workflow;
- Benchmark Studio FastAPI routes, Postgres repositories, application shell,
  workflow React UI, or authorization code;
- live source-system retrieval as the Agent Workbench runtime path;
- mutable benchmark state or copied benchmark labels;
- source credentials, connection strings, `.env`, or generated evidence; or
- AI prompts, tools, and agents unless the user explicitly includes first-agent
  development in the request.

When the target includes the Agent Workbench eval explorer, port the standalone
reviewer-evidence schema, normalization semantics, and evidence display into the
project-owned extension points. Use `$port-eval-explorer-use-case` for that UI
handoff; do not copy the Benchmark Studio application around it.

Source-system code may be read to understand frozen artifacts, but the target
runtime must retrieve the exact published artifacts from Azure using read-only
access and verify their size/hash before decoding.

## Build In This Order

1. **Frozen evidence retrieval**
   - Load one explicit published benchmark version and example.
   - Retrieve its frozen artifacts through the existing read-only contract.
   - Verify artifact identity, size, hash, capture window, and known gaps.
   - Reject evidence after the decision timestamp.

2. **Typed normalization boundary**
   - Decode use-case artifact formats in a use-case-owned retriever or adapter.
   - Hydrate typed datasets and identity onto the process object.
   - Preserve the source pipeline's field meaning; do not preserve accidental
     framework structure merely because it exists in the source.

3. **Visualization path**
   - Port the transformations and views needed to inspect what reviewers saw.
   - Run one representative example before building decision logic.
   - Preserve the same data, cutoff, windows, gaps, derived values, markers,
     labels, and context. Layout and styling may differ unless the user requires
     screenshot-level parity.

4. **Compute-only control pipeline**
   - Add the minimum deterministic processor or evidence summary that proves
     the complete retrieve/process/action path.
   - Wire a source-controlled `.ppln` using explicit benchmark metadata.
   - Declare `benchmark_contract` compatibility in the `.ppln`: published
     contract schema version, evidence-recipe ID, source-snapshot contract ID,
     and the use-case artifact kinds required by that pipeline.
   - Put compact identity and control output on the final receipt; keep large
     datasets and images as artifacts or visualization output.

5. **Runner and tests**
   - Support an explicit project, benchmark key/version, and example ID.
   - Run successfully without the Benchmark Studio checkout or live source
     system available.
   - Keep all-example orchestration available when the target template already
     supports it.

Stop after the control pipeline is sound. Continue with the **Build The First
Agent Or Next Variant** workflow in `$pipeline-builder`; use
`$ai-processor-builder` for the AI processor implementation details.

## Preserve These Invariants

- `example_id`, `unit_id`, and `decision_timestamp` remain stable from
  publication through pipeline receipts.
- `decision_timestamp` is a hard default cutoff; do not introduce hindsight.
- The target reads frozen source artifacts and verifies their published
  integrity metadata.
- Shared benchmark models and runtime metadata stay use-case-neutral; required
  artifact names and byte decoding belong in the ported retriever or adapter.
- Benchmark Studio remains the only source of benchmark and label truth.
- Evidence shown during target inspection has the same semantic content as the
  reviewer evidence used to create labels.
- The target has no runtime import or filesystem dependency on the source repo.
- Final receipt output is compact, serializable, and suitable for later evals.

## Verify The Port

At minimum:

1. Run component tests for artifact decoding, cutoff rejection, normalization,
   hydrators, visualization, and receipt output.
2. Build the YAML pipeline through the real component registry.
3. Run one published representative example from frozen Azure evidence.
4. Compare its normalized evidence and relevant visualization semantics with
   Benchmark Studio.
5. Run a broader example scope when credentials and benchmark size make it
   practical.
6. Temporarily make the source checkout unavailable, or otherwise prove the
   target has no runtime dependency on it.
7. Run the target repository's relevant test suite with `uv run pytest`.

Pixel-identical images are not required unless the user asks. Any deliberate
semantic difference from reviewer evidence must be explained and approved.

## Record Provenance Concisely

Record the source repository, commit, source pipeline/config paths, evidence
recipe identity, and meaningful adaptations in the target's existing README or
project provenance documentation. Rely on normal target Git history and tests
for the implementation record; do not create a generic port manifest, port
database, or content-addressed port subsystem.

## Done Checklist

- Source repository and commit are recorded.
- Ported files contain only target-owned use-case and pipeline behavior.
- Published frozen evidence is retrieved and integrity-checked read-only.
- Identity, cutoff, evidence-recipe, and reviewer-evidence semantics are
  preserved.
- One representative example and its visualization are verified.
- A compute-only YAML control pipeline runs and produces a stable receipt.
- Target tests pass without the source repository or live source system.
- The next agent variant can build on the control pipeline without redoing the
  evidence port.
