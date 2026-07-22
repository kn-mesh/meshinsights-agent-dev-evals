# Human Eval Results Explorer

## Outcome

Complete the Agent Workbench MVP human-inspection experience with a locally
hosted, read-only application in which an FDE can select a retained evaluation
run, filter and inspect its attempts, review the exact model inputs and outputs
including tool activity, and view the same use-case evidence package that an
FDE or SME used in Benchmark Studio.

The application is a presentation and query layer over existing Agent
Workbench and published-benchmark contracts. It does not create another
evaluation representation, copy benchmark truth locally, or add a write path
to Benchmark Studio.

**Implementation status (July 22, 2026):** the local MVP is implemented. It
includes run selection, compact attempt filtering, evaluation/model/tool/raw
detail, verified frozen-evidence reconstruction, and the Spirax evidence view.
Richer comparison navigation and additional facet controls remain follow-up
work under the variant-comparison feature.

## Product Job

The primary job is:

```text
select an eval run
  -> understand aggregate quality and reliability
  -> find an incorrect, unstable, invalid, or failed attempt
  -> inspect the complete model execution
  -> inspect the complete human-review evidence package
  -> understand the difference between available evidence and consumed evidence
  -> carry exact example/run identities into the next agent iteration
```

Aggregate metrics alone are not sufficient. The FDE must be able to answer:

- What benchmark label and structured output were compared?
- What did the model initially receive?
- Which tools did an agent call, with which inputs and results?
- What raw, parsed, retried, and final output did the model produce?
- What complete normalized evidence was available to the human reviewer?
- Which parts of that evidence did the model consume directly or through tools?
- Which exact benchmark, source snapshot, agent, model, grader, and runtime
  produced the observation?

## Decisions

- Build a local browser application, not a notebook, static report, or terminal
  dashboard.
- Use a React and TypeScript single-page application built by Vite.
- Keep selected run, attempt, filter, and tab state in validated URL search
  parameters; use TanStack Query for remote state, caching, and progressive
  loading. The MVP does not need a routing framework.
- Use small project-owned CSS that follows the existing Benchmark Studio
  component conventions; avoid adopting a styling framework for this app.
- Use Plotly through `react-plotly.js` for the existing interactive evidence
  views and as one reusable visualization primitive.
- Use FastAPI, Pydantic, and Uvicorn as the only browser-facing data boundary.
- Serve the compiled Vite assets from FastAPI so the normal local experience is
  one Python process. Vite runs separately only during frontend development.
- Do not use TanStack Start, Nitro, SSR, Next.js, Electron, Tauri, or Streamlit.
- Do not add PostgreSQL or SQLite. Existing manifests, materialized views,
  indexes, and immutable Azure artifacts remain authoritative.
- Standardize the complete evaluation-review workflow and a reusable evidence
  component kit. Keep the evidence payload and final evidence composition
  use-case-owned and open-ended.
- Register one use-case adapter at build time. Each generated project represents
  one configured use case and does not need a dynamic plugin marketplace.
- Make the core-versus-use-case boundary visible in the filesystem. Reusable
  result querying, API routes, app shell, and UI primitives must not live under
  a project use-case package; project evidence code must not be added to a core
  package.
- Port the standalone evidence payload, renderer, and parity fixtures from
  Benchmark Studio during the initial evidence-pipeline port. Do not port its
  labeling workflow, routes, authorization, database repositories, or app shell.
- Keep Agent Workbench independently runnable. It must not import from or read
  the Benchmark Studio source checkout at runtime.

## Initial Benchmark Studio Parity Baseline

The first implementation targets the Spirax evidence experience from:

- repository: `https://github.com/Mesh-Systems-Eng/meshinsights-label-benchmark.git`;
- inspected revision: `ea40dec5b406bda62a5734c19f483cfae0481098`;
- backend view envelope:
  `api/label_benchmark/use_cases/spirax/evidence.py`;
- backend reviewer normalization:
  `api/label_benchmark/use_cases/spirax/pipeline/evidence_pipeline.py` and
  `api/label_benchmark/use_cases/spirax/pipeline/retriever.py`;
- frontend evidence contract and adapter:
  `www/src/lib/api/types.ts`, `www/src/use-cases/types.ts`, and
  `www/src/use-cases/spirax.tsx`;
