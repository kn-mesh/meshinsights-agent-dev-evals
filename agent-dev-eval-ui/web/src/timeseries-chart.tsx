import { lazy, Suspense, useMemo } from "react";
import type { Data, Layout } from "plotly.js";

const Plot = lazy(async () => {
  const [{ default: createPlot }, { default: Plotly }] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-cartesian-dist-min"),
  ]);
  return { default: createPlot(Plotly) };
});

export interface Series {
  key: string;
  label: string;
  color: string;
  unit?: string;
}

export function TimeseriesChart({
  rows,
  series,
  yAxisLabel,
  zeroLine = false,
  alarmTimestamp,
  yAxisRange,
  height = 410,
}: {
  rows: Array<Record<string, unknown>>;
  series: Series[];
  yAxisLabel?: string;
  zeroLine?: boolean;
  alarmTimestamp?: string;
  yAxisRange?: [number, number];
  height?: number;
}) {
  const data = useMemo<Data[]>(
    () =>
      series.map((item) => ({
        type: "scattergl",
        mode: "lines",
        name: item.label,
        x: rows.map((row) => String(row.timestamp ?? "")),
        y: rows.map((row) => {
          const value = row[item.key];
          return typeof value === "number" ? value : null;
        }),
        connectgaps: false,
        line: { color: item.color, width: 1.2 },
        hovertemplate: `${item.label}: %{y:.2f}${item.unit ? ` ${item.unit}` : ""}<extra></extra>`,
      })),
    [rows, series],
  );
  const layout: Partial<Layout> = {
    autosize: true,
    height,
    margin: { l: 58, r: 24, t: 16, b: 48 },
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#52606d" },
    hovermode: "x unified",
    xaxis: { rangeslider: { visible: false }, gridcolor: "#e5e7eb" },
    yaxis: {
      title: { text: yAxisLabel },
      gridcolor: "#e5e7eb",
      zeroline: zeroLine,
      zerolinecolor: "#64748b",
      range: yAxisRange,
    },
    legend: { orientation: "h", y: 1.12 },
    shapes: alarmTimestamp ? [{
      type: "line",
      x0: alarmTimestamp,
      x1: alarmTimestamp,
      y0: 0,
      y1: 1,
      yref: "paper",
      line: { color: "#d97706", width: 1.5, dash: "dot" },
    }] : undefined,
  };
  return (
    <Suspense fallback={<div className="empty">Loading interactive chart…</div>}>
      <Plot
        data={data}
        layout={layout}
        config={{ responsive: true, displaylogo: false, scrollZoom: false }}
        style={{ width: "100%", height: height + 20 }}
        useResizeHandler
      />
    </Suspense>
  );
}
