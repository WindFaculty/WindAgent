import { useEffect } from "react";
import { create } from "zustand";
import {
  decidePermission,
  fetchConversationAgents,
  fetchConversationTasks,
  type AgentBoardRow,
  type TaskGraphEdge,
  type TaskGraphNode,
} from "../api/client";
import type { ConversationEventEnvelope, PermissionRequestPayload } from "../api/types";
import { conversationSocketManager } from "../services/conversationSocketManager";

interface AgentEvents {
  sequence: number;
  lines: string[];
}

export interface ConversationProjection {
  conversationId: string;
  agentInstanceIds: string[];
  planVersionIds: string[];
  sequence: number;
}

export interface AgentSessionProjection {
  agentSessionId: string;
  agentInstanceId: string;
  windagentSessionId: string | null;
  runtimeLocator: string | null;
  hermesRunId: string | null;
  status: string | null;
}

/** The normalized Phase 7 desktop projection; every key is a durable ID. */
export interface State {
  conversations: Record<string, ConversationProjection>;
  agents: Record<string, AgentBoardRow>;
  sessions: Record<string, AgentSessionProjection>;
  events: Record<string, AgentEvents>;
  taskNodes: Record<string, Record<string, TaskGraphNode>>;
  taskEdges: Record<string, TaskGraphEdge[]>;
  browserSessionIds: Record<string, string>;
  selectedAgentId: string | null;
}

interface MultiAgentStore {
  state: State;
  conversationId: string | null;
  permissionQueue: PermissionRequestPayload[];

  setConversationId: (conversationId: string | null) => void;
  select: (agentInstanceId: string) => void;
  refresh: () => Promise<void>;
  appendEvents: (agentInstanceId: string, sequence: number, lines: string[]) => void;
  syncWebSockets: () => Promise<void>;
  closeAllWebSockets: () => void;
  enqueuePermission: (payload: PermissionRequestPayload) => void;
  removePermission: (requestId: string) => void;
  resolvePermission: (requestId: string, decision: "granted" | "denied") => Promise<void>;
}

const initialState: State = {
  conversations: {},
  agents: {},
  sessions: {},
  events: {},
  taskNodes: {},
  taskEdges: {},
  browserSessionIds: {},
  selectedAgentId: null,
};

export const useMultiAgentStore = create<MultiAgentStore>((set, get) => ({
  state: initialState,
  conversationId: null,
  permissionQueue: [],

  setConversationId: (conversationId) => {
    if (get().conversationId === conversationId) return;
    get().closeAllWebSockets();
    set((previous) => ({
      conversationId,
      state: { ...previous.state, selectedAgentId: null },
      permissionQueue: [],
    }));
  },

  select: (agentInstanceId) => {
    set((previous) => ({
      state: { ...previous.state, selectedAgentId: agentInstanceId },
    }));
  },

  refresh: async () => {
    const conversationId = get().conversationId;
    if (!conversationId) return;
    await get().syncWebSockets();

    try {
      const [agents, plans] = await Promise.all([
        fetchConversationAgents(conversationId),
        fetchConversationTasks(conversationId),
      ]);
      set((previous) => {
        const agentIds = agents.map((agent) => agent.agent_instance_id);
        const planIds = plans.map((plan) => plan.plan_version_id);
        const agentsById = { ...previous.state.agents };
        const sessionsById = { ...previous.state.sessions };
        const nodesByPlan = { ...previous.state.taskNodes };
        const edgesByPlan = { ...previous.state.taskEdges };

        for (const agent of agents) {
          agentsById[agent.agent_instance_id] = agent;
          if (agent.agent_session_id) {
            sessionsById[agent.agent_session_id] = {
              agentSessionId: agent.agent_session_id,
              agentInstanceId: agent.agent_instance_id,
              windagentSessionId: agent.windagent_session_id,
              runtimeLocator: agent.runtime_locator,
              hermesRunId: agent.hermes_run_id,
              status: agent.session_status,
            };
          }
        }
        for (const plan of plans) {
          nodesByPlan[plan.plan_version_id] = Object.fromEntries(
            plan.nodes.map((node) => [node.node_id, node]),
          );
          edgesByPlan[plan.plan_version_id] = plan.edges;
        }

        const current = previous.state.conversations[conversationId];
        const selectedAgentId = previous.state.selectedAgentId;
        const selectedStillPresent = selectedAgentId !== null && agentIds.includes(selectedAgentId);
        const firstSubAgent = agents.find((agent) => agent.agent_type !== "orchestrator");
        return {
          state: {
            ...previous.state,
            conversations: {
              ...previous.state.conversations,
              [conversationId]: {
                conversationId,
                agentInstanceIds: agentIds,
                planVersionIds: planIds,
                sequence: current?.sequence ?? 0,
              },
            },
            agents: agentsById,
            sessions: sessionsById,
            taskNodes: nodesByPlan,
            taskEdges: edgesByPlan,
            selectedAgentId: selectedStillPresent
              ? selectedAgentId
              : firstSubAgent?.agent_instance_id ?? agents[0]?.agent_instance_id ?? null,
          },
        };
      });
    } catch (error) {
      console.warn("[MultiAgentStore] workspace refresh failed:", error);
    }
  },

  appendEvents: (agentInstanceId, sequence, lines) => {
    set((previous) => {
      const current = previous.state.events[agentInstanceId] ?? { sequence: 0, lines: [] };
      if (sequence <= current.sequence) return previous;
      return {
        state: {
          ...previous.state,
          events: {
            ...previous.state.events,
            [agentInstanceId]: {
              sequence,
              lines: [...current.lines, ...lines].slice(-500),
            },
          },
        },
      };
    });
  },

  syncWebSockets: async () => {
    const conversationId = get().conversationId;
    if (!conversationId) return;
    conversationSocketManager.connect(
      conversationId,
      () => get().state.conversations[conversationId]?.sequence ?? 0,
    );
    conversationSocketManager.subscribe(conversationId, handleConversationEvent);
  },

  closeAllWebSockets: () => {
    const conversationId = get().conversationId;
    if (conversationId) conversationSocketManager.disconnect(conversationId);
  },

  enqueuePermission: (payload) => {
    if (get().permissionQueue.some((request) => request.request_id === payload.request_id)) return;
    set((previous) => ({ permissionQueue: [...previous.permissionQueue, payload] }));
  },

  removePermission: (requestId) => {
    set((previous) => ({
      permissionQueue: previous.permissionQueue.filter((request) => request.request_id !== requestId),
    }));
  },

  resolvePermission: async (requestId, decision) => {
    try {
      await decidePermission(requestId, decision);
      get().removePermission(requestId);
    } catch (error) {
      console.warn("[MultiAgentStore] resolvePermission failed:", error);
    }
  },
}));

