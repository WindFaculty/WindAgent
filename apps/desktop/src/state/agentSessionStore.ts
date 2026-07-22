import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import {
  createSession as apiCreateSession,
  sendMessage as apiSendMessage,
  controlSession as apiControlSession,
  fetchSession,
  fetchSessionMessages,
} from "../api/client";

// ---------- Types ----------

export type SessionStatus =
  | "idle"
  | "creating"
  | "connecting"
  | "running"
  | "waiting_input"
  | "paused"
  | "cancelling"
  | "cancelled"
  | "completed"
  | "error"
  | "disconnected"
  | "interrupted"
  | "reconnecting";

export type ConnectionStatus =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting";

export interface ChatMessage {
  id: string;
  sender: "user" | "assistant" | "system";
  content: string;
  createdAt: number;
}

export interface ToolCallLog {
  id: string;
  toolName: string;
  status: "pending" | "success" | "failed";
  durationMs: number;
  at: number;
  errorMessage?: string;
  resolvedPoint?: {
    x: number;
    y: number;
    confidence: number;
    method: string;
  };
}

export interface BrowserSessionState {
  url: string;
  title: string;
  loading: boolean;
  screenshotUrl: string | null;
  controlledBy: "agent" | "user";
}

export interface AgentSessionEntity {
  id: string;
  agentId?: string;
  title?: string;
  status: SessionStatus;

  messages: ChatMessage[];
  toolCalls: ToolCallLog[];
  workflow: any;
  permissionQueue: any[];
  recentActions: any[];
  terminalLines: string[];
  browser: BrowserSessionState;

  lastEventSequence: number;
  connectionStatus: ConnectionStatus;

  isHydrated: boolean;
  isLoading: boolean;
  error: string | null;

  createdAt?: string;
  updatedAt?: string;
}

// State machine: allowed transitions
const ALLOWED_TRANSITIONS: Record<SessionStatus, SessionStatus[]> = {
  idle: ["creating", "connecting", "running", "error", "completed"],
  creating: ["connecting", "error", "idle"],
  connecting: ["running", "disconnected", "error"],
  running: ["waiting_input", "paused", "cancelling", "completed", "error", "disconnected"],
  waiting_input: ["running", "cancelling", "cancelled"],
  paused: ["running", "cancelling", "cancelled"],
  cancelling: ["cancelled", "error"],
  cancelled: [],
  completed: [],
  error: ["connecting", "idle"],
  disconnected: ["connecting", "reconnecting", "error"],
  interrupted: ["connecting", "idle"],
  reconnecting: ["connecting", "disconnected", "error"],
};

export function isValidTransition(from: SessionStatus, to: SessionStatus): boolean {
  return ALLOWED_TRANSITIONS[from]?.includes(to) ?? false;
}

// ---------- Store shape ----------

interface AgentSessionStoreState {
  activeSessionId: string | null;
  sessionOrder: string[];
  sessionsById: Record<string, AgentSessionEntity>;
  draftBySessionId: Record<string, string>;
}

interface AgentSessionStoreActions {
  setActiveSession(sessionId: string | null): void;
  upsertSession(data: Partial<AgentSessionEntity> & { id: string }): void;
  removeSessionLocal(sessionId: string): void;
  appendMessage(sessionId: string, message: ChatMessage): void;
  upsertMessage(sessionId: string, message: ChatMessage): void;
  appendToolCall(sessionId: string, toolCall: ToolCallLog): void;
  upsertToolCall(sessionId: string, toolCall: ToolCallLog): void;
  updateWorkflow(sessionId: string, workflow: any): void;
  updateStatus(sessionId: string, status: SessionStatus): void;
  updateConnectionStatus(sessionId: string, status: ConnectionStatus): void;
  updateLastEventSequence(sessionId: string, seq: number): void;
  updateBrowserState(sessionId: string, browser: Partial<BrowserSessionState>): void;
  appendTerminalLine(sessionId: string, line: string): void;
  appendTerminalLines(sessionId: string, lines: string[]): void;
  clearTerminal(sessionId: string): void;
  enqueuePermission(sessionId: string, payload: any): void;
  resolvePermissionLocal(sessionId: string, requestId: string): void;
  appendRecentAction(sessionId: string, action: any): void;
  updateStepStatus(sessionId: string, stepId: string, status: string): void;
  setDraft(sessionId: string, draft: string): void;
  hydrateSession(sessionId: string): Promise<void>;
  createSession(agentId: string, title?: string): Promise<string>;
  sendMessage(sessionId: string, content: string): Promise<void>;
  cancelSession(sessionId: string): Promise<void>;
  archiveSession(sessionId: string): Promise<void>;
  deleteSession(sessionId: string): Promise<void>;
}

