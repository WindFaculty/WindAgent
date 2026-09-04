/**
 * Canonical Transport DTOs for the WindAgent V2 API (/api/v4/*).
 */

// --- System & Diagnostics ---
export interface HealthResponse {
  status: "ok";
  version: string;
}

export interface ReadinessResponse {
  status: "ready";
  environment: "development" | "test" | "production";
  database: string;
}

export interface SystemModuleInfo {
  name: string;
  version: string;
  status: "active" | "degraded" | "disabled";
  capabilities: string[];
}

export interface SystemModulesResponse {
  api_version: string;
  modules: SystemModuleInfo[];
}

// --- Workspace Module ---
export interface WorkspaceMember {
  user_id: string;
  email: string;
  role: "OWNER" | "ADMIN" | "MEMBER" | "VIEWER";
  joined_at: string;
}

export interface WorkspaceQuota {
  max_projects: number;
  max_storage_bytes: number;
  max_concurrent_runs: number;
  max_credits_per_month: number;
  current_projects: number;
  current_storage_bytes: number;
  current_concurrent_runs: number;
  used_credits_this_month: number;
}

export interface ResourceLock {
  lock_id: string;
  resource_type: string;
  resource_id: string;
  holder_id: string;
  fencing_token: number;
  expires_at: string;
}

export interface WorkspaceDTO {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  status: "active" | "suspended" | "archived";
  created_at: string;
  updated_at: string;
  members_count: number;
}

// --- Model Gateway Module ---
export interface ProviderDTO {
  id: string;
  name: string;
  provider_type: "openai" | "anthropic" | "google" | "ollama" | "custom";
  status: "healthy" | "degraded" | "circuit_open" | "offline";
  is_enabled: boolean;
  base_url?: string;
  latency_ms: number;
}

export interface ModelDTO {
  id: string;
  provider_id: string;
  model_name: string;
  context_window: number;
  max_tokens: number;
  input_cost_per_1k: number;
  output_cost_per_1k: number;
  is_active: boolean;
}

export interface RoutingRuleDTO {
  id: string;
  name: string;
  priority: number;
  task_family: string;
  target_model_id: string;
  fallback_model_id?: string;
  is_active: boolean;
}

export interface ModelReceiptDTO {
  receipt_id: string;
  provider_id: string;
  model_id: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_cost: number;
  latency_ms: number;
  created_at: string;
}

// --- Automation Module ---
export interface ToolDefinitionDTO {
  id: string;
  name: string;
  description: string;
  runtime: "in_process" | "subprocess" | "browser" | "mcp" | "desktop" | "container" | "remote";
  risk_level: "safe" | "low" | "medium" | "high" | "critical";
  requires_approval: boolean;
  parameters_schema: Record<string, unknown>;
  enabled: boolean;
}

export interface ToolRunDTO {
  run_id: string;
  tool_id: string;
  tool_name: string;
  caller: string;
  status: "running" | "succeeded" | "failed" | "denied";
  duration_ms: number;
  result_preview?: string;
  error_message?: string;
  created_at: string;
}

// --- Agent Runtime Module ---
export interface AgentSessionDTO {
  id: string;
  title: string;
  agent_name: string;
  status: "active" | "paused" | "completed" | "failed";
  budget_remaining: number;
  total_steps: number;
  created_at: string;
  updated_at: string;
}

export interface WorkflowNode {
  id: string;
  label: string;
  step_type: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
}

export interface WorkflowEdge {
  from: string;
  to: string;
}

export interface WorkflowDTO {
  id: string;
  session_id: string;
  name: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  current_step_id?: string;
  created_at: string;
}

export interface ApprovalRequestDTO {
  id: string;
  session_id: string;
  action_name: string;
  risk_level: "medium" | "high" | "critical";
  description: string;
  parameters: Record<string, unknown>;
  status: "pending" | "approved" | "rejected";
  created_at: string;
}

// --- Memory Module ---
export interface MemoryRecordDTO {
  id: string;
  scope: "working" | "session" | "project" | "user" | "episodic" | "semantic" | "procedural" | "policy";
  key: string;
  content: string;
  confidence: number;
  status: "unvalidated" | "proposed" | "validated" | "promoted" | "rejected" | "superseded";
  provenance: string;
  created_at: string;
  expires_at?: string;
}

