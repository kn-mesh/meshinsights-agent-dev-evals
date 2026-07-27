// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvalExplorerApp } from "@eval-ui/eval-explorer-app";
import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";

const run = {
  run_id: "run-a",
  lifecycle_state: "working" as const,
  result_status: "materialized",
  agent_version_id: "av-a",
  pipeline_path: "pipeline.ppln",
  benchmark_key: "benchmark-a",
  benchmark_version: 1,
  model: "provider:model",
  reasoning_effort: "low",
  planned_attempts: 1201,
  recorded_attempts: 1201,
  review_status: "complete",
  created_at_utc: "2026-07-23T10:00:00Z",
  accuracy: {
    complete_evaluation: { accuracy: 0.7, correct_runs: 7, evaluated_runs: 10 },
    by_field: {
      classification: {
        accuracy: 0.8,
        correct_runs: 8,
        evaluated_runs: 10,
        by_confidence: {
          High: { accuracy: 0.875, correct_runs: 7, evaluated_runs: 8 },
          Low: { accuracy: 0.5, correct_runs: 1, evaluated_runs: 2 },
        },
      },
      root_cause: {
        accuracy: 0.6,
        correct_runs: 3,
        evaluated_runs: 5,
        by_confidence: {
          High: { accuracy: 0.75, correct_runs: 3, evaluated_runs: 4 },
          Low: { accuracy: 0, correct_runs: 0, evaluated_runs: 1 },
        },
      },
    },
  },
  cost: {
    attempts_with_cost_observations: 1201,
    recorded_attempts: 1201,
    units_with_complete_cost_observations: 1201,
    units_with_partial_pricing: 0,
    units_without_usable_cost_information: 0,
    status_counts: { estimated_complete: 1201 },
    actual_by_currency: {},
    estimated_by_currency: { USD: 12.3456 },
    complete_unit_cost_by_currency: {
      USD: {
        count: 1201,
        total: 12.3456,
        average: 0.010279,
        p5: 0.004321,
        p95: 0.023456,
      },
    },
  },
};

const row = {
  example_id: "example-a",
  unit_id: "unit-a",
  run_index: 1,
  execution_id: "execution-a.1",
  execution_status: "completed",
  output_contract_status: "valid",
  scoring_status: "scored",
  complete_evaluation_correct: false,
  benchmark_labels: { classification: "Failure" },
  agent_output: { classification: { value: "Healthy" } },
  evaluations: { classification: { correct: false } },
  slice_keys: ["priority"],
  flaky: false,
  review_status: "complete",
};

const adapter: UseCaseAdapter = {
  EvidenceDisplay: ({ evidence }: { evidence: EvidenceView }) => <div>Evidence for {evidence.example.example_id}</div>,
  contextLabel: "Reference use case / Evaluation",
  evaluationFieldLabels: {
    classification: "Failure classification",
    root_cause: "Root cause classification",
  },
  sourceVerificationSchemas: [{
    schema_key: "spirax_customer_verification",
    version: "1",
    title: "Customer verification",
    fields: [
      { key: "failure_cause", label: "Customer outcome", value_type: "text" },
      { key: "action_to_resolve", label: "Action taken", value_type: "text" },
      { key: "resolution_notes", label: "Resolution notes", value_type: "long_text" },
    ],
  }],
};

const benchmarkContext = {
  availability: "available",
  reviewer_coverage: [{
    review_event_id: "review-a",
    label_revision: 2,
    reviewer_user_id: "reviewer-user-a",
    reviewer_display_name: "Alex Labeler",
    reviewer_project_role: "domain_reviewer",
    submitted_at: "2026-07-20T09:30:00Z",
    is_selected_label_revision: true,
  }],
  verification: {
    source: "operator_feedback",
    note: "Confirmed during the customer review.",
    recorded_at: "2026-07-21T11:00:00Z",
    source_content_sha256: "f".repeat(64),
    context_schema_key: "spirax_customer_verification",
    context_schema_version: "1",
    source_fields: {
      failure_cause: "Trap failed closed",
      action_to_resolve: "Replaced the trap",
      resolution_notes: "Normal steam flow returned after replacement.",
    },
  },
} as const;

