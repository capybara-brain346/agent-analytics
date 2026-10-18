// Types for the JSON of apps/api. One type for each response model in
// apps/api/src/models/api.py, plus the routes that return plain dicts.
// JSON is snake_case. Times are ISO 8601 UTC strings.

export type Label = "observed" | "inferred" | "unknown";
export type TrafficClass = 1 | 2 | 3 | 4 | 5 | 6;
export type Verdict =
  "VERIFIED" | "CLAIMED" | "UNVERIFIED" | "SPOOFED" | "UNKNOWN";
export type ConfidenceLevel = "high" | "medium" | "low";
export type ChangeKind = "new" | "open" | "gone";

export type PageInfo = {
  limit: number;
  offset: number;
  total: number;
  next_offset: number | null;
};
export type Paged<T> = { items: T[]; page: PageInfo };
export type ErrorBody = { code: string; message: string };
export type LabeledText = { text: string | null; label: Label };

export type Window = {
  site: string;
  start: string;
  end: string;
  classes: number[];
};

// ---- health (GET /health, answers 503 with the same body when unhealthy)
export type LaneHealth = {
  site_id: string;
  lane: "fast" | "slow";
  last_success: string | null;
  healthy: boolean;
};
export type HealthAlert = {
  id: number;
  site_id: string;
  kind: string;
  source: string | null;
  message: string;
  raised_at: string;
};
export type Health = {
  healthy: boolean;
  lanes: LaneHealth[];
  alerts: HealthAlert[];
};

// ---- overview
export type KeyNumber = {
  value: number | null;
  previous: number | null;
  change_pct: number | null;
  unit: "requests" | "percent" | "agents";
  label: Label;
};
export type KeyNumberName =
  | "total_requests"
  | "ai_or_automated_share"
  | "distinct_agents"
  | "error_rate"
  | "denial_rate";
export type ClassRow = {
  traffic_class: TrafficClass;
  name: string;
  requests: number;
  share_pct: number;
  high: number;
  medium: number;
  low: number;
  label: Label;
};
export type TrendPoint = {
  bucket: string;
  total: number;
  // Keys are class numbers as strings, or "unclassified".
  by_class: Record<string, number>;
};
export type TopAgent = {
  agent: string;
  traffic_class: TrafficClass;
  requests: number;
};
export type TopPage = {
  path: string;
  agent_requests: number;
  errors: number;
  blocks: number;
};
export type FreshnessState =
  | "ok"
  | "updating"
  | "last_run_failed"
  | "alert_failing"
  | "alert_no_data"
  | "no_runs";
export type Freshness = {
  state: FreshnessState;
  text: string;
  data_up_to: string | null;
  last_import_at: string | null;
  latest_run_id: string | null;
  failed_step: string | null;
  consecutive_failures: number;
};
export type AlertOut = {
  id: number;
  kind: string;
  source: string | null;
  message: string;
  raised_at: string;
  resolved_at: string | null;
};
export type Coverage = {
  sources_configured: string[];
  sources_present: string[];
  paired_share_pct: number | null;
  unknown_share_pct: number | null;
  cannot_see: string[];
  partial: string[];
  label: Label;
};
export type RecommendationBrief = {
  id: number;
  rank: number | null;
  target: string;
  pattern: string;
  pattern_name: string;
  score: number;
  confidence: string;
  change: ChangeKind | null;
};
export type Overview = {
  window: Window;
  empty: boolean;
  freshness: Freshness;
  key_numbers: Record<KeyNumberName, KeyNumber>;
  traffic_by_class: ClassRow[];
  unclassified_requests: number;
  trend: TrendPoint[];
  top_agents: TopAgent[];
  top_pages: TopPage[];
  top_recommendations: RecommendationBrief[];
  coverage: Coverage;
  open_alerts_count: number;
  open_alerts: AlertOut[];
};

// ---- recommendations
export type Factor = { value: number; why: string | null };
export type Priority = {
  score: number;
  formula: string;
  factors: Record<"impact" | "frequency" | "severity" | "confidence", Factor>;
};
export type EvidenceRef = {
  sessions_count: number;
  events_count: number;
  session_ids: string[];
  event_ids: number[];
  label: Label;
};
export type RunHeader = {
  id: number;
  site: string;
  status: string;
  window_size: string;
  window_start: string;
  window_end: string;
  created_at: string;
  finished_at: string | null;
  rule_version: string | null;
  prompt_version: string | null;
  model: string | null;
  compared_with_run_id: number | null;
  counts: { new: number; open: number; gone: number; total: number };
  error: string | null;
};
export type RecommendationItem = {
  id: number;
  run_id: number;
  stable_id: string;
  rank: number | null;
  change: ChangeKind | null;
  pattern: string;
  pattern_name: string;
  journey_id: string | null;
  target: string;
  recommended_test: string | null;
  priority: Priority;
  confidence: string;
  sessions_count: number;
  events_count: number;
  text_source: string;
};
export type RecommendationList = {
  run: RunHeader | null;
  empty_reason: "no_run" | "no_candidates" | null;
  items: RecommendationItem[];
  gone: RecommendationItem[];
};
export type HistoryEntry = {
  run_id: number;
  recommendation_id: number;
  rank: number | null;
  score: number;
  change: string | null;
};
export type RecommendationDetail = RecommendationItem & {
  reason: LabeledText;
  evidence: EvidenceRef;
  potential_issue: LabeledText;
  suggested_validation: LabeledText;
  next_action: LabeledText;
  model: string | null;
  prompt_version: string | null;
  text_source_note: string;
  fact_bundle: Record<string, unknown>;
  history: HistoryEntry[];
  first_seen_run_id: number;
  related: RecommendationBrief[];
  run: RunHeader;
};
export type GenerateResult = { status: "completed"; run: RunHeader | null };
// Rows in the "recommendations" list of event, session and page detail.
export type RecommendationRef = {
  id: number;
  run_id: number;
  pattern: string;
  target: string;
  score: number;
  // Only on page detail.
  confidence?: string;
  change?: string | null;
};

