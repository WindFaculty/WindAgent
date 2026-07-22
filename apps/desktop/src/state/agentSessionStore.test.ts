/**
 * agentSessionStore.test.ts — Unit tests for global multi-session Zustand store.
 *
 * Tests cover:
 *  - add/upsert/remove session
 *  - active session management
 *  - message deduplication (idempotent append)
 *  - tool call deduplication
 *  - workflow update
 *  - sequence handling (monotonic advance only)
 *  - permission queue idempotency
 *  - draft per session
 */

import { describe, it, expect, beforeEach } from "vitest";
import { useAgentSessionStore } from "./agentSessionStore";
import type { AgentSessionEntity, ChatMessage, ToolCallLog } from "./agentSessionStore";

// Reset store before each test
function resetStore() {
  useAgentSessionStore.setState({
    activeSessionId: null,
    sessionOrder: [],
    sessionsById: {},
    draftBySessionId: {},
  });
}

describe("agentSessionStore — session CRUD", () => {
  beforeEach(resetStore);

  it("upsertSession adds new session to sessionsById and sessionOrder", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", agentId: "coder", status: "idle" });

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-1"]).toBeDefined();
    expect(state.sessionsById["sess-1"].agentId).toBe("coder");
    expect(state.sessionOrder).toContain("sess-1");
  });

  it("upsertSession merges into existing session without overwriting other fields", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", agentId: "coder", status: "idle" });
    store.upsertSession({ id: "sess-1", status: "running" });

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-1"].agentId).toBe("coder"); // preserved
    expect(state.sessionsById["sess-1"].status).toBe("running"); // updated
  });

  it("upsertSession does not duplicate in sessionOrder", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    store.upsertSession({ id: "sess-1", status: "running" });

    const state = useAgentSessionStore.getState();
    expect(state.sessionOrder.filter((id) => id === "sess-1")).toHaveLength(1);
  });

  it("removeSessionLocal removes session and updates activeSessionId", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    store.upsertSession({ id: "sess-2", status: "idle" });
    store.setActiveSession("sess-1");

    store.removeSessionLocal("sess-1");

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-1"]).toBeUndefined();
    expect(state.sessionOrder).not.toContain("sess-1");
    // Active session should fall back to next available
    expect(state.activeSessionId).toBe("sess-2");
  });

  it("setActiveSession updates activeSessionId", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    store.setActiveSession("sess-1");

    expect(useAgentSessionStore.getState().activeSessionId).toBe("sess-1");
  });

  it("setActiveSession can be set to null", () => {
    const store = useAgentSessionStore.getState();
    store.setActiveSession(null);
    expect(useAgentSessionStore.getState().activeSessionId).toBeNull();
  });
});

describe("agentSessionStore — message deduplication", () => {
  beforeEach(resetStore);

  it("appendMessage adds message", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const msg: ChatMessage = { id: "msg-1", sender: "user", content: "hello", createdAt: 1000 };
    store.appendMessage("sess-1", msg);

    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.messages).toHaveLength(1);
    expect(session.messages[0].id).toBe("msg-1");
  });

  it("appendMessage is idempotent — duplicate id is ignored", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const msg: ChatMessage = { id: "msg-1", sender: "user", content: "hello", createdAt: 1000 };
    store.appendMessage("sess-1", msg);
    store.appendMessage("sess-1", msg); // duplicate

    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.messages).toHaveLength(1);
  });

  it("upsertMessage updates existing message content", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const msg: ChatMessage = { id: "msg-1", sender: "assistant", content: "Hello", createdAt: 1000 };
    store.appendMessage("sess-1", msg);
    store.upsertMessage("sess-1", { ...msg, content: "Hello world" });

    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.messages).toHaveLength(1);
    expect(session.messages[0].content).toBe("Hello world");
  });

  it("appendMessage on non-existent session is no-op", () => {
    const store = useAgentSessionStore.getState();
    store.appendMessage("non-existent", { id: "msg-1", sender: "user", content: "hi", createdAt: 1000 });
    // Should not throw or create session
    expect(useAgentSessionStore.getState().sessionsById["non-existent"]).toBeUndefined();
  });
});

describe("agentSessionStore — tool call deduplication", () => {
  beforeEach(resetStore);

  it("appendToolCall adds tool call", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const tc: ToolCallLog = { id: "tc-1", toolName: "read_file", status: "pending", durationMs: 0, at: 1000 };
    store.appendToolCall("sess-1", tc);

    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.toolCalls).toHaveLength(1);
  });

  it("appendToolCall is idempotent — duplicate id ignored", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const tc: ToolCallLog = { id: "tc-1", toolName: "read_file", status: "pending", durationMs: 0, at: 1000 };
    store.appendToolCall("sess-1", tc);
    store.appendToolCall("sess-1", tc);

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].toolCalls).toHaveLength(1);
  });

  it("upsertToolCall updates existing tool call status", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });

    const tc: ToolCallLog = { id: "tc-1", toolName: "read_file", status: "pending", durationMs: 0, at: 1000 };
    store.appendToolCall("sess-1", tc);
    store.upsertToolCall("sess-1", { ...tc, status: "success", durationMs: 123 });

    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.toolCalls).toHaveLength(1);
    expect(session.toolCalls[0].status).toBe("success");
    expect(session.toolCalls[0].durationMs).toBe(123);
  });
});

