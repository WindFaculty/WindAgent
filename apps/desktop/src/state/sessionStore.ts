/** Lightweight in-memory store for the active session + events.
 *
 * MVP scope: single-session, no persistence, no zustand yet. Easy to
 * swap for a proper store later if needed.
 */

import type {
  EventEnvelope,
  PermissionRequestPayload,
  RecentAction,
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
  recentActions: RecentAction[];
  modelsOnline: boolean | null;
  terminalLines: string[];
  browser: {
    url: string;
    title: string;
    loading: boolean;
    screenshotUrl: string | null;
    controlledBy: "agent" | "user";
  };
}

export const initialState: SessionState = {
  sessionId: null,
  workflow: null,
  runner: { kind: "idle" },
  messages: [],
  toolCalls: [],
  permissionQueue: [],
  recentActions: [],
  modelsOnline: null,
  terminalLines: [],
  browser: {
    url: "about:blank",
    title: "New Tab",
    loading: false,
    screenshotUrl: null,
    controlledBy: "agent",
  },
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
    | { type: "updateBrowserState"; browser: Partial<SessionState["browser"]> }
    | { type: "clearTerminal" }
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
    case "updateBrowserState":
      return {
        ...state,
        browser: { ...state.browser, ...action.browser },
      };
    case "clearTerminal":
      return { ...state, terminalLines: [] };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

// Append a normalized action to the Recent Actions timeline. Keeps the
// newest first, cap at 50 (docs ban_ke_hoach.md §10 says 20-50).
function pushAction(
  state: SessionState,
  action: RecentAction,
): RecentAction[] {
  const next = [action, ...state.recentActions];
  return next.slice(0, 50);
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
      const tempMsg = state.messages.find(
        (m) => m.sender === "user" && m.content === data.content && m.id.startsWith("user_")
      );
      
      let newMessages = [...state.messages];
      if (tempMsg) {
        newMessages = state.messages.map((m) =>
          m === tempMsg ? { ...m, id: data.message_id } : m
        );
      } else {
        newMessages.push({
          id: data.message_id,
          sender: "user",
          content: data.content,
          createdAt: Date.parse(env.timestamp),
        });
      }

      return {
        ...state,
        messages: newMessages,
        recentActions: pushAction(state, {
          id: `msg-${data.message_id}`,
          kind: "message",
          label: "You sent a message",
          detail: data.content,
          timestamp: env.timestamp,
        }),
      };
    }
    case "workflow_created":
    case "workflow_updated": {
      // Backend sends Hermes todo list as a full Workflow payload
      // (objective + ordered steps). Replace, don't merge, so a
      // re-emitted full list can't duplicate steps.
      const wf = env.data as unknown as Partial<Workflow>;
      if (!wf || !wf.workflow_id) return state;
      const steps = (wf.steps ?? []).map((s) => ({
        ...s,
        status: (s.status ?? "pending") as Workflow["steps"][number]["status"],
      }));
      return {
        ...state,
        workflow: {
          workflow_id: wf.workflow_id,
          session_id: wf.session_id ?? state.sessionId ?? "",
          objective: wf.objective ?? "",
          created_at: wf.created_at ?? env.timestamp,
          status: (wf.status ?? "running") as Workflow["status"],
          steps,
        },
        recentActions: pushAction(state, {
          id: `wf-${wf.workflow_id}-${env.event}-${env.timestamp}`,
          kind: "workflow",
          label:
            env.event === "workflow_created"
              ? "Task plan created"
              : "Task plan updated",
          detail: wf.objective || `${steps.length} tasks`,
          timestamp: env.timestamp,
        }),
      };
    }
    case "assistant_message_delta": {
      const data = env.data as { message_id?: string; delta: string };
      const messages = [...state.messages];
      const lastMsg = messages[messages.length - 1];
      if (lastMsg && lastMsg.sender === "assistant") {
        const updatedMessages = messages.map((m, idx) =>
          idx === messages.length - 1
            ? { ...m, content: m.content + data.delta }
            : m
        );
        return { ...state, messages: updatedMessages };
      } else {
        return {
          ...state,
          messages: [
            ...messages,
            {
              id: data.message_id || "assistant_msg_" + Math.random().toString(36).substring(2, 11),
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
    case "permission_request": {
      const payload = env.data as unknown as PermissionRequestPayload;
      return {
        ...state,
        permissionQueue: [...state.permissionQueue, payload],
        recentActions: pushAction(state, {
          id: `perm-${payload.request_id}`,
          kind: "permission",
          label: "Permission requested",
          detail: payload.summary,
          timestamp: env.timestamp,
        }),
      };
    }
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
    case "step_started":
    case "step_completed":
    case "step_failed":
    case "step_cancelled": {
      const data = env.data as {
        step_id: string;
        step_name?: string;
        status?: string;
      };
      if (!data.step_id || !state.workflow) return state;
      const statusMap: Record<string, Workflow["steps"][number]["status"]> = {
        step_started: "running",
        step_completed: "success",
        step_failed: "failed",
        step_cancelled: "cancelled",
      };
      const newStatus = statusMap[env.event];
      const steps = state.workflow.steps.map((s) =>
        s.id === data.step_id ? { ...s, status: newStatus } : s,
      );
      const labelMap: Record<string, string> = {
        step_started: "Started task",
        step_completed: "Completed task",
        step_failed: "Failed task",
        step_cancelled: "Cancelled task",
      };
      const step = steps.find((s) => s.id === data.step_id);
      return {
        ...state,
        workflow: { ...state.workflow, steps },
        recentActions: pushAction(state, {
          id: `step-${data.step_id}-${env.event}-${env.timestamp}`,
          kind: "step",
          label: labelMap[env.event],
          detail: step?.name ?? data.step_name ?? data.step_id,
          timestamp: env.timestamp,
        }),
      };
    }
    case "tool_call_started": {
      const data = env.data as { tool_name: string; input?: { arguments?: string } };
      const cmdStr = data.input?.arguments ? ` ${data.input.arguments}` : "";
      const termLine = `> ${data.tool_name}${cmdStr}`;
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
        terminalLines: [...state.terminalLines, termLine],
      };
    }
    case "tool_call_progress": {
      const data = env.data as { progress: string };
      if (!data.progress) return state;
      const progressLines = data.progress.split("\n").filter(line => line.trim() !== "");
      return {
        ...state,
        terminalLines: [...state.terminalLines, ...progressLines],
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
      const toolCalls = existingCall
        ? state.toolCalls.map(c => {
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
          })
        : [
            ...state.toolCalls,
            {
              toolName: data.tool_name,
              status: data.status,
              durationMs: data.duration_ms,
              at: Date.parse(env.timestamp),
              errorMessage: data.error?.message,
              resolvedPoint: data.output?.resolved_point,
            },
          ];

      const statusLine = `[Finished] Status: ${data.status} | Duration: ${data.duration_ms}ms`;
      const extraLines = [];
      if (data.status === "failed" && data.error?.message) {
        extraLines.push(`[Error] ${data.error.message}`);
      }

      return {
        ...state,
        toolCalls,
        terminalLines: [...state.terminalLines, statusLine, ...extraLines],
        recentActions: pushAction(state, {
          id: `tool-${data.tool_name}-${env.timestamp}`,
          kind: "tool_call",
          label: data.status === "failed" ? `Tool failed: ${data.tool_name}` : `Ran ${data.tool_name}`,
          detail: data.error?.message,
          timestamp: env.timestamp,
        }),
      };
    }
    case "browser_session_started": {
      const data = env.data as { url?: string; title?: string; controlled_by?: "agent" | "user" };
      return {
        ...state,
        browser: {
          ...state.browser,
          url: data.url || state.browser.url,
          title: data.title || state.browser.title,
          controlledBy: data.controlled_by || state.browser.controlledBy,
        },
      };
    }
    case "browser_navigation_started": {
      const data = env.data as { url?: string };
      return {
        ...state,
        browser: {
          ...state.browser,
          loading: true,
          url: data.url || state.browser.url,
        },
      };
    }
    case "browser_navigation_completed": {
      const data = env.data as { url?: string; title?: string; controlled_by?: "agent" | "user" };
      return {
        ...state,
        browser: {
          ...state.browser,
          loading: false,
          url: data.url || state.browser.url,
          title: data.title || state.browser.title,
          controlledBy: data.controlled_by || state.browser.controlledBy,
        },
      };
    }
    case "browser_screenshot_updated": {
      const data = env.data as { screenshot_url?: string; controlled_by?: "agent" | "user" };
      return {
        ...state,
        browser: {
          ...state.browser,
          screenshotUrl: data.screenshot_url || state.browser.screenshotUrl,
          controlledBy: data.controlled_by || state.browser.controlledBy,
        },
      };
    }
    case "browser_action_started": {
      return {
        ...state,
        browser: {
          ...state.browser,
          loading: true,
        },
      };
    }
    case "browser_action_completed": {
      const data = env.data as { url?: string; title?: string };
      return {
        ...state,
        browser: {
          ...state.browser,
          loading: false,
          url: data.url || state.browser.url,
          title: data.title || state.browser.title,
        },
      };
    }
    case "error": {
      const data = env.data as { context?: string; error?: { message?: string } };
      return {
        ...state,
        recentActions: pushAction(state, {
          id: `err-${env.timestamp}`,
          kind: "error",
          label: "Error",
          detail: data.error?.message || data.context,
          timestamp: env.timestamp,
        }),
      };
    }
    default:
      return state;
  }
}