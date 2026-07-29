export interface CampaignStartingAgent {
  git_commit?: string | null;
  agent_version_id?: string | null;
  selection_summary?: string | null;
}

export interface CampaignRuntimeConfiguration {
  id: string;
  role?: string | null;
  model?: string | null;
  reasoning_effort?: string | null;
}

export interface CampaignOutcomes {
  keep: number;
  discard: number;
  inconclusive: number;
  crash: number;
}

export interface CampaignEntry {
  campaign_id: string;
  status: string;
  created_at_utc?: string | null;
  completed_at_utc?: string | null;
  termination_reason?: string | null;
  starting_agent: CampaignStartingAgent;
  base_agent_name?: string | null;
  benchmark_key?: string | null;
  benchmark_version?: number | null;
  research_scope?: unknown;
  qualification_scope?: unknown;
  runtime_configurations: CampaignRuntimeConfiguration[];
  selection_configuration_id: string;
  primary_metric?: string | null;
  attempts_finished: number;
  max_attempts: number;
  stored_total_cost: number;
  baseline_metric?: number | null;
  best_metric?: number | null;
  outcomes: CampaignOutcomes;
}

export interface CampaignEvaluation {
  configuration_id?: string | null;
  eval_id?: string | null;
  primary_metric?: number | null;
  scoring_coverage?: number | null;
  critical_regressions?: number | null;
  cost?: number | null;
}

export interface CampaignTrial {
  trial: number;
  parent_commit?: string | null;
  candidate_commit?: string | null;
  agent_version_id?: string | null;
  hypothesis?: string | null;
  change_summary?: string | null;
  changed_paths?: string[];
  evaluations?: CampaignEvaluation[];
  decision?: "keep" | "discard" | "inconclusive" | "crash" | string;
  decision_summary?: string | null;
}

export interface CampaignPoint extends CampaignEvaluation {
  stage: "baseline" | "trial" | "qualification";
  trial: number;
  decision: string;
  agent_version_id?: string | null;
}

export interface CampaignDetail extends CampaignEntry {
  direction: string;
  points: CampaignPoint[];
  trials: CampaignTrial[];
}

export interface CampaignFinding {
  campaign_id: string;
  code: string;
  message: string;
}

export interface CampaignListPayload {
  campaigns: CampaignEntry[];
  findings: CampaignFinding[];
}
