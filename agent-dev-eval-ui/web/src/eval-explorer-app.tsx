import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import type {
  AttemptPerformancePayload,
  AttemptRow,
  DurationStats,
  EvidenceView,
  PerformancePayload,
  RunEntry,
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
  performance: AttemptPerformancePayload;
};
type ComparisonEntry = {
  comparison_id: string;
  result_path?: string | null;
  run_ids: string[];
  varying_dimensions: string[];
};
type ComparisonsPayload = { comparisons: ComparisonEntry[] };

const pageSize = 100;

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
  const [tab, setTab] = useState(initial.get("tab") ?? "evaluation");
  const [comparisonId, setComparisonId] = useState(initial.get("comparison") ?? "");

  useEffect(() => {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries({
      run: runId,
      execution: executionId,
      state,
      search,
      field,
      slice: sliceKey,
      offset: offset > 0 ? String(offset) : "",
      tab,
      comparison: comparisonId,
    })) {
      if (value) url.searchParams.set(key, String(value));
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", url);
  }, [runId, executionId, state, search, field, sliceKey, offset, tab, comparisonId]);

  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<RunPayload>("/runs") });
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api<Record<string, unknown>>(`/runs/${encodeURIComponent(runId)}`),
    enabled: Boolean(runId),
  });
  const performance = useQuery({
    queryKey: ["performance", runId],
    queryFn: () => api<PerformancePayload>(
      `/runs/${encodeURIComponent(runId)}/performance`,
    ),
    enabled: Boolean(runId),
  });
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
  const comparisons = useQuery({
    queryKey: ["comparisons"],
    queryFn: () => api<ComparisonsPayload>("/comparisons"),
  });
  const comparison = useQuery({
    queryKey: ["comparison", comparisonId],
    queryFn: () => api<Record<string, unknown>>(`/comparisons/${encodeURIComponent(comparisonId)}`),
    enabled: Boolean(comparisonId),
  });

  const selectedRun = useMemo(
    () => runs.data?.runs.find((item) => item.run_id === runId),
    [runs.data, runId],
  );
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
      <header>
        <div>
          <div className="eyebrow">MeshInsights Agent Workbench</div>
          <h1>Eval Explorer</h1>
        </div>
        <select
          aria-label="Evaluation run"
          value={runId}
          onChange={(event) => {
            setRunId(event.target.value);
            setExecutionId("");
            setOffset(0);
          }}
        >
          <option value="">Select an evaluation run…</option>
          {runs.data?.runs.map((item) => (
            <option key={item.run_id} value={item.run_id}>
              {item.pipeline_path ?? "pipeline"} · {item.model ?? "model"} · {item.run_id.slice(0, 20)}
            </option>
          ))}
        </select>
      </header>

      {runs.error ? <QueryError error={runs.error} /> : null}
      {!runId ? <div className="welcome">Choose a retained schema-v1 run to explore its results and evidence.</div> : null}

      {runId ? (
        <>
          <section className="run-bar">
            <strong>{selectedRun?.benchmark_key} v{selectedRun?.benchmark_version}</strong>
            <span>{selectedRun?.model}</span>
            <span>{selectedRun?.reasoning_effort}</span>
            <span>{selectedRun?.recorded_attempts}/{selectedRun?.planned_attempts} attempts</span>
            <span>review: {selectedRun?.review_status}</span>
          </section>
          <details className="summary-card">
            <summary>Run metrics and configuration</summary>
            <Json value={run.data ?? { loading: true }} />
          </details>
          {run.error ? <QueryError error={run.error} /> : null}
          <PerformancePanel
            performance={performance.data}
            error={performance.error}
            onSelectExecution={(value) => {
              setExecutionId(value);
              setTab("performance");
            }}
          />
          <ComparisonPanel
            comparisons={comparisons.data?.comparisons}
            listError={comparisons.error}
            comparisonId={comparisonId}
            onComparisonChange={setComparisonId}
            comparison={comparison.data}
            detailError={comparison.error}
          />

          <main>
            <aside>
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
                    <div className="output-line">
                      <span>Expected {compact(row.benchmark_labels)}</span>
                      <span>Actual {compact(row.agent_output)}</span>
                    </div>
                  </button>
                ))}
              </div>
              <div className="pagination">
                <button
                  type="button"
                  aria-label="Previous attempts"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - pageSize))}
                >Previous</button>
                <button
                  type="button"
                  aria-label="Next attempts"
                  disabled={!attempts.data || offset + attempts.data.rows.length >= attempts.data.matched}
                  onClick={() => setOffset(offset + pageSize)}
                >Next</button>
              </div>
            </aside>

            <article>
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
                      ["evaluation", "Evaluation"],
                      ["performance", "Performance"],
                      ["evidence", "Evidence package"],
                      ["input", "Agent input"],
                      ["execution", "Execution & tools"],
                      ["raw", "Raw"],
                    ].map(([key, label]) => (
                      <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>
                    ))}
                  </nav>
                  {tab === "evaluation" ? <Evaluation row={detail.data.row} /> : null}
                  {tab === "performance" ? <AttemptPerformance performance={detail.data.performance} /> : null}
                  {tab === "evidence" ? (
                    evidence.isPending ? <div className="empty">Loading and verifying frozen evidence…</div> :
                    evidence.error ? <QueryError error={evidence.error} /> :
                    evidence.data ? <EvidenceDisplay evidence={evidence.data} /> : null
                  ) : null}
                  {tab === "input" ? <ReviewSection review={detail.data.review} row={detail.data.row} section="model_interactions" /> : null}
                  {tab === "execution" ? <Execution review={detail.data.review} row={detail.data.row} /> : null}
                  {tab === "raw" ? <Json value={detail.data} /> : null}
                </>
              ) : null}
            </article>
          </main>
        </>
      ) : null}
    </div>
  );
}

