/**
 * useAgentSession.ts — Facade hook for consuming a single agent session.
 *
 * IMPORTANT: This hook is a READ-ONLY view + action dispatcher.
 * It does NOT own any domain state. All state lives in agentSessionStore.
 *
 * Changes from old implementation:
 *  - No useReducer (state is global Zustand store)
 *  - No wsRef (socket is managed by agentSocketManager singleton)
 *  - Cleanup does NOT reset session or close WebSocket
 *  - Component unmount does NOT affect session lifecycle
 */

import { useEffect, useCallback } from "react";
import { useAgentSessionStore } from "./agentSessionStore";
import type { AgentSessionEntity, SessionStatus } from "./agentSessionStore";
import { agentSocketManager } from "../services/agentSocketManager";
import { decidePermission } from "../api/client";

/**
 * Use a session by its sessionId.
 * Connects the WebSocket on first call (idempotent).
 * Unsubscribes on unmount — does NOT close the socket.
 */
export function useAgentSession(sessionId: string | null) {
  const store = useAgentSessionStore;

  // Narrow selector — only subscribe to this session's data
  const session = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId] ?? null : null),
  );

  const activeSessionId = useAgentSessionStore((state) => state.activeSessionId);
  const draft = useAgentSessionStore(
    (state) => (sessionId ? state.draftBySessionId[sessionId] ?? "" : ""),
  );

  // Connect socket when sessionId changes (idempotent — no duplicate sockets)
  useEffect(() => {
    if (!sessionId) return;

    // Hydrate session state from backend if not yet loaded
    const currentSession = store.getState().sessionsById[sessionId];
    if (!currentSession?.isHydrated && !currentSession?.isLoading) {
      store.getState().hydrateSession(sessionId);
    }

    // Connect WebSocket (deduplication enforced in agentSocketManager)
    agentSocketManager.connect(sessionId).catch((err) => {
      console.error(`[useAgentSession] Failed to connect WS for session ${sessionId}:`, err);
    });

    // NOTE: cleanup does NOT disconnect the socket.
    // The socket belongs to agentSocketManager, not this component.
    return () => {
      // Only cleanup component-level subscriptions here
      // agentSocketManager handles socket lifecycle independently
    };
  }, [sessionId]);

  // ---- Actions ----

  const handleSend = useCallback(
    async (content: string) => {
      if (!sessionId || !content.trim()) return;
      await store.getState().sendMessage(sessionId, content);
    },
    [sessionId],
  );

  const resolvePermission = useCallback(
    async (requestId: string, decision: "granted" | "denied") => {
      if (!sessionId) return;
      try {
        await decidePermission(requestId, decision);
        store.getState().resolvePermissionLocal(sessionId, requestId);
      } catch (err) {
        console.error("[useAgentSession] resolvePermission failed:", err);
      }
    },
    [sessionId],
  );

  const stopRun = useCallback(async () => {
    if (!sessionId) return;
    await store.getState().cancelSession(sessionId);
  }, [sessionId]);

  const reconnect = useCallback(async () => {
    if (!sessionId) return;
    await agentSocketManager.reconnect(sessionId);
  }, [sessionId]);

  const selectSession = useCallback(
    (newSessionId: string) => {
      store.getState().setActiveSession(newSessionId);
    },
    [],
  );

  const setDraft = useCallback(
    (value: string) => {
      if (!sessionId) return;
      store.getState().setDraft(sessionId, value);
    },
    [sessionId],
  );

  const clearTerminal = useCallback(() => {
    if (!sessionId) return;
    store.getState().clearTerminal(sessionId);
  }, [sessionId]);

  const updateBrowserState = useCallback(
    (browserUpdate: Partial<AgentSessionEntity["browser"]>) => {
      if (!sessionId) return;
      store.getState().updateBrowserState(sessionId, browserUpdate);
    },
    [sessionId],
  );

  return {
    session,
    draft,
    activeSessionId,
    handleSend,
    resolvePermission,
    stopRun,
    reconnect,
    selectSession,
    setDraft,
    clearTerminal,
    updateBrowserState,
    // Convenience derived state
    messages: session?.messages ?? [],
    toolCalls: session?.toolCalls ?? [],
    workflow: session?.workflow ?? null,
    permissionQueue: session?.permissionQueue ?? [],
    recentActions: session?.recentActions ?? [],
    terminalLines: session?.terminalLines ?? [],
    browserState: session?.browser ?? null,
    sessionId,
    status: session?.status ?? ("idle" as SessionStatus),
    connectionStatus: session?.connectionStatus ?? "disconnected",
    isHydrated: session?.isHydrated ?? false,
    isLoading: session?.isLoading ?? false,
    error: session?.error ?? null,
  };
}

/**
 * Backward-compatible hook for components that pass agentId instead of sessionId.
 * Creates a new session for the agent if none exists.
 *
 * @deprecated Prefer useAgentSession(sessionId) directly.
 */
export function useAgentSessionByAgentId(agentId: string) {
  const store = useAgentSessionStore;

  // Find the most recent session for this agent
  const sessionId = useAgentSessionStore((state) => {
    const sessions = state.sessionOrder
      .map((id) => state.sessionsById[id])
      .filter((s) => s?.agentId === agentId);
    return sessions[sessions.length - 1]?.id ?? null;
  });

  const session = useAgentSession(sessionId);

  // Auto-create session for agent if none exists
  useEffect(() => {
    if (!agentId) return;

    const existingSessionId = store.getState().sessionOrder.find((id) => {
      const s = store.getState().sessionsById[id];
      return s?.agentId === agentId;
    });

    if (!existingSessionId) {
      // Create session for this agent
      store
        .getState()
        .createSession(agentId)
        .catch((err) => {
          console.error(`[useAgentSessionByAgentId] Failed to create session for agent ${agentId}:`, err);
        });
    } else {
      // Set as active if not already
      const currentActive = store.getState().activeSessionId;
      if (!currentActive) {
        store.getState().setActiveSession(existingSessionId);
      }
    }
  }, [agentId]);

  return {
    ...session,
    agentId,
  };
}
