export interface FactItem {
  claim: string;
  source_url: string;
  category: string;
}

export interface InferenceItem {
  insight: string;
  confidence: number;
  basis: string;
}

export interface BusinessProfile {
  id: string;
  name: string;
  url?: string;
  description: string;
  industry: string;
  niche: string;
  main_product_or_service: string;
  features: string[];
  problems_solved: string[];
  customer_outcomes: string[];
  icp: string;
  target_industries: string[];
  target_roles: string[];
  customer_demographics: string[];
  customer_frustrations: string[];
  competitors_and_alternatives: string[];
  unique_selling_points: string[];
  pricing_info?: string;
  geographic_market: string;
  trigger_events: string[];
  pain_vocabulary: string[];
  not_for: string[];
  facts: FactItem[];
  inferences: InferenceItem[];
  confirmed: boolean;
  created_at: number;
  updated_at: number;
}

export interface SearchQuery {
  id: string;
  query: string;
  intent_type: string;
  platform: string;
  target_community?: string;
  rationale: string;
  stage?: string;
}

export interface Campaign {
  id: string;
  name: string;
  business_profile_id: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'cancelled';
  selected_platforms: string[];
  queries: SearchQuery[];
  diagnostics?: Record<string, number>;
  total_found: number;
  total_qualified: number;
  high_potential_count: number;
  progress_percentage: number;
  current_step: string;
  created_at: number;
  completed_at?: number;
}

export interface ScoreBreakdown {
  icp_match: number;
  problem_fit: number;
  buying_intent: number;
  urgency: number;
  recency: number;
  total: number;
  explanation: string;
}

export type LeadClassification =
  | 'high_potential'
  | 'relevant_potential'
  | 'customer_insight'
  | 'competitor_intel'
  | 'irrelevant';

export interface ThreadHealth {
  verified?: boolean;
  commentable?: boolean | null;
  num_comments?: number | null;
  score?: number | null;
  age_days?: number | null;
  kind?: string;
  warnings?: string[];
  crowded?: boolean;
}

export interface LeadQualification {
  id: string;
  discovered_item_id: string;
  title: string;
  url: string;
  platform: string;
  community: string;
  author: string;
  published_at: string;
  excerpt: string;
  customer_problem: string;
  pain_point_category: string;
  profile_match: string;
  competitor_mentioned?: string;
  purchase_intent: 'High' | 'Medium' | 'Low' | 'None';
  urgency: 'High' | 'Medium' | 'Low';
  product_fit_explanation: string;
  evidence: string;
  score: number;
  score_breakdown: ScoreBreakdown;
  classification: LeadClassification;
  confidence: number;
  judged_by?: 'llm' | 'heuristic';
  thread_health?: ThreadHealth;
  post_type?: string;
  evidence_verified?: boolean;
  reply_policy?: 'draft' | 'human_only' | string;
  status?: 'new' | 'rejected' | 'replied' | 'closed';
  reject_reason?: string;
  created_at: number;
}

export type LintSeverity = 'error' | 'warn';

export interface LintIssue {
  code: string;
  severity: LintSeverity;
  message: string;
}

export interface LintReport {
  passed: boolean;
  words: number;
  voice_score?: number | null;
  issues: LintIssue[];
}

export interface GeneratedReply {
  id: string;
  lead_id: string;
  account_id?: string;
  value_first: string;
  product_aware: string;
  edited_reply?: string;
  selected_version: 'value_first' | 'product_aware' | 'custom';
  status: 'draft' | 'approved' | 'pending_manual_post' | 'published' | 'rejected';
  published_at?: number;
  platform: string;
  target_url: string;
  affiliation_disclosure: string;
  error_message?: string;
  target_kind?: 'post' | 'comment';
  target_comment_id?: string;
  target_author?: string;
  target_text?: string;
  target_reason?: string;
  pitch_level?: number;
  lint?: {
    value_first?: LintReport;
    product_aware?: LintReport;
    final?: LintReport;
    [key: string]: any;
  };
  needs_human_edit?: boolean;
  generated_by?: string;
  published_comment_id?: string;
  published_url?: string;
  outcome?: Record<string, any>;
  created_at?: number;
  updated_at?: number;
}

export interface PostingSettings {
  mode: 'draft' | 'manual' | 'automatic';
  daily_limit: number;
  min_interval_seconds: number;
  allowed_communities: string[];
  require_account_health?: boolean;
  emergency_stop: boolean;
  interval_jitter?: number;
  max_mention_ratio?: number;
  require_rules_ack?: boolean;
  max_replies_per_thread?: number;
  min_thread_gap_minutes?: number;
  product_community_gap_days?: number;
  reddit_client_id?: string;
  reddit_client_secret?: string;
  reddit_username?: string;
  reddit_password?: string;
  github_token?: string;
  has_reddit_password?: boolean;
  has_reddit_client_secret?: boolean;
  has_github_token?: boolean;
}

