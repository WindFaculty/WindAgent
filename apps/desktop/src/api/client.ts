/** Thin REST + WebSocket client for the WindAgent backend.
 *
 * Base URL: in dev, Vite proxies /api and /ws to http://127.0.0.1:8765
 * (see vite.config.ts). In Tauri production the backend runs as a
 * sidecar (Phase 9) and the host is the same.
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

const API_PREFIX = "/api";
const WS_PREFIX = "/ws";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_PREFIX}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // ignore — fall back to status code
    }
    throw new Error(`API ${res.status}: ${detail}`);
  }
  // Some endpoints (POST /sessions/{id}/stop) return 204 with no body.
  // Treat an empty body as the void-ish cast below.
  const text = await res.text();
  if (!text) {
    return undefined as unknown as T;
  }
  return JSON.parse(text) as T;
}

export async function fetchHealth(): Promise<{ status: string; phase: number }> {
  return jsonFetch("/health");
}

export async function fetchModelsHealth(): Promise<ModelsHealthResponse> {
  return jsonFetch("/models/health");
}

export async function createSession(): Promise<CreateSessionResponse> {
  return jsonFetch("/sessions", { method: "POST" });
}

export async function fetchSession(sessionId: string): Promise<ChatSession> {
  return jsonFetch(`/sessions/${sessionId}`);
}

export async function sendMessage(
  sessionId: string,
  content: string,
): Promise<SendMessageResponse> {
  return jsonFetch(`/sessions/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function fetchWorkflow(sessionId: string): Promise<Workflow> {
  return jsonFetch(`/sessions/${sessionId}/workflow`);
}

export async function fetchRunner(sessionId: string): Promise<{ runner: RunnerState | null }> {
  return jsonFetch(`/sessions/${sessionId}/runner`);
}

export async function controlSession(
  sessionId: string,
  action: "pause" | "resume" | "stop",
): Promise<void> {
  await jsonFetch(`/sessions/${sessionId}/${action}`, { method: "POST" });
}

export async function retryStep(stepId: string): Promise<void> {
  await jsonFetch(`/workflow/${stepId}/retry`, { method: "POST" });
}

// ---------- Permission ----------

export async function fetchPermissionConfig(): Promise<PermissionConfigResponse> {
  return jsonFetch("/permissions/config");
}

export async function patchPermissionConfig(
  patch: Partial<PermissionConfigResponse>,
): Promise<PermissionConfigResponse> {
  return jsonFetch("/permissions/config", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function decidePermission(
  requestId: string,
  decision: "granted" | "denied",
): Promise<void> {
  await jsonFetch(`/permissions/${requestId}/decide`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}

// ---------- WebSocket ----------

export type WsListener = (env: EventEnvelope) => void;
export type WsCloseListener = (reason: string) => void;

export interface WsHandle {
  send: (text: string) => void;
  close: () => void;
}

/** Connect to /ws/{session_id}. Reconnects with backoff on close.
 *
 * Returns a handle with `send` and `close`. Use `subscribe`/`onClose`
 * to receive events.
 */
export function connectWs(
  sessionId: string,
  listeners: { onEvent?: WsListener; onClose?: WsCloseListener } = {},
): WsHandle {
  const url = `${WS_PREFIX}/${sessionId}`.replace(/^http/, "ws");
  let ws: WebSocket | null = null;
  let closedByUser = false;
  let retry = 0;
  let reconnectTimer: number | null = null;

  const open = () => {
    ws = new WebSocket(url);

    ws.onmessage = (msg) => {
      const data = typeof msg.data === "string" ? msg.data : "";
      if (data === "ping") {
        return;
      }
      try {
        const env = JSON.parse(data) as EventEnvelope;
        listeners.onEvent?.(env);
      } catch {
        // Ignore malformed frames (keepalive, etc).
      }
    };

    ws.onclose = (ev) => {
      listeners.onClose?.(ev.reason || "closed");
      if (!closedByUser) {
        const delay = Math.min(1000 * 2 ** retry, 15000);
        retry += 1;
        reconnectTimer = window.setTimeout(open, delay);
      }
    };

    ws.onerror = () => {
      // onclose will follow.
    };
  };

  open();

  return {
    send: (text: string) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(text);
      }
    },
    close: () => {
      closedByUser = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      ws?.close();
    },
  };
}