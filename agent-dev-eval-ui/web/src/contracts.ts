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

export interface DurationStats {
  count: number;
  minimum: number | null;
  maximum: number | null;
  mean?: number | null;
  median: number | null;
  p95: number | null;
}

export interface SlowModelCall {
  execution_id?: string | null;
  work_item_id?: string | null;
  example_id?: string | null;
  unit_id?: string | null;
  duration_seconds?: number | null;
  status?: string | null;
  timeout_seconds?: number | null;
  duration_exceeded_configured_timeout?: boolean | null;
  transport_attempts_observed?: number | null;
  provider_response_id?: string | null;
  error_type?: string | null;
}

export interface PerformancePayload {
  run_id: string;
  availability: "available" | "unavailable";
  reason?: string | null;
  schema_version?: number;
  recorded_executions?: number;
  summary?: {
    evaluation_wall_time_seconds?: number | null;
    throughput_runs_per_minute?: number | null;
    run_duration_seconds?: DurationStats;
    stage_duration_seconds?: Record<string, DurationStats>;
  };
  model_calls?: {
    count?: number;
    duration_seconds?: DurationStats;
    duration_exceeded_configured_timeout_count?: number;
    long_tail_at_or_above_p95_count?: number;
    transport_retry_categories?: Record<string, number>;
    slowest?: SlowModelCall[];
  };
  retries?: {
    availability_counts?: Record<string, number>;
    observed_model_requests?: number;
    observed_tool_calls?: number;
    observed_output_validation_attempts?: number;
    observed_transport_attempts?: number | null;
    observed_transport_retry_categories?: Record<string, number>;
  };
}

export interface AttemptPerformancePayload {
  availability: "available" | "unavailable";
  reason?: string | null;
  execution_id?: string;
  started_at_utc?: string;
  completed_at_utc?: string;
  executor_duration_seconds?: number;
  metrics?: Record<string, unknown>;
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
