import { lazy, Suspense, useMemo } from "react";
import type { Data, Dash, Layout, Shape } from "plotly.js";

const Plot = lazy(async () => {
  const [{ default: createPlot }, { default: Plotly }] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-cartesian-dist-min"),
  ]);
  return { default: createPlot(Plotly) };
});

export const DEFAULT_TIMESERIES_CHART_HEIGHT = 420;
export const TIMESERIES_GAP_BREAK_THRESHOLD_MS = 24 * 60 * 60 * 1000;
const GAP_BREAK_OFFSET_MS = 1000;
const X_RANGE_PADDING_RATIO = 0.015;
const X_RANGE_END_PADDING_MS = 60 * 60 * 1000;
const Y_RANGE_PADDING_RATIO = 0.18;

export interface Series {
  key: string;
  label: string;
  color: string;
  unit?: string;
}

export interface TimeseriesMarker {
  id: string;
  timestamp: string;
  color: string;
  dash?: string;
  width?: number;
}

type TimeseriesPoint = {
  timestamp: string;
  t: number;
  values: Record<string, number>;
};

export type SeriesTracePoint = {
  timestamp: string;
  value: number | null;
};

export function TimeseriesChart({
  rows,
  series,
  yAxisLabel,
  zeroLine = false,
  markers = [],
  alarmTimestamp,
  xRange,
  height = DEFAULT_TIMESERIES_CHART_HEIGHT,
  ariaLabel = "Interactive time series chart",
}: {
  rows: Array<Record<string, unknown>>;
  series: Series[];
  yAxisLabel?: string;
  zeroLine?: boolean;
  markers?: TimeseriesMarker[];
  alarmTimestamp?: string;
  xRange?: { start?: string; end?: string };
  height?: number;
  ariaLabel?: string;
}) {
  const points = useMemo(
    () => normalizePoints(rows, series),
    [rows, series],
  );
  const chartMarkers = useMemo(
    () => alarmTimestamp
      ? [
          ...markers,
          {
            id: "decision",
            timestamp: alarmTimestamp,
            color: "#b7791f",
            dash: "2 3",
            width: 1.5,
          },
        ]
      : markers,
    [alarmTimestamp, markers],
  );
  const data = useMemo<Data[]>(
    () => series.flatMap((item) => {
      const tracePoints = buildSeriesTracePoints(points, item.key);
      const valueCount = tracePoints.filter((point) => point.value !== null).length;
      if (valueCount < 2) return [];
      return [{
        type: "scattergl" as const,
        mode: "lines+markers" as const,
        name: item.label,
        x: tracePoints.map((point) => point.timestamp),
        y: tracePoints.map((point) => point.value),
        connectgaps: false,
        line: { color: item.color, width: 1.15 },
        marker: { color: item.color, opacity: 0.68, size: 2.4 },
        hovertemplate: `${item.label}: %{y:.2f}${item.unit ? ` ${item.unit}` : ""}<extra></extra>`,
      }];
    }),
    [points, series],
  );
  const layout = useMemo<Partial<Layout>>(
    () => buildLayout({
      height,
      markers: chartMarkers,
      points,
      series,
      xRange,
      yAxisLabel,
      zeroLine,
    }),
    [chartMarkers, height, points, series, xRange, yAxisLabel, zeroLine],
  );

  if (!points.length || !data.length) {
    return (
      <div
        className="grid place-items-center rounded-lg border border-dashed bg-muted/35 p-8 text-center text-sm text-muted-foreground"
        style={{ height }}
      >
        Not enough retained samples to chart this signal.
      </div>
    );
  }

  return (
    <div className="relative min-w-0 overflow-hidden" role="img" aria-label={ariaLabel} style={{ height: height + 20 }}>
      <Suspense
        fallback={
          <div
            className="grid place-items-center rounded-lg border border-dashed bg-muted/35 p-8 text-center text-sm text-muted-foreground"
            style={{ height }}
          >
            Loading interactive chart…
          </div>
        }
      >
        <Plot
          data={data}
          layout={layout}
          config={{
            responsive: true,
            displaylogo: false,
            doubleClick: "reset",
            scrollZoom: false,
            toImageButtonOptions: {
              filename: "evidence-chart",
              format: "png",
              height: 900,
              scale: 2,
              width: 1600,
            },
          }}
          style={{ width: "100%", height }}
          useResizeHandler
        />
      </Suspense>
    </div>
  );
}

