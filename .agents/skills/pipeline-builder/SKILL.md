---
name: pipeline-builder
description: Build or evolve stage-based use-case pipelines in this repo. Use for retrievers, hydrators, process or action objects, pipeline YAML, exact-example runners, receipt contracts, processor variants, matching agent policies, or progression from deterministic logic to optional AI and eval support.
---

# Pipeline Builder

Build the next measurable pipeline stage while preserving current coherent
project contracts. Use `$benchmark-pipeline-port` for an initial Studio port,
`$ai-processor-builder` for AI implementation, `$run-use-case-evals` for
execution, and `$agent-eval-builder` for eval contract changes.

## Boundaries

- Read `docs/use_case/`, current pipeline configs, objects, receipts, runners,
  and focused tests before editing.
- Keep use-case rules in manifest-declared reference paths. Reuse `mi.core`,
  `mi.ai`, and existing helpers.
- If the request explicitly authorizes the named reusable scope, proceed after
  stating its ownership and focused tests. Otherwise, identify the exact
  reusable paths/contracts and pause once for approval.
- Use `$external-runtime-setup` for provider auth, telemetry, model catalogs, or
  runtime compatibility. Do not reproduce those details here.

## Core Contracts

Design receipt-first: keep intermediate data on typed process artifacts and
place the compact, serializable business outcome in act-stage
`PipelineReceipt` metadata.

Organize variant-specific processors under `src/processors/<variant>/` and
shared processors under `src/processors/common/`. Reuse objects and hydrators
when the variant hypothesis does not require changing them.

Every evaluable `pipeline_configs/<stem>.ppln` needs a matching
`agent_version_configs/<stem>.agent.yaml`. Components own declarations for
their behavior-bearing assets and contracts through `version_assets()` and
`version_contracts()`. The policy supplements that graph with:

- `source_pipeline` and `model_policy`;
- top-level structured input/output, action-policy, and evidence-recipe
  contracts;
- `additional_assets` only for behavior-bearing files no component declares;
  and
- `non_execution_exclusions`.

Candidate resolution must discover component source and schemas, merge both
declaration sources, and prove the complete graph was captured.

## Ordered Workflow

1. **Inspect evidence.** Resolve one exact published benchmark version and
   example, verify frozen artifact identities and hashes, and inspect the
   normalized evidence required by the decision.
2. **Build the deterministic control path.** Add or update the retriever,
   retrieve-to-process hydrator, typed process and action objects, processor,
   process-to-action/finalize hydrators, terminal action, `.ppln`, and matching
   agent policy.
3. **Make YAML runnable.** Keep YAML limited to class wiring, constructor
   arguments, and a `benchmark_contract` declaring the published schema,
   evidence recipe, source snapshot contract, and required artifact kinds.
   Inject exact benchmark/example metadata at runtime; never store secrets.
   Inspect current `pipeline_configs/` and `mi-core` pipeline docs for syntax
   rather than copying a generic example.
4. **Validate one exact example.** The runner owns only unit-level execution.
   `run_pipeline(...)` receives the exact `BenchmarkVersion` and
   `BenchmarkExample`, verifies raw artifacts before decoding, and returns a
   receipt containing the final determination.
5. **Add AI only when justified.** Choose a one-shot workflow when prepared
   evidence is sufficient and a bounded tool-using agent only when runtime
   investigation materially helps. Keep the handoff stable:
   process artifact → action decision → act-stage receipt metadata.
6. **Resolve the candidate.** Report immutable identity without promotion:

   ```bash
   uv run python -m src.agent_versions.cli --json resolve \
     --pipeline pipeline_configs/<variant>.ppln \
     --agent-policy agent_version_configs/<variant>.agent.yaml \
     --dirty-policy capture
   ```

7. **Evaluate only the requested scope.** Once the exact pipeline run passes,
   use `$run-use-case-evals`. Do not create a one-example eval occurrence as a
   development prerequisite or silently run a broad eval.

Require explicit benchmark version and example identity for recorded
validation and handoff; permit latest-version resolution only for interactive discovery.
Never record an omitted version as the validation command.

## Runner And YAML Rules

- Let the benchmark-aware runner validate and remove `benchmark_contract`
  before calling `PipelineBuilder`.
- Apply temporary `--ai-model` or `--ai-reasoning-effort` overrides only to AI
  entries; never rewrite source YAML.
- Keep benchmark-wide selection, batching, repetition, concurrency, resume, and
  aggregation in eval orchestration.
- Do not add execution modes, persistence, identity, recovery, or artifact
  lifecycle machinery without a demonstrated FDE need.

## Adding An Artifact

1. Add typed process-object accessors.
2. Give the artifact one clear producer that validates its inputs.
3. Update declared consumers and the action/receipt handoff when relevant.
4. Add focused tests and inspectability.
5. Re-evaluate only if the artifact can change measured behavior.

## Acceptance Checks

Select every changed layer from the
[repository verification matrix](../project-guide/references/verification-matrix.md).

- Frozen source evidence is verified before decoding.
- The `.ppln` and agent policy match and build through the real registry.
- The final outcome reaches stable receipt metadata.
- Deterministic logic was preferred; any AI or agent complexity is justified.
- Focused tests and one exact, explicitly versioned pipeline example pass.
- The report states the hypothesis, changed and held-constant dimensions,
  pipeline/policy paths, example identity, candidate `agent_version_id`, and
  requested eval command or `run_id`.