export interface LLMSettings {
  provider: string;
  model: string;
  api_key?: string;
  has_api_key?: boolean;
  configured?: boolean;
}

export interface MCPSettings {
  discovery_mode: 'host_driven' | 'built_in_auto';
  default_output_format: 'markdown' | 'json' | 'both';
  default_min_score: number;
  default_export_path: string;
  emergency_stop: boolean;
  auto_launch_dashboard: boolean;
}

export interface SettingsPayload {
  posting_settings: PostingSettings;
  llm_settings: LLMSettings;
  mcp_settings?: MCPSettings;
}

export interface PlatformInfo {
  platforms: string[];
  default: string[];
  weak: string[];
  needs_key?: string[];
}

export interface AccountHealth {
  stage: number;
  stage_name: string;
  max_pitch_level: number;
  suggested_daily_cap: number;
  reasons: string[];
  known: boolean;
}

export interface AccountCredentialVariable {
  name: string;
  set: boolean;
  also_read?: string | null;
}

export interface AccountCredentialReport {
  account: string;
  posting: 'api' | 'manual';
  ready: boolean;
  variables: AccountCredentialVariable[];
  note: string;
}

export interface LinkedAccountDetail {
  platform: string;
  handle: string;
  alias: string;
  focus: string[];
  mode: 'manual' | 'api';
  health: AccountHealth;
  credentials: AccountCredentialReport;
  voice_samples_count: number;
  voice_samples?: string[];
  added_at: number;
  snapshot: Record<string, any>;
}

export interface ConnectionVariable {
  name: string;
  required: boolean;
  purpose: string;
  set: boolean;
}

export interface ConnectionPackage {
  import: string;
  install: string;
  purpose: string;
  installed: boolean;
}

export interface ConnectionSource {
  source: string;
  name: string;
  works_without_setup: string;
  read_variables: ConnectionVariable[];
  packages: ConnectionPackage[];
  posting: string;
  posting_variables?: string;
  how_to_get: string[];
  limits: string;
  accounts?: Array<{
    id: string;
    mode: string;
    alias: string | null;
    credentials: AccountCredentialReport;
  }>;
  accounts_linked?: number;
  status: 'ready' | 'partial';
  server_model_ready?: boolean;
  search_with_api?: boolean;
  transcripts_ready?: boolean;
}

export interface ConnectionsGuide {
  sources: ConnectionSource[];
  where_to_set_variables: string;
  several_accounts: string;
}

export interface CEOIntakeJob {
  id: string;
  platform: string;
  status: 'running' | 'done' | 'failed' | 'interrupted';
  summary?: string;
  threads?: number;
  communities?: Array<{ name: string; threads: number }>;
  queries?: number;
  rejected?: Record<string, number>;
}

export interface CEOIntakeQuestion {
  key: string;
  question: string;
  why: string;
}

export interface CEOIntakeState {
  collected: Record<string, string>;
  accepted: string[];
  rejected: Record<string, string>;
  missing_required: Array<{ key: string; question: string }>;
  jobs: CEOIntakeJob[];
  started_now: string[];
  tell_owner: string;
  ask_next: CEOIntakeQuestion[];
  actions_for_you: string[];
  prefetched_threads: number;
  directive_id?: string | null;
  ready_for_pipeline: boolean;
  suggested_request?: string;
  next?: string;
}

export interface AnalyticsSummary {
  total_leads: number;
  top_communities?: { community: string; leads: number; high_potential: number }[];
  reply_mix?: {
    published_last_90_days: number;
    product_aware: number;
    value_first: number;
    product_share?: number;
  };
  common_complaints: { problem: string; count: number; category: string }[];
  pain_point_categories: { category: string; count: number }[];
  high_urgency_problems: { problem: string; count: number; community: string; excerpt: string }[];
  competitor_intelligence: { competitor: string; mentions: number }[];
  intent_distribution: Record<string, number>;
  urgency_distribution: Record<string, number>;
  platform_distribution: Record<string, number>;
  recommendations: { type: string; title: string; description: string }[];
}

// ── Company & Team Layer Types ──

export type DirectiveStatus =
  | 'open'
  | 'running'
  | 'waiting_owner'
  | 'needs_ceo'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type TaskStatus =
  | 'pending'
  | 'ready'
  | 'running'
  | 'done'
  | 'escalated'
  | 'needs_owner'
  | 'blocked'
  | 'skipped';

export interface Evidence {
  id: string;
  tool: string;
  ok: boolean;
  args: Record<string, any>;
  text: string;
  urls: string[];
  at: number;
}

