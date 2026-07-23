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

export type BenchmarkContext =
  | {
      availability: "available";
      labeler_notes: PublishedLabelerNote[];
      verification: PublishedVerification | null;
    }
  | {
      availability: "unavailable";
      reason: string;
    };

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
  evaluationFieldLabels?: Record<string, string>;
  sourceVerificationSchemas?: SourceVerificationSchema[];
}
