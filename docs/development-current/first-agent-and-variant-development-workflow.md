# First-Agent And Variant Development Workflow

**Status:** Implemented for MVP

**Implementation summary:** The existing `pipeline-builder` skill now connects
the ported control pipeline, structured output, smallest-useful AI shape,
one-example runner, smoke eval, and immutable candidate-version workflow. The
adjacent skills route into that path, and the current Spirax `v1_3` and `v2`
references are documented without adding product machinery.

**Backlog feature:** `docs/development-backlog/features.md` → First-Agent And
Variant Development Workflow

## Outcome

Make the existing FDE workflow for building a first agent explicit and
repeatable:

1. start from the working pipeline ported from Benchmark Studio;
2. define a structured output that can be measured against the benchmark;
3. add the simplest useful AI processor;
4. run one example;
5. run an eval; and
6. preserve useful versions while trying the next improvement.

This is guidance for Codex and an FDE, not a new Agent Workbench subsystem.

## Product Fit

This feature directly serves jobs 3, 5, and 7 in
`docs/product-strategy/jobs-to-be-done.md`: build the first lightweight agent,
evaluate it, and improve or try another strategy.

The company strategy says Mesh should differentiate through the readiness and
continuous-improvement loop, not through generic agent infrastructure. The
implementation should therefore make the loop easy to perform without adding
another runtime, generator, catalog, or workflow product.

## What Already Exists

The repository already has nearly everything needed:

- `benchmark-pipeline-port` leaves a working evidence/control pipeline;
- `pipeline-builder` describes the progression from control pipeline to AI and
  already owns pipeline variants, YAML, receipts, and runners;
- `ai-processor-builder` explains how to implement a structured workflow or a
  tool-using agent;
- `src/pipelines/pipeline_run_from_yaml.py` runs one exact benchmark example;
- `src/evals/eval_orchestration.py` runs one-example smoke evals and wider
  evaluations;
- evaluation profiles connect structured receipt outputs to benchmark labels;
- candidate agent-version resolution preserves the exact assets used by every
  eval; and
- Spirax `v1_3` and `v2` already demonstrate a workflow and an agent variant.

The gap is concise guidance connecting these pieces. It is not missing runtime
capability.

## Decisions

### Extend the existing skills

Do not create another skill. Add a short **Build The First Agent Or Next
Variant** section to `pipeline-builder` that tells Codex to:

1. preserve the working parent pipeline;
2. define the benchmark-aligned structured output first;
3. choose the simplest processor shape;
4. add the variant at a new pipeline path;
5. verify the output reaches act-stage receipt metadata;
6. run one example and then a one-example eval; and
7. stop and report before running a broad eval or making another change.

Continue routing AI implementation details to `ai-processor-builder` and eval
execution to `run-use-case-evals`. Add only a short handoff sentence to those
skills if needed.

### Prefer the simplest processor shape

Use this order:

1. Keep deterministic logic when it solves the decision reliably.
2. Use a one-shot AI workflow when the model can make the decision from the
   evidence already prepared by the pipeline.
3. Use a tool-using agent only when the model needs to choose a bounded
   investigation at runtime.

The workflow supports all three shapes, but a project does not need to
implement all three.

### Keep variants as normal project assets

A variant consists of the assets the repository already understands:

- a new `.ppln` file under `pipeline_configs/`;
- variant-specific processors under `src/processors/<variant>/` when needed;
- shared processors under `src/processors/common/`;
- the existing structured output and receipt contract;
- an evaluation profile when the output-to-benchmark mapping changes; and
- an agent policy under `agent_version_configs/` for AI variants.

Do not add a variant manifest, `docs/variants/` hierarchy, experiment database,
or new identity. The pipeline filename is the human working name. The existing
`agent_version_id` identifies exact executable content, and the existing
`run_id` identifies an eval.

Record a variant's short hypothesis in the existing
`docs/use_case/PipelineVersions.md`. Keep it brief: what changed, why, and which
pipeline it was based on.

### Reuse current commands

Do not add a new CLI. Use:

- `src.pipelines.pipeline_run_from_yaml` for one-example execution;
- `src.evals.eval_orchestration` for smoke and wider evals;
- `src.evals.inspection_cli` to inspect failures; and
- `src.agent_versions.cli` when a useful version should be inspected or
  promoted.