// ---- agents
export type AgentRow = {
  agent_id: string;
  name: string;
  vendor: string | null;
  traffic_class: TrafficClass;
  class_name: string;
  verification: Verdict | null;
  verification_note: string;
  confidence: ConfidenceLevel | null;
  first_seen: string | null;
  last_seen: string | null;
  requests: number;
  sessions: number;
  distinct_pages: number;
  common_paths: string[];
  label: Label;
};
export type VerdictRow = {
  id: number;
  checked_at: string;
  verdict: Verdict;
  method: string;
  evidence: string | null;
  registry_version: string | null;
  ip_snapshot_version: string | null;
  claimed_agent: string | null;
  client_key: string;
  user_agent: string | null;
  client_ip: string | null;
  edge_signal: string;
  traffic_class: TrafficClass | null;
  confidence: ConfidenceLevel | null;
  rule_id: string | null;
  rule_version: string | null;
  class_evidence: string | null;
  flags: string[];
  ua_type: string | null;
  registry_category: string | null;
  events_link: string;
};
export type ClientKeyRow = {
  client_key: string;
  user_agent: string | null;
  client_ip: string | null;
  shared_ip: boolean;
};
// Inputs of a classification rule. Used by agent detail and event detail.
export type ClassInputs = {
  verdict: Verdict | null;
  registry_category: string | null;
  ua_type: string | null;
  edge_signal: string | null;
};
export type WhyThisClass = {
  rule_id: string | null;
  rule_version: string | null;
  registry_version: string | null;
  inputs: ClassInputs;
  evidence: string | null;
  label: "inferred";
};
export type AgentDetail = {
  agent: AgentRow;
  why_this_class: WhyThisClass;
  verdict_history: VerdictRow[];
  client_keys: ClientKeyRow[];
  activity: { hour: string; requests: number }[];
  top_paths: { path: string; requests: number }[];
  status_mix: { status: number | null; requests: number }[];
  sessions: SessionRow[];
};

// ---- events
export type EventRow = {
  id: number;
  ts: string;
  method: string | null;
  host: string | null;
  path: string;
  status: number | null;
  edge_status: number | null;
  origin_status: number | null;
  source: string;
  pair_state: string;
  client_key: string | null;
  user_agent: string | null;
  client_ip: string | null;
  verdict_id: number | null;
  claimed_agent: string | null;
  verdict: Verdict | null;
  confidence: ConfidenceLevel | null;
  traffic_class: TrafficClass | null;
  class_name: string | null;
  session_id: string | null;
};
export type SessionLink = { session_id: string; position: number; of: number };
export type EventRequest = {
  ts: string;
  host: string | null;
  method: string | null;
  path: string;
  status: number | null;
  bytes_sent: number | null;
  response_time_ms: number | null;
  referrer: string | null;
  user_agent: string | null;
  client_ip: string | null;
  client_key: string | null;
  edge_signal: string | null;
};
export type EventSource = {
  source: string;
  pair_state: string;
  edge_status: number | null;
  origin_status: number | null;
  request_id: string | null;
  edge_request_id: string | null;
  cdn_bypass: boolean | null;
  file_id: string | null;
  line_no: number | null;
};
export type EventClassification = {
  traffic_class: TrafficClass;
  class_name: string | null;
  confidence: ConfidenceLevel | null;
  rule_id: string | null;
  rule_version: string | null;
  inputs: ClassInputs;
  evidence: string | null;
  label: "inferred";
};
export type EventImportFile = {
  id: string;
  source: string;
  entry: string;
  status: string;
  received_at: string;
  finished_at: string | null;
  lines_total: number;
  lines_imported: number;
  lines_rejected: number;
  lines_duplicate: number;
  object_key: string | null;
};
export type EventDetail = {
  id: number;
  request: EventRequest;
  request_label: Label;
  source: EventSource;
  verdict: VerdictRow | null;
  classification: EventClassification | null;
  session: SessionLink | null;
  import_file: EventImportFile | null;
  recommendations: RecommendationRef[];
};

