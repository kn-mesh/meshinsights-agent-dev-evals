# Evaluation Workflow Simplification Plan

## Status

Implemented and validated on 2026-07-23. The supported scope/runtime/resume
surface, model/pricing configuration, token and cost summaries, operator docs,
and skills are in place. A live 70-example Terra/low run completed with all
attempts valid and scored.

## FDE Outcome

An FDE can select the intended published benchmark units, run an explicit agent
and model configuration through one understandable execution path, resume
missing work after interruption, and receive the accuracy, reliability, token,
and cost information needed for the next agent decision.

## Current State

The current path in `src/evals/eval_orchestration.py`,
`src/evals/run_store.py`, `src/evals/evaluation_profile.py`, and
`agent-dev-eval-core/evaluation/` already supports the core job, but also
exposes:

- serial, threaded, and process runtimes;
- example, unit, label-filter, arbitrary predicate, and slice concepts;
- several resume and selective failure-rerun modes;
- materialization-only operations;
- comparison orchestration;
- invocation and performance schemas; and
- a broad set of identity and recovery invariants.

`model_catalog.py` already supports versioned input, output, cached-input, and
reasoning token rates. The eval runner already snapshots pricing and estimates
cost, but the model configuration experience does not collect or maintain
pricing and the aggregate cost result lacks the decided per-unit percentile
statistics.

## Protected MVP Workflow

The supported workflow is:

1. choose the published benchmark and version;
2. choose the agent candidate;
3. choose the model and reasoning configuration;
4. select all units, an explicit unit list, or one or more named use-case
   sections;
5. execute with bounded threaded concurrency;
6. write each completed unit durably;
7. resume only missing units when the same run is interrupted; and
8. review the completed result through Codex or the local app.

Comparison is downstream review of completed evals. It is not a required phase
inside execution.

## Feature 1: Model Configuration And Pricing

Use the Workbench-owned reusable pricing catalog and project model-selection
workflow to:

- lists configured provider/model identifiers;
- creates or edits a selectable model;
- reference a reusable billing identity from each selected model;
- capture currency, pricing version, effective date, source, and input/output
  rates in `model_pricing.yaml`;
- optionally capture cached-input and reasoning-token prices there;
- validates non-negative rates;
- keep `models.yaml` limited to project selection, API family, and pricing keys;
- displays configured prices when the model is selected for an eval; and
- freezes the selected pricing snapshot into the run identity and result.

Do not fetch or silently refresh current vendor prices during an eval. Historical
cost estimates must continue to use the snapshot selected for that run.

## Feature 2: Three Explicit Scope Choices

Make the normal scope selector present only:

- full benchmark;
- explicit unit/example list; and
- named use-case sections declared in the evaluation profile.

Use-case sections may be implemented by the existing profile predicate
mechanics, but the FDE should select a named section such as `Open Failure`, not
construct an arbitrary predicate.

Keep conditional field applicability internal to scoring. Do not remove the
predicate evaluator if configured profiles require it.

## Feature 3: One Normal Runtime

- Make bounded threaded execution the default and normal path.
- Keep serial execution as an explicit debugging option.
- Hide or mark process execution unsupported in operator help and skills.
- Remove process-specific implementation only when tests show it is isolated
  and removal is lower risk than leaving it dormant.

Do not add another concurrency backend.

## Feature 4: Simple Interruption And Resume

Persist each completed attempt before scheduling or awaiting the full run to
finish. When an invocation exits early because of `Ctrl-C`, terminal or machine
shutdown, or another process-level interruption:

- leave the run visibly incomplete;
- preserve completed units;
- print the exact resume command or parameters; and
- rerun only missing units for the same immutable run identity.

The supported resume promise is `missing` only. Failed unit results remain
inspectable results; selective failed-generation reruns are not part of the
normal MVP workflow.

Deleted runs cannot be resumed.

## Feature 5: Required Token And Cost Summary

For every completed or partial run, report:

- total input tokens;
- total output tokens;
- total tokens;
- cached-input and reasoning tokens when available;
- total actual or estimated cost by currency;
- average cost per completed unit;
- P5 cost per completed unit;
- P95 cost per completed unit;
- units with complete cost observations;
- units with partial pricing; and
- units without usable cost information.

Percentiles must be calculated from per-unit cost observations, not from
aggregate token totals. Preserve whether a cost is provider-reported,
completely estimated, partially estimated, or unavailable.

Detailed speed and latency summaries are disposable working data and are not
part of the retained-result contract.

## Feature 6: Reduce The Supported Command Surface

Classify current options into:

- **supported:** benchmark/version, agent, model/reasoning, full/list/named
  section scope, threaded execution, serial debugging, bounded concurrency,
  repetitions when explicitly required, missing-only resume, and review
  capture;
- **internal compatibility:** conditional predicates, deterministic identities,
  atomic unit persistence, result materialization needed by the supported path;
  and
- **unsupported or maintenance-only:** process runtime, arbitrary label-filter
  construction, selective failure generations, materialization-only commands,
  generalized rerun policies, and comparison as a runner phase.

First remove unsupported concepts from help text, interactive prompts, docs,
and skills. Delete implementation only after proving that no supported path or
retained artifact depends on it.

## Agent Skill Deliverables

### Update `run-use-case-evals`

Make it the authoritative operational skill for:

- selecting all, explicit units, or named sections;
- choosing threaded or serial-debug execution;
- configuring bounded concurrency;
- recognizing interruption;
- resuming missing units;
- reading accuracy, reliability, token, and cost summaries; and
- handing completed results to the review or analysis workflow.

Remove the requirement to understand advanced runtime, rerun, materialization,
or predicate flags. Keep use-case defaults project-owned so the skill can be
rewritten cleanly when Spirax is replaced.

### Update `external-runtime-setup`

Add model-catalog and pricing setup, validation, and troubleshooting. Keep
provider credentials separate from non-secret model pricing.

### Update `agent-eval-builder`

Replace current compatibility detail with the protected workflow after the code
changes. Preserve its gate against adding new execution or recovery modes.

### Update `project-guide`

Route model pricing and operational eval questions to the correct skills and
enforce approval before any reusable eval implementation change.

## Validation

- Full benchmark, explicit list, and named-section selection tests.
- Threaded default and serial-debug tests.
- `Ctrl-C` or simulated process interruption followed by missing-only resume.
- Stable run identity across resume.
- Pricing validation and frozen snapshot tests.
- Actual, estimated, partially estimated, and unavailable cost cases.
- P5, P95, average, and total cost tests over representative unit counts.
- CLI/help tests proving unsupported concepts are absent from the normal path.
- Spirax smoke and full-scope compatibility tests.

## Non-Goals

- failure-specific rerun generations;
- process-pool execution;
- arbitrary operator-authored predicate expressions;
- cost forecasting before execution;
- dynamic vendor-price lookup;
- performance benchmarking as a retained result;
- comparison orchestration inside the eval runner; and
- new storage or lifecycle machinery.

## Completion Criteria

An FDE can describe the supported eval workflow without learning internal
execution or persistence abstractions, and every supported command produces a
durable result with correct benchmark identity, grading, token usage, and the
decided cost statistics.
