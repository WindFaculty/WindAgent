/** TypeScript types mirroring backend Pydantic schemas.
 *
 * Source of truth (Architecture V2):
 *  - docs/event_protocol.md (events)
 *  - docs/api_contract.md (REST + WS shapes)
 *  - apps/api/windagent_api/schemas/ (canonical V2 request/response schemas)
 *
 * Keep these in sync with windagent_api schemas.
 */

// ---------- Chat session ----------

export type SessionStatus =
  | "idle"
  | "planning"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled"
  | "reconnecting";

export type Sender = "user" | "assistant" | "system";

export interface ChatSession {
  id: string;
  created_at: string;
  updated_at: string;
  status: SessionStatus;
}

// ---------- Workflow ----------

export type WorkflowStatus =
  | "pending"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

export type StepStatus =
  | "pending"
  | "running"
  | "success"
  | "failed"
  | "skipped"
  | "cancelled";

// Tool names come from both the native GUI runner (open_app, type_text, ...)
// and the Hermes runtime (terminal, read_file, todo, ...). Keep open + alias
// the native set rather than enumerating every possible Hermes tool.
export type ToolName =
  | "open_app"
  | "open_url"
  | "type_text"
  | "hotkey"
  | "press_key"
  | "click_xy"
  | "scroll"
  | "screenshot"
  | "wait"
  | string;

export interface WorkflowStep {
  id: string;
  order: number;
  name: string;
  tool_name: ToolName;
  params: Record<string, unknown>;
  status: StepStatus;
}

export interface Workflow {
  workflow_id: string;
  session_id: string;
  objective: string;
  created_at: string;
  status: WorkflowStatus;
  steps: WorkflowStep[];
}

// Recent Actions timeline (docs ban_ke_hoach.md §10). Derived from normalized
// events so the UI never hardcodes a fake activity feed.
export type RecentActionKind =
  | "tool_call"
  | "step"
  | "message"
  | "permission"
  | "workflow"
  | "error";

export interface RecentAction {
  id: string;
  kind: RecentActionKind;
  label: string;
  detail?: string;
  timestamp: string;
}

// ---------- Runner ----------

export interface RunnerState {
  session_id: string;
  workflow_id: string;
  paused: boolean;
  stop_requested: boolean;
  current_step_index: number;
  last_failed_step_id: string | null;
  task_done: boolean;
  final_status: WorkflowStatus | null;
}

// ---------- Events (WebSocket) ----------

export type EventName =
  | "session_created"
  | "session_finished"
  | "message_received"
  | "planning_started"
  | "planning_finished"
  | "workflow_created"
  | "workflow_updated"
  | "step_started"
  | "step_completed"
  | "step_failed"
  | "step_cancelled"
  | "tool_call_started"
  | "tool_call_finished"
  | "permission_request"
  | "permission_granted"
  | "permission_denied"
  | "user_paused"
  | "user_resumed"
  | "user_stopped"
  | "error"
  | "assistant_message_started"
  | "assistant_message_delta"
  | "assistant_message_completed"
  | "reasoning_delta"
  | "tool_call_progress"
  | "terminal_output"
  | "artifact_created"
  | "clarification_request"
    | "replan_notification"
    | "browser_session_started"
    | "browser_navigation_started"
    | "browser_navigation_completed"
    | "browser_screenshot_updated"
    | "browser_action_started"
    | "browser_action_completed"
    | "browser_console"
    | "browser_error";

export interface EventEnvelope {
  event: EventName;
  timestamp: string;
  seq?: number;
  data: Record<string, unknown>;
}

/** Durable, replayable event emitted by the conversation stream. */
export interface ConversationEventEnvelope {
  event_id: string;
  idempotency_key: string;
  conversation_id: string;
  agent_instance_id: string | null;
  agent_session_id: string | null;
  sequence: number;
  event_type: EventName | string;
  data: Record<string, unknown>;
  occurred_at: string;
  is_replay: boolean;
}

// ---------- Permission ----------

export interface PermissionRequestPayload {
  session_id: string;
  step_id: string;
  request_id: string;
  tool_name: ToolName;
  risk_level: "safe" | "medium" | "high";
  summary: string;
  params: Record<string, unknown>;
}

export interface PermissionDecisionPayload {
  session_id: string;
  step_id: string;
  tool_name: ToolName;
  reason: string | null;
}

// ---------- REST helpers ----------

export interface CreateSessionResponse {
  session_id: string;
  created_at: string;
  status: SessionStatus;
}

export interface SendMessageResponse {
  message_id: string;
  workflow_id: string;
  step_count: number;
}

export interface PermissionConfigResponse {
  safe_mode: boolean;
  confirm_before_type: boolean;
  confirm_before_click: boolean;
  type_text_length_threshold: number;
  request_timeout_s: number;
}

export interface ModelsHealthResponse {
  provider: string;
  online: boolean;
  model: string;
  latency_ms: number | null;
  error: string | null;
}

export interface ApiError {
  detail: string;
}
