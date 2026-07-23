import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Loader2,
  Search,
  StickyNote,
  XCircle,
} from "lucide-react";
import { api } from "./api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Select } from "./components/ui/select";
import { cn } from "./lib/utils";
import type {
  AccuracyMetric,
  AttemptRow,
  BenchmarkContext,
  CostDistribution,
  CostSummary,
  EvidenceView,
  PerformanceSummary,
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
  const performance = useQuery({
    queryKey: ["performance", runId],
    queryFn: () => api<PerformanceSummary>(
      `/runs/${encodeURIComponent(runId)}/performance`,
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
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center border-b bg-card/95 shadow-sm backdrop-blur-md supports-[backdrop-filter]:bg-card/80">
        <div className="flex h-full shrink-0 items-center gap-3 border-r px-5">
          <div
            aria-hidden="true"
            className="grid size-8 place-items-center rounded-md bg-foreground font-heading text-[11px] font-bold tracking-tight text-background"
          >
            MI
          </div>
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight">MeshInsights</div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Agent Workbench
            </div>
          </div>
        </div>
        <div className="min-w-0 flex-1 px-5 leading-tight max-[900px]:hidden">
          <div className="truncate text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {adapter.contextLabel ?? "Evaluation review"}
          </div>
          <h1 className="mt-0.5 truncate text-sm font-semibold tracking-tight">
            {runId ? "Run analysis" : "Evaluation results"}
          </h1>
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
        <main className="mx-auto max-w-2xl px-4 py-8">
          <EmptyState title="Evaluation run unavailable">
            <span>This run does not exist locally or may have been permanently deleted.</span>
            <Button variant="outline" onClick={showOverview} className="mt-2">
              <ArrowLeft className="size-3.5" />
              Back to evaluation results
            </Button>
          </EmptyState>
        </main>
      ) : null}

      {runId && runs.isSuccess && !runUnavailable ? (
        <>
          <section className="flex flex-wrap items-center justify-between gap-4 border-b bg-card px-5 py-3">
            <div className="flex min-w-0 items-center gap-4">
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label="Back to evaluation results"
                onClick={showOverview}
              >
                <ArrowLeft className="size-3.5" />
                <span>Evaluation results</span>
              </Button>
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Evaluation run
                </div>
                <h2 className="mt-0.5 truncate text-base font-semibold tracking-tight">
                  {selectedRun?.benchmark_key ?? "Benchmark"}{" "}
                  <span className="font-medium text-muted-foreground">
                    v{selectedRun?.benchmark_version ?? "—"}
                  </span>
                </h2>
              </div>
            </div>
            <div className="flex items-center">
              <RunFact label="Model" value={selectedRun?.model ?? "Unknown"} />
              <RunFact label="Reasoning" value={selectedRun?.reasoning_effort ?? "—"} />
              <RunFact label="Attempts" value={`${selectedRun?.recorded_attempts ?? 0}/${selectedRun?.planned_attempts ?? 0}`} />
            </div>
          </section>
          {selectedRun ? (
            <details className="run-summary group border-b bg-muted/40">
              <summary className="flex min-h-[2.65rem] cursor-pointer list-none items-center gap-2.5 px-5 py-2.5 text-[13px] text-muted-foreground [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
                  <BarChart3 className="size-[0.95rem]" />
                  Run metrics
                </span>
                <div className="ml-auto flex items-center gap-5">
                  <CostHighlight cost={selectedRun.cost} />
                </div>
                <ChevronRight className="ml-1 size-[0.95rem] shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
              </summary>
              <div className="grid border-t">
                {selectedRun.accuracy ? (
                  <RunAccuracySummary
                    run={selectedRun}
                    fieldLabels={adapter.evaluationFieldLabels}
                  />
                ) : null}
                <RunCostSummary cost={selectedRun.cost} />
                <RunDurationSummary
                  performance={performance.data}
                  isPending={performance.isPending}
                  error={performance.error}
                />
              </div>
            </details>
          ) : null}

          <main className="mx-5 my-4 grid min-h-[calc(100vh-11rem)] grid-cols-[340px_minmax(0,1fr)] overflow-clip rounded-xl border bg-card shadow-sm max-[900px]:grid-cols-1">
            <aside className="min-w-0 border-r bg-muted/25 max-[900px]:border-b max-[900px]:border-r-0">
              <div className="flex min-h-[3.75rem] items-center justify-between gap-3 border-b bg-card px-3.5">
                <div className="flex items-baseline gap-2">
                  <h2 className="text-sm font-semibold">Attempts</h2>
                  <span className="text-[0.65rem] text-muted-foreground">{attempts.data?.matched ?? 0} results</span>
                </div>
                <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">
                  {state === "all" ? "All states" : humanize(state)}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 border-b bg-card p-3.5">
                <label className="relative col-span-2 block">
                  <span className="sr-only">Search attempts</span>
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    aria-label="Search attempts"
                    placeholder="Search unit or output"
                    value={search}
                    className="pl-8"
                    onChange={(event) => {
                      setSearch(event.target.value);
                      resetAttemptSelection();
                    }}
                  />
                </label>
                <Select
                  aria-label="Attempt state"
                  value={state}
                  onValueChange={(value) => {
                    setState(value);
                    resetAttemptSelection();
                  }}
                >
                  {states.map((item) => (
                    <option key={item} value={item}>
                      {item} ({attempts.data?.facets.states[item] ?? 0})
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Evaluation field"
                  value={field}
                  onValueChange={(value) => {
                    setField(value);
                    resetAttemptSelection();
                  }}
                >
                  <option value="">All fields</option>
                  {attempts.data?.facets.fields.map((item) => <option key={item} value={item}>{item}</option>)}
                </Select>
                <Select
                  aria-label="Evaluation slice"
                  value={sliceKey}
                  onValueChange={(value) => {
                    setSliceKey(value);
                    resetAttemptSelection();
                  }}
                >
                  <option value="">All slices</option>
                  {attempts.data?.facets.slices.map((item) => <option key={item} value={item}>{item}</option>)}
                </Select>
              </div>
              {attempts.error ? <QueryError error={attempts.error} compact /> : null}
              <div className="flex items-center justify-between gap-3 border-b bg-muted/40 px-3.5 py-2.5 text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">
                <span>Attempt queue</span>
                {attempts.data ? <span>{pageRange(attempts.data, offset)}</span> : null}
              </div>
              <div className="max-h-[calc(100vh-15rem)] overflow-y-auto">
                {attempts.isPending ? <LoadingState label="Loading attempts…" compact /> : null}
                {attempts.data && !attempts.data.rows.length ? (
                  <EmptyState className="m-3 min-h-28 p-4">No attempts match these filters.</EmptyState>
                ) : null}
                {attempts.data?.rows.map((row) => (
                  <button
                    type="button"
                    key={row.execution_id}
                    onClick={() => setExecutionId(row.execution_id)}
                    aria-current={row.execution_id === executionId ? "true" : undefined}
                    className={cn(
                      "block w-full border-t border-l-2 border-l-transparent px-3.5 py-3 text-left outline-none transition-colors first:border-t-0 hover:bg-card focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
                      row.execution_id === executionId && "border-l-primary bg-card",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3 text-[0.8125rem] font-semibold">
                      <span className="truncate">{row.unit_id}</span>
                      <Status row={row} />
                    </div>
                    <small className="text-[0.6875rem] text-muted-foreground">
                      {row.example_id} · repetition {row.run_index}
                    </small>
                    <div className="mt-1.5 truncate text-[0.6875rem] text-foreground/70">
                      AI output · {summarizeOutput(row.agent_output)}
                    </div>
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2 border-t p-3">
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Previous attempts"
                  disabled={offset === 0}
                  onClick={() => {
                    setExecutionId("");
                    setOffset(Math.max(0, offset - pageSize));
                  }}
                >
                  <ChevronLeft className="size-3.5" />
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label="Next attempts"
                  disabled={!attempts.data || offset + attempts.data.rows.length >= attempts.data.matched}
                  onClick={() => {
                    setExecutionId("");
                    setOffset(offset + pageSize);
                  }}
                >
                  Next
                  <ChevronRight className="size-3.5" />
                </Button>
              </div>
            </aside>

            <article className="min-w-0 bg-card">
              {!executionId && !attempts.isPending ? (
                <EmptyState className="m-5 min-h-40">No attempt is selected.</EmptyState>
              ) : null}
              {detail.isPending && executionId ? <LoadingState label="Loading attempt review…" /> : null}
              {detail.error ? <QueryError error={detail.error} /> : null}
              {detail.data ? (
                <>
                  <div className="flex min-h-[4.8rem] items-center justify-between gap-4 border-b bg-card px-5 py-3.5">
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                        Attempt review
                      </div>
                      <h2 className="mt-0.5 truncate text-[1.05rem] font-semibold tracking-tight">
                        {detail.data.row.unit_id}
                      </h2>
                      <p className="mt-0.5 text-[0.7rem] text-muted-foreground">
                        {detail.data.row.example_id} · repetition {detail.data.row.run_index}
                      </p>
                    </div>
                    <Status row={detail.data.row} />
                  </div>
                  <nav aria-label="Attempt review sections" className="flex flex-wrap gap-1 border-b px-5">
                    {[
                      ["evaluation", "AI output"],
                      ["evidence", "Evidence"],
                      ["execution", "Execution"],
                    ].map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        aria-current={tab === key ? "page" : undefined}
                        onClick={() => setTab(key)}
                        className={cn(
                          "border-b-2 border-transparent px-3 py-2.5 text-[0.8125rem] font-medium text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
                          tab === key && "border-primary font-semibold text-primary",
                        )}
                      >
                        {label}
                      </button>
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
                    evidence.isPending ? (
                      <EmptyState className="m-5 min-h-40">Loading and verifying frozen evidence…</EmptyState>
                    ) : evidence.error ? (
                      <QueryError error={evidence.error} />
                    ) : evidence.data ? (
                      <EvidenceDisplay evidence={evidence.data} />
                    ) : null
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
    <main className="mx-auto grid max-w-[1600px] gap-4 px-9 py-8 max-[900px]:px-4 max-[900px]:py-4">
      <section className="flex flex-wrap items-end justify-between gap-8 py-1">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Evaluation runs
          </div>
          <h2 className="mt-0.5 text-[clamp(1.65rem,3vw,2.35rem)] font-bold tracking-tight">
            Overall evaluation results
          </h2>
          <p className="mt-1.5 max-w-3xl text-[0.8125rem] leading-relaxed text-muted-foreground">
            Review recent detail or compare meaningful elevated results, then open a run to inspect units and evidence.
          </p>
        </div>
        <div className="grid min-w-32 gap-0.5 border-l pl-5 text-right max-[900px]:border-l-0 max-[900px]:pl-0 max-[900px]:text-left">
          <strong className="font-heading text-[1.75rem] leading-none">{filteredRuns.length}</strong>
          <span className="text-[0.6875rem] uppercase text-muted-foreground">
            {filteredRuns.length === 1 ? "run shown" : "runs shown"}
          </span>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="border-b px-4 py-3.5">
          <h3 className="text-[0.95rem] font-semibold">Results by run</h3>
          <p className="mt-0.5 max-w-3xl text-[0.8125rem] leading-relaxed text-muted-foreground">
            Select any row to inspect its attempts and retained evidence.
          </p>
        </div>
        <section
          aria-label="Evaluation result table controls"
          className="grid grid-cols-[minmax(220px,1.6fr)_repeat(4,minmax(130px,1fr))_auto] items-end gap-3 border-b bg-muted p-3.5 max-[1100px]:grid-cols-2 max-[560px]:grid-cols-1"
        >
          <label className="grid min-w-0 gap-1">
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Search runs</span>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                aria-label="Search evaluation runs"
                placeholder="Run ID, model, benchmark, pipeline…"
                value={search}
                onChange={(event) => onSearch(event.target.value)}
                className="pl-8"
              />
            </div>
          </label>
          <label className="grid min-w-0 gap-1">
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Lifecycle</span>
            <Select aria-label="Filter by lifecycle" value={lifecycleFilter} onValueChange={onLifecycleFilter}>
              <option value="">All evals</option>
              <option value="working">Not elevated</option>
              <option value="retained">Elevated</option>
            </Select>
          </label>
          <label className="grid min-w-0 gap-1">
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Model</span>
            <Select aria-label="Filter by model" value={modelFilter} onValueChange={onModelFilter}>
              <option value="">All models</option>
              {models.map((model) => <option key={model} value={model}>{model}</option>)}
            </Select>
          </label>
          <label className="grid min-w-0 gap-1">
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Reasoning</span>
            <Select aria-label="Filter by reasoning effort" value={reasoningFilter} onValueChange={onReasoningFilter}>
              <option value="">All efforts</option>
              {reasoningEfforts.map((effort) => <option key={effort} value={effort}>{humanize(effort)}</option>)}
            </Select>
          </label>
          <label className="grid min-w-0 gap-1">
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Sort by</span>
            <Select aria-label="Sort evaluation runs" value={activeSort} onValueChange={onSort}>
              {sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </Select>
          </label>
          {controlsChanged ? (
            <Button
              variant="outline"
              size="sm"
              className="self-end"
              onClick={() => {
                onSearch("");
                onModelFilter("");
                onReasoningFilter("");
                onLifecycleFilter("");
                onSort(defaultRunSort);
              }}
            >
              Reset
            </Button>
          ) : null}
        </section>
        {filteredRuns.length ? (
          <div className="overflow-x-auto overscroll-x-contain">
            <table aria-label="Evaluation runs and metrics" className="w-full min-w-[1040px] border-collapse text-[0.75rem]">
              <thead>
                <tr>
                  <th className="min-w-[250px] border-b bg-muted px-3.5 py-2.5 text-left align-bottom text-[0.625rem] font-bold uppercase leading-snug tracking-wide text-muted-foreground">
                    Run inputs
                  </th>
                  {metricColumns.map((column) => (
                    <th key={column.key} className="border-b bg-muted px-3.5 py-2.5 text-left align-bottom text-[0.625rem] font-bold uppercase leading-snug tracking-wide text-muted-foreground">
                      {column.label}
                    </th>
                  ))}
                  <th className="border-b bg-muted px-3.5 py-2.5 text-left align-bottom text-[0.625rem] font-bold uppercase leading-snug tracking-wide text-muted-foreground">
                    Cost
                  </th>
                  <th className="border-b bg-muted px-3.5 py-2.5 text-left align-bottom text-[0.625rem] font-bold uppercase leading-snug tracking-wide text-muted-foreground">
                    <span className="sr-only">Open run</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredRuns.map((run) => (
                  <tr
                    key={run.run_id}
                    className="group cursor-pointer transition-colors hover:bg-accent/40"
                    onClick={() => onSelectRun(run.run_id)}
                  >
                    <td className="border-t px-3.5 py-3 align-middle">
                      <div className="grid gap-0.5">
                        <button
                          type="button"
                          aria-label={`Open evaluation run ${run.run_id}`}
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelectRun(run.run_id);
                          }}
                          className="w-fit max-w-full overflow-hidden text-ellipsis whitespace-nowrap border-0 bg-transparent p-0 text-left text-[0.75rem] font-bold text-foreground outline-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {run.model ?? "Unknown model"}
                        </button>
                        {run.lifecycle_state === "retained" ? (
                          <Badge variant="primary" className="w-fit">Elevated</Badge>
                        ) : null}
                        <span className="text-muted-foreground">{humanize(run.reasoning_effort ?? "unspecified")} reasoning</span>
                        <small className="text-muted-foreground">
                          {formatRunDate(run.created_at_utc)} · {run.recorded_attempts}/{run.planned_attempts} attempts
                        </small>
                        <code title={run.run_id} className="mt-1 w-fit text-[0.625rem] text-foreground/65">
                          {shortRunId(run.run_id)}
                        </code>
                      </div>
                    </td>
                    {metricColumns.map((column) => <MetricCell key={column.key} metric={column.get(run)} />)}
                    <CostCell cost={run.cost} />
                    <td className="border-t px-3.5 py-3 text-center align-middle text-muted-foreground transition-colors group-hover:translate-x-0.5 group-hover:text-primary" aria-hidden="true">
                      <ChevronRight className="inline size-4" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState className="m-3.5 min-h-36">
            {runs.length ? "No evaluation runs match these controls." : "No evaluation runs are available yet."}
          </EmptyState>
        )}
      </section>
    </main>
  );
}

function MetricCell({ metric }: { metric: AccuracyMetric | null }) {
  return (
    <td className="min-w-[105px] border-t px-3.5 py-3 align-middle">
      <strong className="block font-heading text-[0.9rem]">{formatAccuracy(metric)}</strong>
      <small className="mt-0.5 block text-[0.625rem] text-muted-foreground">
        {metric ? `${metric.correct_runs}/${metric.evaluated_runs}` : "No data"}
      </small>
    </td>
  );
}

function CostCell({ cost }: { cost?: CostSummary | null }) {
  const rows = costRows(cost);
  if (!cost || !rows.length) {
    return (
      <td className="min-w-[230px] border-t px-3.5 py-3 align-middle">
        <strong className="block font-heading text-[0.9rem]">—</strong>
        <small className="mt-0.5 block text-[0.625rem] text-muted-foreground">Unavailable</small>
      </td>
    );
  }
  return (
    <td className="min-w-[230px] border-t px-3.5 py-3 align-middle">
      {rows.map((row, index) => (
        <div key={row.currency} className={cn(index > 0 && "mt-2 border-t pt-2")}>
          <strong className="block font-heading text-[0.9rem]">{formatCost(row.total, row.currency)}</strong>
          <small className="mt-0.5 block text-[0.625rem] text-muted-foreground">
            Mean {formatCost(row.distribution?.average, row.currency)}
            {" · "}P5 {formatCost(row.distribution?.p5, row.currency)}
            {" · "}P95 {formatCost(row.distribution?.p95, row.currency)}
          </small>
        </div>
      ))}
      <small className="mt-1.5 block text-[0.625rem] text-muted-foreground">{costCoverageLabel(cost)}</small>
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
    <section aria-label="Run accuracy summary" className="border-b bg-muted/30 px-5 py-4">
      <div className="mb-2.5 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Evaluation statistics</div>
          <h2 className="mt-0.5 text-sm font-semibold tracking-tight">Run accuracy</h2>
        </div>
        <span className="text-[0.65rem] text-muted-foreground">Correct / evaluated</span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] overflow-hidden rounded-lg border bg-card">
        {metrics.map((column) => {
          const metric = column.get(run);
          return (
            <div className="grid min-w-0 gap-1 border-r px-3.5 py-3 last:border-r-0" key={column.key}>
              <span className="min-h-[2.2em] text-[0.65rem] font-semibold uppercase leading-tight text-muted-foreground">{column.label}</span>
              <strong className="font-heading text-[1.1rem]">{formatAccuracy(metric)}</strong>
              <small className="text-[0.625rem] text-muted-foreground">{metric ? `${metric.correct_runs} / ${metric.evaluated_runs}` : "No data"}</small>
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
    <span className="grid gap-0.5 text-right">
      <strong className="font-heading text-[0.85rem] text-foreground">{formatCost(primary.total, primary.currency)}</strong>
      <small className="text-[0.625rem] text-muted-foreground">{rows.length === 1 ? "eval cost" : `eval cost · ${rows.length} currencies`}</small>
    </span>
  );
}

function RunCostSummary({ cost }: { cost?: CostSummary | null }) {
  const rows = costRows(cost);
  return (
    <section aria-label="Run cost summary" className="bg-muted/20 px-5 py-4">
      <div className="mb-2.5 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Pricing statistics</div>
          <h2 className="mt-0.5 text-sm font-semibold tracking-tight">Run cost</h2>
        </div>
        <span className="text-[0.65rem] text-muted-foreground">{cost ? costCoverageLabel(cost) : "Cost information unavailable"}</span>
      </div>
      {rows.length ? (
        <div className="grid gap-2.5">
          {rows.map((row) => (
            <section key={row.currency} className="overflow-hidden rounded-lg border bg-card">
              <div className="flex items-center justify-between border-b px-3.5 py-2.5">
                <strong className="text-[0.7rem] tracking-wide">{row.currency}</strong>
                <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">{costStatus(cost)}</span>
              </div>
              <div className="grid grid-cols-4 max-[560px]:grid-cols-1">
                <CostMetric label="Overall eval" value={formatCost(row.total, row.currency)} />
                <CostMetric label="Mean / unit" value={formatCost(row.distribution?.average, row.currency)} />
                <CostMetric label="P5 / unit" value={formatCost(row.distribution?.p5, row.currency)} />
                <CostMetric label="P95 / unit" value={formatCost(row.distribution?.p95, row.currency)} />
              </div>
            </section>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed px-3.5 py-3 text-[0.75rem] text-muted-foreground">
          No usable cost observations were stored for this run.
        </div>
      )}
    </section>
  );
}

function CostMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 border-r px-3.5 py-3 last:border-r-0 max-[560px]:border-b max-[560px]:border-r-0 max-[560px]:last:border-b-0">
      <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
      <strong className="font-heading text-[1rem]">{value}</strong>
    </div>
  );
}

function RunDurationSummary({
  performance,
  isPending,
  error,
}: {
  performance?: PerformanceSummary;
  isPending: boolean;
  error: Error | null;
}) {
  const distribution = performance?.availability === "available"
    ? performance.summary.run_duration_seconds
    : null;
  const coverage = performance?.availability === "available"
    ? `${distribution?.count ?? 0}/${performance.recorded_executions} runs timed`
    : "Timing information unavailable";

  return (
    <section aria-label="Run duration summary" className="border-t bg-muted/20 px-5 py-4">
      <div className="mb-2.5 flex items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Performance statistics</div>
          <h2 className="mt-0.5 text-sm font-semibold tracking-tight">Run duration</h2>
        </div>
        <span className="text-[0.65rem] text-muted-foreground">{coverage}</span>
      </div>
      {isPending ? (
        <div className="rounded-lg border border-dashed px-3.5 py-3 text-[0.75rem] text-muted-foreground">
          Loading duration observations…
        </div>
      ) : error ? (
        <div className="rounded-lg border border-dashed px-3.5 py-3 text-[0.75rem] text-muted-foreground">
          Duration information could not be loaded.
        </div>
      ) : performance?.availability === "available" && distribution?.count ? (
        <div className="overflow-hidden rounded-lg border bg-card">
          <div className="grid grid-cols-4 max-[560px]:grid-cols-1">
            <CostMetric label="Elapsed eval" value={formatDuration(performance.summary.evaluation_wall_time_seconds)} />
            <CostMetric label="Mean / run" value={formatDuration(distribution.mean)} />
            <CostMetric label="P5 / run" value={formatDuration(distribution.p5)} />
            <CostMetric label="P95 / run" value={formatDuration(distribution.p95)} />
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed px-3.5 py-3 text-[0.75rem] text-muted-foreground">
          {performance?.availability === "unavailable"
            ? performance.reason
            : "No usable duration observations were stored for this run."}
        </div>
      )}
    </section>
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
  const columns: MetricColumn[] = [];
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
    <div className="grid gap-4 px-5 py-5 pb-10">
      <section className="flex flex-wrap items-end justify-between gap-6 py-1">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Evaluation</div>
          <h3 className="mt-0.5 text-base font-semibold tracking-tight">Expected and actual output</h3>
        </div>
        <p className="max-w-lg text-right text-[0.75rem] leading-relaxed text-muted-foreground">
          Compare scored fields, then open the evidence when a result needs investigation.
        </p>
      </section>
      <section aria-label="AI output comparison" className="overflow-hidden rounded-lg border shadow-sm">
        <div
          aria-hidden="true"
          className="grid grid-cols-[minmax(110px,0.7fr)_minmax(140px,1fr)_minmax(180px,1.3fr)_88px] items-center gap-4 bg-muted px-4 py-2.5 text-[0.675rem] font-semibold uppercase tracking-wide text-muted-foreground"
        >
          <span>Field</span><span>Benchmark</span><span>AI output</span><span>Result</span>
        </div>
        {fields.map((fieldName) => {
          const result = fieldResult(row.evaluations[fieldName]);
          return (
            <div
              key={fieldName}
              className="grid grid-cols-[minmax(110px,0.7fr)_minmax(140px,1fr)_minmax(180px,1.3fr)_88px] items-start gap-4 border-t px-4 py-3.5 text-[0.8125rem]"
            >
              <strong className="font-semibold">{humanize(fieldName)}</strong>
              <span className="min-w-0 break-words leading-relaxed">{displayValue(row.benchmark_labels[fieldName])}</span>
              <AiOutputValue value={row.agent_output[fieldName]} />
              <ComparisonResultBadge result={result} />
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

function ComparisonResultBadge({ result }: { result: boolean | null }) {
  if (result === true) {
    return (
      <Badge variant="success" className="w-fit gap-1">
        <CheckCircle2 className="size-3" />
        Match
      </Badge>
    );
  }
  if (result === false) {
    return (
      <Badge variant="destructive" className="w-fit gap-1">
        <XCircle className="size-3" />
        Mismatch
      </Badge>
    );
  }
  return <Badge variant="neutral" className="w-fit">Review</Badge>;
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
    <details open className="benchmark-context group overflow-hidden rounded-lg border">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 bg-muted/60 px-4 py-3.5 [&::-webkit-details-marker]:hidden">
        <div className="flex items-center gap-2.5">
          <StickyNote className="size-4 text-primary" />
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Supporting context</div>
            <h3 className="mt-0.5 text-[0.95rem] font-semibold tracking-tight">Labeler notes and verification</h3>
          </div>
        </div>
        <span className="flex items-center gap-2.5">
          {verification ? (
            <span className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Verified</span>
          ) : null}
          <ChevronRight className="size-[0.95rem] text-muted-foreground transition-transform group-open:rotate-90" />
        </span>
      </summary>

      <div className="grid grid-cols-2 border-t max-[900px]:grid-cols-1">
        <section className="min-w-0 p-4">
          <h4 className="mb-2.5 text-[0.78rem] font-semibold">Labeler notes</h4>
          {notes.length ? (
            <div className="grid gap-2.5">
              {notes.map((note) => (
                <article className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1.5 rounded-md border bg-card p-3" key={note.review_event_id}>
                  <div className="grid min-w-0 gap-0.5">
                    <strong className="text-[0.75rem] font-semibold">{note.reviewer_display_name}</strong>
                    <span className="text-[0.65rem] text-muted-foreground">{humanize(note.reviewer_project_role)} · {formatRunDate(note.submitted_at)}</span>
                  </div>
                  {note.selected_for_publication ? (
                    <span className="justify-self-end text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">Selected label</span>
                  ) : null}
                  <p className="col-span-2 whitespace-pre-wrap text-[0.75rem] leading-relaxed text-foreground/85">{note.explanation}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="text-[0.75rem] leading-relaxed text-muted-foreground">No labeler notes were attached to the published reviewer revisions.</p>
          )}
        </section>

        <section className="min-w-0 border-l p-4 max-[900px]:border-l-0 max-[900px]:border-t">
          <h4 className="mb-2.5 text-[0.78rem] font-semibold">{verification ? verificationSourceLabel(verification.source) : "Customer verification"}</h4>
          {verification ? (
            <>
              <p className="text-[0.75rem] leading-relaxed text-muted-foreground">
                The following frozen benchmark labels were covered by this verification.
              </p>
              <dl className="mt-2.5 grid grid-cols-2 gap-2">
                {Object.entries(benchmarkLabels).map(([key, value]) => (
                  <div className="min-w-0 rounded-md bg-muted px-2.5 py-2" key={key}>
                    <dt className="text-[0.625rem] text-muted-foreground">{fieldLabels[key] ?? humanize(key)}</dt>
                    <dd className="mt-0.5 break-words text-[0.75rem] font-semibold leading-tight">{displayValue(value)}</dd>
                  </div>
                ))}
              </dl>
              <VerificationDetails verification={verification} schemas={verificationSchemas} />
            </>
          ) : (
            <p className="text-[0.75rem] leading-relaxed text-muted-foreground">No customer or onsite verification was frozen with this benchmark example.</p>
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
    <div className="mt-3.5 border-t pt-3">
      {verification.note ? <p className="mb-2.5 text-[0.75rem] leading-relaxed">{verification.note}</p> : null}
      {schema ? (
        <>
          <div className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted-foreground">{schema.title} · Immutable source record</div>
          <dl className="mt-2.5 grid grid-cols-2 gap-2">
            {schema.fields.flatMap((field) => {
              const value = fields[field.key];
              if (value == null || value === "") return [];
              return (
                <div
                  className={cn("min-w-0 rounded-md bg-muted px-2.5 py-2", field.value_type === "long_text" && "col-span-2")}
                  key={field.key}
                >
                  <dt className="text-[0.625rem] text-muted-foreground">{field.label}</dt>
                  <dd className="mt-0.5 break-words text-[0.75rem] font-semibold leading-tight">
                    {field.value_type === "timestamp" && typeof value === "string" ? formatRunDate(value) : displayValue(value)}
                  </dd>
                </div>
              );
            })}
          </dl>
        </>
      ) : null}
      {verification.recorded_at ? (
        <small className="mt-2.5 block text-[0.625rem] text-muted-foreground">Recorded {formatRunDate(verification.recorded_at)}</small>
      ) : null}
    </div>
  );
}

function verificationSourceLabel(source: "direct_observation" | "operator_feedback") {
  return source === "operator_feedback" ? "Customer verified" : "Verified by direct observation";
}

function Execution({ review, row }: { review: Record<string, unknown> | null; row: AttemptRow }) {
  if (!review) return <ReviewUnavailable row={row} />;
  return (
    <div className="grid gap-3.5 px-5 py-5 pb-10">
      <section aria-label="Attempt status" className="grid grid-cols-4 overflow-hidden rounded-lg border bg-muted max-[560px]:grid-cols-2">
        <ReviewFact label="Execution" value={row.execution_status} />
        <ReviewFact label="Output contract" value={row.output_contract_status} />
        <ReviewFact label="Scoring" value={row.scoring_status} />
        <ReviewFact label="Stability" value={row.flaky ? "Flaky" : "Stable"} />
      </section>
      <p className="max-w-lg text-[0.75rem] leading-relaxed text-muted-foreground">
        Technical trace data is collapsed by default so it does not compete with output and evidence review.
      </p>
      <CollapsibleJson title="Model interactions and tool activity" value={review.model_interactions ?? { unavailable: true }} />
      <CollapsibleJson title="Pipeline trace" value={review.pipeline ?? { unavailable: true }} />
      <CollapsibleJson title="Attempt outcome" value={review.attempt_outcome ?? { unavailable: true }} />
    </div>
  );
}

function CollapsibleJson({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="group overflow-hidden rounded-lg border bg-card">
      <summary className="cursor-pointer px-3.5 py-3 text-[0.8125rem] font-semibold group-open:border-b [&::-webkit-details-marker]:hidden">
        {title}
      </summary>
      <Json value={value} className="max-h-96 rounded-none" />
    </details>
  );
}

function ReviewFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5 border-l px-3.5 py-2.5 first:border-l-0">
      <small className="text-[0.65rem] uppercase tracking-wide text-muted-foreground">{label}</small>
      <strong className="text-[0.75rem] font-semibold">{humanize(value)}</strong>
    </div>
  );
}

function AiOutputValue({ value }: { value: unknown }) {
  const record = asRecord(value);
  const confidence = typeof record?.confidence === "string" ? record.confidence : null;
  const explanation = typeof record?.explanation === "string" ? record.explanation : null;
  return (
    <div className="grid min-w-0 gap-1">
      <span className="break-words font-medium leading-relaxed">{displayValue(value)}</span>
      {confidence ? <small className="text-[0.6875rem] text-muted-foreground">{confidence} confidence</small> : null}
      {explanation ? (
        <details className="mt-0.5">
          <summary className="w-fit cursor-pointer text-[0.7rem] font-semibold text-primary [&::-webkit-details-marker]:hidden">
            Model rationale
          </summary>
          <p className="mt-1.5 text-[0.75rem] font-normal leading-relaxed text-foreground/80">{explanation}</p>
        </details>
      ) : null}
    </div>
  );
}

function ReviewUnavailable({ row }: { row: AttemptRow }) {
  const reason = row.review_unavailable_reason;
  return (
    <EmptyState className="m-5 min-h-40">
      Detailed review unavailable ({reason?.code ?? "absent"})
      {reason?.message ? `: ${reason.message}` : "."}
    </EmptyState>
  );
}

function Status({ row }: { row: AttemptRow }) {
  const value = row.execution_status === "failed" ? "failed" : row.complete_evaluation_correct === true ? "correct" : row.complete_evaluation_correct === false ? "incorrect" : row.scoring_status;
  const isCorrect = value === "correct";
  const isNegative = value === "incorrect" || value === "failed";
  const variant = isCorrect ? "success" : isNegative ? "destructive" : "neutral";
  const Icon = isCorrect ? CheckCircle2 : isNegative ? XCircle : Clock;
  return (
    <Badge variant={variant} className="w-fit shrink-0 gap-1 whitespace-nowrap">
      <Icon className="size-3" />
      {value}
    </Badge>
  );
}

function RunFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 max-w-[220px] gap-0.5 border-l px-4 first:border-l-0 first:pl-0">
      <small className="text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</small>
      <strong className="truncate text-[13px] font-semibold">{value}</strong>
    </div>
  );
}

function EmptyState({
  title,
  children,
  className,
}: {
  title?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid min-h-40 place-items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground", className)}>
      {title ? <strong className="text-base font-semibold text-foreground">{title}</strong> : null}
      {children}
    </div>
  );
}

function Json({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn("m-0 max-h-[32rem] overflow-auto whitespace-pre-wrap break-words rounded-md bg-[#151b20] p-3 font-mono text-[0.75rem] leading-relaxed text-[#dce8ed]", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function QueryError({ error, compact = false }: { error: Error; compact?: boolean }) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2.5 rounded-md border border-destructive/30 bg-destructive/10 px-3.5 py-3 text-sm text-destructive",
        compact ? "m-2.5" : "m-4",
      )}
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span>{error.message}</span>
    </div>
  );
}

function LoadingState({ label, compact = false }: { label: string; compact?: boolean }) {
  return (
    <div
      role="status"
      className={cn(
        "flex items-center justify-center gap-2.5 text-sm text-muted-foreground",
        compact ? "min-h-28" : "m-4 min-h-40",
      )}
    >
      <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
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

function formatDuration(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  if (value < 1) return `${Math.round(value * 1_000)} ms`;
  if (value < 60) {
    return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)} s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
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
