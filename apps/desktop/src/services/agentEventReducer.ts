/**
 * agentEventReducer.ts — Single point of truth for translating WebSocket
 * EventEnvelopes into AgentSessionStore mutations.
 *
 * Rules:
 *  - Every event type handled here and NOWHERE else.
 *  - All mutations are idempotent (safe to re-apply after reconnect).
 *  - Sequence is tracked to detect and drop duplicate/out-of-order events.
 *  - No React dependencies — pure functions calling Zustand store.
 */

import type { EventEnvelope } from "../api/types";
import type { Workflow } from "../api/types";
import { useAgentSessionStore } from "../state/agentSessionStore";
import type { ToolCallLog } from "../state/agentSessionStore";

// ---------- Event processing ----------

/**
 * Apply an EventEnvelope to the global session store.
 * Called by AgentSocketManager whenever a new event arrives.
 * Idempotent: safe to call multiple times with same event.
 */
export function applyAgentEvent(sessionId: string, env: EventEnvelope): void {
  const store = useAgentSessionStore.getState();

  // Track sequence — only advance, never go backward
  if (env.seq !== undefined && env.seq > 0) {
    const currentSeq = store.sessionsById[sessionId]?.lastEventSequence ?? 0;
    if (env.seq <= currentSeq) {
      // Duplicate or out-of-order event — drop silently
      console.debug(
        `[agentEventReducer] Dropping duplicate event seq=${env.seq} (current=${currentSeq}) for session ${sessionId}`,
      );
      return;
    }
    store.updateLastEventSequence(sessionId, env.seq);
  }

  switch (env.event) {
    case "message_received": {
      const data = env.data as { content: string; message_id: string };
      const session = store.sessionsById[sessionId];

      // Check if temp user message exists with same content — update its id
      const tempMsg = session?.messages.find(
        (m) =>
          m.sender === "user" &&
          m.content === data.content &&
          m.id.startsWith("user_"),
      );

      if (tempMsg) {
        // Remove old temp
        useAgentSessionStore.setState((prev) => {
          const s = prev.sessionsById[sessionId];
          if (!s) return prev;
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: {
                ...s,
                messages: s.messages
                  .filter((m) => m.id !== tempMsg.id)
                  .concat({
                    ...tempMsg,
                    id: data.message_id,
                  }),
              },
            },
          };
        });
      } else {
        store.appendMessage(sessionId, {
          id: data.message_id,
          sender: "user",
          content: data.content,
          createdAt: Date.parse(env.timestamp),
        });
      }

      store.appendRecentAction(sessionId, {
        id: `msg-${data.message_id}`,
        kind: "message",
        label: "You sent a message",
        detail: data.content,
        timestamp: env.timestamp,
      });
      break;
    }

    case "workflow_created":
    case "workflow_updated": {
      const wf = env.data as unknown as Partial<Workflow>;
      if (!wf?.workflow_id) break;

      const steps = (wf.steps ?? []).map((s) => ({
        ...s,
        status: (s.status ?? "pending") as Workflow["steps"][number]["status"],
      }));

      const workflow: Workflow = {
        workflow_id: wf.workflow_id,
        session_id: wf.session_id ?? sessionId,
        objective: wf.objective ?? "",
        created_at: wf.created_at ?? env.timestamp,
        status: (wf.status ?? "running") as Workflow["status"],
        steps,
      };

      store.updateWorkflow(sessionId, workflow);
      store.appendRecentAction(sessionId, {
        id: `wf-${wf.workflow_id}-${env.event}-${env.timestamp}`,
        kind: "workflow",
        label: env.event === "workflow_created" ? "Task plan created" : "Task plan updated",
        detail: wf.objective || `${steps.length} tasks`,
        timestamp: env.timestamp,
      });
      break;
    }

    case "assistant_message_started": {
      const data = env.data as { message_id?: string };
      const msgId =
        data.message_id ||
        "assistant_msg_" + Math.random().toString(36).substring(2, 11);
      // Start a new assistant message entry (empty content, will be filled by deltas)
      store.appendMessage(sessionId, {
        id: msgId,
        sender: "assistant",
        content: "",
        createdAt: Date.parse(env.timestamp),
      });
      break;
    }

    case "assistant_message_delta": {
      const data = env.data as { message_id?: string; delta: string };
      const session = store.sessionsById[sessionId];
      if (!session) break;

      const messages = session.messages;
      const lastMsg = messages[messages.length - 1];

      if (lastMsg?.sender === "assistant") {
        // Append delta to last assistant message
        useAgentSessionStore.setState((prev) => {
          const s = prev.sessionsById[sessionId];
          if (!s) return prev;
          const msgs = [...s.messages];
          const last = msgs[msgs.length - 1];
          if (!last || last.sender !== "assistant") return prev;
          msgs[msgs.length - 1] = { ...last, content: last.content + data.delta };
          return {
            sessionsById: {
              ...prev.sessionsById,
              [sessionId]: { ...s, messages: msgs },
            },
          };
        });
      } else {
        // No current assistant message — create one
        store.appendMessage(sessionId, {
          id:
            data.message_id ||
            "assistant_msg_" + Math.random().toString(36).substring(2, 11),
          sender: "assistant",
          content: data.delta,
          createdAt: Date.parse(env.timestamp),
        });
      }
      break;
    }

    case "assistant_message_completed": {
      // Message is complete — no extra action needed, just update status if needed
      break;
    }

    case "reasoning_delta": {
      // Ignore reasoning for now (could add reasoning panel later)
      break;
    }

    case "permission_request": {
      const payload = env.data as unknown as import("../api/types").PermissionRequestPayload;
      store.enqueuePermission(sessionId, payload);
      store.appendRecentAction(sessionId, {
        id: `perm-${payload.request_id}`,
        kind: "permission",
        label: "Permission requested",
        detail: payload.summary,
        timestamp: env.timestamp,
      });
      break;
    }

    case "permission_granted":
    case "permission_denied": {
      const data = env.data as { request_id?: string };
      if (!data.request_id) break;
      store.resolvePermissionLocal(sessionId, data.request_id);
      break;
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
      if (!data.step_id) break;

      const statusMap: Record<string, string> = {
        step_started: "running",
        step_completed: "success",
        step_failed: "failed",
        step_cancelled: "cancelled",
      };

      store.updateStepStatus(sessionId, data.step_id, statusMap[env.event]);

      const labelMap: Record<string, string> = {
        step_started: "Started task",
        step_completed: "Completed task",
        step_failed: "Failed task",
        step_cancelled: "Cancelled task",
      };

      const session = store.sessionsById[sessionId];
      const step = session?.workflow?.steps.find((s: any) => s.id === data.step_id);
      store.appendRecentAction(sessionId, {
        id: `step-${data.step_id}-${env.event}-${env.timestamp}`,
        kind: "step",
        label: labelMap[env.event],
        detail: step?.name ?? data.step_name ?? data.step_id,
        timestamp: env.timestamp,
      });
      break;
    }

    case "tool_call_started": {
      const data = env.data as { tool_name: string; input?: { arguments?: string }; call_id?: string };
      const cmdStr = data.input?.arguments ? ` ${data.input.arguments}` : "";
      const termLine = `> ${data.tool_name}${cmdStr}`;

      const toolCallId = data.call_id || `tc_${data.tool_name}_${Date.now()}`;
      const toolCall: ToolCallLog = {
        id: toolCallId,
        toolName: data.tool_name,
        status: "pending",
        durationMs: 0,
        at: Date.parse(env.timestamp),
      };

      store.appendToolCall(sessionId, toolCall);
      store.appendTerminalLine(sessionId, termLine);
      break;
    }

    case "tool_call_progress": {
      const data = env.data as { progress: string };
      if (!data.progress) break;
      const progressLines = data.progress
        .split("\n")
        .filter((line) => line.trim() !== "");
      store.appendTerminalLines(sessionId, progressLines);
      break;
    }

    case "tool_call_finished": {
      const data = env.data as {
        tool_name: string;
        status: "success" | "failed";
        duration_ms: number;
        call_id?: string;
        error?: { message?: string };
        output?: {
          resolved_point?: { x: number; y: number; confidence: number; method: string };
        };
      };

      const session = store.sessionsById[sessionId];
      // Find pending tool call matching this tool_name
      const existingCall = session?.toolCalls.find(
        (tc) =>
          tc.toolName === data.tool_name &&
          tc.status === "pending" &&
          (!data.call_id || tc.id === data.call_id),
      );

      const updatedCall: ToolCallLog = {
        id: existingCall?.id || data.call_id || `tc_${data.tool_name}_${Date.now()}`,
        toolName: data.tool_name,
        status: data.status,
        durationMs: data.duration_ms,
        at: existingCall?.at ?? Date.parse(env.timestamp),
        errorMessage: data.error?.message,
        resolvedPoint: data.output?.resolved_point,
      };

      store.upsertToolCall(sessionId, updatedCall);

      const statusLine = `[Finished] Status: ${data.status} | Duration: ${data.duration_ms}ms`;
      const extraLines: string[] = [];
      if (data.status === "failed" && data.error?.message) {
        extraLines.push(`[Error] ${data.error.message}`);
      }
      store.appendTerminalLines(sessionId, [statusLine, ...extraLines]);

      store.appendRecentAction(sessionId, {
        id: `tool-${data.tool_name}-${env.timestamp}`,
        kind: "tool_call",
        label:
          data.status === "failed"
            ? `Tool failed: ${data.tool_name}`
            : `Ran ${data.tool_name}`,
        detail: data.error?.message,
        timestamp: env.timestamp,
      });
      break;
    }

    case "session_finished": {
      store.updateStatus(sessionId, "completed");
      break;
    }

    case "user_stopped": {
      store.updateStatus(sessionId, "cancelled");
      break;
    }

    case "user_paused": {
      store.updateStatus(sessionId, "paused");
      break;
    }

    case "user_resumed": {
      store.updateStatus(sessionId, "running");
      break;
    }

    case "browser_session_started": {
      const data = env.data as { url?: string; title?: string; controlled_by?: "agent" | "user" };
      store.updateBrowserState(sessionId, {
        url: data.url,
        title: data.title,
        controlledBy: data.controlled_by,
      });
      break;
    }

    case "browser_navigation_started": {
      const data = env.data as { url?: string };
      store.updateBrowserState(sessionId, { loading: true, url: data.url });
      break;
    }

    case "browser_navigation_completed": {
      const data = env.data as {
        url?: string;
        title?: string;
        controlled_by?: "agent" | "user";
      };
      store.updateBrowserState(sessionId, {
        loading: false,
        url: data.url,
        title: data.title,
        controlledBy: data.controlled_by,
      });
      break;
    }

    case "browser_screenshot_updated": {
      const data = env.data as {
        screenshot_url?: string;
        controlled_by?: "agent" | "user";
      };
      store.updateBrowserState(sessionId, {
        screenshotUrl: data.screenshot_url,
        controlledBy: data.controlled_by,
      });
      break;
    }

    case "browser_action_started": {
      store.updateBrowserState(sessionId, { loading: true });
      break;
    }

    case "browser_action_completed": {
      const data = env.data as { url?: string; title?: string };
      store.updateBrowserState(sessionId, {
        loading: false,
        url: data.url,
        title: data.title,
      });
      break;
    }

    case "error": {
      const data = env.data as { context?: string; error?: { message?: string } };
      store.appendRecentAction(sessionId, {
        id: `err-${env.timestamp}`,
        kind: "error",
        label: "Error",
        detail: data.error?.message || data.context,
        timestamp: env.timestamp,
      });
      break;
    }

    default:
      // Unknown events are silently ignored
      break;
  }
}
