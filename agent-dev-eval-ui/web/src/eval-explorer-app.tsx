import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import type {
  AccuracyMetric,
  AttemptRow,
  BenchmarkContext,
  EvidenceView,
  RunEntry,
  SourceVerificationSchema,
  UseCaseAdapter,
} from "./contracts";

type RunPayload = { runs: RunEntry[]; findings: unknown[] };
type AttemptsPayload = {
  rows: AttemptRow[];
  matched: number;
  facets: { states: Record<string, number>; fields: string[]; slices: string[] };
};
type AttemptPayload = {
  row: AttemptRow;
  review: Record<string, unknown> | null;
  benchmark_context: BenchmarkContext;
};

const pageSize = 100;
const reviewTabs = ["evaluation", "evidence", "execution"] as const;
const defaultRunSort = "newest";

const states = [
  "all",
  "correct",
  "incorrect",
  "failed",
  "invalid",
  "flaky",
  "unscored",
  "review-unavailable",
];

export function EvalExplorerApp({ adapter }: { adapter: UseCaseAdapter }) {
  const EvidenceDisplay = adapter.EvidenceDisplay;
  const initial = new URL(window.location.href).searchParams;
  const [runId, setRunId] = useState(initial.get("run") ?? "");
  const [executionId, setExecutionId] = useState(initial.get("execution") ?? "");
  const [state, setState] = useState(states.includes(initial.get("state") ?? "") ? initial.get("state")! : "all");
  const [search, setSearch] = useState(initial.get("search") ?? "");
  const [field, setField] = useState(initial.get("field") ?? "");
  const [sliceKey, setSliceKey] = useState(initial.get("slice") ?? "");
  const [offset, setOffset] = useState(parseOffset(initial.get("offset")));
  const [modelFilter, setModelFilter] = useState(initial.get("model") ?? "");
  const [reasoningFilter, setReasoningFilter] = useState(initial.get("reasoning") ?? "");
  const [runSearch, setRunSearch] = useState(initial.get("q") ?? "");
  const [runSort, setRunSort] = useState(initial.get("sort") ?? defaultRunSort);
  const initialTab = initial.get("tab");
  const [tab, setTab] = useState(
    reviewTabs.includes(initialTab as (typeof reviewTabs)[number]) ? initialTab! : "evaluation",
  );

  useEffect(() => {
    const url = new URL(window.location.href);
    const detailState = runId ? {
      run: runId,
      execution: executionId,
      state: state === "all" ? "" : state,
      search,
      field,
      slice: sliceKey,
      offset: offset > 0 ? String(offset) : "",
      tab: tab === "evaluation" ? "" : tab,
    } : {
      run: "",
      execution: "",
      state: "",
      search: "",
      field: "",
      slice: "",
      offset: "",
      tab: "",
    };
    for (const [key, value] of Object.entries({
      ...detailState,
      model: modelFilter,
      reasoning: reasoningFilter,
      q: runSearch,
      sort: runSort === defaultRunSort ? "" : runSort,
    })) {
      if (value) url.searchParams.set(key, String(value));
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", url);
  }, [runId, executionId, state, search, field, sliceKey, offset, tab, modelFilter, reasoningFilter, runSearch, runSort]);

  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<RunPayload>("/runs") });
  const attempts = useQuery({
    queryKey: ["attempts", runId, state, search, field, sliceKey, offset],
    queryFn: () => api<AttemptsPayload>(
      attemptsPath({ runId, state, search, field, sliceKey, offset }),
    ),
    enabled: Boolean(runId),
  });
  const detail = useQuery({
    queryKey: ["attempt", runId, executionId],
    queryFn: () => api<AttemptPayload>(
      `/runs/${encodeURIComponent(runId)}/attempts/${encodeURIComponent(executionId)}`,
    ),
    enabled: Boolean(runId && executionId),
  });
  const evidence = useQuery({
    queryKey: ["evidence", runId, detail.data?.row.example_id],
    queryFn: () => api<EvidenceView>(
      `/runs/${encodeURIComponent(runId)}/examples/${encodeURIComponent(detail.data!.row.example_id)}/evidence`,
    ),
    enabled: Boolean(runId && detail.data?.row.example_id && tab === "evidence"),
    staleTime: Infinity,
  });
  const selectedRun = useMemo(
    () => runs.data?.runs.find((item) => item.run_id === runId),
    [runs.data, runId],
  );
  const selectRun = (selectedRunId: string) => {
    setRunId(selectedRunId);
    setExecutionId("");
    setOffset(0);
  };
  const showOverview = () => {
    setRunId("");
    setExecutionId("");
    setOffset(0);
  };
  useEffect(() => {
    if (!attempts.data) return;
    const maximum = attempts.data.matched > 0
      ? Math.floor((attempts.data.matched - 1) / pageSize) * pageSize
      : 0;
    if (offset > maximum) setOffset(maximum);
    if (field && !attempts.data.facets.fields.includes(field)) setField("");
    if (sliceKey && !attempts.data.facets.slices.includes(sliceKey)) setSliceKey("");
  }, [attempts.data, field, offset, sliceKey]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">MI</div>
          <div>
            <div className="brand-name">MeshInsights</div>
            <div className="brand-product">Agent Workbench</div>
          </div>
        </div>
        <div className="header-context">
          <div className="eyebrow">Spirax Pulse / Evaluation</div>
          <h1>{runId ? "Run analysis" : "Evaluation results"}</h1>
        </div>
      </header>

      {runs.error ? <QueryError error={runs.error} /> : null}
      {!runId && runs.data ? (
        <ResultsOverview
          adapter={adapter}
          runs={runs.data.runs}
          modelFilter={modelFilter}
          reasoningFilter={reasoningFilter}
          search={runSearch}
          sort={runSort}
          onModelFilter={setModelFilter}
          onReasoningFilter={setReasoningFilter}
          onSearch={setRunSearch}
          onSort={setRunSort}
          onSelectRun={selectRun}
        />
      ) : null}

      {runId ? (
        <>
          <nav className="run-navigation" aria-label="Run navigation">
            <button type="button" aria-label="Back to evaluation results" onClick={showOverview}>
              <span aria-hidden="true">←</span>
              <span>Back to evaluation results</span>
            </button>
            <span className="run-navigation-current">Run details · {shortRunId(runId)}</span>
          </nav>
          <section className="run-bar">
            <RunFact label="Benchmark" value={`${selectedRun?.benchmark_key ?? "Unknown"} v${selectedRun?.benchmark_version ?? "—"}`} />
            <RunFact label="Model" value={selectedRun?.model ?? "Unknown"} />
            <RunFact label="Reasoning" value={selectedRun?.reasoning_effort ?? "—"} />
            <RunFact label="Attempts" value={`${selectedRun?.recorded_attempts ?? 0}/${selectedRun?.planned_attempts ?? 0}`} />
            <RunFact label="Review" value={selectedRun?.review_status ?? "Unknown"} />
          </section>
          {selectedRun?.accuracy ? (
            <RunAccuracySummary
              run={selectedRun}
              fieldLabels={adapter.evaluationFieldLabels}
            />
          ) : null}

          <main className="explorer-workspace">
            <aside className="attempt-sidebar">
              <div className="filters">
                <input
                  aria-label="Search attempts"
                  placeholder="Search example, unit, output…"
                  value={search}
                  onChange={(event) => {
                    setSearch(event.target.value);
                    setOffset(0);
                  }}
                />
                <select aria-label="Attempt state" value={state} onChange={(event) => {
                  setState(event.target.value);
                  setOffset(0);
                }}>
                  {states.map((item) => (
                    <option key={item} value={item}>
                      {item} ({attempts.data?.facets.states[item] ?? 0})
                    </option>
                  ))}
                </select>
                <select aria-label="Evaluation field" value={field} onChange={(event) => {
                  setField(event.target.value);
                  setOffset(0);
                }}>
                  <option value="">All fields</option>
                  {attempts.data?.facets.fields.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <select aria-label="Evaluation slice" value={sliceKey} onChange={(event) => {
                  setSliceKey(event.target.value);
                  setOffset(0);
                }}>
                  <option value="">All slices</option>
                  {attempts.data?.facets.slices.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
              {attempts.error ? <QueryError error={attempts.error} compact /> : null}
              <div className="attempt-count">
                <span>{attempts.data?.matched ?? 0} matching attempts</span>
                {attempts.data ? <span>{pageRange(attempts.data, offset)}</span> : null}
              </div>
              <div className="attempt-list">
                {attempts.data?.rows.map((row) => (
                  <button
                    className={row.execution_id === executionId ? "attempt active" : "attempt"}
                    key={row.execution_id}
                    onClick={() => setExecutionId(row.execution_id)}
                  >
                    <div className="attempt-title">
                      <span>{row.unit_id}</span>
                      <Status row={row} />
                    </div>
                    <small>{row.example_id} · repetition {row.run_index}</small>
                    <div className="output-line">AI output · {summarizeOutput(row.agent_output)}</div>
                  </button>
                ))}
              </div>
              <div className="pagination">
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Previous attempts"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                >Previous</Button>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Next attempts"
                  disabled={!attempts.data || offset + attempts.data.rows.length >= attempts.data.matched}
                  onClick={() => setOffset(offset + pageSize)}
                >Next</Button>
              </div>
            </aside>

            <article className="attempt-detail">
              {!executionId ? <div className="empty">Select an attempt to inspect.</div> : null}
              {detail.error ? <QueryError error={detail.error} /> : null}
              {detail.data ? (
                <>
                  <div className="detail-heading">
                    <div>
                      <div className="eyebrow">{detail.data.row.example_id}</div>
                      <h2>{detail.data.row.unit_id} · repetition {detail.data.row.run_index}</h2>
                    </div>
                    <Status row={detail.data.row} />
                  </div>
                  <nav className="tabs">
                    {[
                      ["evaluation", "AI output"],
                      ["evidence", "Evidence package"],
                      ["execution", "Execution details"],
                    ].map(([key, label]) => (
                      <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>
                    ))}
                  </nav>
                  {tab === "evaluation" ? (
                    <Evaluation
                      row={detail.data.row}
                      benchmarkContext={detail.data.benchmark_context}
                      adapter={adapter}
                    />
                  ) : null}
                  {tab === "evidence" ? (
                    evidence.isPending ? <div className="empty">Loading and verifying frozen evidence…</div> :
                    evidence.error ? <QueryError error={evidence.error} /> :
                    evidence.data ? <EvidenceDisplay evidence={evidence.data} /> : null
                  ) : null}
                  {tab === "execution" ? <Execution review={detail.data.review} row={detail.data.row} /> : null}
                </>
              ) : null}
            </article>
          </main>
        </>
      ) : null}
    </div>
  );
}

type MetricColumn = {
  key: string;
  label: string;
  get: (run: RunEntry) => AccuracyMetric | null;
};

type RunSortOption = {
  value: string;
  label: string;
};

function ResultsOverview({
  adapter,
  runs,
  modelFilter,
  reasoningFilter,
  search,
  sort,
  onModelFilter,
  onReasoningFilter,
  onSearch,
  onSort,
  onSelectRun,
}: {
  adapter: UseCaseAdapter;
  runs: RunEntry[];
  modelFilter: string;
  reasoningFilter: string;
  search: string;
  sort: string;
  onModelFilter: (value: string) => void;
  onReasoningFilter: (value: string) => void;
  onSearch: (value: string) => void;
  onSort: (value: string) => void;
  onSelectRun: (runId: string) => void;
}) {
  const models = uniqueValues(runs.map((run) => run.model));
  const reasoningEfforts = uniqueValues(runs.map((run) => run.reasoning_effort));
  const metricColumns = buildMetricColumns(runs, adapter.evaluationFieldLabels);
  const sortOptions = buildRunSortOptions(metricColumns);
  const activeSort = sortOptions.some((option) => option.value === sort) ? sort : defaultRunSort;
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const filteredRuns = sortRuns(runs
    .filter((run) => !modelFilter || run.model === modelFilter)
    .filter((run) => !reasoningFilter || run.reasoning_effort === reasoningFilter)
    .filter((run) => !normalizedSearch || runSearchText(run).includes(normalizedSearch)), activeSort, metricColumns);
  const controlsChanged = Boolean(modelFilter || reasoningFilter || search || activeSort !== defaultRunSort);

  return (
    <main className="results-overview">
      <section className="overview-heading">
        <div>
          <div className="eyebrow">Published evaluation runs</div>
          <h2>Overall evaluation results</h2>
          <p>Compare accuracy across retained runs, then open a run to investigate individual attempts and evidence.</p>
        </div>
        <div className="overview-run-count">
          <strong>{filteredRuns.length}</strong>
          <span>{filteredRuns.length === 1 ? "run shown" : "runs shown"}</span>
        </div>
      </section>

      <section className="run-results-panel">
        <div className="run-results-heading">
          <div>
            <h3>Results by run</h3>
            <p>Select any row to inspect its attempts and retained evidence.</p>
          </div>
        </div>
        <section className="overview-filters" aria-label="Evaluation result table controls">
          <label className="run-search-control">
            <span>Search runs</span>
            <input
              type="search"
              aria-label="Search evaluation runs"
              placeholder="Run ID, model, benchmark, pipeline…"
              value={search}
              onChange={(event) => onSearch(event.target.value)}
            />
          </label>
          <label>
            <span>Model</span>
            <select aria-label="Filter by model" value={modelFilter} onChange={(event) => onModelFilter(event.target.value)}>
              <option value="">All models</option>
              {models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <label>
            <span>Reasoning</span>
            <select aria-label="Filter by reasoning effort" value={reasoningFilter} onChange={(event) => onReasoningFilter(event.target.value)}>
              <option value="">All efforts</option>
              {reasoningEfforts.map((effort) => <option key={effort} value={effort}>{humanize(effort)}</option>)}
            </select>
          </label>
          <label>
            <span>Sort by</span>
            <select aria-label="Sort evaluation runs" value={activeSort} onChange={(event) => onSort(event.target.value)}>
              {sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          {controlsChanged ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                onSearch("");
                onModelFilter("");
                onReasoningFilter("");
                onSort(defaultRunSort);
              }}
            >Reset</Button>
          ) : null}
        </section>
        {filteredRuns.length ? (
            <div className="run-results-scroll">
              <table className="run-results-table">
                <thead>
                  <tr>
                    <th>Run inputs</th>
                    {metricColumns.map((column) => <th key={column.key}>{column.label}</th>)}
                    <th><span className="sr-only">Open run</span></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => (
                    <tr
                      key={run.run_id}
                      className="selectable-run"
                      role="button"
                      tabIndex={0}
                      aria-label={`Open evaluation run ${run.run_id}`}
                      onClick={() => onSelectRun(run.run_id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onSelectRun(run.run_id);
                        }
                      }}
                    >
                      <td>
                        <div className="run-inputs">
                          <strong>{run.model ?? "Unknown model"}</strong>
                          <span>{humanize(run.reasoning_effort ?? "unspecified")} reasoning</span>
                          <small>{formatRunDate(run.created_at_utc)} · {run.recorded_attempts}/{run.planned_attempts} attempts</small>
                          <code title={run.run_id}>{shortRunId(run.run_id)}</code>
                        </div>
                      </td>
                      {metricColumns.map((column) => <MetricCell key={column.key} metric={column.get(run)} />)}
                      <td className="run-row-action" aria-hidden="true">›</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        ) : (
          <div className="empty table-empty">No evaluation runs match these controls.</div>
        )}
      </section>
    </main>
  );
}

