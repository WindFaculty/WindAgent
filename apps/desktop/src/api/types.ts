/** TypeScript types mirroring backend Pydantic schemas.
 *
 * Source of truth:
 *  - docs/event_protocol.md (events)
 *  - docs/api_contract.md (REST + WS shapes)
 *  - apps/backend/schemas/event.py + session.py + workflow.py
 *
 * Keep these in sync with the backend.
 */

// ---------- Chat session ----------

export type SessionStatus =
  | "idle"
  | "planning"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "cancelled";

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

export type ToolName =
  | "open_app"
  | "open_url"
  | "type_text"
  | "hotkey"
  | "press_key"
  | "click_xy"
  | "scroll"
  | "screenshot"
  | "wait";

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
  created_at: string;
  status: WorkflowStatus;
  steps: WorkflowStep[];
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
  | "step_started"
  | "step_completed"
  | "step_failed"
  | "tool_call_started"
  | "tool_call_finished"
  | "permission_request"
  | "permission_granted"
  | "permission_denied"
  | "user_paused"
  | "user_resumed"
  | "user_stopped"
  | "error";

export interface EventEnvelope {
  event: EventName;
  timestamp: string;
  data: Record<string, unknown>;
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