- reusable chart implementation:
  `www/src/features/evidence/interactive-timeseries-chart.tsx`; and
- focused frontend tests:
  `www/tests/interactive-timeseries-chart.test.ts` and
  `www/tests/use-cases.test.ts`.

The source files above were clean at the inspected revision. Record the actual
source revision used when the port is implemented if it differs from this
planning baseline.

## Existing Agent Workbench Sources Of Truth

| Concern | Existing source |
|---|---|
| Run/version/comparison discovery | `src/lifecycle/` derived catalog |
| Exact run plan and identity | `<run-dir>/manifest.json` |
| Immutable attempt generations | `<run-dir>/attempts/` |
| Canonical schema-v3 result view | `<run-dir>/result.json` through verified result loading |
| Compact attempt inspection | `<run-dir>/review/index.json` and `src/evals/inspection.py` |
| Model messages, images, tools, transcripts, retries | `<run-dir>/review/` through `LocalReviewStore` |
| Run comparison | `src/evals/comparisons.py` and comparison JSON |
| Published benchmark membership and labels | Benchmark Studio published contract, read-only |
| Frozen source evidence | Azure artifacts referenced by published examples, size/hash verified |
| Use-case normalization | Project-owned retriever, hydrator, and deterministic evidence processors |

The explorer must load these contracts through their existing integrity-aware
APIs. The browser must never receive or select arbitrary filesystem paths.

## Architecture

```text
Browser
  React + TypeScript + TanStack Router/Query + Plotly
    |
    | localhost /api/*
    v
FastAPI application
  |-- lifecycle catalog query service
  |-- verified schema-v3 result query service
  |-- LocalReviewStore model-execution service
  |-- comparison query service
  `-- use-case evidence adapter
        |
        | exact benchmark/version/example/source snapshot
        v
      published benchmark repository + verified Azure artifacts
        |
        v
      ported normalization -> typed EvidenceView payload
```

The compiled frontend is served by FastAPI. A single command starts the local
server, binds only to `127.0.0.1`, and opens the default browser:

```text
uv run python -m src.apps.eval_explorer
```

During frontend development, Vite proxies `/api` to the local FastAPI port.
Node and pnpm are development/build requirements, not additional application
servers in the normal local runtime.

## Generic Versus Use-Case-Owned Behavior

### Layering Rule

The directory boundary is an architectural boundary:

- `agent-dev-eval-core/` owns use-case-neutral Python evaluation and inspection
  mechanics with no React or project evidence dependency.
- `agent-dev-eval-ui/` owns the reusable local FastAPI application, React app
  shell, API client, routes, model-execution views, and evidence component kit.
  It depends on `agent-dev-eval-core` contracts and accepts injected project
  adapters.
- root `src/` owns project evidence decoding, normalization, and the one thin
  application composition entry point.
- root `www/` owns only the thin Vite composition entry point and the active
  use-case React adapter/schema.

Imports flow inward toward generic contracts:

```text
root project composition
  |-- project Python evidence adapter
  |-- project React evidence adapter
  `-- agent-dev-eval-ui
        `-- agent-dev-eval-core
