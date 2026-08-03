/** REST + WebSocket client for the canonical WindAgent Architecture V2 API. */

import type {
  ChatSession,
  ConversationEventEnvelope,
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

export function resolveApiUrl(path: string): string {
  return path.startsWith("/") ? `${BASE_URL}${path}` : path;
}

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

function v2Unavailable(feature: string): never {
  throw new Error(`${feature} is not available in the Architecture V2 API`);
}

export async function fetchHealth(): Promise<{ status: string; phase: number }> {
  const data = await request<{ status: string; service?: string }>("/health/live");
  return { status: data.status, phase: 2 };
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
  return {
    enabled: false,
    reachable: false,
    version: "",
    api_server: false,
    runs_api: false,
    session_streaming: false,
    approval: false,
    stop: false,
    pause: false,
    profile: null,
    latency_ms: 0,
    api_key_scrubbed: true,
  };
}

export async function fetchModelsHealth(): Promise<ModelsHealthResponse> {
  return request<ModelsHealthResponse>("/api/v2/providers/health");
}

export async function createSession(agentId?: string, workspaceRoot?: string): Promise<CreateSessionResponse> {
  return request<CreateSessionResponse>("/api/v2/sessions", {
    method: "POST",
    body: JSON.stringify({
      agent_id: agentId || "coder",
      workspace_root: workspaceRoot || null,
      title: null,
    }),
  });
}

export async function fetchSession(sessionId: string): Promise<ChatSession> {
  return request<ChatSession>(`/api/v2/sessions/${sessionId}`);
}

export async function fetchSessions(
  limit = 50,
  offset = 0,
  excludeArchived = true,
  statusFilter?: string,
): Promise<any[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    exclude_archived: String(excludeArchived),
  });
  if (statusFilter) params.set("status", statusFilter);
  return request<any[]>(`/api/v2/sessions?${params}`);
}

export async function fetchSessionSnapshot(sessionId: string): Promise<{
  session: any;
  messages: any[];
  tool_calls: any[];
  workflow: any | null;
  last_event_sequence: number;
}> {
  return request(`/api/v2/sessions/${sessionId}/snapshot`);
}

export async function fetchSessionEvents(
  sessionId: string,
  afterSeq = 0,
): Promise<{ session_id: string; events: any[]; after_seq: number; count: number }> {
  return request(`/api/v2/sessions/${sessionId}/events?after_seq=${afterSeq}`);
}

export async function cancelSessionApi(sessionId: string): Promise<void> {
  await request<void>(`/api/v2/sessions/${sessionId}/cancel`, { method: "POST" });
}

export async function archiveSessionApi(sessionId: string): Promise<void> {
  await request<void>(`/api/v2/sessions/${sessionId}/archive`, { method: "POST" });
}

export async function deleteSessionApi(sessionId: string): Promise<void> {
  await request<void>(`/api/v2/sessions/${sessionId}`, { method: "DELETE" });
}

export async function fetchSessionMessages(sessionId: string): Promise<any[]> {
  return request<any[]>(`/api/v2/sessions/${sessionId}/messages`);
}


