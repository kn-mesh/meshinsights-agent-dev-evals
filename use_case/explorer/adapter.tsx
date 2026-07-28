import type { EvidenceView, UseCaseAdapter } from "@eval-ui/contracts";
import { Button } from "@eval-ui/components/ui/button";
import { cn } from "@eval-ui/lib/utils";
import {
  Activity,
  AlertTriangle,
  Clock,
  Database,
  Gauge,
  Maximize2,
  Minimize2,
  type LucideIcon,
} from "lucide-react";
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
    <div className="grid gap-4 px-5 py-5 pb-10">
      <section className="flex flex-wrap items-center justify-between gap-4">
        <dl className="grid flex-1 grid-cols-4 gap-x-7 gap-y-3 max-[1100px]:grid-cols-2">
          <Meta label="Sensor ID" value={evidence.example.unit_id} />
          <Meta label="Alarm" value={formatDate(alarmTimestamp)} />
          <Meta
            label="Trap type"
            value={payload.asset.steam_trap_type ?? metadata.steam_trap_type}
          />
          <Meta label="Customer" value={metadata.organization ?? metadata.customer} />
        </dl>
        <div className="flex max-w-64 items-center gap-2 text-[0.75rem] leading-snug text-muted-foreground">
          <Clock className="size-4 shrink-0" />
          <span>{historyLabel} ending at the retained alarm decision.</span>
        </div>
      </section>

      <details className="group overflow-hidden rounded-lg border bg-card">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-3.5 py-2.5 text-[0.8125rem] text-muted-foreground group-open:border-b group-open:text-foreground [&::-webkit-details-marker]:hidden">
          <Database className="size-4" />
          Frozen evidence provenance
        </summary>
        <dl className="grid grid-cols-4 gap-x-7 gap-y-3 px-3.5 py-3.5 max-[1100px]:grid-cols-2">
          <Meta label="Source snapshot" value={evidence.metadata.source_snapshot_id} />
          <Meta label="Evidence recipe" value={evidence.metadata.evidence_recipe_id} />
          <Meta label="Schema" value={evidence.metadata.evidence_schema_version} />
          <Meta label="Source kind" value={evidence.metadata.source_kind} />
        </dl>
      </details>

      {knownGaps.length ? (
        <div role="note" className="flex items-start gap-2.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-3.5 py-3 text-[0.8125rem] text-amber-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <div>
            <strong className="font-semibold">Evidence gaps</strong>
            <ul className="mt-1.5 list-disc pl-4">
              {knownGaps.map((gap) => <li key={gap}>{gap}</li>)}
            </ul>
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Frozen source evidence</div>
          <h3 className="mt-0.5 text-base font-semibold tracking-tight">Telemetry at the alarm decision</h3>
        </div>
        <p className="max-w-xl text-right text-[0.75rem] leading-relaxed text-muted-foreground max-[900px]:text-left">
          Use the time controls to inspect 1 day, 7 days, 30 days, 6 months, or the complete retained window.
        </p>
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
    <div className="min-w-0">
      <dt className="text-[0.6875rem] text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 overflow-hidden text-ellipsis whitespace-nowrap text-[0.8125rem] font-semibold" title={displayValue(value)}>
        {displayValue(value)}
      </dd>
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

const chartPanelIcons: Record<"gauge" | "activity", LucideIcon> = {
  gauge: Gauge,
  activity: Activity,
};

function ChartPanel({
  title,
  icon,
  children,
}: {
  title: string;
  icon: "gauge" | "activity";
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
  const Icon = chartPanelIcons[icon];

  return (
    <section
      data-fullscreen={isMaximized}
      className={cn(
        "min-w-0 rounded-lg border bg-card p-3.5",
        isMaximized && "fixed inset-0 z-[100] h-screen overflow-auto rounded-none border-0 bg-background p-6",
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-4">
        <h3 className="text-[0.8125rem] tracking-[-0.005em]">{title}</h3>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Icon className="size-4" />
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setIsMaximized((value) => !value)}
            title={isMaximized ? "Exit full screen" : "Maximize chart"}
            aria-label={isMaximized ? "Exit full screen" : `Maximize ${title}`}
          >
            {isMaximized ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
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

export const projectUseCaseAdapter: UseCaseAdapter = {
  EvidenceDisplay: SpiraxEvidenceDisplay,
  contextLabel: "Spirax Pulse / Evaluation",
  evaluationFieldLabels: {
    classification: "Failure classification",
    root_cause: "Root cause classification",
  },
  evaluationFieldValueOrder: {
    classification: ["Healthy", "Failure"],
    root_cause: ["Unknown", "Closed Failure", "Open Failure"],
  },
  sourceVerificationSchemas: [{
    schema_key: "spirax_customer_verification",
    version: "1",
    title: "Customer verification",
    fields: [
      { key: "failure_cause", label: "Customer outcome", value_type: "text" },
      { key: "action_to_resolve", label: "Action taken", value_type: "text" },
      { key: "resolution_notes", label: "Resolution notes", value_type: "long_text" },
      { key: "acknowledgement_status", label: "Acknowledgement status", value_type: "text" },
      { key: "acknowledgement_notes", label: "Acknowledgement notes", value_type: "long_text" },
    ],
  }],
};