function normalizePoints(rows: Array<Record<string, unknown>>, series: Series[]): TimeseriesPoint[] {
  return rows
    .map((row) => ({
      timestamp: String(row.timestamp ?? ""),
      t: Date.parse(String(row.timestamp ?? "")),
      values: Object.fromEntries(
        series
          .map((item) => [item.key, row[item.key]])
          .filter((entry): entry is [string, number] => typeof entry[1] === "number"),
      ),
    }))
    .filter((point) => Number.isFinite(point.t))
    .sort((a, b) => a.t - b.t);
}

export function buildSeriesTracePoints(
  points: TimeseriesPoint[],
  seriesKey: string,
): SeriesTracePoint[] {
  const tracePoints: SeriesTracePoint[] = [];
  let previousValuedPoint: TimeseriesPoint | null = null;
  let hasBreakSincePreviousValue = false;

  for (const point of points) {
    const value = point.values[seriesKey] ?? null;
    if (typeof value === "number" && previousValuedPoint) {
      const gapMs = point.t - previousValuedPoint.t;
      if (!hasBreakSincePreviousValue && gapMs >= TIMESERIES_GAP_BREAK_THRESHOLD_MS) {
        tracePoints.push({
          timestamp: new Date(previousValuedPoint.t + GAP_BREAK_OFFSET_MS).toISOString(),
          value: null,
        });
      }
    }
    tracePoints.push({ timestamp: point.timestamp, value });
    if (typeof value === "number") {
      previousValuedPoint = point;
      hasBreakSincePreviousValue = false;
    } else if (previousValuedPoint) {
      hasBreakSincePreviousValue = true;
    }
  }
  return tracePoints;
}

function buildLayout({
  height,
  markers,
  points,
  series,
  xRange,
  yAxisLabel,
  zeroLine,
}: {
  height: number;
  markers: TimeseriesMarker[];
  points: TimeseriesPoint[];
  series: Series[];
  xRange?: { start?: string; end?: string };
  yAxisLabel?: string;
  zeroLine: boolean;
}): Partial<Layout> {
  const firstPoint = points[0];
  const lastPoint = points.at(-1);
  const range = computeXRange(points, xRange);
  const { min, max } = computeYRange(points, series, zeroLine);
  const allButtonDays = firstPoint && lastPoint
    ? Math.max(1, Math.ceil((lastPoint.t - firstPoint.t) / 86_400_000) + 2)
    : 1;
  const chartTheme = {
    font: "#64748b",
    hoverBackground: "rgba(255,255,255,.94)",
    hoverBorder: "rgba(148,163,184,.35)",
    hoverText: "#334155",
    selector: "rgba(242,243,245,.92)",
    selectorActive: "#e0f3ef",
    selectorBorder: "rgba(122,127,133,.24)",
  };

  return {
    autosize: true,
    dragmode: "zoom",
    height,
    font: { color: chartTheme.font, family: "var(--font-chart)", size: 11 },
    hoverlabel: {
      bgcolor: chartTheme.hoverBackground,
      bordercolor: chartTheme.hoverBorder,
      font: { color: chartTheme.hoverText, size: 11 },
    },
    hovermode: "x unified",
    legend: {
      bgcolor: "rgba(255,255,255,0)",
      itemclick: false,
      itemdoubleclick: false,
      orientation: "h",
      x: 1,
      xanchor: "right",
      y: 1.14,
      yanchor: "bottom",
    },
    margin: { b: 40, l: yAxisLabel ? 68 : 44, pad: 0, r: 16, t: 44 },
    paper_bgcolor: "rgba(255,255,255,0)",
    plot_bgcolor: "rgba(255,255,255,0)",
    shapes: buildMarkerShapes(markers),
    uirevision: [firstPoint?.timestamp ?? "", lastPoint?.timestamp ?? "", series.map((item) => item.key).join(",")].join("|"),
    xaxis: {
      automargin: true,
      gridcolor: "rgba(148,163,184,.24)",
      hoverformat: "%b %d, %Y %H:%M",
      range,
      rangeselector: {
        activecolor: chartTheme.selectorActive,
        bgcolor: chartTheme.selector,
        bordercolor: chartTheme.selectorBorder,
        borderwidth: 1,
        buttons: [
          { count: 1, label: "1d", step: "day", stepmode: "backward" },
          { count: 7, label: "7d", step: "day", stepmode: "backward" },
          { count: 30, label: "30d", step: "day", stepmode: "backward" },
          { count: 6, label: "6m", step: "month", stepmode: "backward" },
          { count: allButtonDays, label: "all", step: "day", stepmode: "backward" },
        ],
        font: { color: chartTheme.font, size: 11 },
        x: 0,
        y: 1.14,
      },
      showgrid: true,
      type: "date",
      zeroline: false,
    },
    yaxis: {
      automargin: true,
      gridcolor: "rgba(148,163,184,.24)",
      range: [min, max],
      showgrid: true,
      tickformat: ".3~f",
      title: yAxisLabel ? { standoff: 14, text: yAxisLabel } : undefined,
      zeroline: zeroLine,
      zerolinecolor: "rgba(100,116,139,.9)",
      zerolinewidth: 1,
    },
  };
}