export async function sendMessage(
  sessionId: string,
  content: string,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(`/api/v2/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function fetchWorkflow(sessionId: string): Promise<Workflow> {
  const snapshot = await fetchSessionSnapshot(sessionId);
  if (!snapshot.workflow) {
    return v2Unavailable("Session workflow projection");
  }
  return snapshot.workflow as Workflow;
}

export async function fetchRunner(sessionId: string): Promise<{ runner: RunnerState | null }> {
  await fetchSession(sessionId);
  return { runner: null };
}

export async function controlSession(
  sessionId: string,
  action: "pause" | "resume" | "stop",
): Promise<void> {
  if (action === "stop") {
    await cancelSessionApi(sessionId);
    return;
  }
  return v2Unavailable(`Session ${action}`);
}

// ---------- Phase 8: multi-agent workspace ----------

export interface AgentBoardRow {
  agent_instance_id: string;
  parent_task_id: string | null;
  agent_type: string;
  status: string;
  permission_profile: Record<string, unknown>;
  canonical_model_id: string | null;
  assigned_node_id: string | null;
  agent_session_id: string | null;
  windagent_session_id: string | null;
  runtime_locator: string | null;
  hermes_run_id: string | null;
  session_status: string | null;
  agent_run_id: string | null;
  agent_run_status: string | null;
  fencing_token: string | null;
  task_node_run_id: string | null;
  node_state: string | null;
  node_version: number | null;
  concurrency_group: string | null;
  next_retry_at: string | null;
  worktree_id: string | null;
  worktree_path: string | null;
  worktree_branch: string | null;
  worktree_status: string | null;
  worktree_quarantine_path: string | null;
  planned_tool_name: string | null;
  current_tool_name: string | null;
  route_lock_id: string | null;
  provider_binding_id: string | null;
}

export interface TaskGraphNode {
  node_id: string;
  position: number;
  objective: string;
  agent_type: string | null;
  tool_name: string | null;
  concurrency_group: string | null;
  status: string | null;
  task_node_run_id: string | null;
  node_version: number | null;
  next_retry_at: string | null;
  assigned_agent_instance_id: string | null;
}

export interface TaskGraphEdge {
  edge_id: string;
  from_node_id: string;
  to_node_id: string;
}

export interface TaskGraph {
  plan_version_id: string;
  version: number;
  parent_task_id: string;
  objective: string;
  nodes: TaskGraphNode[];
  edges: TaskGraphEdge[];
}

export async function fetchConversationAgents(
  conversationId: string,
): Promise<AgentBoardRow[]> {
  return request<AgentBoardRow[]>(
    `/api/v2/conversations/${encodeURIComponent(conversationId)}/agents`,
  );
}

export async function fetchConversationTasks(
  conversationId: string,
): Promise<TaskGraph[]> {
  return request<TaskGraph[]>(
    `/api/v2/conversations/${encodeURIComponent(conversationId)}/task-graphs`,
  );
}

export async function stopConversationAgent(
  conversationId: string,
  agentInstanceId: string,
): Promise<void> {
  await request<{ status: string }>(
    `/api/v2/conversations/${encodeURIComponent(conversationId)}/agents/${encodeURIComponent(agentInstanceId)}/stop`,
    { method: "POST" },
  );
}

export async function fetchAgentEvents(
  agentInstanceId: string,
  afterSeq = 0,
): Promise<{ agent_instance_id: string; session_id: string | null; events: any[] }> {
  const events = await request<any[]>(
    `/api/v2/events?aggregate_id=${encodeURIComponent(agentInstanceId)}&min_sequence=${afterSeq}`,
  );
  return { agent_instance_id: agentInstanceId, session_id: null, events };
}

export async function retryStep(stepId: string): Promise<void> {
  return v2Unavailable(`Workflow step retry for ${stepId}`);
}

export async function fetchPermissionConfig(): Promise<PermissionConfigResponse> {
  return v2Unavailable("Mutable permission configuration");
}

export async function patchPermissionConfig(
  patch: Partial<PermissionConfigResponse>,
): Promise<PermissionConfigResponse> {
  void patch;
  return v2Unavailable("Mutable permission configuration");
}

export async function decidePermission(
  requestId: string,
  decision: "granted" | "denied",
): Promise<void> {
  void decision;
  return v2Unavailable(`Permission decision for ${requestId}`);
}

// ---------- Agent Registry API ----------

export async function fetchAgents(): Promise<any[]> {
  return v2Unavailable("Agent registry");
}

export async function fetchAgentSummary(): Promise<any> {
  return v2Unavailable("Agent summary");
}

export async function fetchAgent(agentId: string): Promise<any> {
  return v2Unavailable(`Agent ${agentId}`);
}

export async function createAgent(agentData: any): Promise<any> {
  void agentData;
  return v2Unavailable("Agent creation");
}

export async function updateAgent(agentId: string, agentData: any): Promise<any> {
  void agentData;
  return v2Unavailable(`Agent update for ${agentId}`);
}

export async function deleteAgent(agentId: string): Promise<void> {
  return v2Unavailable(`Agent deletion for ${agentId}`);
}

export async function startAgent(agentId: string): Promise<void> {
  return v2Unavailable(`Agent start for ${agentId}`);
}

export async function stopAgent(agentId: string): Promise<void> {
  return v2Unavailable(`Agent stop for ${agentId}`);
}

export async function restartAgent(agentId: string): Promise<void> {
  return v2Unavailable(`Agent restart for ${agentId}`);
}

export async function fetchAgentSessions(agentId: string): Promise<any[]> {
  return v2Unavailable(`Agent sessions for ${agentId}`);
}

export async function fetchAgentActivity(agentId: string): Promise<any[]> {
  return v2Unavailable(`Agent activity for ${agentId}`);
}

// ---------- Browser API ----------

export interface BrowserState {
  session_id: string;
  url: string;
  title: string;
  loading: boolean;
  screenshot_url: string | null;
  controlled_by: "agent" | "user";
  extracted_text: string;
  content_chars: number;
  error: string | null;
  authenticated: boolean;
  profile: string | null;
}

export async function fetchBrowserState(sessionId: string): Promise<BrowserState> {
  return request<BrowserState>(`/api/v2/browser/sessions/${encodeURIComponent(sessionId)}`);
}

export async function navigateBrowser(
  sessionId: string,
  url: string,
  options: { authenticated?: boolean; profile?: string } = {},
): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/navigate`,
    {
      method: "POST",
      body: JSON.stringify({ url, ...options }),
    },
  );
}

export async function clickBrowser(
  sessionId: string,
  x: number,
  y: number,
  selector?: string,
): Promise<BrowserState> {
  if (selector) {
    throw new Error("Coordinate clicks cannot include a selector.");
  }
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/click`,
    { method: "POST", body: JSON.stringify({ x, y }) },
  );
}

export async function typeBrowser(
  sessionId: string,
  text: string,
  selector?: string,
): Promise<BrowserState> {
  if (!selector) {
    throw new Error("A browser selector is required when typing text.");
  }
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/type`,
    { method: "POST", body: JSON.stringify({ selector, text }) },
  );
}

