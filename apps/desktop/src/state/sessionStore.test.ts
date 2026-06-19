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
      env: env("workflow_created", { workflow_id: "wf-1", steps: [] }),
    });
    expect(state).toBe(initialState); // identity preserved (no-op transition)
  });

  it("reset returns to initialState", () => {
    const populated: SessionState = {
      ...initialState,
      sessionId: "sess-1",
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
