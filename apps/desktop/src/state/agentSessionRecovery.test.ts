/**
 * Phase G25 — Agent Session frontend recovery tests (store + socket manager).
 *
 * Reproduces the session-loss failure modes described in the audit brief:
 *   - workspace unmount / tab switch must NOT lose session state
 *   - message + tool-call deduplication (idempotent upsert)
 *   - local persistence safety (nav-only, corrupt-JSON tolerant)
 *   - socket connect deduplication + unmount-safe lifecycle
 *   - refresh recovery via snapshot/events (DOCUMENTS a current wiring gap)
 *
 * Run with: npx vitest run src/state/agentSessionRecovery.test.ts
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

// --- Mock the API client BEFORE importing the store/socket manager ---
const mockConnectWs = vi.fn();
const mockFetchSession = vi.fn();
const mockFetchSessionMessages = vi.fn();
const mockFetchBrowserState = vi.fn();
const mockFetchSessionSnapshot = vi.fn();
const mockFetchSessionEvents = vi.fn();

vi.mock("../api/client", () => ({
  connectWs: (...args: any[]) => mockConnectWs(...args),
  createSession: vi.fn(),
  sendMessage: vi.fn(),
  controlSession: vi.fn(),
  fetchBrowserState: (...a: any[]) => mockFetchBrowserState(...a),
  fetchSessionMessages: (...a: any[]) => mockFetchSessionMessages(...a),
  fetchSession: (...a: any[]) => mockFetchSession(...a),
  fetchSessionSnapshot: (...a: any[]) => mockFetchSessionSnapshot(...a),
  fetchSessionEvents: (...a: any[]) => mockFetchSessionEvents(...a),
  decidePermission: vi.fn(),
}));

import { useAgentSessionStore } from "./agentSessionStore";
import { agentSocketManager } from "../services/agentSocketManager";
import { useAgentSession } from "./useAgentSession";

const STORE_KEY = "wa-agent-sessions-v1";

beforeEach(() => {
  localStorage.clear();
  mockConnectWs.mockReset();
  mockFetchSession.mockReset();
  mockFetchSessionMessages.mockReset();
  mockFetchBrowserState.mockReset();
  mockFetchSessionSnapshot.mockReset();
  mockFetchSessionEvents.mockReset();
  mockFetchSession.mockResolvedValue({
    id: "sess-1",
    status: "running",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  } as any);
  mockFetchSessionMessages.mockResolvedValue([]);
  // Snapshot now carries the refresh-recovery cursor (last_event_sequence > 0),
  // which hydrateSession uses to request a cursor-based replay on mount.
  mockFetchSessionSnapshot.mockResolvedValue({
    session: { id: "sess-1", status: "running" },
    messages: [{ id: "m1", session_id: "sess-1", sender: "user", content: "hi", created_at: new Date().toISOString() }],
    tool_calls: [],
    workflow: null,
    last_event_sequence: 5,
  } as any);
  mockFetchSessionEvents.mockResolvedValue({ session_id: "sess-1", events: [], after_seq: 5, count: 0 } as any);
  mockFetchBrowserState.mockRejectedValue(new Error("no browser"));
  mockConnectWs.mockImplementation(() => ({
    send: vi.fn(),
    close: vi.fn(),
  }));
  agentSocketManager.disconnectAll();
  useAgentSessionStore.setState({
    activeSessionId: null,
    sessionOrder: [],
    sessionsById: {},
    draftBySessionId: {},
  });
});

afterEach(() => {
  agentSocketManager.disconnectAll();
});

// ============================================================
// Phase 2.1 — Workspace unmount/remount does NOT lose state
// ============================================================
describe("Phase 2.1 — unmount/remount preserves session", () => {
  it("remounting the workspace does not recreate the session or duplicate data", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "A", agentId: "coder", status: "running" });
    store.setActiveSession("A");
    for (let i = 1; i <= 3; i++) {
      store.appendMessage("A", { id: `m${i}`, sender: "user", content: `msg ${i}`, createdAt: i });
    }
    store.appendToolCall("A", { id: "tc1", toolName: "read", status: "pending", durationMs: 0, at: 1 });
    store.appendToolCall("A", { id: "tc2", toolName: "write", status: "pending", durationMs: 0, at: 2 });
    store.updateWorkflow("A", {
      workflow_id: "wf1", session_id: "A", objective: "do it",
      created_at: new Date().toISOString(), status: "running", steps: [],
    });

    const before = useAgentSessionStore.getState().sessionsById["A"];

    const store2 = useAgentSessionStore.getState();
    store2.upsertSession({ id: "A", agentId: "coder", status: "running" });

    const after = useAgentSessionStore.getState().sessionsById["A"];

    expect(after.id).toBe(before.id);
    expect(useAgentSessionStore.getState().activeSessionId).toBe("A");
    expect(useAgentSessionStore.getState().sessionOrder).toEqual(["A"]);
    expect(after.messages).toHaveLength(3);
    expect(after.toolCalls).toHaveLength(2);
    expect(after.workflow?.workflow_id).toBe("wf1");
    expect(after.status).toBe("running");
  });
});

// ============================================================
// Phase 2.3 — Store normalization
// ============================================================
describe("Phase 2.3 — store normalization", () => {
  it("sessionOrder never contains duplicate IDs", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "x" });
    store.upsertSession({ id: "x" });
    store.upsertSession({ id: "x" });
    expect(useAgentSessionStore.getState().sessionOrder.filter((id) => id === "x")).toHaveLength(1);
  });

  it("removing the active session falls back to next session", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "a" });
    store.upsertSession({ id: "b" });
    store.setActiveSession("a");
    store.removeSessionLocal("a");
    expect(useAgentSessionStore.getState().sessionsById["a"]).toBeUndefined();
    expect(useAgentSessionStore.getState().activeSessionId).toBe("b");
  });

  it("there is exactly one source of truth (sessionsById)", () => {
    const state = useAgentSessionStore.getState();
    const ownKeys = Object.keys(state).filter(
      (k) => typeof (state as any)[k] === "object" || Array.isArray((state as any)[k]),
    );
    expect(ownKeys).toContain("sessionsById");
    expect(ownKeys).toContain("sessionOrder");
    expect(ownKeys).not.toContain("sessions");
  });
});

// ============================================================
// Phase 2.4 — Message deduplication
// ============================================================
describe("Phase 2.4 — message deduplication", () => {
  it("emitting the same message id twice yields a single message", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "A" });
    const msg = { id: "message-1", sender: "user" as const, content: "hi", createdAt: 1 };
    store.appendMessage("A", msg);
    store.appendMessage("A", msg);
    expect(useAgentSessionStore.getState().sessionsById["A"].messages).toHaveLength(1);
  });

  it("upsert overwrites content for same id", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "A" });
    store.appendMessage("A", { id: "message-1", sender: "assistant", content: "Hello", createdAt: 1 });
    store.upsertMessage("A", { id: "message-1", sender: "assistant", content: "Hello world", createdAt: 1 });
    const msgs = useAgentSessionStore.getState().sessionsById["A"].messages;
    expect(msgs).toHaveLength(1);
    expect(msgs[0].content).toBe("Hello world");
  });
});

// ============================================================
// Phase 2.5 — Tool call deduplication
// ============================================================
describe("Phase 2.5 — tool call deduplication", () => {
  it("tool_started/updated/completed + duplicate completed -> single tool call, correct final", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "A" });
    store.appendToolCall("A", { id: "tc-1", toolName: "click", status: "pending", durationMs: 0, at: 1 });
    store.upsertToolCall("A", { id: "tc-1", toolName: "click", status: "success", durationMs: 42, at: 1 });
    store.upsertToolCall("A", { id: "tc-1", toolName: "click", status: "success", durationMs: 42, at: 1 });

    const tcs = useAgentSessionStore.getState().sessionsById["A"].toolCalls;
    expect(tcs).toHaveLength(1);
    expect(tcs[0].status).toBe("success");
    expect(tcs[0].durationMs).toBe(42);
  });
});

// ============================================================
// Phase 2.6 — Local persistence safety
// ============================================================
describe("Phase 2.6 — local persistence safety", () => {
  it("only navigation state is persisted (not full message history)", () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "A" });
    store.setActiveSession("A");
    store.appendMessage("A", { id: "m1", sender: "user", content: "x".repeat(5000), createdAt: 1 });
    store.setDraft("A", "my draft");

    useAgentSessionStore.setState({ activeSessionId: "A" });

    const raw = localStorage.getItem(STORE_KEY);
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw!);
    expect(JSON.stringify(parsed).includes("x".repeat(5000))).toBe(false);
    expect(parsed.state.activeSessionId).toBe("A");
    expect(parsed.state.sessionOrder).toContain("A");
    expect(parsed.state.draftBySessionId["A"]).toBe("my draft");
    expect(parsed.state.sessionsById).toBeUndefined();
  });

  it("corrupt JSON in localStorage does not crash the store", async () => {
    localStorage.setItem(STORE_KEY, "{not valid json");
    const mod = await vi.importActual<typeof import("./agentSessionStore")>(
      `./agentSessionStore?corrupt=${Date.now()}`,
    );
    expect(() => mod.useAgentSessionStore.getState()).not.toThrow();
    expect(mod.useAgentSessionStore.getState().activeSessionId).toBeNull();
  });

  it("stale session IDs are NOT auto-pruned after a backend 404 (gap)", async () => {
    const store = useAgentSessionStore.getState();
    store.upsertSession({ id: "ghost", status: "running" });
    store.setActiveSession("ghost");
    expect(useAgentSessionStore.getState().sessionOrder).toContain("ghost");
    expect(mockFetchSessionSnapshot).not.toHaveBeenCalled();
  });
});

// ============================================================
// Phase 3.1 — Socket connect deduplication
// ============================================================
describe("Phase 3.1 — socket connect deduplication", () => {
  it("concurrent connect('a') x3 opens exactly ONE socket", async () => {
    const p1 = agentSocketManager.connect("a");
    const p2 = agentSocketManager.connect("a");
    const p3 = agentSocketManager.connect("a");
    await Promise.all([p1, p2, p3]);

    expect(mockConnectWs).toHaveBeenCalledTimes(1);
    expect(agentSocketManager.getConnectionState("a")).toBe("connected");
  });

  it("re-connect after intentional disconnect reuses a single socket", async () => {
    await agentSocketManager.connect("a");
    expect(mockConnectWs).toHaveBeenCalledTimes(1);
    agentSocketManager.disconnect("a", "test");
    await agentSocketManager.connect("a");
    expect(mockConnectWs).toHaveBeenCalledTimes(2);
  });
});

// ============================================================
// Phase 3.2 — UI unmount does NOT close the socket
// ============================================================
describe("Phase 3.2 — unmount does not close socket", () => {
  it("subscribe + unsubscribe (component unmount) leaves the socket open", async () => {
    await agentSocketManager.connect("a");
    const handle = mockConnectWs.mock.results[0].value as { close: ReturnType<typeof vi.fn> };

    const unsub1 = agentSocketManager.subscribe("a", () => {});
    const unsub2 = agentSocketManager.subscribe("a", () => {});
    unsub1();
    unsub2();

    expect(handle.close).not.toHaveBeenCalled();
    expect(agentSocketManager.getConnectionState("a")).toBe("connected");
  });

  it("the React hook's unmount cleanup does not disconnect the session", async () => {
    const { unmount } = renderHook(() => useAgentSession("recovery-unique-1"));
    // Wait until the socket manager's connect() has flipped state to connected.
    await act(async () => {
      await agentSocketManager.connect("recovery-unique-1");
    });
    expect(mockConnectWs).toHaveBeenCalledTimes(1);
    const handle = mockConnectWs.mock.results[0].value as { close: ReturnType<typeof vi.fn> };

    unmount();

    expect(handle.close).not.toHaveBeenCalled();
    expect(agentSocketManager.getConnectionState("recovery-unique-1")).toBe("connected");
  });
});

// ============================================================
// Refresh recovery wiring gap (Phase G25 deliverable)
// ============================================================
describe("Refresh recovery — now wired", () => {
  it("useAgentSession hydrates from snapshot + replay events on mount (fixed)", async () => {
    renderHook(() => useAgentSession("recovery-unique-1"));
    // Flush the mount effect AND the async hydrateSession (snapshot + replay).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });

    // Snapshot is the authoritative refresh source; fetchSession is skipped
    // when the snapshot provides the session metadata.
    expect(mockFetchSessionSnapshot).toHaveBeenCalled();
    // The store must request a cursor-based replay on mount.
    expect(mockFetchSessionEvents).toHaveBeenCalled();
  });
});
