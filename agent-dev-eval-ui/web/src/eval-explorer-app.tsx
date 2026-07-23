import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import type {
  AttemptRow,
  EvidenceView,
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
};

const pageSize = 100;
const reviewTabs = ["evaluation", "evidence", "execution"] as const;

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
  const initialTab = initial.get("tab");
  const [tab, setTab] = useState(
    reviewTabs.includes(initialTab as (typeof reviewTabs)[number]) ? initialTab! : "evaluation",
  );

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
    })) {
      if (value) url.searchParams.set(key, String(value));
      else url.searchParams.delete(key);
    }
    window.history.replaceState(null, "", url);
  }, [runId, executionId, state, search, field, sliceKey, offset, tab]);

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
          <h1>Eval Explorer</h1>
        </div>
        <div className="header-actions">
          <label className="run-select-wrap">
            <span>Evaluation run</span>
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
          </label>
        </div>
      </header>

      {runs.error ? <QueryError error={runs.error} /> : null}
      {!runId ? <div className="welcome">Choose a retained schema-v1 run to explore its results and evidence.</div> : null}

      {runId ? (
        <>
          <section className="run-bar">
            <RunFact label="Benchmark" value={`${selectedRun?.benchmark_key ?? "Unknown"} v${selectedRun?.benchmark_version ?? "—"}`} />
            <RunFact label="Model" value={selectedRun?.model ?? "Unknown"} />
            <RunFact label="Reasoning" value={selectedRun?.reasoning_effort ?? "—"} />
            <RunFact label="Attempts" value={`${selectedRun?.recorded_attempts ?? 0}/${selectedRun?.planned_attempts ?? 0}`} />
            <RunFact label="Review" value={selectedRun?.review_status ?? "Unknown"} />
          </section>

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
                  {tab === "evaluation" ? <Evaluation row={detail.data.row} /> : null}
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

function Evaluation({ row }: { row: AttemptRow }) {
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
      <section className="review-status-strip" aria-label="Attempt status">
        <ReviewFact label="Execution" value={row.execution_status} />
        <ReviewFact label="Output contract" value={row.output_contract_status} />
        <ReviewFact label="Scoring" value={row.scoring_status} />
        <ReviewFact label="Stability" value={row.flaky ? "Flaky" : "Stable"} />
      </section>
    </div>
  );
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

function humanize(value: string) {
  if (!value) return "—";
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