export type AgentSessionStore = AgentSessionStoreState & AgentSessionStoreActions;

// ---------- Default session entity ----------

function makeDefaultSession(id: string, agentId?: string): AgentSessionEntity {
  return {
    id,
    agentId,
    status: "idle",
    messages: [],
    toolCalls: [],
    workflow: null,
    permissionQueue: [],
    recentActions: [],
    terminalLines: [],
    browser: {
      url: "about:blank",
      title: "New Tab",
      loading: false,
      screenshotUrl: null,
      controlledBy: "agent",
    },
    lastEventSequence: 0,
    connectionStatus: "disconnected",
    isHydrated: false,
    isLoading: false,
    error: null,
  };
}

// ---------- Recent actions cap ----------

const RECENT_ACTIONS_CAP = 50;

function pushRecentAction(actions: any[], action: any): any[] {
  return [action, ...actions].slice(0, RECENT_ACTIONS_CAP);
}

// ---------- Store implementation ----------

export const useAgentSessionStore = create<AgentSessionStore>()(
  persist(
    (set, get) => ({
      activeSessionId: null,
      sessionOrder: [],
      sessionsById: {},
      draftBySessionId: {},

      setActiveSession(sessionId: string | null) {
        set({ activeSessionId: sessionId });
      },

      upsertSession(data: Partial<AgentSessionEntity> & { id: string }) {
        set((prev) => {
          const existing = prev.sessionsById[data.id];
          const next: any = {
            ...(existing ?? makeDefaultSession(data.id)),
            ...data,
            createdAt: existing?.createdAt ?? new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          };
          const sessionsById = { ...prev.sessionsById, [data.id]: next };
          const sessionOrder = prev.sessionOrder.includes(data.id)
            ? prev.sessionOrder
            : [...prev.sessionOrder, data.id];

          return {
            sessionsById,
            sessionOrder,
            activeSessionId: prev.activeSessionId ?? data.id,
          } as any;
        });
      },

      removeSessionLocal(sessionId: string) {
        set((prev) => {
          const { [sessionId]: _, ...sessionsById } = prev.sessionsById;
          return {
            sessionsById,
            sessionOrder: prev.sessionOrder.filter((id) => id !== sessionId),
            activeSessionId:
              prev.activeSessionId === sessionId
                ? prev.sessionOrder.find((id) => id !== sessionId) ?? null
                : prev.activeSessionId,
          };
        });
      },

      appendMessage(sessionId: string, message: ChatMessage) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          const exists = session.messages.some((m) => m.id === message.id);
          if (exists) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                messages: [...session.messages, message],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      upsertMessage(sessionId: string, message: ChatMessage) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          const messages = session.messages.map((m) =>
            m.id === message.id ? message : m,
          );
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                messages,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      appendToolCall(sessionId: string, toolCall: ToolCallLog) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          const exists = session.toolCalls.some((t) => t.id === toolCall.id);
          if (exists) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                toolCalls: [...session.toolCalls, toolCall],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      upsertToolCall(sessionId: string, toolCall: ToolCallLog) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          const toolCalls = session.toolCalls.map((t) =>
            t.id === toolCall.id ? toolCall : t,
          );
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                toolCalls,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateWorkflow(sessionId: string, workflow: any) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                workflow,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateStatus(sessionId: string, status: SessionStatus) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                status,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateConnectionStatus(sessionId: string, status: ConnectionStatus) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                connectionStatus: status,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateLastEventSequence(sessionId: string, seq: number) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                lastEventSequence: seq,
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateBrowserState(sessionId: string, browser: Partial<BrowserSessionState>) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                browser: { ...session.browser, ...browser },
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      appendTerminalLine(sessionId: string, line: string) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                terminalLines: [...session.terminalLines, line],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      appendTerminalLines(sessionId: string, lines: string[]) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                terminalLines: [...session.terminalLines, ...lines],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      clearTerminal(sessionId: string) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                terminalLines: [],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      enqueuePermission(sessionId: string, payload: any) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                permissionQueue: [...session.permissionQueue, payload],
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      resolvePermissionLocal(sessionId: string, requestId: string) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                permissionQueue: session.permissionQueue.filter(
                  (p) => p.request_id !== requestId,
                ),
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      appendRecentAction(sessionId: string, action: any) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                recentActions: pushRecentAction(session.recentActions, action),
                updatedAt: new Date().toISOString(),
              },
            },
          };
        });
      },

      updateStepStatus(sessionId: string, stepId: string, status: string) {
        set((prev) => {
          const session = prev.sessionsById[sessionId];
          if (!session || !session.workflow) return prev;

          const steps = session.workflow.steps.map((step: any) =>
            step.id === stepId ? { ...step, status } : step,
          );

          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...session,
                workflow: { ...session.workflow, steps } as any,
                updatedAt: new Date().toISOString(),
              },
            },
          } as any;
        });
      },

      setDraft(sessionId: string, draft: string) {
        set((prev) => ({
          draftBySessionId: { ...prev.draftBySessionId, [sessionId]: draft },
        }));
      },

      async hydrateSession(sessionId: string) {
        set((prev) => ({
          sessionsById: {
            ...prev.sessionsById,
            [sessionId]: {
              ...(prev.sessionsById[sessionId] ?? makeDefaultSession(sessionId)),
              isLoading: true,
              error: null,
            },
          },
        }));

        try {
          const [session, messages, toolCalls, workflow] = await Promise.all([
            fetchSession(sessionId),
            fetchSessionMessages(sessionId),
            fetchSessionMessages(sessionId).then((items: any[]) =>
              items.filter((item) => item.type === "tool_call"),
            ),
            get().updateStepStatus(sessionId, "", ""),
          ]);

          set((prev) => {
            const current = prev.sessionsById[sessionId] ?? makeDefaultSession(sessionId);
            const mappedMessages: ChatMessage[] = (messages ?? []).map(
              (m: any) => ({
                id: m.id ?? m.message_id ?? `${sessionId}-${Date.now()}`,
                sender: m.sender ?? m.role ?? "user",
                content: m.content ?? m.message ?? "",
                createdAt: Date.parse(m.created_at ?? m.createdAt ?? new Date().toISOString()),
              }),
            );

            const mappedToolCalls: ToolCallLog[] = (toolCalls ?? []).map(
              (t: any) => ({
                id: t.id ?? `${sessionId}-tool-${Date.now()}`,
                toolName: t.tool_name ?? t.toolName ?? "unknown",
                status: t.status ?? "pending",
                durationMs: t.duration_ms ?? t.durationMs ?? 0,
                at: Date.parse(t.created_at ?? t.at ?? new Date().toISOString()),
                errorMessage: t.error_message ?? t.errorMessage,
                resolvedPoint: t.resolved_point ?? t.resolvedPoint,
              }),
            );

            return {
              sessionsById: {
                ...prev.sessionsById,
                [sessionId]: {
                  ...current,
                  ...session,
                  messages: mappedMessages,
                  toolCalls: mappedToolCalls,
                  workflow,
                  isHydrated: true,
                  isLoading: false,
                  lastEventSequence: current.lastEventSequence,
                },
              },
            } as any;
          });
        } catch (err) {
          set((prev) => ({
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...(prev.sessionsById[sessionId] ?? makeDefaultSession(sessionId)),
                isLoading: false,
                error: err instanceof Error ? err.message : "hydrate failed",
              },
            },
          }));
        }
      },

      async createSession(agentId: string, title?: string) {
        const response = await apiCreateSession(agentId, title ?? undefined);
        const sessionId = response.session_id;
        get().upsertSession({
          id: sessionId,
          agentId,
          status: response.status as any,
        });
        return sessionId;
      },

      async sendMessage(sessionId: string, content: string) {
        const tempId = `user_${Date.now()}`;
        get().appendMessage(sessionId, {
          id: tempId,
          sender: "user",
          content,
          createdAt: Date.now(),
        });
        get().setDraft(sessionId, "");

        try {
          const response = await apiSendMessage(sessionId, content);
          get().upsertMessage(sessionId, {
            id: response.message_id,
            sender: "user",
            content,
            createdAt: Date.now(),
          });
        } catch (err) {
          get().updateStatus(sessionId, "error");
          throw err;
        }
      },

      async cancelSession(sessionId: string) {
        get().updateStatus(sessionId, "cancelling");
        try {
          await apiControlSession(sessionId, "stop");
        } catch (err) {
          console.error(`[agentSessionStore] cancelSession failed for ${sessionId}:`, err);
          get().updateStatus(sessionId, "error");
          throw err;
        }
      },

      async archiveSession(sessionId: string) {
        get().removeSessionLocal(sessionId);
      },

      async deleteSession(sessionId: string) {
        get().removeSessionLocal(sessionId);
      },
    }),
    {
      name: "wa-agent-sessions-v1",
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        activeSessionId: state.activeSessionId,
        sessionOrder: state.sessionOrder,
        draftBySessionId: state.draftBySessionId,
      }),
      onRehydrateStorage: () => (_state, error) => {
        if (error) {
          console.warn("[agentSessionStore] Failed to rehydrate from localStorage:", error);
        }
      },
    },
  ),
);
