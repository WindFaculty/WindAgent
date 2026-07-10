/** REST + WebSocket client for the WindAgent FastAPI Sidecar Backend. */

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

const BASE_URL = "http://127.0.0.1:8765";
const WS_URL = "ws://127.0.0.1:8765";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    let detail = "API Request failed";
    try {
      const errorJson = JSON.parse(errorText);
      detail = errorJson.detail || detail;
    } catch {
      detail = errorText || detail;
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export async function fetchHealth(): Promise<{ status: string; phase: number }> {
  const data = await request<{ status: string; service?: string }>(`/api/v1/health`);
  return { status: data.status, phase: 6 };
}

export interface HermesHealthResponse {
  enabled: boolean;
  reachable: boolean;
  version: string;
  api_server: boolean;
  runs_api: boolean;
  session_streaming: boolean;
  approval: boolean;
  stop: boolean;
  pause: boolean;
  profile: string | null;
  latency_ms: number;
  api_key_scrubbed: boolean;
}

export async function fetchHermesHealth(): Promise<HermesHealthResponse> {
  return request<HermesHealthResponse>(`/api/v1/runtimes/hermes/health`);
}

export async function fetchModelsHealth(): Promise<ModelsHealthResponse> {
  return request<ModelsHealthResponse>(`/api/v1/models/health`);
}

export async function createSession(agentId?: string, workspaceRoot?: string): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>(`/api/v1/sessions`, {
    method: "POST",
    body: JSON.stringify({
      agent_id: agentId || "coder",
      workspace_root: workspaceRoot || null,
      title: null,
    }),
  });
}

export async function fetchSession(sessionId: string): Promise<ChatSession> {
  return request<ChatSession>(`/api/v1/sessions/${sessionId}`);
}

export async function sendMessage(
  sessionId: string,
  content: string,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(`/api/v1/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function fetchWorkflow(sessionId: string): Promise<Workflow> {
  return request<Workflow>(`/api/v1/sessions/${sessionId}/workflow`);
}

export async function fetchRunner(sessionId: string): Promise<{ runner: RunnerState | null }> {
  return request<{ runner: RunnerState | null }>(`/api/v1/sessions/${sessionId}/runner`);
}

export async function controlSession(
  sessionId: string,
  action: "pause" | "resume" | "stop",
): Promise<void> {
  await request<void>(`/api/v1/sessions/${sessionId}/${action}`, {
    method: "POST",
  });
}

export async function retryStep(stepId: string): Promise<void> {
  await request<void>(`/api/v1/workflow/${stepId}/retry`, {
    method: "POST",
  });
}

export async function fetchPermissionConfig(): Promise<PermissionConfigResponse> {
  return request<PermissionConfigResponse>(`/api/v1/permissions/config`);
}

export async function patchPermissionConfig(
  patch: Partial<PermissionConfigResponse>,
): Promise<PermissionConfigResponse> {
  return request<PermissionConfigResponse>(`/api/v1/permissions/config`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function decidePermission(
  requestId: string,
  decision: "granted" | "denied",
): Promise<void> {
  await request<void>(`/api/v1/permissions/${requestId}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}

// ---------- Agent Registry API ----------

export async function fetchAgents(): Promise<any[]> {
  return request<any[]>(`/api/v1/agents`);
}

export async function fetchAgentSummary(): Promise<any> {
  return request<any>(`/api/v1/agents/summary`);
}

export async function fetchAgent(agentId: string): Promise<any> {
  return request<any>(`/api/v1/agents/${agentId}`);
}

export async function createAgent(agentData: any): Promise<any> {
  return request<any>(`/api/v1/agents`, {
    method: "POST",
    body: JSON.stringify(agentData),
  });
}

export async function updateAgent(agentId: string, agentData: any): Promise<any> {
  return request<any>(`/api/v1/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(agentData),
  });
}

export async function deleteAgent(agentId: string): Promise<void> {
  await request<void>(`/api/v1/agents/${agentId}`, {
    method: "DELETE",
  });
}

export async function startAgent(agentId: string): Promise<void> {
  await request<void>(`/api/v1/agents/${agentId}/start`, {
    method: "POST",
  });
}

export async function stopAgent(agentId: string): Promise<void> {
  await request<void>(`/api/v1/agents/${agentId}/stop`, {
    method: "POST",
  });
}

export async function restartAgent(agentId: string): Promise<void> {
  await request<void>(`/api/v1/agents/${agentId}/restart`, {
    method: "POST",
  });
}

export async function fetchAgentSessions(agentId: string): Promise<any[]> {
  return request<any[]>(`/api/v1/agents/${agentId}/sessions`);
}

export async function fetchAgentActivity(agentId: string): Promise<any[]> {
  return request<any[]>(`/api/v1/agents/${agentId}/activity`);
}

// ---------- WebSocket Client ----------

export type WsListener = (env: EventEnvelope) => void;
export type WsCloseListener = (reason: string) => void;

export interface WsHandle {
  send: (text: string) => void;
  close: () => void;
}

export function connectWs(
  sessionId: string,
  listeners: { onEvent?: WsListener; onClose?: WsCloseListener } = {},
): WsHandle {
  const wsUrl = `${WS_URL}/ws/${sessionId}`;
  logDebug(`WebSocket connecting to ${wsUrl}`);
  
  const ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    if (event.data === "ping" || event.data === "pong") {
      return; // filter keepalive frames
    }
    try {
      const envelope: EventEnvelope = JSON.parse(event.data);
      listeners.onEvent?.(envelope);
    } catch (e) {
      logDebug(`Failed to parse WS message: ${event.data}, error: ${e}`);
    }
  };

  ws.onclose = (event) => {
    listeners.onClose?.(event.reason || "Connection closed");
  };

  ws.onerror = (error) => {
    logDebug(`WebSocket error: ${error}`);
  };

  return {
    send: (text: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(text);
      }
    },
    close: () => {
      ws.close();
    },
  };
}

function logDebug(msg: string) {
  console.log(`[WebSocket] ${msg}`);
}