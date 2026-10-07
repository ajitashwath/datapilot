export type ColumnKind = "numeric" | "categorical" | "date" | "text" | "boolean";

export interface TopValue {
  value: string | number | boolean | null;
  count: number;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  kind: ColumnKind;
  missing: number;
  missing_pct: number;
  distinct: number;
  min: string | number | null;
  max: string | number | null;
  mean: number | null;
  std: number | null;
  median: number | null;
  q1: number | null;
  q3: number | null;
  top_values: TopValue[];
  samples: unknown[];
}

export interface DatasetProfile {
  name: string;
  filename: string;
  rows: number;
  column_count: number;
  duplicate_rows: number;
  skipped_rows: number;
  columns: ColumnProfile[];
}

export interface DatasetDetail {
  profile: DatasetProfile;
  quality_score: number;
  issue_count: number;
}

export interface Relationship {
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  cardinality: string;
  overlap_pct: number;
  source: "inferred" | "user";
}

export interface SessionState {
  session_id: string;
  datasets: DatasetDetail[];
  relationships: Relationship[];
  filters: Record<string, string>;
  active_dataset: string | null;
  llm: { provider: string; model: string } | null;
}

export interface QualityIssue {
  severity: "low" | "medium" | "high";
  type: string;
  column: string | null;
  message: string;
  count: number;
}

export interface QualityReport {
  dataset: string;
  score: number;
  issues: QualityIssue[];
}

export interface TableResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}

export interface AnomalyResult {
  is_anomaly: boolean;
  method: string;
  column: string;
  affected_rows: Record<string, unknown>[];
  total_flagged: number;
  reason: string;
  severity: "none" | "low" | "medium" | "high";
  bounds: Record<string, number>;
}

export interface ChartSpec {
  type: "bar" | "line" | "pie" | "scatter" | "histogram";
  title: string;
  x_label: string;
  y_label: string;
  x_key: string;
  y_keys: string[];
  data: Record<string, string | number | null>[];
  note: string | null;
}

export interface ToolResult {
  ok: boolean;
  data: Record<string, unknown>;
  error: string | null;
  sql: string | null;
  code: string | null;
  table: TableResult | null;
  chart: ChartSpec | null;
  anomalies: AnomalyResult[];
}

export interface Overview {
  dataset: string;
  rows: number;
  columns: number;
  duplicate_rows: number;
  quality_score: number;
  key_metrics: { column: string; sum: number; mean: number | null; min: number | null; max: number | null; median: number | null }[];
  missing: { column: string; missing: number; missing_pct: number }[];
  distributions: { column: string; bins: { bin: string; count: number }[]; outliers_excluded: number }[];
  categories: { column: string; distinct: number; top: { value: string; count: number; share_pct: number }[] }[];
  date_ranges: { column: string; min: string; max: string }[];
  suggested_questions: string[];
}

export interface AppConfig {
  llm_configured: boolean;
  provider: string;
  model: string;
  default_models: Record<string, string>;
  max_upload_mb: number;
  max_files_per_session: number;
  sql_timeout_seconds: number;
  python_timeout_seconds: number;
  max_result_rows: number;
  sample_datasets: string[];
  auth_required: boolean;
  python_enabled: boolean;
}

export interface UploadResponse {
  datasets: DatasetDetail[];
  errors: { filename: string; message: string }[];
}

export type StreamEvent =
  | { type: "text"; step: number; delta: string }
  | { type: "tool_call"; step: number; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; step: number; id: string; name: string; duration_ms: number; result: ToolResult }
  | { type: "done"; tools_used: string[]; warnings: string[]; duration_ms: number }
  | { type: "error"; message: string };

export type Step =
  | { kind: "text"; step: number; text: string }
  | { kind: "tool"; id: string; name: string; input: Record<string, unknown>; result?: ToolResult; durationMs?: number };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  steps: Step[];
  status: "streaming" | "done" | "error";
  error?: string;
  warnings: string[];
  durationMs?: number;
}

export interface TranscriptEntry {
  question: string;
  events: StreamEvent[];
}
