import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Search } from "lucide-react";
import { api } from "./api";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Select } from "./components/ui/select";
import { CampaignProgressChart } from "./campaign-progress-chart";
import type {
  CampaignDetail,
  CampaignEntry,
  CampaignFinding,
  CampaignListPayload,
  CampaignTrial,
} from "./campaign-contracts";

export function CampaignExplorer({
  campaignId,
  onSelectCampaign,
  onOpenRun,
}: {
  campaignId: string;
  onSelectCampaign: (campaignId: string) => void;
  onOpenRun: (runId: string) => void;
}) {
  const campaigns = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api<CampaignListPayload>("/campaigns"),
  });
  const detail = useQuery({
    queryKey: ["campaign", campaignId],
    queryFn: () => api<CampaignDetail>(
      `/campaigns/${encodeURIComponent(campaignId)}`,
    ),
    enabled: Boolean(campaignId),
  });

  if (campaignId) {
    if (detail.isPending) return <CampaignState>Loading campaign…</CampaignState>;
    if (detail.error) return <CampaignState>{errorMessage(detail.error)}</CampaignState>;
    if (detail.data) {
      return (
        <CampaignDetailView
          campaign={detail.data}
          onBack={() => onSelectCampaign("")}
          onOpenRun={onOpenRun}
        />
      );
    }
  }

  if (campaigns.isPending) return <CampaignState>Loading campaigns…</CampaignState>;
  if (campaigns.error) return <CampaignState>{errorMessage(campaigns.error)}</CampaignState>;
  return (
    <CampaignOverview
      campaigns={campaigns.data?.campaigns ?? []}
      findings={campaigns.data?.findings ?? []}
      onSelectCampaign={onSelectCampaign}
    />
  );
}