```

Neither core package may import `src.evidence`, root `www/src/use_case`, or a
named customer/use-case module. The root project may import core packages.
Crossing the boundary requires a typed adapter passed at composition time, not
a conditional import hidden inside core code.

Add architectural tests that fail if:

- `agent-dev-eval-core` or `agent-dev-eval-ui` imports a root project module;
- generic React code imports the active use-case implementation directly;
- project evidence decoding is duplicated under an app/API route; or
- a use-case adapter reaches into core package internals rather than its public
  contracts.

### Provided Out Of The Box

- local application startup, routing, layout, theme, and accessibility;
- run and comparison discovery through the lifecycle catalog;
- run summary covering accuracy, reliability, scoring coverage, performance,
  usage, retries, cost, and nondeterminism without changing denominators;
- attempt search, filters, facets, sorting, paging, and deep links;
- expected and actual structured outputs and field-level grader details;
- execution, output-contract, and scoring state presentation;
- prompts, model messages, output schema, raw/parsed output, validation history,
  retry history, and final decision presentation;
- chronological tool definitions, calls, inputs, results, errors, and correlated
  model turns;
- generic text, JSON, image, file, and object-reference viewers;
- repetition navigation and flaky-attempt presentation;
- comparison navigation and improved/regressed/disagreement drill-down;
- loading, unavailable, partial, failed, purged, and integrity-error states;
- safe lazy resolution of large run-local review objects; and
- reusable evidence UI primitives and focused test harnesses.

### Owned By Each Use-Case Project

- frozen-artifact decoding and domain normalization;
- derived evidence fields and evidence-cutoff behavior;
- a versioned evidence payload schema;
- the final React evidence-package composition;
- optional attempt-list columns and domain output formatting; and
- optional specialized artifact viewers where generic text, JSON, image, table,
  and time-series components are insufficient.

The project-specific work is not a second evidence implementation. It is the
same evidence behavior already created for Benchmark Studio and ported with the
working evidence pipeline. Agent Workbench adds the surrounding evaluation
experience once.

## Evidence Contract And Escape Hatch

Do not attempt to describe every use case with one universal chart YAML or one
closed set of evidence blocks. The stable contract is a small envelope around
an opaque, versioned, use-case-owned payload:

```ts
export interface EvidenceView<TPayload = unknown> {
  example: {
    example_id: string;
    unit_id: string;
    decision_timestamp: string;
    metadata: Record<string, unknown>;
  };
  window: {
    start: string;
    end: string;
    basis: string;
    [key: string]: unknown;
  };
  evidence: TPayload;
  metadata: {
    evidence_schema_version: string;
    evidence_recipe_id: string;
    source_snapshot_id: string;
    source_snapshot_content_sha256: string;
    source_kind: string;
    known_gaps: string[];
  };
}
```

Each project validates `evidence` with Zod and supplies a normal React
component. It may compose the workbench primitives or render arbitrary React
content:

```ts
export interface WorkbenchUseCaseAdapter<TPayload> {
  useCaseId: string;
  evidenceSchemaVersion: string;
  evidenceSchema: z.ZodType<TPayload>;
  EvidenceDisplay: React.ComponentType<{
    example: EvalExample;
    evidence: EvidenceView<TPayload>;
  }>;
  attemptColumns?: AttemptColumn[];
  formatOutputField?: (
    field: string,
    value: unknown,
  ) => React.ReactNode;
}
```

This is a compile-time extension point, not a restricted configuration system.
A time-series project can be implemented mostly from shared primitives; a map,
document, image, audio, diagram, or specialized industrial view can provide a
fully custom component without changing the explorer shell.

The first reusable component kit should include:

- `EvidenceLayout` and `EvidenceMetadata`;
- `ChartPanel`, `TimeseriesChart`, and linked-axis helpers;
- `MetricGrid` and `DataTable`;
- `EventTimeline`;
- `ImageGallery` and `DocumentViewer`;
- `StructuredData`;
- `EvidenceWarning` and unavailable/error states;
- `FullscreenPanel`; and
- safe artifact download/open actions.

## Backend Use-Case Boundary

The generic FastAPI service in `agent-dev-eval-ui` resolves the selected run,
exact published benchmark version, example, and raw-artifact manifest through
public services from `agent-dev-eval-core`. A project-owned adapter under root
`src/evidence/` decodes and normalizes the verified bytes into the use-case
payload:

```python
class WorkbenchEvidenceAdapter(Protocol):
    use_case_id: str
    evidence_schema_version: str

    def build_view(
        self,
        *,
        run: VerifiedRun,
        example: PublishedBenchmarkExample,
        artifacts: tuple[VerifiedArtifact, ...],
    ) -> EvidenceView:
        ...
```

The adapter must reuse the project pipeline's decoder and normalization logic;
it must not maintain a parallel transformation solely for the UI. For Spirax,
the published telemetry and alarm artifacts are verified and decoded through
the existing frozen-evidence path, then projected into the reviewer-facing
telemetry, delta, microphone, alarm-marker, coverage, and known-gap payload
used by the ported React component.

Each project contains one explicit adapter registration. Do not add dynamic
package discovery or a plugin installation subsystem for MVP.

The root application entry point is composition only:

```python
from agent_eval_ui import create_app
from src.evidence import PROJECT_EVIDENCE_ADAPTER

