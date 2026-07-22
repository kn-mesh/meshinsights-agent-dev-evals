# Spirax Pulse Steam-Trap Failure Analysis

This Agent Workbench project evaluates agents that classify a selected Pulse
steam-trap alarm and, when applicable, identify its root cause using only the
evidence available at the alarm decision timestamp.

- Benchmark Studio project: `spirax-pulse`
- Published benchmark: `steam-trap-regression`
- Unit identity: numeric Pulse sensor ID, carried generically as `unit_id`
- Evidence recipe: `spirax-steam-trap-evidence@v2`
- Frozen artifacts: telemetry Parquet and alarm NDJSON objects in Azure Blob
  Storage, verified by byte size and SHA-256 before decoding
- Evaluation labels: `classification` and `root_cause`

See `UseCase-V2.md`, `PipelineVersions.md`, and `MongoDbSchema.md` in this
directory for the detailed domain and pipeline context.