function CampaignOverview({
  campaigns,
  findings,
  onSelectCampaign,
}: {
  campaigns: CampaignEntry[];
  findings: CampaignFinding[];
  onSelectCampaign: (campaignId: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [configuration, setConfiguration] = useState("");
  const statuses = unique(campaigns.map((campaign) => campaign.status));
  const configurations = unique(campaigns.flatMap(
    (campaign) => campaign.runtime_configurations.map((item) => item.model ?? item.id),
  ));
  const normalized = search.trim().toLocaleLowerCase();
  const filtered = useMemo(
    () => campaigns.filter((campaign) => {
      if (status && campaign.status !== status) return false;
      if (
        configuration
        && !campaign.runtime_configurations.some(
          (item) => (item.model ?? item.id) === configuration,
        )
      ) return false;
      return !normalized || campaignSearchText(campaign).includes(normalized);
    }),
    [campaigns, configuration, normalized, status],
  );

  return (
    <main className="mx-auto grid max-w-[1500px] gap-4 px-8 py-8 max-[900px]:px-4">
      <section>
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          Autoresearch campaigns
        </div>
        <h2 className="mt-1 text-[clamp(1.65rem,3vw,2.35rem)] font-bold tracking-tight">
          Agent improvement over time
        </h2>
        <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          Review bounded hill-climbing campaigns separately from traditional evaluation runs.
        </p>
      </section>

      {findings.length ? (
        <section role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          {findings.length} campaign {findings.length === 1 ? "ledger is" : "ledgers are"} unavailable.
        </section>
      ) : null}

      <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
        <div className="grid items-end gap-3 border-b p-4 lg:grid-cols-[minmax(260px,1fr)_180px_240px]">
          <label className="grid gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Search</span>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="Search autoresearch campaigns"
                value={search}
                placeholder="Campaign, agent, benchmark, model…"
                onChange={(event) => setSearch(event.target.value)}
                className="pl-9"
              />
            </div>
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Status</span>
            <Select aria-label="Filter campaigns by status" value={status} onValueChange={setStatus}>
              <option value="">All statuses</option>
              {statuses.map((item) => <option key={item} value={item}>{humanize(item)}</option>)}
            </Select>
          </label>
          <label className="grid gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Model/config</span>
            <Select aria-label="Filter campaigns by model configuration" value={configuration} onValueChange={setConfiguration}>
              <option value="">All configurations</option>
              {configurations.map((item) => <option key={item} value={item}>{item}</option>)}
            </Select>
          </label>
        </div>
        {filtered.length ? (
          <div className="overflow-x-auto">
            <table aria-label="Autoresearch campaigns" className="w-full min-w-[980px] border-collapse text-sm">
              <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-3">Campaign</th>
                  <th className="px-4 py-3">Starting agent</th>
                  <th className="px-4 py-3">Progress</th>
                  <th className="px-4 py-3">Primary metric</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((campaign) => (
                  <tr
                    key={campaign.campaign_id}
                    className="group cursor-pointer border-t hover:bg-accent/40"
                    onClick={() => onSelectCampaign(campaign.campaign_id)}
                  >
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        aria-label={`Open autoresearch campaign ${campaign.campaign_id}`}
                        className="font-semibold"
                        onClick={(event) => {
                          event.stopPropagation();
                          onSelectCampaign(campaign.campaign_id);
                        }}
                      >
                        {campaign.campaign_id}
                      </button>
                      <div className="mt-1 flex items-center gap-2">
                        <CampaignStatus value={campaign.status} />
                        <span className="text-xs text-muted-foreground">{formatDate(campaign.created_at_utc)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-mono text-xs">{campaign.starting_agent.agent_version_id ?? "Unknown"}</div>
                      <div className="mt-1 text-xs text-muted-foreground">{campaign.benchmark_key ?? "Benchmark"} v{campaign.benchmark_version ?? "—"}</div>
                    </td>
                    <td className="px-4 py-3">{campaign.attempts_finished}/{campaign.max_attempts} trials</td>
                    <td className="px-4 py-3">
                      <strong>{formatMetric(campaign.best_metric)}</strong>
                      <div className="text-xs text-muted-foreground">Baseline {formatMetric(campaign.baseline_metric)}</div>
                    </td>
                    <td className="px-4 py-3">{formatCost(campaign.stored_total_cost)}</td>
                    <td className="px-4 py-3 text-right text-muted-foreground"><ChevronRight className="inline size-4" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <CampaignState>
            {campaigns.length ? "No campaigns match these filters." : "No autoresearch campaigns are available yet."}
          </CampaignState>
        )}
      </section>
    </main>
  );
}

function CampaignDetailView({
  campaign,
  onBack,
  onOpenRun,
}: {
  campaign: CampaignDetail;
  onBack: () => void;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <main className="mx-auto grid max-w-[1500px] gap-5 px-8 py-6 max-[900px]:px-4">
      <section className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Button variant="outline" size="sm" onClick={onBack}>
            <ArrowLeft className="size-3.5" />
            Autoresearch campaigns
          </Button>
          <div className="mt-5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Campaign detail
          </div>
          <h2 className="mt-1 text-2xl font-bold tracking-tight">{campaign.campaign_id}</h2>
          <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
            {campaign.starting_agent.selection_summary ?? "No starting-agent selection summary was recorded."}
          </p>
        </div>
        <CampaignStatus value={campaign.status} />
      </section>

      <section aria-label="Campaign summary" className="grid gap-4 rounded-xl border bg-card p-5 shadow-sm md:grid-cols-2 xl:grid-cols-4">
        <CampaignFact label="Starting agent" value={campaign.starting_agent.agent_version_id ?? "Unknown"} />
        <CampaignFact label="Benchmark" value={`${campaign.benchmark_key ?? "Unknown"} v${campaign.benchmark_version ?? "—"}`} />
        <CampaignFact label="Trials" value={`${campaign.attempts_finished}/${campaign.max_attempts}`} />
        <CampaignFact label="Stored cost" value={formatCost(campaign.stored_total_cost)} />
        <CampaignFact label="Baseline" value={formatMetric(campaign.baseline_metric)} />
        <CampaignFact label="Best" value={formatMetric(campaign.best_metric)} />
        <CampaignFact label="Selection config" value={configurationName(campaign, campaign.selection_configuration_id)} />
        <CampaignFact label="Termination" value={campaign.termination_reason ? humanize(campaign.termination_reason) : "Not terminated"} />
      </section>

      <section className="rounded-xl border bg-card p-5 shadow-sm">
        <h3 className="text-base font-semibold">Performance over time</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Baseline is trial 0. Select a measured point to open its traditional eval run.
        </p>
        <div className="mt-4">
          <CampaignProgressChart campaign={campaign} onOpenRun={onOpenRun} />
        </div>
      </section>

      <section className="rounded-xl border bg-card shadow-sm">
        <div className="border-b px-5 py-4">
          <h3 className="text-base font-semibold">What changed</h3>
          <p className="mt-1 text-sm text-muted-foreground">Candidate changes and decisions in trial order.</p>
        </div>
        {campaign.trials.length ? (
          <div className="divide-y">
            {campaign.trials.map((trial) => (
              <TrialSummary
                key={trial.trial}
                campaign={campaign}
                trial={trial}
                onOpenRun={onOpenRun}
              />
            ))}
          </div>
        ) : (
          <CampaignState>No candidate trials have been finalized yet.</CampaignState>
        )}
      </section>
    </main>
  );
}

function TrialSummary({
  campaign,
  trial,
  onOpenRun,
}: {
  campaign: CampaignDetail;
  trial: CampaignTrial;
  onOpenRun: (runId: string) => void;
}) {
  return (
    <article className="grid gap-3 px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Trial {trial.trial}</div>
          <h4 className="mt-1 font-semibold">{trial.hypothesis ?? "No hypothesis recorded"}</h4>
        </div>
        <CampaignStatus value={trial.decision ?? "unknown"} />
      </div>
      <p className="text-sm">{trial.change_summary ?? "No change summary recorded."}</p>
      {trial.changed_paths?.length ? (
        <p className="font-mono text-xs text-muted-foreground">{trial.changed_paths.join(" · ")}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {trial.evaluations?.map((evaluation) => (
          <Button
            key={`${trial.trial}-${evaluation.configuration_id}`}
            variant="outline"
            size="sm"
            aria-label={evaluation.eval_id
              ? `Open evaluation run ${evaluation.eval_id}`
              : undefined}
            disabled={!evaluation.eval_id}
            onClick={() => evaluation.eval_id && onOpenRun(evaluation.eval_id)}
          >
            {configurationName(campaign, evaluation.configuration_id)}
            <span className="text-muted-foreground">{formatMetric(evaluation.primary_metric)}</span>
          </Button>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">{trial.decision_summary ?? "No decision summary recorded."}</p>
    </article>
  );
}

function CampaignStatus({ value }: { value: string }) {
  const positive = value === "keep" || value === "complete" || value === "qualified";
  const negative = value === "discard" || value === "crash" || value === "failed";
  return (
    <Badge variant={positive ? "success" : negative ? "destructive" : "neutral"}>
      {humanize(value)}
    </Badge>
  );
}

function CampaignFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm font-semibold">{value}</div>
    </div>
  );
}

function CampaignState({ children }: { children: ReactNode }) {
  return <div className="grid min-h-52 place-items-center p-8 text-center text-sm text-muted-foreground">{children}</div>;
}

function configurationName(campaign: CampaignEntry, id?: string | null) {
  const configuration = campaign.runtime_configurations.find((item) => item.id === id);
  if (!configuration) return id ?? "Configuration";
  return `${configuration.model ?? configuration.id}${configuration.reasoning_effort ? ` · ${configuration.reasoning_effort}` : ""}`;
}

function campaignSearchText(campaign: CampaignEntry) {
  return [
    campaign.campaign_id,
    campaign.status,
    campaign.starting_agent.agent_version_id,
    campaign.starting_agent.selection_summary,
    campaign.benchmark_key,
    ...campaign.runtime_configurations.flatMap((item) => [item.id, item.model, item.reasoning_effort]),
  ].filter(Boolean).join(" ").toLocaleLowerCase();
}

function unique(values: string[]) {
  return Array.from(new Set(values)).sort();
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMetric(value?: number | null) {
  if (typeof value !== "number") return "Unavailable";
  return value >= 0 && value <= 1
    ? `${(value * 100).toFixed(1)}%`
    : value.toFixed(3);
}

function formatCost(value?: number | null) {
  return typeof value === "number" ? `$${value.toFixed(2)}` : "Unavailable";
}

function formatDate(value?: string | null) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : date.toLocaleDateString();
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Campaign data is unavailable.";
}
