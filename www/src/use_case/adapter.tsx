import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";
import { TimeseriesChart } from "@eval-ui/timeseries-chart";
import type { ReactNode } from "react";
import { spiraxEvidenceSchema } from "./evidence.schema";

const dayMs = 24 * 60 * 60 * 1000;

export function SpiraxEvidenceDisplay({ evidence }: { evidence: EvidenceView }) {
  const payload = spiraxEvidenceSchema.parse(evidence.evidence);
  const exampleMetadata = evidence.example.metadata;
  const alarmTimestamp = evidence.example.decision_timestamp;
  const windows = buildEvidenceWindows(payload.telemetry, alarmTimestamp);
  const temperatureRange = numericRange(payload.telemetry, ["steam_temperature", "condensate_temperature"]);
  const deltaRange = numericRange(payload.telemetry, ["temperature_delta"]);
  return (
    <div className="evidence-stack">
      <section className="evidence-meta">
        <Meta label="Sensor ID" value={evidence.example.unit_id} />
        <Meta label="Alarm" value={evidence.example.decision_timestamp} />
        <Meta label="Trap type" value={payload.asset.steam_trap_type ?? exampleMetadata.steam_trap_type} />
        <Meta label="Customer" value={exampleMetadata.organization ?? exampleMetadata.customer} />
        <Meta label="Source snapshot" value={evidence.metadata.source_snapshot_id} />
        <Meta label="Evidence recipe" value={evidence.metadata.evidence_recipe_id} />
      </section>
      {payload.known_gaps.length ? <div className="warning">Evidence gaps: {payload.known_gaps.join("; ")}</div> : null}

      <section className="evidence-window" aria-label="365-day evidence window">
        <h3>365-day temperature history</h3>
        <p className="muted">Four consecutive chronological segments with a shared scale; the alarm is at the right edge of segment 4.</p>
        <div className="segmented-chart-grid">
          {windows.year.map((segment, index) => (
            <Segment key={`temperature-${segment.start}`} label={`Segment ${index + 1} · ${dateLabel(segment.start)}–${dateLabel(segment.end)}`}>
              <TimeseriesChart
                rows={segment.rows}
                series={temperatureSeries}
                yAxisLabel="Temperature (C)"
                yAxisRange={temperatureRange}
                alarmTimestamp={index === windows.year.length - 1 ? alarmTimestamp : undefined}
                height={270}
              />
            </Segment>
          ))}
        </div>
        <div className="segmented-chart-grid">
          {windows.year.map((segment, index) => (
            <Segment key={`delta-${segment.start}`} label={`Delta segment ${index + 1}`}>
              <TimeseriesChart
                rows={segment.rows}
                series={deltaSeries}
                yAxisLabel="Delta (C)"
                yAxisRange={deltaRange}
                zeroLine
                alarmTimestamp={index === windows.year.length - 1 ? alarmTimestamp : undefined}
                height={230}
              />
            </Segment>
          ))}
        </div>
      </section>

      <section className="evidence-window" aria-label="30-day evidence window">
        <h3>30-day alarm context</h3>
        <Chart title="Steam & condensate temperature (30-day history)">
          <TimeseriesChart
            rows={windows.month}
            series={temperatureSeries}
            yAxisLabel="Temperature (C)"
            alarmTimestamp={alarmTimestamp}
          />
        </Chart>
        <Chart title="Steam − condensate temperature delta (30-day history)">
          <TimeseriesChart
            rows={windows.month}
            series={deltaSeries}
            yAxisLabel="Delta (C)"
            zeroLine
            alarmTimestamp={alarmTimestamp}
          />
        </Chart>
      </section>

      <section className="evidence-window" aria-label="7-day evidence window">
        <h3>7-day alarm detail</h3>
        <Chart title="Steam & condensate temperature (7-day history)">
          <TimeseriesChart
            rows={windows.week}
            series={temperatureSeries}
            yAxisLabel="Temperature (C)"
            alarmTimestamp={alarmTimestamp}
          />
        </Chart>
        <Chart title="Steam − condensate temperature delta (7-day history)">
          <TimeseriesChart
            rows={windows.week}
            series={deltaSeries}
            yAxisLabel="Delta (C)"
            zeroLine
            alarmTimestamp={alarmTimestamp}
          />
        </Chart>
      </section>

      <Chart title="Front microphone acoustic level (365-day history)">
        <TimeseriesChart
          rows={payload.telemetry}
          series={[{ key: "front_mic", label: "Front Mic", color: "#00b8c4" }]}
          alarmTimestamp={alarmTimestamp}
        />
      </Chart>
    </div>
  );
}

const temperatureSeries = [
  { key: "steam_temperature", label: "Steam", color: "#c9636d", unit: "C" },
  { key: "condensate_temperature", label: "Condensate", color: "#4a86b8", unit: "C" },
];
const deltaSeries = [
  { key: "temperature_delta", label: "Steam - Condensate", color: "#7255a3", unit: "C" },
];

type TelemetryRow = ReturnType<typeof spiraxEvidenceSchema.parse>["telemetry"][number];
type SegmentWindow = { start: string; end: string; rows: TelemetryRow[] };

export function buildEvidenceWindows(rows: TelemetryRow[], alarmTimestamp: string) {
  const end = Date.parse(alarmTimestamp);
  if (!Number.isFinite(end)) throw new Error(`Invalid alarm timestamp: ${alarmTimestamp}`);
  return {
    year: segmentedRows(rows, end, 365, 4),
    month: rowsWithin(rows, end - 30 * dayMs, end),
    week: rowsWithin(rows, end - 7 * dayMs, end),
  };
}

function segmentedRows(rows: TelemetryRow[], end: number, days: number, count: number): SegmentWindow[] {
  const start = end - days * dayMs;
  const width = (end - start) / count;
  return Array.from({ length: count }, (_, index) => {
    const segmentStart = start + width * index;
    const segmentEnd = index === count - 1 ? end : start + width * (index + 1);
    return {
      start: new Date(segmentStart).toISOString(),
      end: new Date(segmentEnd).toISOString(),
      rows: rowsWithin(rows, segmentStart, segmentEnd, index === count - 1),
    };
  });
}

function rowsWithin(rows: TelemetryRow[], start: number, end: number, inclusiveEnd = true) {
  return rows.filter((row) => {
    const timestamp = Date.parse(row.timestamp);
    return timestamp >= start && (inclusiveEnd ? timestamp <= end : timestamp < end);
  });
}

function numericRange(rows: TelemetryRow[], keys: Array<keyof TelemetryRow>): [number, number] | undefined {
  const values = rows.flatMap((row) => keys.map((key) => row[key])).filter((value): value is number => typeof value === "number");
  if (!values.length) return undefined;
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.05, 1);
  return [minimum - padding, maximum + padding];
}

function dateLabel(value: string) {
  return value.slice(0, 10);
}

function Meta({ label, value }: { label: string; value: unknown }) {
  return <div><small>{label}</small><strong>{displayValue(value)}</strong></div>;
}

function displayValue(value: unknown) {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return "Unknown";
}

function Chart({ title, children }: { title: string; children: ReactNode }) {
  return <section className="chart-panel"><h3>{title}</h3>{children}</section>;
}

function Segment({ label, children }: { label: string; children: ReactNode }) {
  return <section className="segment-card"><h4>{label}</h4>{children}</section>;
}

export const projectUseCaseAdapter: UseCaseAdapter = {
  EvidenceDisplay: SpiraxEvidenceDisplay,
};