// ---- sessions
export type SessionRow = {
  session_id: string;
  client_key: string;
  agent: string | null;
  traffic_class: TrafficClass | null;
  class_name: string | null;
  confidence: ConfidenceLevel | null;
  started: string;
  last_seen: string;
  state: "in_progress" | "closed";
  in_progress: boolean;
  last_event_age_seconds: number | null;
  requests: number;
  distinct_pages: number;
  has_retry: boolean;
  has_loop: boolean;
  reached_conversion: boolean;
  // Journey id -> highest step reached (1-based).
  journeys_reached: Record<string, number>;
  label: Label;
};
export type SessionStep = {
  seq: number;
  event_id: number;
  ts: string;
  path: string;
  method: string | null;
  status: number | null;
  delta_seconds: number | null;
  // "retry" | "loop" | "key_page" | "conversion_page"
  flags: string[];
};
export type Gap = { text: string; label: Label };
export type SessionFacts = {
  state: string;
  requests: number;
  distinct_pages: number;
  // HTTP status -> count.
  status_counts: Record<string, number>;
  has_retry: boolean;
  has_loop: boolean;
  retries: number;
  key_pages_visited: number;
  reached_conversion: boolean;
  journeys_reached: Record<string, number>;
};
export type SessionDetail = {
  session: SessionRow;
  facts: SessionFacts;
  facts_label: Label;
  grouping: LabeledText;
  confidence_reason: LabeledText;
  steps: SessionStep[];
  outcome: LabeledText;
  gaps: Gap[];
  recommendations: RecommendationRef[];
};

// ---- pages
export type PageRow = {
  path: string;
  // "key" | "conversion" | other stored tags
  tags: string[];
  agent_requests: number;
  requests: number;
  sessions: number;
  distinct_agents: number;
  error_rate_pct: number | null;
  block_rate_pct: number | null;
  retries: number;
  median_bytes: number | null;
  label: Label;
};
export type PageView =
  "agent_heavy" | "errors" | "blocks" | "retries" | "never_reached";
export type PageList = { view: PageView | null; items: PageRow[] };
export type PageClassRow = {
  traffic_class: TrafficClass | null;
  requests: number;
  n_2xx: number;
  n_3xx: number;
  n_403: number;
  n_429: number;
  n_4xx: number;
  n_5xx: number;
  retries: number;
};
export type PageDetail = {
  page: PageRow;
  in_sitemap: boolean;
  access_policy: "allowed" | "blocked_by_intent";
  by_class: PageClassRow[];
  over_time: { hour: string; requests: number; errors: number }[];
  agents: {
    claimed_agent: string | null;
    traffic_class: TrafficClass | null;
    sessions: number;
  }[];
  sessions: SessionRow[];
  recommendations: RecommendationRef[];
};
// GET /api/pages answers PageList, or PageDetail when `path` is set.
export type PagesResponse = PageList | PageDetail;

// ---- journeys
export type JourneyClassRow = {
  traffic_class: TrafficClass;
  class_name: string;
  sessions: number;
  // One value for each step. reached[k]: sessions that got to step k+1 or further.
  reached: number[];
  stopped_at: number[];
  retry_or_loop: number[];
  label: Label;
};
export type JourneyOut = {
  journey_id: string;
  critical: boolean;
  steps: string[];
  by_class: JourneyClassRow[];
  outcome: LabeledText;
};

// ---- pipeline runs (GET /api/runs)
export type PipelineRunOut = {
  id: string;
  site: string;
  lane: "fast" | "slow";
  status: "running" | "success" | "failed" | string;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  failed_step: string | null;
  error: string | null;
  // Counts for each step. The keys depend on the pipeline.
  counts: Record<string, unknown>;
};

// ---- imports (apps/api/src/routes/imports.py, plain models)
export type OverlapWarning = { file_id: string; message: string };
export type ImportFile = {
  id: string;
  site_id: string;
  source: string;
  entry: string;
  priority: string;
  status: string;
  size_bytes: number;
  received_at: string;
  started_at: string | null;
  finished_at: string | null;
  lines_total: number;
  lines_imported: number;
  lines_rejected: number;
  lines_duplicate: number;
  rejects_count: number;
  min_ts: string | null;
  max_ts: string | null;
  error: string | null;
  delete_on: string | null;
  overlap_warning: OverlapWarning | null;
};
// Unlike Paged<T>, this list keeps limit, offset and total at the top level.
export type ImportList = {
  items: ImportFile[];
  total: number;
  limit: number;
  offset: number;
};
// POST /api/imports/upload (202, or 200 when the file is a duplicate).
export type IngestAccepted = { file_id: string; duplicate: boolean };
// DELETE /api/imports/{id}. files_reimported: paired partner files read again.
export type ImportDeleted = {
  file_id: string;
  site_id: string;
  events_deleted: number;
  files_reimported: string[];
};
