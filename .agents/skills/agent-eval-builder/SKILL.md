---
name: agent-eval-builder
description: Build or update MeshInsights Agent Workbench published-benchmark evaluation orchestration for AI-enabled pipelines in this repo. Use when changing Azure PostgreSQL benchmark loading, immutable Azure Blob evidence, repeated-run execution, result contracts, scoring, or evaluation-results apps. Do not use merely to prepare, execute, or troubleshoot an existing use-case eval command; use run-use-case-evals for that.
---

# Agent Eval Builder

Use this skill for Agent Workbench evaluation work tied to published benchmarks
and AI pipeline receipts in this repository.

## Terminology And Sources Of Truth

Use the terminology established by MeshInsights Benchmark Studio and company AI
strategy:

- A **benchmark** is a customer-owned, versioned set of approved examples used
  to measure an agent.
- A **published benchmark version** is immutable evaluation truth in Azure
  PostgreSQL.
- A **benchmark example** is a decision about one `unit_id` at one
  `decision_timestamp`, identified by a stable `example_id`.
- A **raw source snapshot** is the immutable input captured for an example.
- **Raw artifacts** are the exact Parquet/NDJSON objects stored in Azure Blob
  Storage and frozen into benchmark publication with hashes.
- An **evidence view** is generated from raw inputs. It is not the benchmark and
  is not the source of label truth.

Do not call benchmarks “rubrics.” Do not introduce local benchmark JSON or
local evidence snapshots into active pipeline/eval execution.

## Current Repository Contracts

- `src/benchmarks/models.py` defines `BenchmarkVersion`, `BenchmarkExample`,
  and `SourceArtifact`.
- `src/benchmarks/postgres_repository.py` reads published benchmark versions
  from the Benchmark Studio Azure PostgreSQL schema.
- `src/storage/azure_blob.py` performs read-only, integrity-checked artifact
  downloads.
- `src/retrievers/azure_blob_evidence_retriever.py` decodes the raw Spirax
  artifacts into the pipeline evidence contract.
- `src/evals/eval_orchestration.py` owns repeated benchmark evaluation.
- `agent-dev-eval-core/evaluation` owns use-case-neutral execution, typed
  attempts, structured-output extraction, accuracy/reliability/performance
  aggregation, and immutable JSON writing.
- Root-level `eval_results/<pipeline>/` contains persisted evaluation evidence.

Do not reintroduce local rubric models or filesystem label truth. Keep benchmark
loading, use-case label semantics, and named metric views in `src/evals`; keep
the standalone evaluation package independent of `src` and Spirax-specific
models.

## Hosted Inputs

The operator CLI uses `APP_PROJECT_KEY` plus Azure CLI authentication. It runs
read-only benchmark queries through the deployed Benchmark Studio Container App
and loads Blob configuration from that hosted environment.

Direct repository or programmatic execution may instead require:

- `DATABASE_URL` for the Benchmark Studio Azure PostgreSQL database;
- `AZURE_STORAGE_CONNECTION_STRING`;
- `AZURE_STORAGE_CONTAINER`.

Use read-only identities. Never commit credentials. There is no local database
or filesystem fallback in the active benchmark/evidence path.

## Required Evaluation Flow

1. Require an explicit `benchmark_key`.
2. Resolve an explicit version number or the latest published version for that
   key and configured project.
3. Load frozen examples and only the label fields configured in
   `use_case_configs.eval_label_fields`.
4. Select work by `example_id`, `unit_id`, or approved classification.
5. For every attempt, construct `BenchmarkExamplePipelineMetadata` from the
   frozen example and raw artifact manifest.
6. Download Blob artifacts and enforce frozen byte size and SHA-256 before
   decoding them.
7. Run the pipeline and read actual labels from act-stage receipt metadata.
8. Compare actual values to `approved_labels` from the published version.
9. Persist benchmark identity and `source_snapshot_id` in results so every run
   is reproducible.

Prefer `RepeatedEvalExecutor` for repeated serial, threaded, and process runs.
Prefer `StructuredOutputSpec`, `extract_structured_outputs`, and
`validate_metadata_identity` for final output parsing and receipt validation.

## Receipt Contract

The act receipt must include:

- `example_id`
- `benchmark_key`
- `benchmark_version_id`
- `benchmark_version_number`
- `source_snapshot_id`
- `classification`
- `root_cause`

The retrieve receipt should additionally record the frozen source snapshot
content hash and evidence row count.

## Eval JSON Contract

Keep these top-level keys in order:

1. `summary`
2. `run_config`
3. `selected_example_ids`
4. `results`

`run_config` must include:

- project, benchmark key, version ID, version number, and source-state hash;
- `benchmark_source: azure_postgres`;
- `evidence_source: azure_blob`;
- pipeline/model/runtime configuration;
- `runs_per_example` and completion timestamp.

Each result must include `example_id`, `unit_id`, `decision_timestamp`,
`source_snapshot_id`, expected labels, repeated runs, and per-label correctness.
Write result evidence below `eval_results/<pipeline>/`; never place generated
results below `src/`.

Persist effective AI timeout and transport-attempt policies in `run_config`.
For failed runs, preserve stage and pipeline correlation IDs plus a bounded,
structured exception chain. Classify connection/network failures separately from
provider responses, timeouts, pipeline errors, and receipt-contract failures.
Remember that `transport_retries` is the total number of HTTP attempts,
including the initial request.

## Operator Commands

Do not maintain eval command templates in this builder skill. Read the root
`EvalRunbook.md` and use `$run-use-case-evals` for preparing, executing, or
troubleshooting real use-case eval runs. Keep this skill focused on changing
orchestration and result contracts.

## Tests

At minimum test:

- exact/latest published-version selection;
- project and benchmark scoping in PostgreSQL queries;
- evaluation-label filtering via `eval_label_fields`;
- example selection and missing IDs;
- Blob artifact byte-size and checksum enforcement;
- Parquet/NDJSON decoding and decision-timestamp cutoff enforcement;
- repeated result scoring and benchmark identity in output;
- YAML component registration and receipt handoff.

Use injected repositories and Blob clients for deterministic tests. A live
Azure smoke check is useful when credentials are available, but must not be a
required unit test.
