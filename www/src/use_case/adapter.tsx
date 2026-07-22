import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";
import { TimeseriesChart } from "@eval-ui/timeseries-chart";
import type { ReactNode } from "react";
import { spiraxEvidenceSchema } from "./evidence.schema";

function SpiraxEvidenceDisplay({ evidence }: { evidence: EvidenceView }) {
  const payload = spiraxEvidenceSchema.parse(evidence.evidence);
  const historyLabel = typeof evidence.window.lookback_days === "number"
    ? `${evidence.window.lookback_days}-day history`
    : "History";
  const exampleMetadata = evidence.example.metadata;
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
      <Chart title={`Steam & condensate temperature (${historyLabel})`}>
        <TimeseriesChart
          rows={payload.telemetry}
          series={[
            { key: "steam_temperature", label: "Steam", color: "#c9636d", unit: "C" },
            { key: "condensate_temperature", label: "Condensate", color: "#4a86b8", unit: "C" },
          ]}
          yAxisLabel="Temperature (C)"
        />
      </Chart>
      <Chart title={`Steam − condensate temperature delta (${historyLabel})`}>
        <TimeseriesChart
          rows={payload.telemetry}
          series={[{ key: "temperature_delta", label: "Steam - Condensate", color: "#00997d", unit: "C" }]}
          yAxisLabel="Delta (C)"
          zeroLine
        />
      </Chart>
      <Chart title={`Front microphone acoustic level (${historyLabel})`}>
        <TimeseriesChart
          rows={payload.telemetry}
          series={[{ key: "front_mic", label: "Front Mic", color: "#00b8c4" }]}
        />
      </Chart>
    </div>
  );
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

export const projectUseCaseAdapter: UseCaseAdapter = {
  EvidenceDisplay: SpiraxEvidenceDisplay,
};
