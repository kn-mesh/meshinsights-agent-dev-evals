import type { ComponentType } from "react";

export interface RunEntry {
  run_id: string;
  result_status: string;
  agent_version_id: string;
  pipeline_path?: string | null;
  benchmark_key?: string | null;
  benchmark_version?: number | null;
  model?: string | null;
  reasoning_effort?: string | null;
  planned_attempts: number;
  recorded_attempts: number;
  review_status: string;
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
  actual_outputs: Record<string, unknown>;
  fields: Record<string, unknown>;
  slice_keys: string[];
  flaky: boolean;
  review_status: string;
  duration_seconds?: number | null;
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
}
