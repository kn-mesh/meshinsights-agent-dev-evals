import type { ComponentType } from "react";

export interface AccuracyMetric {
  accuracy: number | null;
  correct_runs: number;
  evaluated_runs: number;
}

export interface FieldAccuracyMetric extends AccuracyMetric {
  by_confidence: Record<string, AccuracyMetric>;
}

export interface AccuracySummary {
  complete_evaluation: AccuracyMetric;
  by_field: Record<string, FieldAccuracyMetric>;
}

export interface CostDistribution {
  count: number;
  total: number;
  average: number;
  p5: number;
  p95: number;
}

export interface CostSummary {
  attempts_with_cost_observations: number;
  recorded_attempts: number;
  units_with_complete_cost_observations: number;
  units_with_partial_pricing: number;
  units_without_usable_cost_information: number;
  status_counts: Record<string, number>;
  actual_by_currency: Record<string, number>;
  estimated_by_currency: Record<string, number>;
  complete_unit_cost_by_currency: Record<string, CostDistribution>;
}

export interface PublishedLabelerNote {
  review_event_id: string;
  reviewer_display_name: string;
  reviewer_project_role: string;
  submitted_at: string;
  explanation: string;
  selected_for_publication: boolean;
}

export interface PublishedVerification {
  source: "direct_observation" | "operator_feedback";
  note?: string | null;
  recorded_at?: string | null;
  source_content_sha256?: string | null;
  context_schema_key?: string | null;
  context_schema_version?: string | null;
  source_fields?: Record<string, unknown> | null;
}

export interface BenchmarkContext {
  availability: "available";
  labeler_notes: PublishedLabelerNote[];
  verification: PublishedVerification | null;
}

export interface SourceVerificationSchema {
  schema_key: string;
  version: string;
  title: string;
  fields: Array<{
    key: string;
    label: string;
    value_type: "text" | "long_text" | "timestamp";
  }>;
}

export interface RunEntry {
  run_id: string;
  lifecycle_state: "working" | "retained";
  source_run_id?: string;
  result_status: string;
  agent_version_id: string;
  pipeline_path?: string | null;
  benchmark_key?: string | null;
  benchmark_version?: number | null;
  model?: string | null;
  reasoning_effort?: string | null;
  configuration?: Record<string, unknown>;
  planned_attempts: number;
  recorded_attempts: number;
  review_status: string;
  created_at_utc?: string | null;
  accuracy?: AccuracySummary | null;
  cost?: CostSummary | null;
}

export interface AttemptRow {
  example_id: string;
  unit_id: string;
  run_index: number;
  execution_id: string;
  execution_status: string;
  output_contract_status: string;
  scoring_status: string;
  complete_evaluation_correct: boolean | null;
  benchmark_labels: Record<string, unknown>;
  agent_output: Record<string, unknown>;
  evaluations: Record<string, unknown>;
  slice_keys: string[];
  flaky: boolean;
  review_status: string;
  review_unavailable_reason?: {
    code: "disabled" | "capture_failed" | "capture_partial" | "purged" | "absent";
    error_type?: string | null;
    message?: string | null;
  } | null;
}

export interface EvidenceView<T = unknown> {
  example: {
    example_id: string;
    unit_id: string;
    decision_timestamp: string;
    metadata: Record<string, unknown>;
  };
  window: {
    start: string;
    end: string;
    basis: string;
    [key: string]: unknown;
  };
  evidence: T;
  metadata: {
    evidence_schema_version: string;
    evidence_recipe_id: string;
    source_snapshot_id: string;
    source_snapshot_content_sha256: string;
    source_kind: string;
    known_gaps: string[];
  };
}

export interface UseCaseAdapter {
  EvidenceDisplay: ComponentType<{ evidence: EvidenceView }>;
  contextLabel?: string;
  evaluationFieldLabels?: Record<string, string>;
  sourceVerificationSchemas?: SourceVerificationSchema[];
}