export async function scrollBrowser(
  sessionId: string,
  direction: "up" | "down" = "down",
  pixels = 800,
): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/scroll`,
    { method: "POST", body: JSON.stringify({ direction, pixels }) },
  );
}

export async function controlBrowser(
  sessionId: string,
  control: "agent" | "user",
): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/control`,
    { method: "POST", body: JSON.stringify({ controlled_by: control }) },
  );
}

export async function goBackBrowser(sessionId: string): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/back`,
    { method: "POST" },
  );
}

export async function goForwardBrowser(sessionId: string): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/forward`,
    { method: "POST" },
  );
}

export async function reloadBrowser(sessionId: string): Promise<BrowserState> {
  return request<BrowserState>(
    `/api/v2/browser/sessions/${encodeURIComponent(sessionId)}/reload`,
    { method: "POST" },
  );
}

// ---------- WebSocket Client ----------

export type WsListener = (env: EventEnvelope) => void;
export type WsCloseListener = (reason: string) => void;

export interface WsHandle {
  send: (text: string) => void;
  close: () => void;
}

export type ConversationWsListener = (env: ConversationEventEnvelope) => void;

export function connectWs(
  sessionId: string,
  listeners: { onEvent?: WsListener; onClose?: WsCloseListener } = {},
  afterSeq?: number
): WsHandle {
  const params = new URLSearchParams({ aggregate_id: sessionId });
  if (afterSeq !== undefined) params.set("last_sequence", String(afterSeq));
  const wsUrl = `${WS_URL}/api/v2/events/ws?${params}`;
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

/** Open the single durable event stream for a conversation. */
export function connectConversationWs(
  conversationId: string,
  listeners: { onEvent?: ConversationWsListener; onClose?: WsCloseListener } = {},
  afterSequence = 0,
): WsHandle {
  const params = new URLSearchParams({ after_sequence: String(afterSequence) });
  const wsUrl = `${WS_URL}/ws/conversations/${encodeURIComponent(conversationId)}?${params}`;
  logDebug(`Conversation WebSocket connecting to ${wsUrl}`);

  const ws = new WebSocket(wsUrl);
  ws.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as ConversationEventEnvelope | { type?: string };
      if ("type" in payload && payload.type === "ping") return;
      if ("event_id" in payload) listeners.onEvent?.(payload);
    } catch (error) {
      logDebug(`Failed to parse conversation WS message: ${event.data}, error: ${error}`);
    }
  };
  ws.onclose = (event) => listeners.onClose?.(event.reason || "Connection closed");
  ws.onerror = (error) => logDebug(`Conversation WebSocket error: ${error}`);

  return {
    send: (text: string) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(text);
    },
    close: () => ws.close(),
  };
}

function logDebug(msg: string) {
  console.log(`[WebSocket] ${msg}`);
}

// ---------- Giai đoạn 9 - Task editing and Control API ----------

export async function updateTaskNode(
  conversationId: string,
  nodeId: string,
  data: {
    title?: string;
    description?: string | null;
    agent_type?: string;
    status?: string;
    assigned_agent_instance_id?: string | null;
    version: number;
  }
): Promise<TaskGraph> {
  void data;
  return v2Unavailable(`Task node update ${conversationId}/${nodeId}`);
}

export async function createTaskNode(
  conversationId: string,
  data: {
    title: string;
    description?: string | null;
    agent_type: string;
    status?: string;
    assigned_agent_instance_id?: string | null;
    version: number;
  }
): Promise<TaskGraph> {
  void data;
  return v2Unavailable(`Task node creation for ${conversationId}`);
}

export async function deleteTaskNode(
  conversationId: string,
  nodeId: string,
  version: number
): Promise<TaskGraph> {
  void version;
  return v2Unavailable(`Task node deletion ${conversationId}/${nodeId}`);
}

export async function createTaskEdge(
  conversationId: string,
  data: {
    from_task_id: string;
    to_task_id: string;
    edge_type?: string;
    version: number;
  }
): Promise<TaskGraph> {
  void data;
  return v2Unavailable(`Task edge creation for ${conversationId}`);
}

export async function deleteTaskEdge(
  conversationId: string,
  fromTaskId: string,
  toTaskId: string,
  version: number
): Promise<TaskGraph> {
  void version;
  return v2Unavailable(`Task edge deletion ${conversationId}/${fromTaskId}/${toTaskId}`);
}

export async function pauseTask(nodeId: string): Promise<any> {
  return v2Unavailable(`Task pause for ${nodeId}`);
}

export async function resumeTask(nodeId: string): Promise<any> {
  return v2Unavailable(`Task resume for ${nodeId}`);
}

export async function cancelTask(nodeId: string): Promise<any> {
  return request<any>(`/api/v2/tasks/${nodeId}/cancel`, { method: "POST" });
}

export async function retryTask(nodeId: string): Promise<any> {
  return v2Unavailable(`Task retry for ${nodeId}`);
}