### Preserve useful versions

Never overwrite the only working pipeline or a variant with meaningful eval
results. Copy it to a new pipeline path, change only the intended design
dimension, and let the existing candidate-version and eval identities preserve
the exact comparison points.

## Simple Codex Workflow

### 1. Inspect the starting point

- Read the use-case context and the parent pipeline.
- Confirm the pipeline runs on one published benchmark example.
- Identify the prepared evidence and current receipt output.

### 2. Define the measurable output

- Define or confirm the structured Pydantic output.
- Confirm its required fields align with the evaluation profile.
- Ensure the result flows from the processor to the action and then to
  act-stage receipt metadata.

Do this before prompt or tool work.

### 3. Add the smallest useful variant

- State the short hypothesis.
- Copy the parent `.ppln` to a new version instead of editing it in place.
- Reuse retrieval, evidence preparation, objects, hydrators, and actions unless
  the hypothesis requires changing them.
- Use `ai-processor-builder` for the workflow or agent processor.
- For an agent, keep tools deterministic and bounded.

### 4. Verify one example

- Run focused unit and pipeline tests.
- Run one exact published benchmark example.
- Confirm the structured result is present at the evaluation profile's receipt
  path.
- Fix pipeline and output-contract errors before evaluating more examples.

### 5. Run one-example eval

- Use one repetition, serial runtime, one worker, and stop on error.
- Record the resolved `agent_version_id` and `run_id` produced by the existing
  eval system.
- Inspect the example bundle if the output is invalid or incorrect.

### 6. Hand back to the FDE

Report:

- what changed;
- what stayed constant;
- the one-example result;
- the pipeline path and candidate agent-version ID; and
- the command for a wider eval.

Do not silently run a full benchmark, make another prompt change, or promote
the version.

## Spirax Reference Cleanup

Use the current implementations as examples rather than building new reference
code:

- `v1_3` is the one-shot structured AI workflow example.
- `v2` is the bounded progressive agent example.

For the reference cleanup:

1. Rewrite `docs/use_case/PipelineVersions.md` to describe only the current
   runnable variants, their parent relationship, and their short hypotheses.
2. Remove or clearly archive stale pipeline entries that no longer exist.
3. Confirm `README.md` points to `v1_3` and `v2` as examples, not mandatory
   stages for every project.
4. Confirm both variants still share the expected benchmark contract and final
   `act.metadata.agent_output` structure.
5. Confirm their existing agent policies resolve successfully.

Do not reorganize working processor code, rewrite prompts, or change tool
behavior solely to make the examples look more uniform.

## Implementation Steps

1. Add the concise first-agent/next-variant section to `pipeline-builder`.
2. Add minimal cross-links from `project-guide`, `benchmark-pipeline-port`, and
   `ai-processor-builder` where the handoff is currently unclear.
3. Clean up `docs/use_case/PipelineVersions.md` and README navigation for the
   current Spirax references.
4. Run the existing focused pipeline, evaluation-profile, and agent-version
   tests.
5. Mark the backlog item complete if the documented workflow can take a ported
   pipeline through a one-example eval without new product machinery.

## Verification

```bash
uv run python -m src.pipelines.pipeline_run_from_yaml --help
uv run python -m src.evals.eval_orchestration --help
uv run pytest tests/test_v1_3_runner.py tests/test_v2_progressive_agent.py
uv run pytest tests/test_evaluation_profile.py tests/test_agent_versions.py
```

Live model calls are not part of the default test suite. When credentials and
a published benchmark are available, exercise the workflow with one exact
example before a wider eval.

## Acceptance Criteria

- [x] Existing skills describe one clear path from a ported pipeline to a
  measurable first AI variant.
- [x] The workflow defines the structured output before prompt or tool work.
- [x] Deterministic, workflow, and agent shapes are supported without requiring
  all three.
- [x] A new variant preserves the working parent pipeline.
- [x] One-example pipeline and eval checks are the default validation path.
- [x] Spirax `v1_3` and `v2` are documented as simple reference examples.
- [x] Existing agent-version and eval identities preserve useful comparison
  points.
- [x] No new skill, CLI, manifest, runtime subsystem, catalog, or documentation
  hierarchy is introduced.
