// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvalExplorerApp } from "@eval-ui/eval-explorer-app";
import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";

const run = {
  run_id: "run-a",
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
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
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
  it("restores page state, reaches attempts beyond 1,000, and applies field and slice facets", async () => {
    window.history.replaceState(null, "", "/?run=run-a&offset=900");
    const requested: string[] = [];
    installFetch((url) => {
      requested.push(url);
      if (url.startsWith("/api/runs/run-a/attempts?")) {
        const offset = Number(new URL(url, "http://local").searchParams.get("offset"));
        return attemptsPayload(offset >= 1000 ? { ...row, example_id: "example-after-1000", execution_id: "execution-after-1000.1" } : row);
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
    await waitFor(() => (byLabel("Evaluation slice") as HTMLSelectElement).querySelector('option[value="priority"]') !== null);
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

    await click(button("Evaluation"));
    await waitFor(() => container.textContent?.includes("Expected output") === true);
    expect(container.textContent).not.toContain("Frozen evidence unavailable");
  });

  it("restores attempt detail, exposes review-unavailable state, and loads comparison detail", async () => {
    window.history.replaceState(null, "", "/?run=run-a&execution=execution-a.1&tab=input&comparison=cmp-a");
    installFetch((url) => {
      if (url.endsWith("/attempts/execution-a.1")) {
        return { row: { ...row, review_status: "unavailable", review_unavailable_reason: { code: "purged" } }, review: null, performance: { availability: "unavailable" } };
      }
      if (url === "/api/comparisons") return { comparisons: [{ comparison_id: "cmp-a", result_path: "comparison.json", run_ids: ["run-a", "run-b"], varying_dimensions: ["model.id"] }] };
      if (url === "/api/comparisons/cmp-a") return { comparison_id: "cmp-a", paired_deltas: [{ complete_evaluation: { delta_rate: 0.1 } }] };
      return route(url);
    });
    await render();
    await waitFor(() => container.textContent?.includes("Detailed review unavailable (purged)") === true);
    await waitFor(() => container.textContent?.includes('"comparison_id": "cmp-a"') === true);
    expect(new URL(window.location.href).searchParams.get("execution")).toBe("execution-a.1");
    expect((byLabel("Run comparison") as HTMLSelectElement).value).toBe("cmp-a");
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
  if (url === "/api/comparisons") return { comparisons: [] };
  if (url === "/api/runs/run-a") return { run_id: "run-a", summary: {}, run: {} };
  if (url === "/api/runs/run-a/performance") return { run_id: "run-a", availability: "unavailable", reason: "not retained" };
  if (url.startsWith("/api/runs/run-a/attempts?")) return attemptsPayload(row);
  if (url === "/api/runs/run-a/attempts/execution-a.1") return { row, review: { model_interactions: {} }, performance: { availability: "unavailable" } };
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
  if (!(element instanceof HTMLSelectElement)) throw new Error("Expected a select element.");
  await act(async () => {
    element.value = value;
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

async function waitFor(predicate: () => boolean | undefined) {
  for (let index = 0; index < 40; index += 1) {
    if (predicate()) return;
    await act(async () => new Promise((resolve) => setTimeout(resolve, 0)));
  }
  throw new Error("Timed out waiting for UI state.");
}
