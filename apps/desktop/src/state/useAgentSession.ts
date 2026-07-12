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