// --- Studio Module ---
export interface StudioProjectDTO {
  id: string;
  title: string;
  genre: string;
  synopsis: string;
  status: "draft" | "in_production" | "review" | "completed";
  episodes_count: number;
  characters_count: number;
  created_at: string;
}

export interface EpisodeDTO {
  id: string;
  project_id: string;
  episode_number: number;
  title: string;
  summary: string;
  status: "draft" | "scripted" | "storyboarded" | "rendered";
  duration_estimate_s: number;
}

export interface CharacterDTO {
  id: string;
  project_id: string;
  name: string;
  role: "protagonist" | "antagonist" | "supporting" | "cameo";
  visual_traits: string;
  voice_profile: string;
  avatar_url?: string;
}

export interface WorldEntryDTO {
  id: string;
  project_id: string;
  category: "location" | "faction" | "magic_tech" | "lore";
  name: string;
  description: string;
}

export interface StoryboardSceneDTO {
  id: string;
  episode_id: string;
  scene_number: number;
  heading: string;
  action_description: string;
  dialogue_lines: Array<{ character: string; line: string }>;
  visual_prompt: string;
  camera_direction: string;
}

// --- Production Module ---
export interface ProductionProjectDTO {
  id: string;
  title: string;
  format: "16:9" | "9:16" | "1:1" | "21:9";
  fps: number;
  resolution: string;
  status: "idle" | "rendering" | "assembled" | "error";
  total_shots: number;
  rendered_shots: number;
}

export interface MediaAssetDTO {
  id: string;
  project_id: string;
  name: string;
  asset_type: "video" | "image" | "audio" | "code_animation";
  file_path: string;
  size_bytes: number;
  colorspace: string;
  status: "unprocessed" | "normalized" | "ready" | "error";
  created_at: string;
}

export interface RenderJobDTO {
  id: string;
  project_id: string;
  shot_id: string;
  engine: "ffmpeg" | "code_video" | "gpu_renderer";
  progress_pct: number;
  status: "queued" | "running" | "succeeded" | "failed";
  output_uri?: string;
  created_at: string;
}

// --- Live Record Module ---
export interface LiveRecordPlanDTO {
  id: string;
  title: string;
  target_source: "screen" | "window" | "camera" | "audio_only";
  resolution: string;
  fps: number;
  codec: "nvenc_h264" | "wgc_native" | "cpu_h264";
  status: "draft" | "ready" | "recording" | "completed";
  duration_s: number;
  takes_count: number;
}

export interface RecordingTakeDTO {
  id: string;
  plan_id: string;
  take_number: number;
  status: "captured" | "processing" | "privacy_scanned" | "ready";
  duration_s: number;
  file_uri: string;
  privacy_safe: boolean;
  created_at: string;
}

export interface DirectorCueDTO {
  id: string;
  plan_id: string;
  timestamp_offset_s: number;
  cue_type: "marker" | "caption" | "sound_effect" | "cut";
  label: string;
  payload: Record<string, unknown>;
}

// --- Quality & Verification Module ---
export interface QualityDatasetDTO {
  id: string;
  name: string;
  dimension: string;
  test_cases_count: number;
  description: string;
  created_at: string;
}

export interface TestCaseDTO {
  id: string;
  dataset_id: string;
  name: string;
  input_prompt: string;
  rubric_type: "exact_match" | "regex" | "numeric_threshold" | "json_schema" | "safety_rule" | "code_correctness";
  expected_output: string;
}

export interface EvaluationRunDTO {
  id: string;
  dataset_id: string;
  dataset_name: string;
  target_model: string;
  total_cases: number;
  passed_cases: number;
  score: number;
  status: "running" | "completed" | "blocked";
  evidence_refs: string[];
  created_at: string;
}

export interface VerificationReportDTO {
  id: string;
  suite_name: string;
  gate_type: "TEST_RUNNER" | "LINTER" | "TYPE_CHECKER" | "POLICY_ENGINE" | "SECURITY_SCAN" | "SANDBOX_CHECK" | "INTEGRITY";
  passed: boolean;
  total_checks: number;
  passed_checks: number;
  summary: string;
  generated_at: string;
}

// --- Operations & Telemetry ---
export interface MetricEntryDTO {
  name: string;
  type: "counter" | "gauge" | "histogram";
  value: number;
  labels: Record<string, string>;
}

export interface OutboxEventDTO {
  id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: "pending" | "published" | "failed";
  occurred_at: string;
}
