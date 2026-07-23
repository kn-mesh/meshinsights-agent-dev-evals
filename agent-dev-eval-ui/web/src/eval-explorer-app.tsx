import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import type {
  AccuracyMetric,
  AttemptRow,
  BenchmarkContext,
  CostDistribution,
  CostSummary,
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
  const [lifecycleFilter, setLifecycleFilter] = useState(
    ["working", "retained"].includes(initial.get("lifecycle") ?? "")
      ? initial.get("lifecycle")!
      : "",
  );
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
      lifecycle: lifecycleFilter,
      q: runSearch,
      sort: runSort === defaultRunSort ? "" : runSort,
    })) {
      if (value) url.searchParams.set(key, String(value));
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", url);
  }, [runId, executionId, state, search, field, sliceKey, offset, tab, modelFilter, reasoningFilter, lifecycleFilter, runSearch, runSort]);

  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<RunPayload>("/runs") });
  const selectedRun = useMemo(
    () => runs.data?.runs.find((item) => item.run_id === runId),
    [runs.data, runId],
  );
  const attempts = useQuery({
    queryKey: ["attempts", runId, state, search, field, sliceKey, offset],
    queryFn: () => api<AttemptsPayload>(
      attemptsPath({ runId, state, search, field, sliceKey, offset }),
    ),
    enabled: Boolean(runId && selectedRun),
  });
  const detail = useQuery({
    queryKey: ["attempt", runId, executionId],
    queryFn: () => api<AttemptPayload>(
      `/runs/${encodeURIComponent(runId)}/attempts/${encodeURIComponent(executionId)}`,
    ),
    enabled: Boolean(runId && selectedRun && executionId),
  });
  const evidence = useQuery({
    queryKey: ["evidence", runId, detail.data?.row.example_id],
    queryFn: () => api<EvidenceView>(
      `/runs/${encodeURIComponent(runId)}/examples/${encodeURIComponent(detail.data!.row.example_id)}/evidence`,
    ),
    enabled: Boolean(runId && detail.data?.row.example_id && tab === "evidence"),
    staleTime: Infinity,
  });
  const runUnavailable = Boolean(runId && runs.isSuccess && !selectedRun);
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
  useEffect(() => {
    if (!executionId && attempts.data?.rows.length) {
      setExecutionId(attempts.data.rows[0].execution_id);
    }
  }, [attempts.data, executionId]);
  const resetAttemptSelection = () => {
    setExecutionId("");
    setOffset(0);
  };

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
          <div className="eyebrow">{adapter.contextLabel ?? "Evaluation review"}</div>
          <h1>{runId ? "Run analysis" : "Evaluation results"}</h1>
        </div>
      </header>

      {runs.error ? <QueryError error={runs.error} /> : null}
      {runs.isPending ? <LoadingState label="Loading evaluation runs…" /> : null}
      {!runId && runs.data ? (
        <ResultsOverview
          adapter={adapter}
          runs={runs.data.runs}
          modelFilter={modelFilter}
          reasoningFilter={reasoningFilter}
          lifecycleFilter={lifecycleFilter}
          search={runSearch}
          sort={runSort}
          onModelFilter={setModelFilter}
          onReasoningFilter={setReasoningFilter}
          onLifecycleFilter={setLifecycleFilter}
          onSearch={setRunSearch}
          onSort={setRunSort}
          onSelectRun={selectRun}
        />
      ) : null}

      {runUnavailable ? (
        <main className="unavailable-page">
          <div className="empty">
            <strong>Evaluation run unavailable</strong>
            <span>This run does not exist locally or may have been permanently deleted.</span>
            <Button variant="outline" onClick={showOverview}>Back to evaluation results</Button>
          </div>
        </main>
      ) : null}

      {runId && runs.isSuccess && !runUnavailable ? (
        <>
          <section className="run-page-header">
            <div className="run-page-heading">
              <button type="button" aria-label="Back to evaluation results" onClick={showOverview}>
                <UiIcon name="arrow-left" />
                <span>Evaluation results</span>
              </button>
              <div>
                <div className="eyebrow">Evaluation run</div>
                <h2>{selectedRun?.benchmark_key ?? "Benchmark"} <span>v{selectedRun?.benchmark_version ?? "—"}</span></h2>
              </div>
            </div>
            <div className="run-page-meta">
              <RunFact label="Model" value={selectedRun?.model ?? "Unknown"} />
              <RunFact label="Reasoning" value={selectedRun?.reasoning_effort ?? "—"} />
              <RunFact label="Attempts" value={`${selectedRun?.recorded_attempts ?? 0}/${selectedRun?.planned_attempts ?? 0}`} />
            </div>
          </section>
          {selectedRun?.accuracy || selectedRun?.cost ? (
            <details className="run-summary">
              <summary>
                <span><UiIcon name="chart" /> Run metrics</span>
                <div className="run-summary-highlights">
                  {selectedRun.accuracy ? (
                    <span>
                      <strong>{formatAccuracy(selectedRun.accuracy.complete_evaluation)}</strong>
                      <small>overall accuracy</small>
                    </span>
                  ) : null}
                  <CostHighlight cost={selectedRun.cost} />
                </div>
                <UiIcon name="chevron" />
              </summary>
              <div className="run-metrics-detail">
                {selectedRun.accuracy ? (
                  <RunAccuracySummary
                    run={selectedRun}
                    fieldLabels={adapter.evaluationFieldLabels}
                  />
                ) : null}
                <RunCostSummary cost={selectedRun.cost} />
              </div>
            </details>
          ) : null}

          <main className="explorer-workspace">
            <aside className="attempt-sidebar">
              <div className="attempt-sidebar-heading">
                <div>
                  <h2>Attempts</h2>
                  <span>{attempts.data?.matched ?? 0} results</span>
                </div>
                <span className="attempt-state-label">{state === "all" ? "All states" : humanize(state)}</span>
              </div>
              <div className="filters">
                <label className="search-field">
                  <span className="sr-only">Search attempts</span>
                  <UiIcon name="search" />
                  <input
                    aria-label="Search attempts"
                    placeholder="Search unit or output"
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      resetAttemptSelection();
                    }}
                  />
                </label>
                <select aria-label="Attempt state" value={state} onChange={(event) => {
                  setState(event.target.value);
                  resetAttemptSelection();
                }}>
                  {states.map((item) => (
                    <option key={item} value={item}>
                      {item} ({attempts.data?.facets.states[item] ?? 0})
                    </option>
                  ))}
                </select>
                <select aria-label="Evaluation field" value={field} onChange={(event) => {
                  setField(event.target.value);
                  resetAttemptSelection();
                }}>
                  <option value="">All fields</option>
                  {attempts.data?.facets.fields.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <select aria-label="Evaluation slice" value={sliceKey} onChange={(event) => {
                  setSliceKey(event.target.value);
                  resetAttemptSelection();
                }}>
                  <option value="">All slices</option>
                  {attempts.data?.facets.slices.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
              {attempts.error ? <QueryError error={attempts.error} compact /> : null}
              <div className="attempt-count">
                <span>Attempt queue</span>
                {attempts.data ? <span>{pageRange(attempts.data, offset)}</span> : null}
              </div>
              <div className="attempt-list">
                {attempts.isPending ? <LoadingState label="Loading attempts…" compact /> : null}
                {attempts.data && !attempts.data.rows.length ? (
                  <div className="empty compact-empty">No attempts match these filters.</div>
                ) : null}
                {attempts.data?.rows.map((row) => (
                  <button
                    className={row.execution_id === executionId ? "attempt active" : "attempt"}
                    key={row.execution_id}
                    onClick={() => setExecutionId(row.execution_id)}
                    aria-current={row.execution_id === executionId ? "true" : undefined}
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
                  onClick={() => {
                    setExecutionId("");
                    setOffset(Math.max(0, offset - pageSize));
                  }}
                >Previous</Button>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Next attempts"
                  disabled={!attempts.data || offset + attempts.data.rows.length >= attempts.data.matched}
                  onClick={() => {
                    setExecutionId("");
                    setOffset(offset + pageSize);
                  }}
                >Next</Button>
              </div>
            </aside>

            <article className="attempt-detail">
              {!executionId && !attempts.isPending ? <div className="empty">No attempt is selected.</div> : null}
              {detail.isPending && executionId ? <LoadingState label="Loading attempt review…" /> : null}
              {detail.error ? <QueryError error={detail.error} /> : null}
              {detail.data ? (
                <>
                  <div className="detail-heading">
                    <div>
                      <div className="eyebrow">Attempt review</div>
                      <h2>{detail.data.row.unit_id}</h2>
                      <p>{detail.data.row.example_id} · repetition {detail.data.row.run_index}</p>
                    </div>
                    <Status row={detail.data.row} />
                  </div>
                  <nav className="tabs" aria-label="Attempt review sections">
                    {[
                      ["evaluation", "AI output"],
                      ["evidence", "Evidence"],
                      ["execution", "Execution"],
                    ].map(([key, label]) => (
                      <button
                        key={key}
                        className={tab === key ? "active" : ""}
                        aria-current={tab === key ? "page" : undefined}
                        onClick={() => setTab(key)}
                      >{label}</button>
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
  lifecycleFilter,
  search,
  sort,
  onModelFilter,
  onReasoningFilter,
  onLifecycleFilter,
  onSearch,
  onSort,
  onSelectRun,
}: {
  adapter: UseCaseAdapter;
  runs: RunEntry[];
  modelFilter: string;
  reasoningFilter: string;
  lifecycleFilter: string;
  search: string;
  sort: string;
  onModelFilter: (value: string) => void;
  onReasoningFilter: (value: string) => void;
  onLifecycleFilter: (value: string) => void;
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
    .filter((run) => !lifecycleFilter || run.lifecycle_state === lifecycleFilter)
    .filter((run) => !normalizedSearch || runSearchText(run).includes(normalizedSearch)), activeSort, metricColumns);
  const controlsChanged = Boolean(modelFilter || reasoningFilter || lifecycleFilter || search || activeSort !== defaultRunSort);

  return (
    <main className="results-overview">
      <section className="overview-heading">
        <div>
          <div className="eyebrow">Evaluation runs</div>
          <h2>Overall evaluation results</h2>
          <p>Review recent detail or compare meaningful elevated results, then open a run to inspect units and evidence.</p>
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
            <span>Lifecycle</span>
            <select aria-label="Filter by lifecycle" value={lifecycleFilter} onChange={(event) => onLifecycleFilter(event.target.value)}>
              <option value="">All evals</option>
              <option value="working">Not elevated</option>
              <option value="retained">Elevated</option>
            </select>
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
                onLifecycleFilter("");
                onSort(defaultRunSort);
              }}
            >Reset</Button>
          ) : null}
        </section>
        {filteredRuns.length ? (
            <div className="run-results-scroll">
              <table className="run-results-table" aria-label="Evaluation runs and metrics">
                <thead>
                  <tr>
                    <th>Run inputs</th>
                    {metricColumns.map((column) => <th key={column.key}>{column.label}</th>)}
                    <th>Cost</th>
                    <th><span className="sr-only">Open run</span></th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => (
                    <tr
                      key={run.run_id}
                      className="selectable-run"
                      onClick={() => onSelectRun(run.run_id)}
                    >
                      <td>
                        <div className="run-inputs">
                          <button
                            type="button"
                            className="run-open-button"
                            aria-label={`Open evaluation run ${run.run_id}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              onSelectRun(run.run_id);
                            }}
                          >{run.model ?? "Unknown model"}</button>
                          {run.lifecycle_state === "retained" ? (
                            <Badge variant="primary">Elevated</Badge>
                          ) : null}
                          <span>{humanize(run.reasoning_effort ?? "unspecified")} reasoning</span>
                          <small>{formatRunDate(run.created_at_utc)} · {run.recorded_attempts}/{run.planned_attempts} attempts</small>
                          <code title={run.run_id}>{shortRunId(run.run_id)}</code>
                        </div>
                      </td>
                      {metricColumns.map((column) => <MetricCell key={column.key} metric={column.get(run)} />)}
                      <CostCell cost={run.cost} />
                      <td className="run-row-action" aria-hidden="true">›</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        ) : (
          <div className="empty table-empty">
            {runs.length ? "No evaluation runs match these controls." : "No evaluation runs are available yet."}
          </div>
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

function CostCell({ cost }: { cost?: CostSummary | null }) {
  const rows = costRows(cost);
  if (!cost || !rows.length) {
    return (
      <td className="metric-cell cost-cell">
        <strong>—</strong>
        <small>Unavailable</small>
      </td>
    );
  }
  return (
    <td className="metric-cell cost-cell">
      {rows.map((row) => (
        <div key={row.currency}>
          <strong>{formatCost(row.total, row.currency)}</strong>
          <small>
            Mean {formatCost(row.distribution?.average, row.currency)}
            {" · "}P5 {formatCost(row.distribution?.p5, row.currency)}
            {" · "}P95 {formatCost(row.distribution?.p95, row.currency)}
          </small>
        </div>
      ))}
      <small>{costCoverageLabel(cost)}</small>
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

function CostHighlight({ cost }: { cost?: CostSummary | null }) {
  const rows = costRows(cost);
  if (!rows.length) return null;
  const primary = rows[0];
  return (
    <span>
      <strong>{formatCost(primary.total, primary.currency)}</strong>
      <small>{rows.length === 1 ? "eval cost" : `eval cost · ${rows.length} currencies`}</small>
    </span>
  );
}

function RunCostSummary({ cost }: { cost?: CostSummary | null }) {
  const rows = costRows(cost);
  return (
    <section className="run-cost" aria-label="Run cost summary">
      <div className="run-accuracy-heading">
        <div>
          <div className="eyebrow">Pricing statistics</div>
          <h2>Run cost</h2>
        </div>
        <span>{cost ? costCoverageLabel(cost) : "Cost information unavailable"}</span>
      </div>
      {rows.length ? (
        <div className="run-cost-currencies">
          {rows.map((row) => (
            <section key={row.currency} className="run-cost-currency">
              <div className="run-cost-currency-heading">
                <strong>{row.currency}</strong>
                <span className="run-cost-status">{costStatus(cost)}</span>
              </div>
              <div className="run-cost-grid">
                <CostMetric label="Overall eval" value={formatCost(row.total, row.currency)} />
                <CostMetric label="Mean / unit" value={formatCost(row.distribution?.average, row.currency)} />
                <CostMetric label="P5 / unit" value={formatCost(row.distribution?.p5, row.currency)} />
                <CostMetric label="P95 / unit" value={formatCost(row.distribution?.p95, row.currency)} />
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="run-cost-unavailable">
          No usable cost observations were stored for this run.
        </div>
      )}
    </section>
  );
}

function CostMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="run-cost-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

type CostCurrencyRow = {
  currency: string;
  total: number;
  distribution?: CostDistribution;
};

function costRows(cost?: CostSummary | null): CostCurrencyRow[] {
  if (!cost) return [];
  const currencies = Array.from(new Set([
    ...Object.keys(cost.complete_unit_cost_by_currency ?? {}),
    ...Object.keys(cost.actual_by_currency ?? {}),
    ...Object.keys(cost.estimated_by_currency ?? {}),
  ])).sort();
  return currencies.flatMap((currency) => {
    const distribution = cost.complete_unit_cost_by_currency?.[currency];
    const fallbackTotal = (cost.actual_by_currency?.[currency] ?? 0)
      + (cost.estimated_by_currency?.[currency] ?? 0);
    const total = distribution?.total ?? fallbackTotal;
    return Number.isFinite(total) ? [{ currency, total, distribution }] : [];
  });
}

function costCoverageLabel(cost: CostSummary) {
  const complete = cost.units_with_complete_cost_observations ?? 0;
  const recorded = cost.recorded_attempts ?? 0;
  const partial = cost.units_with_partial_pricing ?? 0;
  if (!recorded) return "No attempts";
  if (complete === recorded) return `${complete}/${recorded} units fully priced`;
  if (partial) return `${complete}/${recorded} fully priced · ${partial} partial`;
  return `${complete}/${recorded} units fully priced`;
}

function costStatus(cost?: CostSummary | null) {
  if (!cost || !cost.recorded_attempts) return "Unavailable";
  if (cost.units_with_complete_cost_observations === cost.recorded_attempts) return "Complete";
  if (cost.units_with_complete_cost_observations || cost.units_with_partial_pricing) return "Partial";
  return "Unavailable";
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
          <div className="eyebrow">Evaluation</div>
          <h3>Expected and actual output</h3>
        </div>
        <p>Compare scored fields, then open the evidence when a result needs investigation.</p>
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
              <span className={`comparison-result ${result === true ? "match" : result === false ? "mismatch" : "review"}`}>
                {result === true ? "Match" : result === false ? "Mismatch" : "Review"}
              </span>
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
  const notes = context.labeler_notes.filter((note) => note.explanation.trim());
  const verification = context.verification;
  return (
    <details className="benchmark-context">
      <summary className="benchmark-context-heading">
        <div>
          <UiIcon name="note" />
          <div>
            <div className="eyebrow">Supporting context</div>
            <h3>Labeler notes and verification</h3>
          </div>
        </div>
        <span>
          {verification ? <span className="context-status">Verified</span> : null}
          <UiIcon name="chevron" />
        </span>
      </summary>

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
                  {note.selected_for_publication ? <span className="label-note-status">Selected label</span> : null}
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
    </details>
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
      <section className="review-status-strip" aria-label="Attempt status">
        <ReviewFact label="Execution" value={row.execution_status} />
        <ReviewFact label="Output contract" value={row.output_contract_status} />
        <ReviewFact label="Scoring" value={row.scoring_status} />
        <ReviewFact label="Stability" value={row.flaky ? "Flaky" : "Stable"} />
      </section>
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
  return <span className={`status-text ${value}`}>{value}</span>;
}

function RunFact({ label, value }: { label: string; value: string }) {
  return <div className="run-fact"><small>{label}</small><strong>{value}</strong></div>;
}

type UiIconName = "arrow-left" | "chart" | "chevron" | "note" | "search";

function UiIcon({ name }: { name: UiIconName }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {name === "arrow-left" ? <><path d="m15 18-6-6 6-6" /><path d="M9 12h10" /></> : null}
      {name === "chart" ? <><path d="M4 19V9M10 19V5M16 19v-7M22 19H2" /></> : null}
      {name === "chevron" ? <path d="m9 18 6-6-6-6" /> : null}
      {name === "note" ? <><path d="M14 2H6a2 2 0 0 0-2 2v16l4-4h10a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 11h8M8 7h2" /></> : null}
      {name === "search" ? <><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></> : null}
    </svg>
  );
}

function Json({ value }: { value: unknown }) {
  return <pre>{JSON.stringify(value, null, 2)}</pre>;
}

function QueryError({ error, compact = false }: { error: Error; compact?: boolean }) {
  return <div className={compact ? "error compact-error" : "error"} role="alert">{error.message}</div>;
}

function LoadingState({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div className={compact ? "loading-state compact-loading" : "loading-state"} role="status">
      <span className="loading-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
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

function formatCost(value: number | null | undefined, currency: string) {
  if (value == null || !Number.isFinite(value)) return "—";
  const absolute = Math.abs(value);
  const fractionDigits = absolute === 0 ? 2 : absolute < 0.01 ? 6 : absolute < 1 ? 4 : 2;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    }).format(value);
  } catch {
    return `${currency} ${value.toFixed(fractionDigits)}`;
  }
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