const performance = {
  availability: "available",
  recorded_executions: 1201,
  summary: {
    evaluation_wall_time_seconds: 404.1,
    throughput_runs_per_minute: 10.4,
    run_duration_seconds: {
      count: 1201,
      minimum: 4.1,
      maximum: 134.5,
      mean: 18.9,
      median: 9.1,
      p5: 6.2,
      p95: 130.2,
    },
  },
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  Element.prototype.scrollIntoView = vi.fn();
  window.history.replaceState(null, "", "/");
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("EvalExplorerApp workflow", () => {
  it("searches, filters, sorts, and drills into a run from its selectable row", async () => {
    const secondRun = {
      ...run,
      run_id: "run-b",
      lifecycle_state: "retained" as const,
      model: "provider:other-model",
      reasoning_effort: "high",
      created_at_utc: "2026-07-22T10:00:00Z",
      accuracy: {
        ...run.accuracy,
        complete_evaluation: { accuracy: 0.2, correct_runs: 2, evaluated_runs: 10 },
        by_field: {
          ...run.accuracy.by_field,
          classification: {
            ...run.accuracy.by_field.classification,
            accuracy: 0.1,
            correct_runs: 1,
            evaluated_runs: 10,
          },
        },
      },
    };
    installFetch((url) => url === "/api/runs" ? { runs: [run, secondRun], findings: [] } : route(url));
    await render();
    await waitFor(() => container.textContent?.includes("Overall evaluation results") === true);

    expect(container.textContent).toContain("Failure classification");
    expect(container.textContent).toContain("Failure classification · High");
    expect(container.textContent).toContain("Root cause classification · High");
    expect(container.textContent).not.toContain("Failure classification · Low");
    expect(container.textContent).not.toContain("Root cause classification · Low");
    expect(container.textContent).not.toContain("Complete evaluation");
    expect(container.textContent).not.toContain("overall accuracy");
    expect(container.textContent).toContain("$12.35");
    expect(container.textContent).toContain("Mean $0.0103");
    expect(container.textContent).toContain("P5 $0.004321");
    expect(container.textContent).toContain("P95 $0.0235");
    expect(container.textContent).toContain("1201/1201 units fully priced");
    expect(container.querySelector(".metric-cards")).toBeNull();
    expect(container.querySelectorAll("tbody tr")).toHaveLength(2);

    await select(byLabel("Filter by lifecycle"), "retained");
    await waitFor(() => container.querySelectorAll("tbody tr").length === 1);
    expect(container.textContent).toContain("Elevated");
    expect(new URL(window.location.href).searchParams.get("lifecycle")).toBe("retained");
    await select(byLabel("Filter by lifecycle"), "");
    expect(container.querySelector('[aria-label="Open evaluation run run-a"]')?.parentElement?.textContent).not.toContain("Working");

    await click(byLabel("Sort by Failure classification"));
    await click(byLabel("Sort by Failure classification"));
    await waitFor(() => container.querySelector("tbody tr button")?.getAttribute("aria-label")?.includes("run-b") === true);
    expect(new URL(window.location.href).searchParams.get("sort")).toBe("field:classification:asc");

    await fill(byLabel("Search evaluation runs"), "run-a");
    await waitFor(() => container.querySelectorAll("tbody tr").length === 1);
    expect(new URL(window.location.href).searchParams.get("q")).toBe("run-a");

    await select(byLabel("Filter by model"), "provider:model");
    const selectedRow = container.querySelector("tbody tr");
    if (!selectedRow) throw new Error("Missing selectable run row.");
    await click(selectedRow);
    await waitFor(() => container.textContent?.includes("Expected and actual output") === true);
    expect(new URL(window.location.href).searchParams.get("run")).toBe("run-a");
    expect(new URL(window.location.href).searchParams.get("execution")).toBe("execution-a.1");
    expect(container.textContent).toContain("Reference use case / Evaluation");
    expect(container.textContent).not.toContain("Spirax Pulse / Evaluation");
    expect(container.querySelector('[aria-label="Evaluation run"]')).toBeNull();

    await click(byLabel("Back to evaluation results"));
    await waitFor(() => container.textContent?.includes("Overall evaluation results") === true);
    expect(new URL(window.location.href).searchParams.get("run")).toBeNull();
    expect(new URL(window.location.href).searchParams.get("q")).toBe("run-a");
  });

  it("restores page state, reaches attempts beyond 1,000, and applies field and slice facets", async () => {
    window.history.replaceState(null, "", "/?run=run-a&offset=900");
    const requested: string[] = [];
    installFetch((url) => {
      requested.push(url);
      if (url.startsWith("/api/runs/run-a/attempts?")) {
        const offset = Number(new URL(url, "http://local").searchParams.get("offset"));
        return attemptsPayload(offset >= 1000 ? { ...row, example_id: "example-after-1000", execution_id: "execution-after-1000.1" } : row);
      }
      if (url.endsWith("/attempts/execution-after-1000.1")) {
        return {
          row: { ...row, example_id: "example-after-1000", execution_id: "execution-after-1000.1" },
          review: { model_interactions: {} },
          benchmark_context: benchmarkContext,
        };
      }
      return route(url);
    });
    await render();
    await waitFor(() => container.textContent?.includes("Showing 901–901") === true);

    await click(byLabel("Next attempts"));
    await waitFor(() => container.textContent?.includes("example-after-1000") === true);
    expect(requested.some((url) => url.includes("offset=1000"))).toBe(true);
    expect(new URL(window.location.href).searchParams.get("offset")).toBe("1000");

    await select(byLabel("Evaluation field"), "classification");
    await waitFor(() => requested.some((url) => url.includes("field=classification")));
    await select(byLabel("Evaluation slice"), "priority");
    await waitFor(() => requested.some((url) => url.includes("field=classification") && url.includes("slice=priority")));
    expect(new URL(window.location.href).searchParams.get("offset")).toBeNull();
  });

  it("keeps an evidence failure inside the evidence tab", async () => {
    window.history.replaceState(null, "", "/?run=run-a&execution=execution-a.1&tab=evidence");
    installFetch((url) => url.includes("/evidence") ? failure("Frozen evidence unavailable") : route(url));
    await render();
    await waitFor(() => container.textContent?.includes("Frozen evidence unavailable") === true);
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("Frozen evidence unavailable");

    await click(button("AI output"));
    await waitFor(() => container.textContent?.includes("Expected and actual output") === true);
    expect(container.textContent).not.toContain("Frozen evidence unavailable");
  });

  it("keeps technical trace secondary while loading run-level duration data", async () => {
    window.history.replaceState(null, "", "/?run=run-a&execution=execution-a.1&tab=execution");
    const requested: string[] = [];
    installFetch((url) => {
      requested.push(url);
      if (url.endsWith("/attempts/execution-a.1")) {
        return {
          row: { ...row, review_status: "unavailable", review_unavailable_reason: { code: "purged" } },
          review: null,
          benchmark_context: benchmarkContext,
        };
      }
      return route(url);
    });
    await render();
    await waitFor(() => container.textContent?.includes("Detailed review unavailable (purged)") === true);
    expect(new URL(window.location.href).searchParams.get("execution")).toBe("execution-a.1");
    expect(requested.some((url) => url.includes("/runs/run-a/performance"))).toBe(true);
    expect(container.textContent).not.toContain("Performance diagnostics");
  });

  it("shows benchmark and AI values without raw JSON walls", async () => {
    window.history.replaceState(null, "", "/?run=run-a&execution=execution-a.1");
    installFetch(route);
    await render();
    await waitFor(() => container.textContent?.includes("Expected and actual output") === true);
    expect(container.textContent).toContain("Failure");
    expect(container.textContent).toContain("Healthy");
    expect(container.textContent).toContain("Mismatch");
    expect(container.textContent).toContain("Run summary");
    expect(container.textContent).toContain("Failure classification accuracy");
    expect(container.textContent).toContain("High confidence");
    expect(container.textContent).toContain("87.5%");
    expect(container.textContent).toContain("Total run cost");
    expect(container.textContent).toContain("Per unit: mean");
    expect(container.textContent).toContain("P5");
    expect(container.textContent).toContain("P95");
    expect(container.textContent).toContain("$12.35");
    expect(container.textContent).toContain("Total run duration");
    expect(container.textContent).toContain("Per run: mean");
    expect(container.textContent).toContain("6m 44s");
    expect(container.textContent).toContain("18.9 s");
    expect(container.textContent).toContain("2m 10s");
    expect(container.textContent).toContain("Alex Labeler");
    expect(container.textContent).toContain("revision 2");
    expect(container.textContent).toContain("Customer verified");
    expect(container.textContent).toContain("Selected label");
    expect(container.textContent).toContain("Trap failed closed");
    expect(container.textContent).toContain("Replaced the trap");
    expect(container.querySelector('[aria-label="Run metrics"]')).not.toBeNull();
    expect(container.querySelector(".benchmark-context")?.hasAttribute("open")).toBe(true);
    expect(container.querySelector("pre")).toBeNull();
  });

  it("labels partial pricing coverage without presenting missing percentiles", async () => {
    const partialRun = {
      ...run,
      cost: {
        ...run.cost,
        units_with_complete_cost_observations: 0,
        units_with_partial_pricing: 1201,
        status_counts: { estimated_partial: 1201 },
        estimated_by_currency: { USD: 8.5 },
        complete_unit_cost_by_currency: {},
      },
    };
    window.history.replaceState(null, "", "/?run=run-a");
    installFetch((url) => url === "/api/runs"
      ? { runs: [partialRun], findings: [] }
      : route(url));
    await render();
    await waitFor(() => container.textContent?.includes("Total run cost") === true);

    expect(container.textContent).toContain("$8.50");
    expect(container.textContent).toContain("0/1201 fully priced · 1201 partial");
    expect(container.textContent).toContain("Partial");
    expect(container.querySelector('[aria-label="Run cost summary"]')?.textContent).toContain("P95 —");
  });

  it("shows cost as unavailable for historical runs without usable observations", async () => {
    const unavailableRun = {
      ...run,
      cost: {
        ...run.cost,
        attempts_with_cost_observations: 1201,
        units_with_complete_cost_observations: 0,
        units_with_partial_pricing: 0,
        units_without_usable_cost_information: 1201,
        status_counts: { unavailable: 1201 },
        estimated_by_currency: {},
        complete_unit_cost_by_currency: {},
      },
    };
    window.history.replaceState(null, "", "/?run=run-a");
    installFetch((url) => url === "/api/runs"
      ? { runs: [unavailableRun], findings: [] }
      : route(url));
    await render();
    await waitFor(() => container.textContent?.includes("Total run cost") === true);

    expect(container.textContent).toContain("No usable cost observations were stored for this run.");
    expect(container.textContent).toContain("0/1201 units fully priced");
  });

  it("shows duration as unavailable when disposable performance was pruned", async () => {
    window.history.replaceState(null, "", "/?run=run-a");
    installFetch((url) => url === "/api/runs/run-a/performance"
      ? {
          availability: "unavailable",
          reason: "Performance detail was pruned when this eval was retained.",
        }
      : route(url));
    await render();
    await waitFor(() => container.textContent?.includes(
      "Performance detail was pruned when this eval was retained.",
    ) === true);

    expect(container.querySelector('[aria-label="Run duration summary"]')?.textContent)
      .toContain("Performance detail was pruned when this eval was retained.");
  });

  it("shows a clear recovery state for an invalid run deep link", async () => {
    window.history.replaceState(null, "", "/?run=missing-run");
    const requested: string[] = [];
    installFetch((url) => {
      requested.push(url);
      return route(url);
    });
    await render();
    await waitFor(() => container.textContent?.includes("Evaluation run unavailable") === true);

    expect(container.textContent).toContain("may have been permanently deleted");
    expect(requested.some((url) => url.includes("missing-run"))).toBe(false);
    await click(button("Back to evaluation results"));
    await waitFor(() => container.textContent?.includes("Overall evaluation results") === true);
  });

  it("shows a distinct empty state when no evals exist", async () => {
    installFetch((url) => url === "/api/runs" ? { runs: [], findings: [] } : route(url));
    await render();
    await waitFor(() => container.textContent?.includes("No evaluation runs are available yet.") === true);
    expect(container.textContent).not.toContain("No evaluation runs match these controls.");
  });

});

async function render() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    root.render(<QueryClientProvider client={client}><EvalExplorerApp adapter={adapter} /></QueryClientProvider>);
  });
}

