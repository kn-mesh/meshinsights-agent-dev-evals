# Codex-Guided Pipeline Port From Benchmark Studio

**Status:** Implemented for MVP through repository skill guidance

**Implementation summary:** The `benchmark-pipeline-port` skill gives Codex a
concise, repeatable workflow for inspecting a working Benchmark Studio source
repository, porting the use-case evidence pipeline into a fresh Agent Workbench
project, replacing live source access with read-only published evidence,
building visualization and compute-only control pipelines, and verifying the
result on representative examples.

**Backlog feature:** `docs/development-backlog/features.md` → Codex-Guided
Pipeline Port From Benchmark Studio

## Outcome

An FDE can give Codex the path to the working Benchmark Studio pipeline and ask
it to establish the initial use-case pipeline in a freshly bootstrapped Agent
Workbench project. The workflow leaves a runnable evidence and control pipeline
that becomes the base for first-agent development.

This is guidance for a coding agent performing use-case-specific engineering.
It is not a generic importer, manifest format, port database, or runtime
subsystem.

## Implemented Skill

`.agents/skills/benchmark-pipeline-port/SKILL.md` directs Codex to:

1. inspect both repositories and record the source Git revision and relevant
   working-tree state;
2. establish unit, decision timestamp, example discriminator, evidence recipe,
   artifact, label, and cutoff semantics;
3. select the source objects, normalization, transforms, visualizations,
   dependencies, tests, and pipeline wiring needed downstream;
4. exclude Benchmark Studio workflow state, APIs, UI, credentials, and live
   source-system access from the target runtime;
5. retrieve and integrity-check published frozen Azure evidence read-only;
6. build typed normalization, visualization, and compute-only YAML control
   pipeline stages;
7. verify one representative example, reviewer-evidence semantics, receipt
   output, source-repository independence, and relevant tests; and
8. record source provenance concisely in normal project documentation.

The skill routes subsequent pipeline construction through `pipeline-builder`,
auth setup through `external-runtime-setup`, and first-agent work through
`ai-processor-builder`.

## Fixed MVP Assumptions

- The target starts as a clean Agent Workbench project without use-case code.
- The source is a working Benchmark Studio checkout supplied by the FDE; its
  revision and relevant working changes are made explicit.
- Benchmark Studio already has a working lightweight evidence pipeline.
- Agent Workbench consumes a published benchmark and frozen evidence read-only.
- Semantic visualization parity is required; pixel identity is not required
  unless the developer asks for it.
- The port stops after a sound compute-only control pipeline. AI variants are
  the next job.

## Spirax Reference

The current repository provides the exercised reference shape:

- source Benchmark Studio evidence pipeline:
  `api/label_benchmark/use_cases/spirax/pipeline/evidence_pipeline.py` at source
  commit `ea40dec5b406bda62a5734c19f483cfae0481098`;
- read-only published artifact retrieval:
  `src/retrievers/spirax_frozen_evidence_retriever.py`;
- typed retrieval and receipt handoff under `src/objects/` and
  `src/hydrators/`;
- visualization processors under `src/processors/`; and
- runnable YAML variants under `pipeline_configs/` with contract and runner
  tests under `tests/`.

This reference demonstrates the result of the workflow without turning its
Spirax-specific files into a required template for future use cases.

## Acceptance Criteria

- [x] A dedicated skill triggers for initial Benchmark Studio pipeline ports.
- [x] The skill assumes a clean target and makes source revision/state explicit.
- [x] The source/target responsibility boundary is explicit.
- [x] Published benchmark and frozen evidence remain read-only.
- [x] Identity, cutoff, recipe, artifact, and visualization invariants are
  explicit.
- [x] The workflow builds visualization before a compute-only YAML control
  pipeline and stops before AI work.
- [x] Representative-example, registry-build, receipt, independence, and test
  verification are required.
- [x] The skill is routed from `project-guide` and `pipeline-builder`.
- [x] The Spirax implementation and focused tests provide a current reference.
- [x] No port-specific runtime subsystem or manifest machinery was added.
