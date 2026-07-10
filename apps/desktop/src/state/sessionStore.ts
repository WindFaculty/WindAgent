/** Lightweight in-memory store for the active session + events.
 *
 * MVP scope: single-session, no persistence, no zustand yet. Easy to
 * swap for a proper store later if needed.
 */

import type {
  EventEnvelope,
  PermissionRequestPayload,
  RunnerState,
  Workflow,
} from "../api/types";

export interface ChatMessage {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  createdAt: number;
}

export interface ToolCallLog {
  toolName: string;
  status: "success" | "failed";
  durationMs: number;
  at: number;
  /** Short human-readable error message if status="failed". */
  errorMessage?: string;
  /** Resolved point from click_target stub (x, y, confidence, method). */
  resolvedPoint?: {
    x: number;
    y: number;
    confidence: number;
    method: string;
  };
}

export type RunnerSnapshot =
  | { kind: "idle" }
  | { kind: "running"; state: RunnerState };

export interface SessionState {
  sessionId: string | null;
  workflow: Workflow | null;
  runner: RunnerSnapshot;
  messages: ChatMessage[];
  toolCalls: ToolCallLog[];
  permissionQueue: PermissionRequestPayload[];
  modelsOnline: boolean | null;
}

export const initialState: SessionState = {
  sessionId: null,
  workflow: null,
  runner: { kind: "idle" },
  messages: [],
  toolCalls: [],
  permissionQueue: [],
  modelsOnline: null,
};

export function reducer(
  state: SessionState,
  action:
    | { type: "setSessionId"; sessionId: string }
    | { type: "setWorkflow"; workflow: Workflow }
    | { type: "setRunner"; snapshot: RunnerSnapshot }
    | { type: "addMessage"; message: ChatMessage }
    | { type: "addToolCall"; call: ToolCallLog }
    | { type: "enqueuePermission"; payload: PermissionRequestPayload }
    | {
        type: "resolvePermission";
        requestId: string;
      }
    | { type: "setModelsOnline"; online: boolean }
    | { type: "processEvent"; env: EventEnvelope }
    | { type: "reset" },
): SessionState {
  // Translate WS event envelopes into store mutations. Keep the
  // logic inline so React's strict mode + concurrent dispatches can't
  // double-handle an event with stale state.
  if (action.type === "processEvent") {
    return applyEvent(state, action.env);
  }
  switch (action.type) {
    case "setSessionId":
      return { ...state, sessionId: action.sessionId };
    case "setWorkflow":
      return { ...state, workflow: action.workflow };
    case "setRunner":
      return { ...state, runner: action.snapshot };
    case "addMessage":
      return { ...state, messages: [...state.messages, action.message] };
    case "addToolCall":
      return { ...state, toolCalls: [...state.toolCalls, action.call] };
    case "enqueuePermission":
      return {
        ...state,
        permissionQueue: [...state.permissionQueue, action.payload],
      };
    case "resolvePermission":
      return {
        ...state,
        permissionQueue: state.permissionQueue.filter(
          (p) => p.request_id !== action.requestId,
        ),
      };
    case "setModelsOnline":
      return { ...state, modelsOnline: action.online };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

// ---------- Event-to-action adapter ----------
//
// Translate raw WS events into new state. Pure function of
// (state, event) -> state, dispatched via the "processEvent" action
// above. Keeps App.tsx free of conditional dispatch logic.

function applyEvent(state: SessionState, env: EventEnvelope): SessionState {
  switch (env.event) {
    case "message_received": {
      const data = env.data as { content: string; message_id: string };
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: data.message_id,
            sender: "user",
            content: data.content,
            createdAt: Date.parse(env.timestamp),
          },
        ],
      };
    }
    case "assistant_message_delta": {
      const data = env.data as { message_id?: string; delta: string };
      const messages = [...state.messages];
      const lastMsg = messages[messages.length - 1];
      if (lastMsg && lastMsg.sender === "assistant") {
        lastMsg.content += data.delta;
        return { ...state, messages };
      } else {
        return {
          ...state,
          messages: [
            ...messages,
            {
              id: data.message_id || "assistant_msg_" + Math.random().toString(36).substr(2, 9),
              sender: "assistant",
              content: data.delta,
              createdAt: Date.parse(env.timestamp),
            },
          ],
        };
      }
    }
    case "reasoning_delta": {
      // Just print reasoning to console or ignore for simple preview
      return state;
    }
    case "permission_request":
      return {
        ...state,
        permissionQueue: [
          ...state.permissionQueue,
          env.data as unknown as PermissionRequestPayload,
        ],
      };
    case "permission_granted":
    case "permission_denied": {
      const data = env.data as { request_id?: string };
      if (!data.request_id) return state;
      return {
        ...state,
        permissionQueue: state.permissionQueue.filter(
          (p) => p.request_id !== data.request_id,
        ),
      };
    }
    case "tool_call_started": {
      const data = env.data as { tool_name: string };
      return {
        ...state,
        toolCalls: [
          ...state.toolCalls,
          {
            toolName: data.tool_name,
            status: "pending" as any,
            durationMs: 0,
            at: Date.parse(env.timestamp),
          },
        ],
      };
    }
    case "tool_call_finished": {
      const data = env.data as {
        tool_name: string;
        status: "success" | "failed";
        duration_ms: number;
        error?: { message?: string };
        output?: { resolved_point?: { x: number; y: number; confidence: number; method: string } };
      };
      
      const existingCall = state.toolCalls.find(c => c.toolName === data.tool_name && c.status === ("pending" as any));
      if (existingCall) {
        return {
          ...state,
          toolCalls: state.toolCalls.map(c => {
            if (c === existingCall) {
              return {
                ...c,
                status: data.status,
                durationMs: data.duration_ms,
                errorMessage: data.error?.message,
                resolvedPoint: data.output?.resolved_point,
              };
            }
            return c;
          }),
        };
      } else {
        return {
          ...state,
          toolCalls: [
            ...state.toolCalls,
            {
              toolName: data.tool_name,
              status: data.status,
              durationMs: data.duration_ms,
              at: Date.parse(env.timestamp),
              errorMessage: data.error?.message,
              resolvedPoint: data.output?.resolved_point,
            },
          ],
        };
      }
    }
    default:
      return state;
  }
}