function installFetch(handler: (url: string) => unknown) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const payload = handler(url);
    if (isFailure(payload)) {
      return { ok: false, status: 400, statusText: "Bad Request", json: async () => ({ detail: payload.message }) } as Response;
    }
    return { ok: true, status: 200, statusText: "OK", json: async () => payload } as Response;
  }));
}

function route(url: string): unknown {
  if (url === "/api/runs") return { runs: [run], findings: [] };
  if (url === "/api/runs/run-a/performance") return performance;
  if (url.startsWith("/api/runs/run-a/attempts?")) return attemptsPayload(row);
  if (url === "/api/runs/run-a/attempts/execution-a.1") {
    return { row, review: { model_interactions: {} }, benchmark_context: benchmarkContext };
  }
  if (url.includes("/evidence")) return { example: { example_id: "example-a", unit_id: "unit-a", decision_timestamp: "2026-01-01T00:00:00Z", metadata: {} }, window: { start: "2025-01-01", end: "2026-01-01", basis: "lookback" }, evidence: {}, metadata: {} };
  throw new Error(`Unhandled fetch: ${url}`);
}

function attemptsPayload(selectedRow: typeof row) {
  return {
    rows: [selectedRow],
    matched: 1201,
    offset: 0,
    limit: 100,
    facets: { states: { all: 1201, correct: 0, incorrect: 1201, failed: 0, invalid: 0, flaky: 0, unscored: 0, "review-unavailable": 0 }, fields: ["classification"], slices: ["priority"] },
  };
}