export interface Verdict {
  passed: boolean;
  issues: string[];
  checks: Record<string, boolean>;
  auditor: 'pass' | 'fail' | 'unavailable' | 'skipped' | string;
  notes: string[];
  trust: 'high' | 'medium' | 'low' | string;
  at: number;
}

export interface TeamTask {
  task_id: string;
  role: string;
  title: string;
  kind: 'work' | 'checkpoint';
  status: TaskStatus;
  depends_on: string[];
  attempts: number;
  issues?: string[];
  checkpoint?: string;
  instruction?: string;
  acceptance?: string[];
  feedback?: string[];
  result?: {
    summary?: string;
    claims?: Array<{ text: string; evidence_ids: string[]; quote?: string; assumption?: boolean }>;
    data?: Record<string, any>;
  };
  verdict?: Verdict;
  owner_message?: string;
  owner_channel?: string;
}

export interface DirectiveSummary {
  directive_id: string;
  request: string;
  intent: string;
  status: DirectiveStatus;
}

export interface DirectiveDetail {
  directive_id: string;
  request: string;
  intent: string;
  status: DirectiveStatus;
  progress: { done: number; total: number };
  notes: string[];
  tasks: TeamTask[];
  events: Array<{ at: number; kind: string; note: string; task_id?: string }>;
  next: string;
}

export interface InspectionRow {
  reply_id: string;
  code: string;
  message: string;
  ready: boolean;
  waits: boolean;
  editor_verdict: string;
  attention: string[];
  title: string;
}

export interface LeadCard {
  lead_id: string;
  title: string;
  url: string;
  platform: string;
  community: string;
  score: number;
  classification: string;
  quote_verified: boolean;
  evidence_quote: string;
  status: string;
  reply?: {
    reply_id: string;
    status: string;
    pitch_level?: number;
    value_first?: string;
    product_aware?: string;
    lint_passed?: boolean;
    gate?: {
      code: string;
      message: string;
      ready: boolean;
      waits: boolean;
      editor_verdict: string;
      attention: string[];
    };
  };
}

export interface TeamReport {
  directive_id: string;
  request: string;
  status: DirectiveStatus;
  headline: string;
  summary: string;
  trust: 'high' | 'medium' | 'low' | 'none' | 'partial' | string;
  lead_cards: LeadCard[];
  inspection: InspectionRow[];
  what_was_tried: string[];
  verified_work: Array<{
    task_id: string;
    role: string;
    title: string;
    summary: string;
    claims: Array<{ text: string; evidence_ids: string[]; quote?: string }>;
    assumptions: string[];
    auditor: string;
    trust: string;
    attempts: number;
  }>;
  not_verified: Array<{
    task_id: string;
    role: string;
    title: string;
    status: string;
    issues: string[];
  }>;
  owner_actions: string[];
  stats: {
    leads: number;
    replies: Record<string, number>;
  };
  quality: {
    tool_calls: number;
    failed_checks_before_pass: number;
    tasks_escalated: number;
    tasks_skipped_for_empty_input: number;
    revision_rounds: number;
  };
  progress: { done: number; total: number };
  ledger: {
    evidence_items: number;
    tool_calls_failed: number;
  };
  owner_confirmations: Array<{
    checkpoint: string;
    via: string;
    message: string;
  }>;
}

export interface RoleSpec {
  name: string;
  title: string;
  tier: 'fast' | 'smart';
  builtin: boolean;
  skills: string[];
  tools: string[];
  automatic: boolean;
}

export interface Playbook {
  name: string;
  description: string;
  steps: string[];
  builtin: boolean;
}

export interface TeamRoster {
  ceo: string;
  roles: RoleSpec[];
  playbooks: Playbook[];
  model_configured: boolean;
  memory_notes: number;
}

export interface MemoryItem {
  id: number;
  category: string;
  text: string;
  directive_id?: string;
  created_at: number;
}

export interface NextStep {
  directive_id: string;
  status: DirectiveStatus;
  progress: { done: number; total: number };
  do: 'work' | 'ask_owner' | 'decide' | 'run' | 'report' | 'wait' | 'stop';
  why?: string;
  call?: string;
  task_id?: string;
  role?: string;
  title?: string;
  checkpoint?: string;
  question?: string;
  issues?: string[];
  choices?: string[];
  then?: string;
  rule?: string;
}

export interface AskCeoResponse {
  directive_id: string;
  intent: string;
  status: DirectiveStatus;
  mode?: 'server' | 'host';
  running?: boolean;
  next?: string;
  readiness?: string[];
  report?: TeamReport | { summary: string };
  error?: string;
}

export interface CheckpointResolution {
  task: TeamTask;
  directive_status: DirectiveStatus;
  owner_channel: string;
}

