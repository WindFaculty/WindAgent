/** useAgentSession: self-managed session lifecycle + websocket -> store.
 *
 * Owns session bootstrap, WS subscription, message send, permission
 * decisions, and stop. AgentWorkspace consumes the store, no props.
 */
import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  connectWs,
  createSession,
  sendMessage,
  decidePermission,
  controlSession,
  fetchBrowserState,
} from "../api/client";
import { reducer, initialState } from "./sessionStore";

export function useAgentSession(agentId: string) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<ReturnType<typeof connectWs> | null>(null);
  const agentRef = useRef(agentId);
  agentRef.current = agentId;

  const connect = useCallback(async (sessionId: string) => {
    wsRef.current?.close();
    wsRef.current = connectWs(sessionId, {
      onEvent: (env) => dispatch({ type: "processEvent", env }),
      onClose: () => {},
    });

    // Hydrate browser state
    fetchBrowserState(sessionId)
      .then((br) => {
        dispatch({
          type: "updateBrowserState",
          browser: {
            url: br.url,
            title: br.title,
            loading: br.loading,
            controlledBy: br.controlled_by,
            screenshotUrl: `/api/v1/sessions/${sessionId}/browser/screenshot`,
          },
        });
      })
      .catch(console.error);
  }, []);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (state.sessionId) return state.sessionId;
    const resp = await createSession(agentRef.current);
    dispatch({ type: "setSessionId", sessionId: resp.session_id });
    await connect(resp.session_id);
    return resp.session_id;
  }, [state.sessionId, connect]);

  const handleSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;
      const sessionId = await ensureSession();
      dispatch({
        type: "addMessage",
        message: {
          id: "user_" + Date.now(),
          sender: "user",
          content,
          createdAt: Date.now(),
        },
      });
      await sendMessage(sessionId, content);
    },
    [ensureSession],
  );

  const resolvePermission = useCallback(
    async (requestId: string, decision: "granted" | "denied") => {
      await decidePermission(requestId, decision);
      dispatch({ type: "resolvePermission", requestId });
    },
    [],
  );

  const stopRun = useCallback(async () => {
    if (state.sessionId) await controlSession(state.sessionId, "stop");
  }, [state.sessionId]);

  // Reset state and close WebSocket when switching agent/runtime
  useEffect(() => {
    dispatch({ type: "reset" });
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [agentId]);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return {
    state,
    dispatch,
    handleSend,
    resolvePermission,
    stopRun,
  };
}
