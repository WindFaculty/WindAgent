import { useEffect } from "react";
import { create } from "zustand";
import {
  connectWs,
  fetchAgentEvents,
  fetchConversationAgents,
  fetchConversationTasks,
  decidePermission,
} from "../api/client";
import type { AgentBoardRow, TaskGraphEdge, TaskGraphNode } from "../api/client";
import type { PermissionRequestPayload } from "../api/types";

interface AgentEvents {
  seq: number;
  lines: string[];
}

export interface State {
  agents: Record<string, AgentBoardRow>;
  agentOrder: string[];
  taskNodes: Record<string, TaskGraphNode>;
  taskEdges: TaskGraphEdge[];
  events: Record<string, AgentEvents>;
  selectedAgentId: string | null;
  version: number;
}

interface MultiAgentStore {
  state: State;
  conversationId: string | null;
  wsConnections: Record<string, { ws: any; sessionId: string; afterSeq: number }>;
  permissionQueue: PermissionRequestPayload[];

  setConversationId: (conversationId: string | null) => void;
  select: (agentId: string) => void;
  refresh: () => Promise<void>;
  appendEvents: (agentId: string, seq: number, lines: string[]) => void;
  syncWebSockets: () => Promise<void>;
  closeAllWebSockets: () => void;

  enqueuePermission: (payload: PermissionRequestPayload) => void;
  removePermission: (requestId: string) => void;
  resolvePermission: (requestId: string, decision: "granted" | "denied") => Promise<void>;
}