app = create_app(evidence_adapter=PROJECT_EVIDENCE_ADAPTER)
```

It must not contain run queries, result parsing, review-object resolution,
filtering, evidence transforms, or use-case visualization behavior.

## Evidence Reconstruction And Parity

The full human evidence package and the exact model inputs are separate views:

- **Evidence Package** reconstructs everything available to the Benchmark
  Studio reviewer from the frozen published source snapshot.
- **Agent Input** displays the exact initial messages, structured content,
  images, and files captured for the model.
- **Execution** displays subsequent tool calls/results and later model turns.

The UI should identify model-consumed artifacts that correspond to the full
evidence package when hashes or explicit references permit it, but it must not
infer equivalence from filenames or display labels.

Evidence reconstruction must:

1. load and integrity-check the selected schema-v3 run;
2. take benchmark key/version, example ID, and source-snapshot identity from
   that run rather than current defaults;
3. retrieve the matching published example read-only;
4. verify every required Azure artifact by byte size and SHA-256;
5. reject snapshot, cutoff, recipe, or artifact incompatibility;
6. normalize through the project-owned evidence path; and
7. return the typed evidence envelope to the use-case display.

Review capture is disposable, while the benchmark evidence remains immutable
in Azure. Purging `<run-dir>/review/` therefore makes prompts and transcripts
unavailable but does not prevent evidence reconstruction while the published
artifacts remain accessible.

For a historical run, record the evidence recipe and view schema/version used
by the agent version. If the current project adapter cannot claim compatibility
with that contract, fail explicitly rather than silently presenting a changed
view as historical parity.

Parity verification for the initial Spirax port must compare the same frozen
example in Benchmark Studio and Agent Workbench for:

- identity, decision cutoff, and evidence window;
- normalized telemetry rows and ordering;
- steam, condensate, delta, and microphone values;
- alarm groups and markers;
- gap behavior, coverage, units, labels, and chart series semantics; and
- a representative browser-rendered visual snapshot or Playwright assertion.

## Information Architecture

### Routes

```text
/?run=:runId&execution=:executionId&state=:state&search=:text&tab=:tab
```

The compiled SPA uses one local entry point. Selected run, attempt, state,
search, and active detail tab use URL search parameters so an FDE can copy a
deep link. Comparison routes can be added when the cross-run comparison UI is
built.

### Run Catalog

Show run ID, pipeline, agent version and promotion state, benchmark and version,
model, reasoning effort, scope, repetitions, completion, accuracy, reliability,
review state, comparison membership, and creation/update observations available
from managed records. Catalog integrity findings remain visible and affected
runs do not silently open as healthy.

### Run Overview

Keep accuracy, reliability, scoring coverage, and performance visually
separate. Show numerators and denominators. Include complete-evaluation and
field accuracy, expected-value and confidence views, slices, failures,
nondeterminism, stage timing, tokens, retries, and cost where available.

### Attempt Explorer

Support combined filters for:

- correct, incorrect, failed, invalid, unscored, flaky, and review unavailable;
- applicable field and field correctness;
- expected and actual scalar value;
- slice and confidence;
- unit ID, example ID, execution ID, and repetition; and
- review capture status.

Generalize the existing inspection projection into a typed query service used
by both the CLI and UI. Do not implement separate filter semantics in the
browser.

### Attempt Detail

The main detail workspace contains:

1. **Evaluation** -- expected/actual values, per-field graders, states, errors,
   timing, usage, cost, and exact identities.
2. **Evidence Package** -- the complete Benchmark Studio-equivalent review
   view reconstructed from frozen evidence.
3. **Agent Input** -- exact initial system/developer/user content, images,
   files, and output schema.
4. **Execution** -- chronological model turns, tool definitions, calls, inputs,
   results, errors, retries, validation history, raw outputs, and final parsed
   output.
5. **Raw** -- bounded structured JSON for debugging and copy/download actions.

Repeated attempts for one example remain adjacent. For a tool-using agent, a
tool-produced chart appears at its chronological position and may link to the
corresponding portion of the full evidence package when identity is explicit.

## API Surface

Initial read-only endpoints:

```text
GET /api/health
GET /api/runs
GET /api/runs/{run_id}
GET /api/runs/{run_id}/attempts
GET /api/runs/{run_id}/attempts/{execution_id}
GET /api/runs/{run_id}/examples/{example_id}/evidence
GET /api/comparisons
GET /api/comparisons/{comparison_id}
```

Every identifier resolves exactly once. Every result, review manifest, and
local object is verified before response. Artifact responses use allowlisted
media types, content-length limits, safe download names, and no arbitrary path
parameter. Azure credentials and signed URLs are never returned to the browser.

Use response pagination and bounded section resolution. Do not place complete
large run results, all prompts, or all evidence packages in the initial app
payload.

## Implemented Repository Layout

```text
# Reusable Python evaluation/inspection mechanics.
agent-dev-eval-core/
  evaluation/
    explorer.py

