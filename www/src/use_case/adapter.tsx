import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";
import { Button } from "@eval-ui/components/ui/button";
import {
  DEFAULT_TIMESERIES_CHART_HEIGHT,
  TimeseriesChart,
} from "@eval-ui/timeseries-chart";
import { useEffect, useState, type ReactNode } from "react";
import { spiraxEvidenceSchema } from "./evidence.schema";

export function SpiraxEvidenceDisplay({ evidence }: { evidence: EvidenceView }) {
  const payload = spiraxEvidenceSchema.parse(evidence.evidence);
  const metadata = evidence.example.metadata;
  const alarmTimestamp = evidence.example.decision_timestamp;
  const chartRows = buildEvidenceWindow(
    payload.telemetry,
    evidence.window.start,
    evidence.window.end,
  );
  const lookbackDays = typeof evidence.window.lookback_days === "number"
    ? evidence.window.lookback_days
    : 365;
  const historyLabel = `${lookbackDays}-Day History`;
  const knownGaps = [...new Set([
    ...payload.known_gaps,
    ...evidence.metadata.known_gaps,
  ].filter(Boolean))];
  const xRange = { start: evidence.window.start, end: evidence.window.end };

  return (
    <div className="evidence-stack">
      <section className="evidence-summary">
        <dl className="evidence-primary-meta">
          <Meta label="Sensor ID" value={evidence.example.unit_id} />
          <Meta label="Alarm" value={formatDate(alarmTimestamp)} />
          <Meta
            label="Trap type"
            value={payload.asset.steam_trap_type ?? metadata.steam_trap_type}
          />
          <Meta label="Customer" value={metadata.organization ?? metadata.customer} />
        </dl>
        <div className="evidence-window-note">
          <UiIcon name="clock" />
          <span>{historyLabel} ending at the retained alarm decision.</span>
        </div>
      </section>

      <details className="provenance-panel">
        <summary>
          <UiIcon name="database" />
          Frozen evidence provenance
        </summary>
        <dl className="provenance-grid">
          <Meta label="Source snapshot" value={evidence.metadata.source_snapshot_id} />
          <Meta label="Evidence recipe" value={evidence.metadata.evidence_recipe_id} />
          <Meta label="Schema" value={evidence.metadata.evidence_schema_version} />
          <Meta label="Source kind" value={evidence.metadata.source_kind} />
        </dl>
      </details>

      {knownGaps.length ? (
        <div className="warning" role="note">
          <UiIcon name="alert" />
          <div>
            <strong>Evidence gaps</strong>
            <ul>{knownGaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </div>
        </div>
      ) : null}

      <div className="chart-intro">
        <div>
          <div className="eyebrow">Frozen source evidence</div>
          <h3>Telemetry at the alarm decision</h3>
        </div>
        <p>Use the time controls to inspect 1 day, 7 days, 30 days, 6 months, or the complete retained window.</p>
      </div>

      <ChartPanel title={`Steam & Condensate Temperature (${historyLabel})`} icon="gauge">
        {({ chartHeight }) => (
          <TimeseriesChart
            height={chartHeight}
            rows={chartRows}
            series={temperatureSeries}
            xRange={xRange}
            yAxisLabel="Temperature (C)"
            alarmTimestamp={alarmTimestamp}
            ariaLabel={`${historyLabel} steam and condensate temperature`}
          />
        )}
      </ChartPanel>

      <ChartPanel title={`Steam − Condensate Temperature Delta (${historyLabel})`} icon="activity">
        {({ chartHeight }) => (
          <TimeseriesChart
            height={chartHeight}
            rows={chartRows}
            series={deltaSeries}
            xRange={xRange}
            yAxisLabel="Delta (C)"
            zeroLine
            alarmTimestamp={alarmTimestamp}
            ariaLabel={`${historyLabel} steam and condensate temperature delta`}
          />
        )}
      </ChartPanel>

      <ChartPanel title={`Front Microphone Acoustic Level (${historyLabel})`} icon="activity">
        {({ chartHeight }) => (
          <TimeseriesChart
            height={chartHeight}
            rows={chartRows}
            series={microphoneSeries}
            xRange={xRange}
            alarmTimestamp={alarmTimestamp}
            ariaLabel={`${historyLabel} front microphone acoustic level`}
          />
        )}
      </ChartPanel>
    </div>
  );
}

const temperatureSeries = [
  { key: "steam_temperature", label: "Steam", color: "#c9636d", unit: "C" },
  { key: "condensate_temperature", label: "Condensate", color: "#4a86b8", unit: "C" },
];
const deltaSeries = [
  { key: "temperature_delta", label: "Steam - Condensate", color: "#00997d", unit: "C" },
];
const microphoneSeries = [
  { key: "front_mic", label: "Front Mic", color: "#00b8c4" },
];

type TelemetryRow = ReturnType<typeof spiraxEvidenceSchema.parse>["telemetry"][number];

export function buildEvidenceWindow(rows: TelemetryRow[], start: string, end: string) {
  const startTime = Date.parse(start);
  const endTime = Date.parse(end);
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) {
    throw new Error(`Invalid evidence window: ${start}–${end}`);
  }
  return rows
    .filter((row) => {
      const timestamp = Date.parse(row.timestamp);
      return timestamp >= startTime && timestamp <= endTime;
    })
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
}

