/** Mock REST + WebSocket client for the WindAgent backend.
 * Enables the frontend to run fully client-side without a running backend.
 */

import type {
  ChatSession,
  CreateSessionResponse,
  EventEnvelope,
  ModelsHealthResponse,
  PermissionConfigResponse,
  RunnerState,
  SendMessageResponse,
  Workflow,
} from "./types";

export async function fetchHealth(): Promise<{ status: string; phase: number }> {
  return { status: "ok", phase: 6 };
}

export async function fetchModelsHealth(): Promise<ModelsHealthResponse> {
  return {
    provider: "openai",
    online: true,
    model: "gpt-4o",
    latency_ms: 120,
    error: null,
  };
}

export async function createSession(): Promise<CreateSessionResponse> {
  return {
    session_id: "mock_session_" + Math.random().toString(36).substr(2, 9),
    created_at: new Date().toISOString(),
    status: "idle",
  };
}

export async function fetchSession(sessionId: string): Promise<ChatSession> {
  return {
    id: sessionId,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    status: "running",
  };
}

export async function sendMessage(
  _sessionId: string,
  _content: string,
): Promise<SendMessageResponse> {
  return {
    message_id: "mock_msg_" + Math.random().toString(36).substr(2, 9),
    workflow_id: "mock_wf_" + Math.random().toString(36).substr(2, 9),
    step_count: 5,
  };
}

export async function fetchWorkflow(_sessionId: string): Promise<Workflow> {
  return {
    workflow_id: "mock_wf_123",
    session_id: "mock_session_123",
    created_at: new Date().toISOString(),
    status: "running",
    steps: [],
  };
}

export async function fetchRunner(_sessionId: string): Promise<{ runner: RunnerState | null }> {
  return { runner: null };
}

export async function controlSession(
  _sessionId: string,
  action: "pause" | "resume" | "stop",
): Promise<void> {
  console.log(`Session control action: ${action}`);
}

export async function retryStep(stepId: string): Promise<void> {
  console.log(`Retrying step: ${stepId}`);
}

export async function fetchPermissionConfig(): Promise<PermissionConfigResponse> {
  return {
    safe_mode: true,
    confirm_before_type: true,
    confirm_before_click: true,
    type_text_length_threshold: 100,
    request_timeout_s: 30,
  };
}

export async function patchPermissionConfig(
  patch: Partial<PermissionConfigResponse>,
): Promise<PermissionConfigResponse> {
  return {
    safe_mode: true,
    confirm_before_type: true,
    confirm_before_click: true,
    type_text_length_threshold: 100,
    request_timeout_s: 30,
    ...patch,
  };
}

export async function decidePermission(
  requestId: string,
  decision: "granted" | "denied",
): Promise<void> {
  console.log(`Permission decision for ${requestId}: ${decision}`);
}

export type WsListener = (env: EventEnvelope) => void;
export type WsCloseListener = (reason: string) => void;

export interface WsHandle {
  send: (text: string) => void;
  close: () => void;
}

export function connectWs(
  _sessionId: string,
  _listeners: { onEvent?: WsListener; onClose?: WsCloseListener } = {},
): WsHandle {
  console.log(`Mock WebSocket connected for session: ${_sessionId}`);
  return {
    send: (text: string) => {
      console.log(`WS Sent: ${text}`);
    },
    close: () => {
      console.log("WS Closed");
    },
  };
}