function handleConversationEvent(event: ConversationEventEnvelope): void {
  const store = useMultiAgentStore.getState();
  const conversationId = store.conversationId;
  if (!conversationId || event.conversation_id !== conversationId) return;
  const conversation = store.state.conversations[conversationId];
  if (event.sequence <= (conversation?.sequence ?? 0)) return;

  const agentInstanceId = event.agent_instance_id ?? "orchestrator";
  if (event.event_type === "terminal_output") {
    const line = String(event.data.output ?? event.data.text ?? "");
    if (line) store.appendEvents(agentInstanceId, event.sequence, [line]);
  }
  if (event.event_type === "browser_session_started") {
    const browserSessionId = String(event.data.browser_session_id ?? event.data.session_id ?? "");
    if (browserSessionId) {
      useMultiAgentStore.setState((previous) => ({
        state: {
          ...previous.state,
          browserSessionIds: {
            ...previous.state.browserSessionIds,
            [agentInstanceId]: browserSessionId,
          },
        },
      }));
    }
  }
  if (event.event_type === "permission_request") {
    store.enqueuePermission(event.data as unknown as PermissionRequestPayload);
  } else if (event.event_type === "permission_granted" || event.event_type === "permission_denied") {
    const requestId = (event.data as { request_id?: string }).request_id;
    if (requestId) store.removePermission(requestId);
  }

  useMultiAgentStore.setState((previous) => ({
    state: {
      ...previous.state,
      conversations: {
        ...previous.state.conversations,
        [conversationId]: {
          ...(previous.state.conversations[conversationId] ?? {
            conversationId,
            agentInstanceIds: [],
            planVersionIds: [],
            sequence: 0,
          }),
          sequence: event.sequence,
        },
      },
    },
  }));
}

export function MultiAgentProvider({
  conversationId,
  children,
}: {
  conversationId: string;
  children: React.ReactNode;
}) {
  const setConversationId = useMultiAgentStore((store) => store.setConversationId);
  const refresh = useMultiAgentStore((store) => store.refresh);
  const closeAll = useMultiAgentStore((store) => store.closeAllWebSockets);

  useEffect(() => {
    setConversationId(conversationId);
    void refresh();
    const timer = setInterval(() => void refresh(), 3_000);
    return () => {
      clearInterval(timer);
      closeAll();
    };
  }, [conversationId, setConversationId, refresh, closeAll]);

  return <>{children}</>;
}

export function useMultiAgent() {
  const state = useMultiAgentStore((store) => store.state);
  const conversationId = useMultiAgentStore((store) => store.conversationId);
  const select = useMultiAgentStore((store) => store.select);
  const refresh = useMultiAgentStore((store) => store.refresh);
  const permissionQueue = useMultiAgentStore((store) => store.permissionQueue);
  const resolvePermission = useMultiAgentStore((store) => store.resolvePermission);
  return { state, conversationId, select, refresh, permissionQueue, resolvePermission };
}