# Reusable local application. No named use-case imports.
agent-dev-eval-ui/
  pyproject.toml
  agent_eval_ui/
    app.py
  web/src/
    api.ts
    contracts.ts
    eval-explorer-app.tsx
    timeseries-chart.tsx

# Thin project composition and all use-case-specific Python behavior.
src/
  apps/
    eval_explorer.py
  evidence/
    __init__.py
    spirax.py

# Thin project frontend plus all use-case-specific React behavior.
www/
  package.json
  vite.config.ts
  src/
    main.tsx
    use_case/
      adapter.tsx
      evidence.schema.ts
      evidence.schema.test.ts
```

`agent-dev-eval-core` is the home for framework-independent evaluation and
inspection mechanics. `agent-dev-eval-ui` is a separate reusable application
package because browser/API dependencies and release cadence should not become
mandatory for headless evaluation users. `mi-core` remains the pipeline/runtime
framework and does not acquire evaluation-product UI concerns.

The root app and frontend are deliberately small composition surfaces. If a
second project needs a change under `agent-dev-eval-ui`, that change must be a
use-case-neutral product capability. If the behavior names domain fields,
artifact kinds, business rules, or a particular visual composition, it belongs
under root `src/evidence/` or `www/src/use_case/`.

### Ownership Examples

| Change | Location |
|---|---|
| Add an `incorrect` plus `flaky` combined filter | `agent-dev-eval-core/evaluation/explorer/` |
| Add a generic tool-call timeline panel | `agent-dev-eval-ui/web/src/` |
| Add a reusable synchronized time-series component | `agent-dev-eval-ui/web/src/timeseries-chart.tsx` |
| Decode a customer's Parquet columns | root `src/evidence/` |
| Compute a domain-specific temperature delta | root `src/evidence/` |
| Compose the Spirax temperature, delta, and microphone charts | root `www/src/use_case/` |
| Add a generic map primitive useful across projects | `agent-dev-eval-ui/src/components/evidence/` |
| Configure one project's map layers and semantics | root `www/src/use_case/` |
| Start the app with the active project adapter | root `src/apps/eval_explorer.py` and `www/src/main.tsx` |

## Local State, Caching, And Performance

- Do not add an application database.
- Use the lifecycle catalog for run/version/comparison discovery.
- Use the existing review index as the replaceable compact attempt projection.
- Cache bounded API responses in memory.
- An optional ignored `.workbench/ui-cache/` may store content-addressed,
  rebuildable normalized evidence or static response artifacts keyed by source
  snapshot hash, evidence recipe, and view schema version.
- A cache miss must never change run identity or evaluation results.
- Cache corruption is discarded and rebuilt after source verification.
- Lazy-load Plotly, evidence, model transcripts, images, and long text.
- The first run page should not download every example's evidence package.

## Security And Failure Behavior

- Bind to `127.0.0.1` by default; remote binding is outside MVP.
- The app is read-only and performs no Benchmark Studio or Azure writes.
- Reuse current secret redaction and review-object integrity checks.
- Do not expose credentials, authorization headers, SAS tokens, provider
  secrets, or avoidable local absolute paths through API payloads or browser
  errors.
- Preserve explicit `unavailable`, `partial`, `failed`, and `purged` states.
- Reject symlinks, path traversal, ambiguous run IDs, mismatched result/run
  identities, corrupt manifests, and changed content-addressed objects.
- Evidence-view failures do not mutate or invalidate the eval result; they are
  surfaced with the source snapshot and compatibility reason needed to debug.

## Template And Pipeline-Port Contract

The standard Agent Workbench template should provide:

- pinned `agent-dev-eval-core` and `agent-dev-eval-ui` dependencies containing
  the complete generic FastAPI/React explorer shell and component kit;
- a generic adapter contract and project-owned example adapter tests;
- one explicit Python and TypeScript project-adapter registration point; and
- build, development, test, and one-command launch scripts.

The Benchmark Studio pipeline-port workflow should be updated to bring across
or adapt only:

- frozen-artifact decoding and normalized reviewer evidence;
- evidence payload schema/version;
- the standalone use-case evidence React component;
- any genuinely use-case-specific visualization helper;
- focused backend/frontend fixtures and parity assertions; and
- source repository/revision and meaningful adaptation provenance.

It must continue to exclude Benchmark Studio workflow pages, labeling forms,
review queues, authentication, authorization, Postgres repositories, mutable
state, and publication behavior.

For common tables, time series, images, metrics, events, and documents, project
components should compose template primitives. For novel maps, diagrams,
audio, video, canvas, or other domain experiences, the adapter may render a
fully custom React component. No core change is required solely because a new
visual form appears.

## Implementation Sequence

1. Add generic attempt queries to `agent-dev-eval-core`.
2. Add the dependency-injected FastAPI app and React shell to
   `agent-dev-eval-ui`.
3. Compose existing lifecycle, result-integrity, and review readers in the
   project backend.
4. Reconstruct Spirax evidence from the selected run's exact immutable
   benchmark version and verified Blob artifacts.
5. Port the Benchmark Studio evidence schema and three interactive charts into
   the project-owned adapter.
6. Add focused Python/frontend tests, the launch entry point, runbook guidance,
   and `$port-eval-explorer-use-case`.
7. Validate formatting, Python types/tests, TypeScript, the production bundle,
   frontend tests, and a localhost browser smoke test.

Steps 1-7 are implemented. Cross-run comparison navigation remains in the
separate variant-comparison backlog item.

## Test Strategy

- Core query tests cover state/search/field/slice filtering, facets, paging,
  and bounds.
- API tests cover dependency delegation, missing-resource mapping, and SPA
  static serving without shadowing unknown API routes.
- Evidence tests cover delta normalization, zero microphone values, gaps,
  alarm groups, cutoff metadata, and snapshot provenance.
- Frontend tests reject unnormalized evidence payloads; strict TypeScript and
  the production build verify generic/project adapter compatibility.
- A local browser smoke test verifies the compiled landing page, run selector,
  URL-backed default state, and absence of console errors.
- Existing retriever and inspection suites continue to cover artifact hash and
  cutoff enforcement, review integrity, redaction, capture-off, and purge.

The July 22 live representative-example probe was attempted against
`spirax-pulse` / `phase-1-benchmark-3fb7f544` v1, but the hosted Azure Container
App query failed before returning the benchmark. Re-run that read-only parity
check when hosted-query access is healthy; it is the remaining environment
validation gap, not a local contract or build failure.

## MVP Acceptance

The local MVP is complete when an FDE can:

- launch the built explorer from the repository with one command;
- select any retained, valid schema-v3 eval run without navigating files;
- see exact run, benchmark, source, agent, model, grader, and runtime identity;
- inspect aggregate accuracy, reliability, coverage, performance, usage, and
  cost from the verified run summary;
- search attempts and filter by correctness, failure/contract/scoring state,
  flakiness, and review availability;
- inspect exact initial model inputs and all captured subsequent model turns;
- inspect tool definitions, calls, inputs, results, failures, and correlation;
- inspect raw, parsed, retried, and final structured output;
- view the complete use-case evidence package with the same semantic data,
  transforms, windows, gaps, markers, labels, and interactive views used in
  Benchmark Studio;
- distinguish complete human-review evidence from evidence actually consumed
  by the model;
- receive explicit and safe errors for missing, purged, incompatible, or
  corrupt review/evidence material; and
- complete the workflow without any write to Benchmark Studio or Azure.

The final diff for a newly ported use case should normally be confined to root
`src/evidence/`, root `www/src/use_case/`, project configuration/provenance,
and focused fixtures/tests. A routine use-case port that edits generic explorer
routes, model-execution views, or core query services fails this architecture
criterion unless it uncovered a genuinely reusable missing capability.

## Deferred Beyond This Feature

- editing labels or benchmark membership;
- publishing eval results to cloud storage;
- multi-project or multi-tenant browsing;
- remote hosting, authentication, and authorization;
- collaborative annotations or experiment journals beyond existing diagnosis
  artifacts;
- automatic agent-code changes or eval reruns from the browser;
- dynamic third-party UI plugins; and
- a universal declarative visualization language.