function buildMarkerShapes(markers: TimeseriesMarker[]): Array<Partial<Shape>> {
  return markers
    .filter((marker) => Number.isFinite(Date.parse(marker.timestamp)))
    .map((marker) => ({
      type: "line",
      x0: marker.timestamp,
      x1: marker.timestamp,
      xref: "x",
      y0: 0,
      y1: 1,
      yref: "paper",
      line: {
        color: marker.color,
        dash: markerDash(marker.dash),
        width: marker.width ?? 2,
      },
    }));
}

function markerDash(value: string | undefined): Dash {
  if (!value) return "solid";
  return value === "2 3" ? "dot" : "dash";
}

function computeXRange(
  points: TimeseriesPoint[],
  requested: { start?: string; end?: string } | undefined,
): [string, string] | undefined {
  const start = validTimestamp(requested?.start) ?? points[0]?.timestamp;
  const end = validTimestamp(requested?.end) ?? points.at(-1)?.timestamp;
  if (!start || !end) return undefined;
  const startTime = Date.parse(start);
  const endTime = Date.parse(end);
  const padding = Math.max((endTime - startTime) * X_RANGE_PADDING_RATIO, 3_600_000);
  return [
    new Date(startTime - padding).toISOString(),
    new Date(endTime + X_RANGE_END_PADDING_MS).toISOString(),
  ];
}

function validTimestamp(value: string | undefined) {
  return value && Number.isFinite(Date.parse(value)) ? value : undefined;
}

function computeYRange(points: TimeseriesPoint[], series: Series[], zeroLine: boolean) {
  const values = [
    ...points.flatMap((point) => series.flatMap((item) => {
      const value = point.values[item.key];
      return typeof value === "number" ? [value] : [];
    })),
    ...(zeroLine ? [0] : []),
  ];
  if (!values.length) return { min: 0, max: 1 };
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const padding = (max - min) * Y_RANGE_PADDING_RATIO;
  return niceRange(min - padding, max + padding, 6);
}

function niceRange(minimum: number, maximum: number, targetTicks: number) {
  const rawStep = (maximum - minimum) / Math.max(targetTicks, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceResidual = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 2.5 ? 2.5 : residual <= 5 ? 5 : 10;
  const step = niceResidual * magnitude;
  return {
    min: Math.floor(minimum / step) * step,
    max: Math.ceil(maximum / step) * step,
  };
}