export function PerformancePanel({
  performance,
  error,
  onSelectExecution,
}: {
  performance: PerformancePayload | undefined;
  error?: Error | null;
  onSelectExecution: (executionId: string) => void;
}) {
  if (error) {
    return <section className="performance-panel"><QueryError error={error} compact /></section>;
  }
  if (!performance) {
    return <section className="performance-panel"><div className="empty compact-empty">Loading performance observations…</div></section>;
  }
  if (performance.availability !== "available") {
    return (
      <section className="performance-panel">
        <div className="performance-heading"><h2>Performance</h2><span className="status">unavailable</span></div>
        <p className="muted">{performance.reason ?? "Performance observations are unavailable."} Durable quality and evidence remain usable.</p>
      </section>
    );
  }
  const stages = performance.summary?.stage_duration_seconds ?? {};
  const modelDuration = performance.model_calls?.duration_seconds;
  const retries = performance.retries;
  return (
    <section className="performance-panel">
      <div className="performance-heading">
        <div><div className="eyebrow">Disposable observations</div><h2>Performance</h2></div>
        <span className="status correct">available</span>
      </div>
      <div className="metric-grid">
        <Metric label="Wall time" value={formatSeconds(performance.summary?.evaluation_wall_time_seconds)} />
        <Metric label="Throughput" value={formatRate(performance.summary?.throughput_runs_per_minute)} />
        <Metric label="Executions" value={String(performance.recorded_executions ?? "—")} />
        <Metric label="Model calls" value={String(performance.model_calls?.count ?? "—")} />
      </div>
      <div className="performance-columns">
        <div>
          <h3>Median / p95 latency</h3>
          <div className="latency-table">
            {Object.entries(stages).map(([name, stats]) => <LatencyRow key={name} name={name} stats={stats} />)}
            {modelDuration ? <LatencyRow name="model API" stats={modelDuration} /> : null}
          </div>
          <p className="muted">
            Duration boundary: {formatCount(performance.model_calls?.duration_exceeded_configured_timeout_count)}. This does not by itself prove a provider timeout. Long tail at or above p95: {formatCount(performance.model_calls?.long_tail_at_or_above_p95_count)}.
          </p>
        </div>
        <div>
          <h3>Retry observations</h3>
          <dl className="observation-list">
            <dt>Model requests</dt><dd>{retries?.observed_model_requests ?? "unavailable"}</dd>
            <dt>HTTP attempts</dt><dd>{retries?.observed_transport_attempts ?? "unavailable"}</dd>
            <dt>Retry categories</dt><dd>{retries?.observed_transport_attempts == null ? "unavailable" : compact(retries.observed_transport_retry_categories ?? {})}</dd>
          </dl>
          {retries?.observed_transport_attempts == null ? <p className="muted">The active provider path did not expose adapter-owned HTTP attempts. Configured retry limits are not shown as observations.</p> : null}
        </div>
      </div>
      <div>
        <h3>Slowest model calls</h3>
        <div className="slow-call-list">
          {performance.model_calls?.slowest?.map((call, index) => (
            <button
              key={`${call.execution_id ?? "unknown"}-${index}`}
              disabled={!call.execution_id}
              onClick={() => call.execution_id && onSelectExecution(call.execution_id)}
            >
              <span><strong>{call.unit_id ?? call.example_id ?? call.work_item_id ?? "unknown"}</strong><small>{call.execution_id ?? "execution unavailable"}</small></span>
              <span>{formatSeconds(call.duration_seconds)}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function ComparisonPanel({
  comparisons,
  listError,
  comparisonId,
  onComparisonChange,
  comparison,
  detailError,
}: {
  comparisons: ComparisonEntry[] | undefined;
  listError: Error | null;
  comparisonId: string;
  onComparisonChange: (value: string) => void;
  comparison: Record<string, unknown> | undefined;
  detailError: Error | null;
}) {
  return (
    <details className="summary-card comparison-card">
      <summary>Run comparisons ({comparisons?.length ?? 0})</summary>
      {listError ? <QueryError error={listError} compact /> : (
        <select aria-label="Run comparison" value={comparisonId} onChange={(event) => onComparisonChange(event.target.value)}>
          <option value="">Select a comparison…</option>
          {comparisons?.map((item) => (
            <option key={item.comparison_id} value={item.comparison_id} disabled={!item.result_path}>
              {item.comparison_id} · {item.run_ids.length} runs · {item.varying_dimensions.join(", ") || "no varying dimensions"}
            </option>
          ))}
        </select>
      )}
      {detailError ? <QueryError error={detailError} compact /> : null}
      {comparison ? <Json value={comparison} /> : null}
    </details>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><small>{label}</small><strong>{value}</strong></div>;
}

function LatencyRow({ name, stats }: { name: string; stats: DurationStats }) {
  return <div><span>{name}</span><span>{formatSeconds(stats.median)} / {formatSeconds(stats.p95)}</span></div>;
}

export function AttemptPerformance({ performance }: { performance: AttemptPerformancePayload }) {
  if (performance.availability !== "available") {
    return <div className="empty">Attempt performance unavailable: {performance.reason ?? "no observation was retained"}. Durable evaluation and evidence remain available.</div>;
  }
  return (
    <div className="stack">
      <div className="metric-grid">
        <Metric label="Executor duration" value={formatSeconds(performance.executor_duration_seconds)} />
        <Metric label="Started" value={performance.started_at_utc ?? "—"} />
        <Metric label="Completed" value={performance.completed_at_utc ?? "—"} />
      </div>
      <Card title="Attempt timing, retries, and model calls"><Json value={performance.metrics ?? { unavailable: true }} /></Card>
    </div>
  );
}

function Evaluation({ row }: { row: AttemptRow }) {
  return (
    <div className="grid-cards">
      <Card title="Expected output"><Json value={row.benchmark_labels} /></Card>
      <Card title="Actual output"><Json value={row.agent_output} /></Card>
      <Card title="Field evaluations"><Json value={row.evaluations} /></Card>
      <Card title="Attempt state"><Json value={{ execution: row.execution_status, output_contract: row.output_contract_status, scoring: row.scoring_status, flaky: row.flaky }} /></Card>
    </div>
  );
}

function Execution({ review, row }: { review: Record<string, unknown> | null; row: AttemptRow }) {
  if (!review) return <ReviewUnavailable row={row} />;
  return (
    <div className="stack">
      <Card title="Model interactions and tool activity"><Json value={review.model_interactions ?? { unavailable: true }} /></Card>
      <Card title="Pipeline trace"><Json value={review.pipeline ?? { unavailable: true }} /></Card>
      <Card title="Attempt outcome"><Json value={review.attempt_outcome ?? { unavailable: true }} /></Card>
    </div>
  );
}

function ReviewSection({ review, row, section }: { review: Record<string, unknown> | null; row: AttemptRow; section: string }) {
  if (!review) return <ReviewUnavailable row={row} />;
  return <Json value={review[section] ?? { unavailable: true }} />;
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
  return <span className={`status ${value}`}>{value}</span>;
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return <section className="card"><h3>{title}</h3>{children}</section>;
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

function compact(value: unknown) {
  const text = JSON.stringify(value) ?? String(value);
  return text.length > 72 ? `${text.slice(0, 69)}…` : text;
}

function formatSeconds(value: number | null | undefined) {
  return value == null ? "unavailable" : `${value.toFixed(value >= 10 ? 1 : 2)} s`;
}

function formatRate(value: number | null | undefined) {
  return value == null ? "unavailable" : `${value.toFixed(2)} runs/min`;
}

function formatCount(value: number | null | undefined) {
  return value == null ? "unavailable" : String(value);
}