function Meta({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd title={displayValue(value)}>{displayValue(value)}</dd>
    </div>
  );
}

function displayValue(value: unknown) {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return "Unknown";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function ChartPanel({
  title,
  icon,
  children,
}: {
  title: string;
  icon: IconName;
  children: ReactNode | ((state: { chartHeight: number }) => ReactNode);
}) {
  const [isMaximized, setIsMaximized] = useState(false);
  const [fullscreenHeight, setFullscreenHeight] = useState(getFullscreenChartHeight);

  useEffect(() => {
    if (!isMaximized) return;
    const updateHeight = () => setFullscreenHeight(getFullscreenChartHeight());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsMaximized(false);
    };
    updateHeight();
    window.addEventListener("resize", updateHeight);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("resize", updateHeight);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isMaximized]);

  const chartHeight = isMaximized ? fullscreenHeight : DEFAULT_TIMESERIES_CHART_HEIGHT;
  const content = typeof children === "function" ? children({ chartHeight }) : children;

  return (
    <section className="chart-panel" data-fullscreen={isMaximized}>
      <div className="chart-panel-heading">
        <h3>{title}</h3>
        <div className="chart-panel-actions">
          <UiIcon name={icon} />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsMaximized((value) => !value)}
            title={isMaximized ? "Exit full screen" : "Maximize chart"}
            aria-label={isMaximized ? "Exit full screen" : `Maximize ${title}`}
          >
            <UiIcon name={isMaximized ? "minimize" : "maximize"} />
          </Button>
        </div>
      </div>
      {content}
    </section>
  );
}

function getFullscreenChartHeight() {
  if (typeof window === "undefined") return 680;
  return Math.max(560, Math.min(window.innerHeight - 132, 920));
}

type IconName = "activity" | "alert" | "clock" | "database" | "gauge" | "maximize" | "minimize";

function UiIcon({ name }: { name: IconName }) {
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
      {name === "activity" ? <path d="M3 12h4l2.5-6 5 12 2.5-6h4" /> : null}
      {name === "alert" ? <><path d="M10.3 3.7 2.4 18a2 2 0 0 0 1.8 3h15.6a2 2 0 0 0 1.8-3L13.7 3.7a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></> : null}
      {name === "clock" ? <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></> : null}
      {name === "database" ? <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" /></> : null}
      {name === "gauge" ? <><path d="M4.9 19a9 9 0 1 1 14.2 0" /><path d="m12 13 4-4M12 19h.01" /></> : null}
      {name === "maximize" ? <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /></> : null}
      {name === "minimize" ? <><path d="M8 8H3V3M16 8h5V3M8 16H3v5M16 16h5v5" /></> : null}
    </svg>
  );
}

export const projectUseCaseAdapter: UseCaseAdapter = {
  EvidenceDisplay: SpiraxEvidenceDisplay,
};
