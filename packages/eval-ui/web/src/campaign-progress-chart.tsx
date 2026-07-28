import { lazy, Suspense, useMemo } from "react";
import type { Data, Layout } from "plotly.js";
import type {
  CampaignDetail,
  CampaignPoint,
} from "./campaign-contracts";

const Plot = lazy(async () => {
  const [{ default: createPlot }, { default: Plotly }] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-cartesian-dist-min"),
  ]);
  return { default: createPlot(Plotly) };
});

const seriesColors = ["#2563eb", "#d97706", "#059669", "#7c3aed", "#dc2626"];

export function CampaignProgressChart({
  campaign,
  onOpenRun,
}: {
  campaign: CampaignDetail;
  onOpenRun: (runId: string) => void;
}) {
  const data = useMemo<Data[]>(
    () => campaign.runtime_configurations.flatMap((configuration, index) => {
      const points = campaign.points.filter(
        (point): point is CampaignPoint & { primary_metric: number } =>
          point.configuration_id === configuration.id
          && typeof point.primary_metric === "number",
      );
      if (!points.length) return [];
      return [{
        type: "scatter" as const,
        mode: "lines+markers" as const,
        name: configurationLabel(configuration),
        x: points.map((point) => point.trial),
        y: points.map((point) => point.primary_metric),
        customdata: points.map((point) => point.eval_id ?? ""),
        text: points.map(pointLabel),
        line: { color: seriesColors[index % seriesColors.length], width: 2 },
        marker: {
          color: points.map((point) => decisionColor(point.decision)),
          size: 9,
          symbol: points.map((point) => point.stage === "qualification" ? "diamond" : "circle"),
          line: { color: "#ffffff", width: 1 },
        },
        hovertemplate: "%{text}<br>Score %{y:.4f}<extra>%{fullData.name}</extra>",
      }];
    }),
    [campaign],
  );
  const layout = useMemo<Partial<Layout>>(
    () => ({
      autosize: true,
      height: 360,
      margin: { l: 58, r: 20, t: 20, b: 52 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      font: { color: "#64748b", family: "Inter, sans-serif", size: 11 },
      hovermode: "closest",
      xaxis: {
        title: { text: "Trial" },
        dtick: 1,
        gridcolor: "rgba(148, 163, 184, 0.2)",
        zeroline: false,
      },
      yaxis: {
        title: { text: campaign.primary_metric ?? "Primary metric" },
        gridcolor: "rgba(148, 163, 184, 0.2)",
        zeroline: false,
      },
      legend: { orientation: "h", x: 0, y: 1.12 },
    }),
    [campaign.primary_metric],
  );

  if (!data.length) {
    return (
      <div className="grid h-72 place-items-center rounded-lg border border-dashed bg-muted/30 text-sm text-muted-foreground">
        No measured campaign points are available yet.
      </div>
    );
  }

  return (
    <div role="img" aria-label="Campaign performance by runtime configuration" className="min-w-0">
      <Suspense fallback={<div className="grid h-72 place-items-center text-sm text-muted-foreground">Loading chart…</div>}>
        <Plot
          data={data}
          layout={layout}
          config={{ displayModeBar: false, responsive: true }}
          useResizeHandler
          style={{ width: "100%", height: "380px" }}
          onClick={(event) => {
            const runId = event.points[0]?.customdata;
            if (typeof runId === "string" && runId) onOpenRun(runId);
          }}
        />
      </Suspense>
    </div>
  );
}

function configurationLabel(
  configuration: CampaignDetail["runtime_configurations"][number],
) {
  const model = configuration.model ?? configuration.id;
  const reasoning = configuration.reasoning_effort
    ? ` · ${configuration.reasoning_effort}`
    : "";
  return `${model}${reasoning}`;
}

function pointLabel(point: CampaignPoint) {
  const stage = point.stage === "trial" ? `Trial ${point.trial}` : point.stage;
  const cost = typeof point.cost === "number" ? ` · $${point.cost.toFixed(2)}` : "";
  return `${stage} · ${point.decision}${cost}`;
}

function decisionColor(decision: string) {
  if (decision === "keep" || decision === "qualification") return "#059669";
  if (decision === "discard") return "#dc2626";
  if (decision === "crash") return "#475569";
  if (decision === "inconclusive") return "#d97706";
  return "#2563eb";
}
