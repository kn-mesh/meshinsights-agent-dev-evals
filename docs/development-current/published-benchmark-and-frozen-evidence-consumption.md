# Published Benchmark And Frozen-Evidence Consumption

**Status:** Implemented for MVP

**Implementation summary:** Shared benchmark models and runtime metadata are
use-case-neutral; pipeline YAML declares compatibility against
`workbench.project.json`; standalone and eval entry points fail closed before
pipeline execution; Azure artifact reads retain byte-size and SHA-256
verification; and the former generic-named retriever is now the explicitly
Spirax-owned `SpiraxFrozenEvidenceRetriever`. A non-Spirax pump fixture proves
arbitrary unit identities and artifact kinds across repository loading,
metadata construction, and compatibility preflight.

**Backlog feature:** `docs/development-backlog/features.md` → Published
Benchmark And Frozen-Evidence Consumption

## Outcome

A freshly bootstrapped and ported use-case project can run a named published
benchmark version without inheriting Spirax assumptions from shared benchmark,
runner, or metadata code. Shared mechanics preserve example identity and verify
the frozen Azure bytes. The ported use-case code owns artifact requirements,
decoding, normalization, and domain validation.

This is a boundary cleanup and preflight-validation feature, not a generic
evidence framework.

## Gaps Closed

- `BenchmarkExample` no longer requires `telemetry`, `alarms`, or a numeric
  `sensor_id`.
- `BenchmarkExamplePipelineMetadata` and the YAML runner now carry only generic
  unit and published-example identity.
- `SpiraxFrozenEvidenceRetriever` explicitly owns the Spirax Parquet/NDJSON
  evidence contract and resolves its sensor identity locally.
- Selected and historical alarm detection/resolution timestamps are rejected
  when they fall outside the frozen raw window or beyond the decision cutoff.
- Pipeline and eval entry points validate `workbench.project.json` and the
  pipeline declaration before execution.
- The published Benchmark Studio v2 contract includes frozen label schemas,
  source-snapshot identity, artifact manifests, byte sizes, and content hashes.
  It does not include evidence-recipe identity, so the workbench must not claim
  to verify that value against Azure publication data.

## Design Boundary

The implementation keeps three responsibilities separate:

1. **Shared published-benchmark mechanics** load immutable versions and carry
   use-case-neutral example, label-schema, snapshot, and artifact metadata.
2. **Shared evidence storage** reads an artifact and verifies its declared byte
   size and SHA-256 digest. `AzureBlobEvidenceStore` already provides this
   boundary and remains the reusable primitive.
3. **Ported use-case code** declares required artifact kinds and converts the
   verified bytes into typed domain data. The existing telemetry/alarm decoder
   remains as the Spirax reference implementation, with an explicit Spirax
   name.

Do not add a decoder registry, plugin protocol, copied benchmark manifest, or
new runtime subsystem. Do not make Spirax process objects, prompts, or
visualizations generic.

## Implementation Plan

### 1. Make the published benchmark runtime contract use-case-neutral

- Remove the `telemetry`/`alarms` requirement and `sensor_id` property from
  `BenchmarkExample`.
- Continue rejecting duplicate artifact kinds so an artifact can be selected
  unambiguously by the ported use case.
- Add generic snapshot invariants that are true for every use case: ordered raw
  windows, no window end after the decision timestamp, and a non-empty artifact
  manifest.
- Remove `sensor_id` from `BenchmarkExamplePipelineMetadata` and from runner
  metadata injection. Preserve `unit`, `example_id`, decision timestamp,
  benchmark identity, source-snapshot identity, raw windows/gaps, artifact
  manifests, and `example_metadata` without domain coercion.

### 2. Make the existing evidence adapter explicitly Spirax-owned

- Rename `AzureBlobEvidenceRetriever` and its module to an explicit Spirax
  frozen-evidence retriever, updating YAML registrations, imports, and focused
  tests.
- Keep its current requirements and behavior: select telemetry and alarm
  artifacts, read them through `EvidenceStore`, decode Parquet/NDJSON, enforce
  the cutoff/window rules, and emit the current Pulse payload.