export const useMultiAgentStore = create<MultiAgentStore>((set, get) => ({
  state: {
    agents: {},
    agentOrder: [],
    taskNodes: {},
    taskEdges: [],
    events: {},
    selectedAgentId: null,
    version: 1,
  },
  conversationId: null,
  wsConnections: {},
  permissionQueue: [],

  setConversationId: (conversationId) => {
    if (get().conversationId === conversationId) return;
    get().closeAllWebSockets();
    set({
      conversationId,
      state: {
        agents: {},
        agentOrder: [],
        taskNodes: {},
        taskEdges: [],
        events: {},
        selectedAgentId: null,
        version: 1,
      },
      permissionQueue: [],
    });
  },

  select: (agentId) => {
    set((prev) => ({
      state: {
        ...prev.state,
        selectedAgentId: agentId,
      },
    }));
  },

  refresh: async () => {
    const conversationId = get().conversationId;
    if (!conversationId) return;

    try {
      const [agents, tasks] = await Promise.all([
        fetchConversationAgents(conversationId),
        fetchConversationTasks(conversationId),
      ]);

      set((prev) => {
        const agentsMap: Record<string, AgentBoardRow> = {};
        for (const a of agents) {
          agentsMap[a.id] = a;
        }

        return {
          state: {
            ...prev.state,
            agents: agentsMap,
            agentOrder: agents.map((a) => a.id),
            selectedAgentId: prev.state.selectedAgentId ?? agents[0]?.id ?? null,
            taskNodes: Object.fromEntries(tasks.nodes.map((n) => [n.id, n])),
            taskEdges: tasks.edges,
            version: tasks.version ?? 1,
          },
        };
      });

      // Synchronize WebSocket connections for all active sub-agents
      await get().syncWebSockets();
    } catch (e) {
      console.warn("[MultiAgentStore] refresh failed:", e);
    }
  },

  appendEvents: (agentId, seq, lines) => {
    set((prev) => {
      const prevEvents = prev.state.events[agentId] ?? { seq: 0, lines: [] };
      // Deduplicate by seq: only append if the new seq is greater than previous seq
      const combined = seq > prevEvents.seq ? [...prevEvents.lines, ...lines] : prevEvents.lines;
      return {
        state: {
          ...prev.state,
          events: {
            ...prev.state.events,
            [agentId]: {
              seq: Math.max(prevEvents.seq, seq),
              lines: combined.slice(-500),
            },
          },
        },
      };
    });
  },

  enqueuePermission: (payload) => {
    if (get().permissionQueue.some((p) => p.request_id === payload.request_id)) return;
    set((prev) => ({
      permissionQueue: [...prev.permissionQueue, payload],
    }));
  },

  removePermission: (requestId) => {
    set((prev) => ({
      permissionQueue: prev.permissionQueue.filter((p) => p.request_id !== requestId),
    }));
  },

  resolvePermission: async (requestId, decision) => {
    try {
      await decidePermission(requestId, decision);
      get().removePermission(requestId);
    } catch (err) {
      console.warn("[MultiAgentStore] resolvePermission failed:", err);
    }
  },

  syncWebSockets: async () => {
    const { agents } = get().state;
    const { wsConnections } = get();
    const activeSessionIds = new Set<string>();

    for (const [agentId, agent] of Object.entries(agents)) {
      const sessionId = agent.session_id;
      if (!sessionId) continue;

      activeSessionIds.add(sessionId);

      // If we don't have an active connection for this session_id, create it
      if (!wsConnections[sessionId]) {
        const lastSeq = get().state.events[agentId]?.seq ?? 0;

        // Step 1: Pre-fetch missed history
        try {
          const back = await fetchAgentEvents(agentId, lastSeq);
          const lines = back.events
            .filter((e: any) => e.event === "terminal_output")
            .map((e: any) => String(e.data?.output ?? e.data?.text ?? ""))
            .filter(Boolean);

          if (lines.length) {
            get().appendEvents(agentId, lastSeq, lines);
          }
        } catch (err) {
          // No events or not initialized yet
        }

        // Step 2: Establish dynamic connection
        const openWs = () => {
          const currentLastSeq = get().state.events[agentId]?.seq ?? 0;
          const wsHandle = connectWs(
            sessionId,
            {
              onEvent: (env: any) => {
                if (env.event === "terminal_output") {
                  const text = String(env.data?.output ?? env.data?.text ?? "");
                  if (text) {
                    get().appendEvents(agentId, env.seq ?? 0, [text]);
                  }
                } else if (env.event === "permission_request") {
                  get().enqueuePermission(env.data as unknown as PermissionRequestPayload);
                } else if (env.event === "permission_granted" || env.event === "permission_denied") {
                  const data = env.data as { request_id?: string };
                  if (data.request_id) {
                    get().removePermission(data.request_id);
                  }
                }
              },
              onClose: () => {
                // Reconnect after 1500ms if session is still listed in active set
                setTimeout(() => {
                  const currentConnections = get().wsConnections;
                  if (currentConnections[sessionId] && activeSessionIds.has(sessionId)) {
                    console.log(`[MultiAgentStore] Reconnecting WS for agent ${agentId}`);
                    openWs();
                  }
                }, 1500);
              },
            },
            currentLastSeq
          );

          set((prev) => ({
            wsConnections: {
              ...prev.wsConnections,
              [sessionId]: { ws: wsHandle, sessionId, afterSeq: currentLastSeq },
            },
          }));
        };

        openWs();
      }
    }

    // Clean up closed/stale connections
    for (const [sessionId, conn] of Object.entries(wsConnections)) {
      if (!activeSessionIds.has(sessionId)) {
        conn.ws.close();
        set((prev) => {
          const newConns = { ...prev.wsConnections };
          delete newConns[sessionId];
          return { wsConnections: newConns };
        });
      }
    }
  },

  closeAllWebSockets: () => {
    const { wsConnections } = get();
    for (const conn of Object.values(wsConnections)) {
      conn.ws.close();
    }
    set({ wsConnections: {} });
  },
}));

export function MultiAgentProvider({
  conversationId,
  children,
}: {
  conversationId: string;
  children: React.ReactNode;
}) {
  const setConversationId = useMultiAgentStore((s) => s.setConversationId);
  const refresh = useMultiAgentStore((s) => s.refresh);
  const closeAll = useMultiAgentStore((s) => s.closeAllWebSockets);

  useEffect(() => {
    setConversationId(conversationId);
    refresh();
    const t = setInterval(refresh, 3000); // Polling agents list and task graph
    return () => {
      clearInterval(t);
      closeAll();
    };
  }, [conversationId, setConversationId, refresh, closeAll]);

  return <>{children}</>;
}

export function useMultiAgent() {
  const state = useMultiAgentStore((s) => s.state);
  const select = useMultiAgentStore((s) => s.select);
  const refresh = useMultiAgentStore((s) => s.refresh);
  const permissionQueue = useMultiAgentStore((s) => s.permissionQueue);
  const resolvePermission = useMultiAgentStore((s) => s.resolvePermission);

  return { state, select, refresh, permissionQueue, resolvePermission };
}