function failure(message: string) {
  return { __failure: true, message } as const;
}

function isFailure(value: unknown): value is ReturnType<typeof failure> {
  return typeof value === "object" && value !== null && "__failure" in value;
}

function byLabel(label: string) {
  const element = container.querySelector(`[aria-label="${label}"]`);
  if (!(element instanceof HTMLElement)) throw new Error(`Missing labeled element: ${label}`);
  return element;
}

function button(label: string) {
  const matches = Array.from(container.querySelectorAll("button")).filter((item) => item.textContent === label);
  if (matches.length !== 1) throw new Error(`Expected one ${label} button; found ${matches.length}.`);
  return matches[0];
}

async function click(element: Element) {
  await act(async () => element.dispatchEvent(new MouseEvent("click", { bubbles: true })));
}

async function select(element: HTMLElement, value: string) {
  if (!(element instanceof HTMLButtonElement)) throw new Error("Expected a select trigger.");
  await click(element);
  const option = document.querySelector(`[role="option"][data-value="${value}"]`);
  if (!(option instanceof HTMLElement)) throw new Error(`Missing select option: ${value}`);
  await click(option);
}

async function fill(element: HTMLElement, value: string) {
  if (!(element instanceof HTMLInputElement)) throw new Error("Expected an input element.");
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(element, value);
    element.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function waitFor(predicate: () => boolean | undefined) {
  for (let index = 0; index < 40; index += 1) {
    if (predicate()) return;
    await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  throw new Error("Timed out waiting for UI state.");
}