function MetricCell({ metric }: { metric: AccuracyMetric | null }) {
  return (
    <td className="metric-cell">
      <strong>{formatAccuracy(metric)}</strong>
      <small>{metric ? `${metric.correct_runs}/${metric.evaluated_runs}` : "No data"}</small>
    </td>
  );
}

function RunAccuracySummary({
  run,
  fieldLabels,
}: {
  run: RunEntry;
  fieldLabels?: Record<string, string>;
}) {
  const metrics = buildMetricColumns([run], fieldLabels);
  return (
    <section className="run-accuracy" aria-label="Run accuracy summary">
      <div className="run-accuracy-heading">
        <div>
          <div className="eyebrow">Evaluation statistics</div>
          <h2>Run accuracy</h2>
        </div>
        <span>Correct / evaluated</span>
      </div>
      <div className="run-accuracy-grid">
        {metrics.map((column) => {
          const metric = column.get(run);
          return (
            <div className="run-accuracy-metric" key={column.key}>
              <span>{column.label}</span>
              <strong>{formatAccuracy(metric)}</strong>
              <small>{metric ? `${metric.correct_runs} / ${metric.evaluated_runs}` : "No data"}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function buildMetricColumns(runs: RunEntry[], labels: Record<string, string> = {}): MetricColumn[] {
  const fieldKeys = Array.from(new Set(
    runs.flatMap((run) => Object.keys(run.accuracy?.by_field ?? {})),
  )).sort((left, right) => metricFieldOrder(left) - metricFieldOrder(right) || left.localeCompare(right));
  const columns: MetricColumn[] = [{
    key: "complete",
    label: "Complete evaluation",
    get: (run) => run.accuracy?.complete_evaluation ?? null,
  }];
  for (const fieldKey of fieldKeys) {
    const label = labels[fieldKey] ?? humanize(fieldKey);
    columns.push({
      key: `field:${fieldKey}`,
      label,
      get: (run) => run.accuracy?.by_field[fieldKey] ?? null,
    });
    const confidences = Array.from(new Set(
      runs.flatMap((run) => Object.keys(run.accuracy?.by_field[fieldKey]?.by_confidence ?? {})),
    )).sort(confidenceOrder);
    for (const confidence of confidences) {
      columns.push({
        key: `field:${fieldKey}:confidence:${confidence}`,
        label: `${label} · ${humanize(confidence)}`,
        get: (run) => run.accuracy?.by_field[fieldKey]?.by_confidence[confidence] ?? null,
      });
    }
  }
  return columns;
}

function buildRunSortOptions(columns: MetricColumn[]): RunSortOption[] {
  return [
    { value: "newest", label: "Newest first" },
    { value: "oldest", label: "Oldest first" },
    { value: "model", label: "Model A–Z" },
    { value: "reasoning", label: "Reasoning effort" },
    ...columns
      .filter((column) => !column.key.includes(":confidence:"))
      .flatMap((column) => [
        { value: `${column.key}:desc`, label: `${column.label}: highest` },
        { value: `${column.key}:asc`, label: `${column.label}: lowest` },
      ]),
  ];
}

function sortRuns(runs: RunEntry[], sort: string, columns: MetricColumn[]) {
  const selectedMetric = columns.find((column) => sort.startsWith(`${column.key}:`));
  return [...runs].sort((left, right) => {
    if (selectedMetric) {
      const direction = sort.endsWith(":asc") ? 1 : -1;
      const leftAccuracy = selectedMetric.get(left)?.accuracy;
      const rightAccuracy = selectedMetric.get(right)?.accuracy;
      if (leftAccuracy == null && rightAccuracy != null) return 1;
      if (leftAccuracy != null && rightAccuracy == null) return -1;
      if (leftAccuracy != null && rightAccuracy != null && leftAccuracy !== rightAccuracy) {
        return (leftAccuracy - rightAccuracy) * direction;
      }
    }
    if (sort === "oldest") return compareRunDates(left, right);
    if (sort === "model") {
      const compared = (left.model ?? "").localeCompare(right.model ?? "");
      if (compared) return compared;
    }
    if (sort === "reasoning") {
      const compared = (left.reasoning_effort ?? "").localeCompare(right.reasoning_effort ?? "");
      if (compared) return compared;
    }
    return compareRunDates(right, left);
  });
}

function compareRunDates(left: RunEntry, right: RunEntry) {
  return (left.created_at_utc ?? "").localeCompare(right.created_at_utc ?? "");
}

function runSearchText(run: RunEntry) {
  return [
    run.run_id,
    run.model,
    run.reasoning_effort,
    run.pipeline_path,
    run.benchmark_key,
    run.agent_version_id,
    JSON.stringify(run.configuration ?? {}),
  ].filter(Boolean).join(" ").toLocaleLowerCase();
}

function Evaluation({
  row,
  benchmarkContext,
  adapter,
}: {
  row: AttemptRow;
  benchmarkContext: BenchmarkContext;
  adapter: UseCaseAdapter;
}) {
  const fields = Array.from(new Set([
    ...Object.keys(row.benchmark_labels),
    ...Object.keys(row.agent_output),
  ]));
  return (
    <div className="review-stack">
      <section className="review-intro">
        <div>
          <div className="eyebrow">Benchmark review</div>
          <h3>AI output compared with expected output</h3>
        </div>
        <p>Use the evidence package to validate the model’s conclusion and investigate incorrect fields.</p>
      </section>
      <section className="output-comparison" aria-label="AI output comparison">
        <div className="comparison-row comparison-header" aria-hidden="true">
          <span>Field</span><span>Benchmark</span><span>AI output</span><span>Result</span>
        </div>
        {fields.map((fieldName) => {
          const result = fieldResult(row.evaluations[fieldName]);
          return (
            <div className="comparison-row" key={fieldName}>
              <strong>{humanize(fieldName)}</strong>
              <span className="review-value">{displayValue(row.benchmark_labels[fieldName])}</span>
              <AiOutputValue value={row.agent_output[fieldName]} />
              <Badge variant={result === true ? "success" : result === false ? "destructive" : "neutral"}>
                {result === true ? "Match" : result === false ? "Mismatch" : "Review"}
              </Badge>
            </div>
          );
        })}
      </section>
      <BenchmarkContextPanel
        context={benchmarkContext}
        benchmarkLabels={row.benchmark_labels}
        fieldLabels={adapter.evaluationFieldLabels}
        verificationSchemas={adapter.sourceVerificationSchemas ?? []}
      />
      <section className="review-status-strip" aria-label="Attempt status">
        <ReviewFact label="Execution" value={row.execution_status} />
        <ReviewFact label="Output contract" value={row.output_contract_status} />
        <ReviewFact label="Scoring" value={row.scoring_status} />
        <ReviewFact label="Stability" value={row.flaky ? "Flaky" : "Stable"} />
      </section>
    </div>
  );
}

function BenchmarkContextPanel({
  context,
  benchmarkLabels,
  fieldLabels = {},
  verificationSchemas,
}: {
  context: BenchmarkContext;
  benchmarkLabels: Record<string, unknown>;
  fieldLabels?: Record<string, string>;
  verificationSchemas: SourceVerificationSchema[];
}) {
  if (context.availability === "unavailable") {
    return (
      <section className="benchmark-context">
        <div className="benchmark-context-heading">
          <div>
            <div className="eyebrow">Published benchmark context</div>
            <h3>Labeler notes and customer verification</h3>
          </div>
        </div>
        <div className="benchmark-context-unavailable">
          <strong>Context was not retained for this run.</strong>
          <span>{context.reason}</span>
        </div>
      </section>
    );
  }

  const notes = context.labeler_notes.filter((note) => note.explanation.trim());
  const verification = context.verification;
  return (
    <section className="benchmark-context">
      <div className="benchmark-context-heading">
        <div>
          <div className="eyebrow">Published benchmark context</div>
          <h3>Labeler notes and customer verification</h3>
        </div>
        {verification ? <Badge variant="success">Verified</Badge> : <Badge variant="neutral">Not verified</Badge>}
      </div>

      <div className="benchmark-context-grid">
        <section className="benchmark-context-section">
          <h4>Labeler notes</h4>
          {notes.length ? (
            <div className="labeler-note-list">
              {notes.map((note) => (
                <article className="labeler-note" key={note.review_event_id}>
                  <div>
                    <strong>{note.reviewer_display_name}</strong>
                    <span>{humanize(note.reviewer_project_role)} · {formatRunDate(note.submitted_at)}</span>
                  </div>
                  {note.selected_for_publication ? <Badge variant="neutral">Selected label</Badge> : null}
                  <p>{note.explanation}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="benchmark-context-empty">No labeler notes were attached to the published reviewer revisions.</p>
          )}
        </section>

        <section className="benchmark-context-section verification-context">
          <h4>{verification ? verificationSourceLabel(verification.source) : "Customer verification"}</h4>
          {verification ? (
            <>
              <p className="verification-summary">
                The following frozen benchmark labels were covered by this verification.
              </p>
              <dl className="verified-labels">
                {Object.entries(benchmarkLabels).map(([key, value]) => (
                  <div key={key}>
                    <dt>{fieldLabels[key] ?? humanize(key)}</dt>
                    <dd>{displayValue(value)}</dd>
                  </div>
                ))}
              </dl>
              <VerificationDetails verification={verification} schemas={verificationSchemas} />
            </>
          ) : (
            <p className="benchmark-context-empty">No customer or onsite verification was frozen with this benchmark example.</p>
          )}
        </section>
      </div>
    </section>
  );
}

function VerificationDetails({
  verification,
  schemas,
}: {
  verification: NonNullable<Extract<BenchmarkContext, { availability: "available" }>["verification"]>;
  schemas: SourceVerificationSchema[];
}) {
  const schema = schemas.find((candidate) =>
    candidate.schema_key === verification.context_schema_key
    && candidate.version === verification.context_schema_version
  );
  const fields = verification.source_fields ?? {};
  return (
    <div className="verification-details">
      {verification.note ? <p className="verification-note">{verification.note}</p> : null}
      {schema ? (
        <>
          <div className="verification-schema-title">{schema.title} · Immutable source record</div>
          <dl>
            {schema.fields.flatMap((field) => {
              const value = fields[field.key];
              if (value == null || value === "") return [];
              return (
                <div className={field.value_type === "long_text" ? "wide" : ""} key={field.key}>
                  <dt>{field.label}</dt>
                  <dd>{field.value_type === "timestamp" && typeof value === "string" ? formatRunDate(value) : displayValue(value)}</dd>
                </div>
              );
            })}
          </dl>
        </>
      ) : null}
      {verification.recorded_at ? <small>Recorded {formatRunDate(verification.recorded_at)}</small> : null}
    </div>
  );
}

function verificationSourceLabel(source: "direct_observation" | "operator_feedback") {
  return source === "operator_feedback" ? "Customer verified" : "Verified by direct observation";
}

function Execution({ review, row }: { review: Record<string, unknown> | null; row: AttemptRow }) {
  if (!review) return <ReviewUnavailable row={row} />;
  return (
    <div className="execution-stack">
      <p className="secondary-note">Technical trace data is collapsed by default so it does not compete with output and evidence review.</p>
      <CollapsibleJson title="Model interactions and tool activity" value={review.model_interactions ?? { unavailable: true }} />
      <CollapsibleJson title="Pipeline trace" value={review.pipeline ?? { unavailable: true }} />
      <CollapsibleJson title="Attempt outcome" value={review.attempt_outcome ?? { unavailable: true }} />
    </div>
  );
}

function CollapsibleJson({ title, value }: { title: string; value: unknown }) {
  return <details className="technical-disclosure"><summary>{title}</summary><Json value={value} /></details>;
}

function ReviewFact({ label, value }: { label: string; value: string }) {
  return <div><small>{label}</small><strong>{humanize(value)}</strong></div>;
}

function AiOutputValue({ value }: { value: unknown }) {
  const record = asRecord(value);
  const confidence = typeof record?.confidence === "string" ? record.confidence : null;
  const explanation = typeof record?.explanation === "string" ? record.explanation : null;
  return (
    <div className="review-value ai-value">
      <span>{displayValue(value)}</span>
      {confidence ? <small>{confidence} confidence</small> : null}
      {explanation ? <details className="rationale"><summary>Model rationale</summary><p>{explanation}</p></details> : null}
    </div>
  );
}

function ReviewUnavailable({ row }: { row: AttemptRow }) {
  const reason = row.review_unavailable_reason;
  return (
    <div className="empty">
      Detailed review unavailable ({reason?.code ?? "absent"})
      {reason?.message ? `: ${reason.message}` : "."}
    </div>
  );
}

function Status({ row }: { row: AttemptRow }) {
  const value = row.execution_status === "failed" ? "failed" : row.complete_evaluation_correct === true ? "correct" : row.complete_evaluation_correct === false ? "incorrect" : row.scoring_status;
  const variant = value === "correct" ? "success" : value === "incorrect" || value === "failed" ? "destructive" : "neutral";
  return <Badge variant={variant} className={`status ${value}`}>{value}</Badge>;
}

function RunFact({ label, value }: { label: string; value: string }) {
  return <div className="run-fact"><small>{label}</small><strong>{value}</strong></div>;
}

function Json({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

function QueryError({ error, compact = false }: { error: Error; compact?: boolean }) {
  return <div className={compact ? "error compact-error" : "error"} role="alert">{error.message}</div>;
}

function attemptsPath({
  runId,
  state,
  search,
  field,
  sliceKey,
  offset,
}: {
  runId: string;
  state: string;
  search: string;
  field: string;
  sliceKey: string;
  offset: number;
}) {
  const params = new URLSearchParams({
    state,
    search,
    offset: String(offset),
    limit: String(pageSize),
  });
  if (field) params.set("field", field);
  if (sliceKey) params.set("slice", sliceKey);
  return `/runs/${encodeURIComponent(runId)}/attempts?${params}`;
}

function parseOffset(value: string | null) {
  const parsed = Number(value ?? 0);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : 0;
}

function pageRange(payload: AttemptsPayload, offset: number) {
  if (payload.matched === 0) return "Showing 0";
  return `Showing ${offset + 1}–${offset + payload.rows.length}`;
}

function summarizeOutput(output: Record<string, unknown>) {
  const entries = Object.entries(output).slice(0, 2);
  if (!entries.length) return "No structured output";
  return entries.map(([key, value]) => `${humanize(key)}: ${displayValue(value)}`).join(" · ");
}

function displayValue(value: unknown): string {
  const record = asRecord(value);
  const unwrapped = record && "value" in record ? record.value : value;
  if (unwrapped == null || unwrapped === "") return "—";
  if (typeof unwrapped === "string" || typeof unwrapped === "number" || typeof unwrapped === "boolean") {
    return String(unwrapped);
  }
  const text = JSON.stringify(unwrapped);
  return text.length > 180 ? `${text.slice(0, 177)}…` : text;
}

function fieldResult(value: unknown): boolean | null {
  const record = asRecord(value);
  if (typeof record?.correct === "boolean") return record.correct;
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function uniqueValues(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();
}

function metricFieldOrder(value: string) {
  if (value === "classification") return 0;
  if (value === "root_cause") return 1;
  return 2;
}

function confidenceOrder(left: string, right: string) {
  const priority = (value: string) => value.toLowerCase() === "high" ? 0 : value.toLowerCase() === "low" ? 1 : 2;
  return priority(left) - priority(right) || left.localeCompare(right);
}

function formatAccuracy(metric: AccuracyMetric | null) {
  if (!metric || metric.accuracy == null || !Number.isFinite(metric.accuracy)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(metric.accuracy);
}

function formatRunDate(value: string | null | undefined) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function shortRunId(runId: string) {
  return runId.length > 24 ? `${runId.slice(0, 24)}…` : runId;
}

function humanize(value: string) {
  if (!value) return "—";
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
