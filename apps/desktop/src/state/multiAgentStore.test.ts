import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockFetchConversationAgents = vi.fn();
const mockFetchConversationTasks = vi.fn();
const mockConnect = vi.fn();
const mockSubscribe = vi.fn();
const mockDisconnect = vi.fn();
let conversationListener: ((event: any) => void) | undefined;

vi.mock("../api/client", () => ({
  fetchConversationAgents: (...args: any[]) => mockFetchConversationAgents(...args),
  fetchConversationTasks: (...args: any[]) => mockFetchConversationTasks(...args),
  decidePermission: vi.fn(),
}));

vi.mock("../services/conversationSocketManager", () => ({
  conversationSocketManager: {
    connect: (...args: any[]) => mockConnect(...args),
    subscribe: (...args: any[]) => mockSubscribe(...args),
    disconnect: (...args: any[]) => mockDisconnect(...args),
  },
}));

import { useMultiAgentStore } from "./multiAgentStore";

const agent = (id: string, type: string, nodeId: string | null) => ({
  agent_instance_id: id,
  parent_task_id: "parent-1",
  agent_type: type,
  status: "running",
  permission_profile: {},
  canonical_model_id: "windagent/local-agent",
  assigned_node_id: nodeId,
  agent_session_id: `session-${id}`,
  windagent_session_id: `wind-${id}`,
  runtime_locator: `runtime://${id}`,
  hermes_run_id: `hermes-${id}`,
  session_status: "running",
  agent_run_id: `run-${id}`,
  agent_run_status: "running",
  fencing_token: "fence",
  task_node_run_id: `node-run-${id}`,
  node_state: "running",
  node_version: 1,
  concurrency_group: null,
  next_retry_at: null,
  worktree_id: null,
  worktree_path: null,
  worktree_branch: null,
  worktree_status: null,
  worktree_quarantine_path: null,
  planned_tool_name: "agent_run",
  current_tool_name: null,
  route_lock_id: null,
  provider_binding_id: null,
});

beforeEach(() => {
  mockFetchConversationAgents.mockReset();
  mockFetchConversationTasks.mockReset();
  mockConnect.mockReset();
  mockSubscribe.mockReset();
  mockDisconnect.mockReset();
  conversationListener = undefined;
  mockSubscribe.mockImplementation((_conversationId, listener) => {
    conversationListener = listener;
    return vi.fn();
  });
  useMultiAgentStore.setState({
    conversationId: null,
    permissionQueue: [],
    state: {
      conversations: {}, agents: {}, sessions: {}, events: {}, taskNodes: {}, taskEdges: {},
      browserSessionIds: {}, selectedAgentId: null,
    },
  });
});

afterEach(() => vi.restoreAllMocks());

describe("multiAgentStore", () => {
  it("normalizes durable workspace projections and keeps A/B terminal output isolated", async () => {
    mockFetchConversationAgents.mockResolvedValue([
      agent("orchestrator", "orchestrator", null),
      agent("agent-a", "research", "node-a"),
      agent("agent-b", "coding", "node-b"),
    ]);
    mockFetchConversationTasks.mockResolvedValue([{
      plan_version_id: "plan-1", version: 1, parent_task_id: "parent-1", objective: "Ship it",
      nodes: [
        { node_id: "node-a", position: 0, objective: "Research", agent_type: "research", tool_name: "agent_run", concurrency_group: null, status: "running", task_node_run_id: "node-run-agent-a", node_version: 1, next_retry_at: null, assigned_agent_instance_id: "agent-a" },
        { node_id: "node-b", position: 1, objective: "Implement", agent_type: "coding", tool_name: "agent_run", concurrency_group: null, status: "running", task_node_run_id: "node-run-agent-b", node_version: 1, next_retry_at: null, assigned_agent_instance_id: "agent-b" },
      ],
      edges: [{ edge_id: "edge-1", from_node_id: "node-a", to_node_id: "node-b" }],
    }]);

    useMultiAgentStore.getState().setConversationId("conversation-1");
    await useMultiAgentStore.getState().refresh();
    expect(mockConnect).toHaveBeenCalledWith("conversation-1", expect.any(Function));
    expect(useMultiAgentStore.getState().state.conversations["conversation-1"].planVersionIds).toEqual(["plan-1"]);
    expect(useMultiAgentStore.getState().state.sessions["session-agent-a"].agentInstanceId).toBe("agent-a");

    conversationListener?.({
      event_id: "event-a", idempotency_key: "event-a", conversation_id: "conversation-1",
      agent_instance_id: "agent-a", agent_session_id: "session-agent-a", sequence: 1,
      event_type: "terminal_output", data: { output: "A only" }, occurred_at: "now", is_replay: false,
    });
    conversationListener?.({
      event_id: "event-b", idempotency_key: "event-b", conversation_id: "conversation-1",
      agent_instance_id: "agent-b", agent_session_id: "session-agent-b", sequence: 2,
      event_type: "terminal_output", data: { output: "B only" }, occurred_at: "now", is_replay: false,
    });

    const state = useMultiAgentStore.getState().state;
    expect(state.events["agent-a"].lines).toEqual(["A only"]);
    expect(state.events["agent-b"].lines).toEqual(["B only"]);
    expect(state.conversations["conversation-1"].sequence).toBe(2);
  });
});
