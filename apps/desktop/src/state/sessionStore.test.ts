/** Phase 10 — Event reducer tests (per ban_ke_hoach.md §Phase 10.1).
 *
 * Verifies that the in-memory store transitions correctly in response
 * to each interesting event from docs/event_protocol.md. Pure logic,
 * no DOM, no fetch — runs in vitest's default node environment.
 */
import { describe, expect, it } from "vitest";

import {
  initialState,
  reducer,
  type SessionState,
} from "../state/sessionStore";
import type { EventEnvelope } from "../api/types";

function env(event: string, data: Record<string, unknown>): EventEnvelope {
  return {
    event: event as EventEnvelope["event"],
    timestamp: "2026-06-19T12:00:00Z",
    data,
  };
}

describe("sessionStore.reducer — processEvent", () => {
  it("appends user message on message_received", () => {
    const state: SessionState = reducer(initialState, {
      type: "processEvent",
      env: env("message_received", {
        message_id: "m1",
        content: "Mở Notepad",
      }),
    });
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0]).toMatchObject({
      id: "m1",
      sender: "user",
      content: "Mở Notepad",
    });
  });

  it("queues permission_request and removes it on granted/denied", () => {
    let state = reducer(initialState, {
      type: "processEvent",
      env: env("permission_request", {
        request_id: "req-1",
        session_id: "sess",
        step_id: "step",
        tool_name: "type_text",
        risk_level: "medium",
        summary: "Type text",
        params: {},
      }),
    });
    expect(state.permissionQueue).toHaveLength(1);

    state = reducer(state, {
      type: "processEvent",
      env: env("permission_granted", { request_id: "req-1" }),
    });
    expect(state.permissionQueue).toHaveLength(0);
  });

  it("records tool_call_finished with status + resolved point", () => {
    const state = reducer(initialState, {
      type: "processEvent",
      env: env("tool_call_finished", {
        tool_name: "click_target",
        status: "failed",
        duration_ms: 42,
        error: { message: "vision not implemented" },
        output: {
          resolved_point: { x: 100, y: 200, confidence: 0.7, method: "manual_stub" },
        },
      }),
    });
    expect(state.toolCalls).toHaveLength(1);
    expect(state.toolCalls[0]).toMatchObject({
      toolName: "click_target",
      status: "failed",
      durationMs: 42,
      errorMessage: "vision not implemented",
      resolvedPoint: { x: 100, y: 200, confidence: 0.7, method: "manual_stub" },
    });
  });

  it("ignores unknown events without mutating state", () => {
    const state = reducer(initialState, {
      type: "processEvent",
      env: env("unknown_event", {}),
    });
    expect(state).toBe(initialState); // identity preserved (no-op transition)
  });

  it("loads workflow + steps from workflow_created", () => {
    const state = reducer(initialState, {
      type: "processEvent",
      env: env("workflow_created", {
        workflow_id: "wf-1",
        session_id: "sess-1",
        objective: "Build the thing",
        status: "running",
        steps: [
          { id: "s1", order: 1, name: "Read repo", tool_name: "read", status: "pending" },
          { id: "s2", order: 2, name: "Edit code", tool_name: "edit", status: "pending" },
        ],
      }),
    });
    expect(state.workflow?.workflow_id).toBe("wf-1");
    expect(state.workflow?.objective).toBe("Build the thing");
    expect(state.workflow?.steps).toHaveLength(2);
    expect(state.recentActions[0].kind).toBe("workflow");
  });

  it("replaces workflow on workflow_updated without duplicating steps", () => {
    let state = reducer(initialState, {
      type: "processEvent",
      env: env("workflow_created", {
        workflow_id: "wf-1",
        session_id: "sess-1",
        objective: "Plan",
        status: "running",
        steps: [{ id: "s1", order: 1, name: "One", tool_name: "t", status: "pending" }],
      }),
    });
    state = reducer(state, {
      type: "processEvent",
      env: env("workflow_updated", {
        workflow_id: "wf-1",
        session_id: "sess-1",
        objective: "Plan",
        status: "running",
        steps: [
          { id: "s1", order: 1, name: "One", tool_name: "t", status: "completed" },
          { id: "s2", order: 2, name: "Two", tool_name: "t", status: "in_progress" },
        ],
      }),
    });
    expect(state.workflow?.steps).toHaveLength(2);
    expect(state.workflow?.steps[0].status).toBe("completed");
    expect(state.workflow?.steps[1].status).toBe("in_progress");
  });

  it("marks step status from step_started/step_completed", () => {
    let state = reducer(initialState, {
      type: "processEvent",
      env: env("workflow_created", {
        workflow_id: "wf-1",
        session_id: "sess-1",
        objective: "Plan",
        status: "running",
        steps: [{ id: "s1", order: 1, name: "One", tool_name: "t", status: "pending" }],
      }),
    });
    state = reducer(state, {
      type: "processEvent",
      env: env("step_started", { step_id: "s1" }),
    });
    expect(state.workflow?.steps[0].status).toBe("running");
    state = reducer(state, {
      type: "processEvent",
      env: env("step_completed", { step_id: "s1", duration_ms: 10 }),
    });
    expect(state.workflow?.steps[0].status).toBe("success");
    expect(state.recentActions.find((a) => a.kind === "step")).toBeTruthy();
  });

  it("appends recent actions for tool calls and messages", () => {
    let state = reducer(initialState, {
      type: "processEvent",
      env: env("message_received", { message_id: "m1", content: "hi" }),
    });
    state = reducer(state, {
      type: "processEvent",
      env: env("tool_call_finished", {
        tool_name: "read_file",
        status: "success",
        duration_ms: 5,
      }),
    });
    expect(state.recentActions.some((a) => a.kind === "message")).toBe(true);
    expect(state.recentActions.some((a) => a.kind === "tool_call")).toBe(true);
  });

  it("reset returns to initialState", () => {
    const populated: SessionState = {
      ...initialState,
      sessionId: "sess-1",
      workflow: {
        workflow_id: "wf-1",
        session_id: "sess-1",
        objective: "x",
        created_at: new Date().toISOString(),
        status: "running",
        steps: [],
      },
      recentActions: [
        { id: "a1", kind: "tool_call", label: "Ran x", timestamp: new Date().toISOString() },
      ],
      messages: [
        {
          id: "m",
          sender: "user",
          content: "hi",
          createdAt: Date.now(),
        },
      ],
    };
    const state = reducer(populated, { type: "reset" });
    expect(state).toEqual(initialState);
  });
});

describe("sessionStore.reducer — plain actions", () => {
  it("setSessionId stores the id", () => {
    const state = reducer(initialState, {
      type: "setSessionId",
      sessionId: "sess-99",
    });
    expect(state.sessionId).toBe("sess-99");
  });

  it("setModelsOnline updates the online flag", () => {
    const state = reducer(initialState, { type: "setModelsOnline", online: true });
    expect(state.modelsOnline).toBe(true);
  });
});