- Resolve the Spirax sensor identity inside this retriever from `unit` or
  `example_metadata`; shared benchmark and runner code must not know that it is
  numeric.
- Leave downstream Spirax hydrators, processors, and visualizations unchanged.

### 3. Add cheap project/pipeline compatibility preflight

- Add one small loader for the existing `workbench.project.json` contract.
- Add a concise `benchmark_contract` declaration to each pipeline YAML with:
  published contract schema version, evidence-recipe ID, source-snapshot
  contract ID, and required artifact kinds.
- Before registry construction or model calls, standalone and eval execution
  must verify that:
  - the requested project, benchmark key, and version exist in the project
    contract;
  - the loaded published contract schema version matches the project and
    pipeline declarations;
  - the pipeline evidence-recipe and source-snapshot contract declarations
    match `workbench.project.json`;
  - configured evaluation label fields exist in the frozen published label
    schemas; and
  - every selected example supplies the artifact kinds required by the
    pipeline.
- Strip the compatibility declaration before passing YAML to the pipeline
  registry. Keep the declaration in source control and include its normalized
  values in run/eval identity where those inputs affect reproducibility.
- Report recipe and snapshot-contract checks accurately as agreement between
  the initialized project and pipeline. Artifact size/hash verification remains
  the check against the actual Azure-published evidence.

### 4. Prove the boundary with focused tests

- Add a non-Spirax benchmark fixture with a nonnumeric unit and arbitrary
  artifact kinds; prove repository loading, standalone runtime metadata, and
  eval selection do not require telemetry, alarms, or sensor IDs.
- Retain tests for duplicate artifacts, label-schema hashes, stable example
  identity, repository parity, and Azure byte-size/SHA-256 failures.
- Add preflight failure tests for project/benchmark/version, schema version,
  label fields, recipe ID, snapshot-contract ID, and missing required artifact
  kinds. Assert these failures occur before pipeline construction or AI calls.
- Update the Spirax retriever tests and build every checked-in YAML pipeline to
  prove the rename and local sensor resolution preserve current behavior.
- Run the benchmark repository, pipeline runner, eval orchestration, bootstrap,
  retriever, and pipeline-contract test suites, followed by the normal project
  lint/type/test gates.

### 5. Align developer guidance

- Update `benchmark-pipeline-port` so a new port declares its artifact kinds and
  compatibility IDs in pipeline YAML and implements decoding in use-case-owned
  retriever code.
- Update `project-guide`, `pipeline-builder`, and `agent-eval-builder` only where
  their routing or contract guidance references the old generic retriever name
  or compatibility boundary.
- Mark the MVP checklist item complete only after a non-Spirax fixture passes
  the same load, preflight, metadata, and eval path.

## Acceptance Criteria

- [x] Shared benchmark models, metadata, and runner code contain no Spirax
  artifact or sensor assumptions.
- [x] Arbitrary published artifact kinds load and retain immutable manifest
  identity.
- [x] Every artifact read from Azure is rejected on byte-size or SHA-256
  mismatch.
- [x] The current Spirax pipeline still decodes and visualizes its frozen
  telemetry/alarm evidence with identical domain semantics.
- [x] Standalone and eval entry points use the same compatibility preflight and
  stable example identity.
- [x] Contract incompatibilities fail before pipeline construction or model
  execution with actionable messages.
- [x] A non-Spirax fixture exercises repository loading, runtime metadata,
  required-artifact validation, and eval selection.
- [x] No Benchmark Studio mutation, evidence copying, decoder registry, or
  genericization of use-case domain code is introduced.

## Deferred

Publishing evidence-recipe and source-snapshot contract IDs directly in a
future Benchmark Studio contract would let Agent Workbench verify those values
against Azure rather than only against initialized project and pipeline
configuration. That cross-repository contract change is useful, but it is not
required to remove the current shared-code coupling or to verify frozen artifact
integrity for this MVP feature.