describe("agentSessionStore — sequence handling", () => {
  beforeEach(resetStore);

  it("updateLastEventSequence advances sequence", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle", lastEventSequence: 0 });
    store.updateLastEventSequence("sess-1", 5);

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].lastEventSequence).toBe(5);
  });

  it("updateLastEventSequence does not go backward", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle", lastEventSequence: 10 });
    store.updateLastEventSequence("sess-1", 5); // attempt to go backward

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].lastEventSequence).toBe(10);
  });
});

describe("agentSessionStore — permission queue idempotency", () => {
  beforeEach(resetStore);

  it("enqueuePermission adds permission request", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    store.enqueuePermission("sess-1", {
      request_id: "req-1",
      session_id: "sess-1",
      step_id: "step-1",
      tool_name: "read_file",
      risk_level: "safe",
      summary: "Read file",
      params: {},
    });

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].permissionQueue).toHaveLength(1);
  });

  it("enqueuePermission is idempotent for same request_id", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    const perm = {
      request_id: "req-1",
      session_id: "sess-1",
      step_id: "step-1",
      tool_name: "read_file" as const,
      risk_level: "safe" as const,
      summary: "Read file",
      params: {},
    };
    store.enqueuePermission("sess-1", perm);
    store.enqueuePermission("sess-1", perm); // duplicate

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].permissionQueue).toHaveLength(1);
  });

  it("resolvePermissionLocal removes permission request", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "idle" });
    store.enqueuePermission("sess-1", {
      request_id: "req-1",
      session_id: "sess-1",
      step_id: "step-1",
      tool_name: "read_file",
      risk_level: "safe",
      summary: "Read file",
      params: {},
    });
    store.resolvePermissionLocal("sess-1", "req-1");

    expect(useAgentSessionStore.getState().sessionsById["sess-1"].permissionQueue).toHaveLength(0);
  });
});

describe("agentSessionStore — draft per session", () => {
  beforeEach(resetStore);

  it("setDraft stores draft for session", () => {
    const store = useAgentSessionStore.getState();
    store.setDraft("sess-1", "Hello world");
    expect(useAgentSessionStore.getState().draftBySessionId["sess-1"]).toBe("Hello world");
  });

  it("draft is independent per session", () => {
    const store = useAgentSessionStore.getState();
    store.setDraft("sess-1", "Draft A");
    store.setDraft("sess-2", "Draft B");

    const state = useAgentSessionStore.getState();
    expect(state.draftBySessionId["sess-1"]).toBe("Draft A");
    expect(state.draftBySessionId["sess-2"]).toBe("Draft B");
  });
});

describe("agentSessionStore — workflow update", () => {
  beforeEach(resetStore);

  it("updateWorkflow replaces workflow", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "running" });

    const workflow = {
      workflow_id: "wf-1",
      session_id: "sess-1",
      objective: "Build it",
      created_at: new Date().toISOString(),
      status: "running" as const,
      steps: [
        { id: "s1", order: 1, name: "Step 1", tool_name: "read_file", params: {}, status: "pending" as const },
      ],
    };

    store.updateWorkflow("sess-1", workflow);
    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.workflow?.workflow_id).toBe("wf-1");
    expect(session.workflow?.steps).toHaveLength(1);
  });

  it("updateStepStatus updates step status without creating duplicate", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-1", status: "running" });
    store.updateWorkflow("sess-1", {
      workflow_id: "wf-1",
      session_id: "sess-1",
      objective: "Test",
      created_at: new Date().toISOString(),
      status: "running",
      steps: [
        { id: "s1", order: 1, name: "Step 1", tool_name: "t", params: {}, status: "pending" as const },
      ],
    });

    store.updateStepStatus("sess-1", "s1", "running");
    const session = useAgentSessionStore.getState().sessionsById["sess-1"];
    expect(session.workflow?.steps).toHaveLength(1); // no duplicate
    expect(session.workflow?.steps[0].status).toBe("running");
  });
});

describe("agentSessionStore — session isolation", () => {
  beforeEach(resetStore);

  it("messages in session A do not appear in session B", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-A", status: "running" });
    store.upsertSession({ id: "sess-B", status: "idle" });

    store.appendMessage("sess-A", { id: "msg-A1", sender: "user", content: "A message", createdAt: 1 });
    store.appendMessage("sess-B", { id: "msg-B1", sender: "user", content: "B message", createdAt: 2 });

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-A"].messages).toHaveLength(1);
    expect(state.sessionsById["sess-B"].messages).toHaveLength(1);
    expect(state.sessionsById["sess-A"].messages[0].id).toBe("msg-A1");
    expect(state.sessionsById["sess-B"].messages[0].id).toBe("msg-B1");
  });

  it("removeSessionLocal does not affect other sessions", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-A", status: "running" });
    store.upsertSession({ id: "sess-B", status: "idle" });
    store.appendMessage("sess-B", { id: "msg-B1", sender: "user", content: "hi", createdAt: 1 });

    store.removeSessionLocal("sess-A");

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-A"]).toBeUndefined();
    expect(state.sessionsById["sess-B"]).toBeDefined();
    expect(state.sessionsById["sess-B"].messages).toHaveLength(1);
  });

  it("updateStatus on session A does not affect session B", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "sess-A", status: "idle" });
    store.upsertSession({ id: "sess-B", status: "idle" });

    store.updateStatus("sess-A", "running");

    const state = useAgentSessionStore.getState();
    expect(state.sessionsById["sess-A"].status).toBe("running");
    expect(state.sessionsById["sess-B"].status).toBe("idle"); // unchanged
  });
});
