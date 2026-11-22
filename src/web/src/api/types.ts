export type EvidenceKind = "synthetic" | "released";
export type RunStatus = "pending" | "running" | "succeeded" | "partial" | "failed";

export interface Page {
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface Dataset {
  id: string;
  dataset_name: string;
  version: number;
  evidence_kind: EvidenceKind;
  release_manifest_sha256: string;
  created_at: string;
  asset_count: number;
  batch_count: number;
  latest_ingestion_status: string | null;
  error_quality_issue_count: number;
  warning_quality_issue_count: number;
}

export interface DatasetSummary {
  dataset: Dataset;
  splits: Record<string, number>;
  quality_by_rule: Array<{
    rule_id: string;
    severity: "warning" | "error";
    count: number;
    asset_count: number;
  }>;
}

export interface Batch {
  id: string;
  dataset_version_id: string;
  kind: string;
  split: string | null;
  member_count: number;
  membership_sha256: string;
  created_at: string;
  latest_run_id: string | null;
  latest_run_status: RunStatus | null;
}

export interface InferenceRun {
  id: string;
  dataset_version_id: string;
  batch_id: string;
  model_id: string;
  status: RunStatus;
  evidence_kind: EvidenceKind;
  architecture: string;
  model_sha256: string;
  expected_items: number;
  succeeded_items: number;
  failed_items: number;
  pending_items: number;
  running_items: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  config: Record<string, unknown>;
}

export interface RunDetail extends InferenceRun {
  batch_kind: string;
  batch_split: string | null;
  membership_sha256: string;
  classes: string[];
  config_sha256: string;
  model_config_sha256: string;
  inference_config: Record<string, unknown>;
  dataset_name: string;
  dataset_release: number;
  dataset_evidence_kind: EvidenceKind;
}

export interface Detection {
  ordinal: number;
  class_id: number;
  class_name: string;
  confidence: number;
  box_xmin: number;
  box_ymin: number;
  box_xmax: number;
  box_ymax: number;
}

export interface ImageResult {
  asset_id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  image_sha256: string;
  width: number;
  height: number;
  detection_count: number | null;
  raw_prediction_count: number | null;
  latency_ms: number | null;
  attempts: number;
  last_error: string | null;
  image_url: string;
  overlay_sha256: string | null;
  overlay_url: string | null;
  detections: Detection[];
}

export interface Metric {
  metric_name: string;
  value: number | null;
  unit: string;
  value_type: string;
  denominator_name: string | null;
  denominator_value: number | null;
  evidence_status: string;
  reason: string | null;
}

export interface Comparison {
  metric_name: string;
  unit: string;
  absolute_delta: number | null;
  relative_delta: number | null;
  relative_delta_reason: string | null;
  percentage_point_delta: number | null;
}

export interface ContextSnapshot {
  id: string;
  payload_sha256: string;
  payload: {
    format: string;
    scope_set: Array<{
      role: "primary" | "left" | "right";
      evidence: {
        scope: Record<string, string | number | null>;
        coverage: Record<string, number | string>;
        provenance: Record<string, unknown>;
        metrics: Metric[];
      };
    }>;
  };
}

export interface UploadRequest {
  id: string;
  original_filename: string;
  content_sha256: string;
  byte_count: number;
  media_type: "image/png" | "image/jpeg";
  width: number;
  height: number;
  artifact_url: string;
  status: "pending" | "ready" | "failed";
  inference_state:
    | "not_started"
    | "pending_registration"
    | "unavailable";
  dataset_version_id: string | null;
  batch_id: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentFixture {
  id: string;
  evidence_kind: "development-fixture";
  question: string;
  status: "answered" | "partial" | "clarification" | "abstained" | "error";
  answer: string;
  numeric_claims: Array<Record<string, unknown>>;
  citations: Array<Record<string, unknown>>;
  verification_status: string;
  tool_trace: Array<Record<string, unknown>>;
}

export interface ApiList<T> {
  items: T[];
  page: Page;
}
