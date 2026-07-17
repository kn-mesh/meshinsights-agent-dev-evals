# Pulse alarm failure analysis v1_3

This pipeline ports the Spirax Pulse `v1_3` alarm classifier into the current unit/decision-timestamp architecture. It is an agent-development baseline: its evidence, agent behavior, output contract, and runtime settings are explicit and independently testable.

## Runtime contract

- `unit`: durable installation/example identity.
- `sensor_id`: Pulse sensor identifier used for retrieval.
- `decision_timestamp`: as-of timestamp used to select the latest eligible FDE alarm.
- Evidence: up to 365 days of inlet/steam and outlet/condensate temperatures ending at the selected alarm.
- Output: `classification` and `root_cause`, recorded in act-stage receipt metadata with the unit, sensor, decision timestamp, alarm timestamp, installation type, and evidence point count.

The Mongo retriever uses `mongodb_username`, `mongodb_password`, `mongodb_host`, and `mongo_database`. Snapshot modes (`use`, `refresh`, and `strict`) support reproducible evidence packages without changing the pipeline contract.

## Agent composition

- The base prompt keeps the task, evidence boundary, and output rules always available.
- The `temperature-evidence-inspection` toolset provides deterministic numeric summaries and at most two targeted zoom charts.
- The deferred `sensor-integrity-review` capability is available for suspected label reversal or instrumentation changes.
- The deferred `steam-trap-failure-diagnosis` skill contains the detailed domain runbook.

The default model request has bounded turns, retries, and timeouts. Input, output, and total token limits remain unset, which is the `mi.ai` unlimited default.

## Run

```bash
uv run python -m src.pipelines.pipeline_run_from_yaml \
  pipeline_configs/v1_3.ppln \
  --unit trap-250003575 \
  --sensor-id 250003575 \
  --decision-timestamp 2026-03-17T23:59:59 \
  --ai-model azure:gpt-5-mini
```

For a deterministic snapshot-backed run:

```bash
uv run python -m src.pipelines.pipeline_run_from_yaml \
  pipeline_configs/v1_3.ppln \
  --unit trap-250003575 \
  --sensor-id 250003575 \
  --decision-timestamp 2026-03-17T23:59:59 \
  --retrieval-snapshot-mode strict \
  --retrieval-snapshot-dir data/local_eval_snapshots
```

The source pipeline YAML is never rewritten for runtime overrides. The runner creates and removes an ephemeral configuration containing the example metadata and optional model/snapshot overrides.

