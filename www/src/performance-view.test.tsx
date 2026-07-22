import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AttemptPerformance, PerformancePanel } from "@eval-ui/eval-explorer-app";

describe("performance views", () => {
  it("shows observed run latency separately from unavailable HTTP attempts", () => {
    const html = renderToStaticMarkup(
      <PerformancePanel
        onSelectExecution={() => undefined}
        performance={{
          run_id: "eval_test",
          availability: "available",
          recorded_executions: 2,
          summary: {
            evaluation_wall_time_seconds: 12,
            throughput_runs_per_minute: 10,
            stage_duration_seconds: {
              process: { count: 2, minimum: 4, maximum: 8, median: 6, p95: 8 },
            },
          },
          model_calls: {
            count: 2,
            duration_seconds: { count: 2, minimum: 3, maximum: 7, median: 5, p95: 7 },
            duration_exceeded_configured_timeout_count: 0,
            long_tail_at_or_above_p95_count: 1,
            slowest: [{ execution_id: "work.1", unit_id: "unit-a", duration_seconds: 7 }],
          },
          retries: {
            observed_model_requests: 2,
            observed_transport_attempts: null,
          },
        }}
      />,
    );

    expect(html).toContain("Performance");
    expect(html).toContain("process");
    expect(html).toContain("model API");
    expect(html).toContain("HTTP attempts</dt><dd>unavailable");
    expect(html).toContain("Retry categories</dt><dd>unavailable");
    expect(html).toContain("Long tail at or above p95: 1");
    expect(html).toContain("unit-a");
    expect(html).toContain("work.1");
  });

  it("does not invent counts omitted by an earlier performance summary", () => {
    const html = renderToStaticMarkup(
      <PerformancePanel
        onSelectExecution={() => undefined}
        performance={{
          run_id: "eval_test",
          availability: "available",
          model_calls: { count: 1 },
          retries: { observed_transport_attempts: null },
        }}
      />,
    );

    expect(html).toContain("Duration boundary: unavailable");
    expect(html).toContain("Long tail at or above p95: unavailable");
  });

  it("keeps unavailable performance a normal independent state", () => {
    const runHtml = renderToStaticMarkup(
      <PerformancePanel
        onSelectExecution={() => undefined}
        performance={{
          run_id: "eval_test",
          availability: "unavailable",
          reason: "Performance summary is absent or was deleted.",
        }}
      />,
    );
    const attemptHtml = renderToStaticMarkup(
      <AttemptPerformance
        performance={{
          availability: "unavailable",
          reason: "Performance observations are absent or were deleted.",
        }}
      />,
    );

    expect(runHtml).toContain("Durable quality and evidence remain usable");
    expect(attemptHtml).toContain("Durable evaluation and evidence remain available");
  });
});
