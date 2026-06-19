import { useCallback, useEffect, useReducer, useState } from "react";

import {
  controlSession,
  createSession,
  decidePermission,
  fetchModelsHealth,
  fetchRunner,
  fetchWorkflow,
  retryStep,
  sendMessage,
} from "./api/client";
import { useSessionEvents } from "./hooks/useSessionEvents";
import {
  initialState,
  reducer,
  type RunnerSnapshot,
} from "./state/sessionStore";

import { ChatPanel } from "./components/ChatPanel";
import { ControlBar } from "./components/ControlBar";
import { PermissionDialog } from "./components/PermissionDialog";
import { StatusBar } from "./components/StatusBar";
import { WorkflowPanel } from "./components/WorkflowPanel";
import type { RunnerState } from "./api/types";

const POLL_RUNNER_MS = 1000;
const POLL_MODELS_MS = 5000;

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // -------- Periodic polling --------

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const mh = await fetchModelsHealth();
        if (!cancelled) dispatch({ type: "setModelsOnline", online: mh.online });
      } catch {
        if (!cancelled) dispatch({ type: "setModelsOnline", online: false });
      }
    };
    void tick();
    const id = window.setInterval(tick, POLL_MODELS_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!state.sessionId) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const [wf, rn] = await Promise.all([
          fetchWorkflow(state.sessionId!),
          fetchRunner(state.sessionId!),
        ]);
        if (cancelled) return;
        dispatch({ type: "setWorkflow", workflow: wf });
        dispatch({
          type: "setRunner",
          snapshot: runnerSnapshotFrom(rn.runner),
        });
      } catch (err) {
        if (!cancelled) {
          setError(`poll failed: ${(err as Error).message}`);
        }
      }
    };
    void tick();
    const id = window.setInterval(tick, POLL_RUNNER_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [state.sessionId]);

  // -------- WebSocket: dispatch into reducer --------

  useSessionEvents(state.sessionId, {
    onEvent: (env) => dispatch({ type: "processEvent", env }),
    onClose: () => {
      /* reconnect handled inside the hook */
    },
  });

  // -------- Actions --------

  const newSession = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await createSession();
      dispatch({ type: "setSessionId", sessionId: resp.session_id });
      dispatch({ type: "setRunner", snapshot: { kind: "idle" } });
    } catch (err) {
      setError(`create session failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }, []);

  const send = useCallback(
    async (content: string) => {
      if (!state.sessionId) return;
      setBusy(true);
      setError(null);
      try {
        await sendMessage(state.sessionId, content);
      } catch (err) {
        setError(`send failed: ${(err as Error).message}`);
      } finally {
        setBusy(false);
      }
    },
    [state.sessionId],
  );

  const pause = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      await controlSession(state.sessionId, "pause");
    } catch (err) {
      setError(`pause failed: ${(err as Error).message}`);
    }
  }, [state.sessionId]);

  const resume = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      await controlSession(state.sessionId, "resume");
    } catch (err) {
      setError(`resume failed: ${(err as Error).message}`);
    }
  }, [state.sessionId]);

  const stop = useCallback(async () => {
    if (!state.sessionId) return;
    try {
      await controlSession(state.sessionId, "stop");
    } catch (err) {
      setError(`stop failed: ${(err as Error).message}`);
    }
  }, [state.sessionId]);

  const retry = useCallback(async () => {
    if (!state.sessionId) return;
    if (state.runner.kind !== "running") return;
    const stepId = state.runner.state.last_failed_step_id;
    if (!stepId) return;
    try {
      await retryStep(stepId);
    } catch (err) {
      setError(`retry failed: ${(err as Error).message}`);
    }
  }, [state.sessionId, state.runner]);

  const decide = useCallback(
    async (requestId: string, decision: "granted" | "denied") => {
      try {
        await decidePermission(requestId, decision);
        dispatch({ type: "resolvePermission", requestId });
      } catch (err) {
        setError(`permission decision failed: ${(err as Error).message}`);
      }
    },
    [],
  );

  // -------- Render --------

  const activePermission = state.permissionQueue[0] ?? null;

  return (
    <div className="app">
      <StatusBar
        modelsOnline={state.modelsOnline}
        hasSession={state.sessionId !== null}
        error={error}
      />
      <main className="main-grid">
        <ChatPanel
          messages={state.messages}
          toolCalls={state.toolCalls}
          disabled={busy || !state.sessionId}
          onSend={state.sessionId ? send : newSession}
        />
        <div className="right-column">
          <WorkflowPanel workflow={state.workflow} />
          <ControlBar
            runner={state.runner}
            hasSession={state.sessionId !== null}
            busy={busy}
            onPause={pause}
            onResume={resume}
            onStop={stop}
            onRetry={retry}
          />
        </div>
      </main>
      {!state.sessionId && (
        <div className="empty-state">
          <button className="btn-primary" onClick={newSession} disabled={busy}>
            {busy ? "Đang tạo..." : "New session"}
          </button>
        </div>
      )}
      {activePermission && (
        <PermissionDialog request={activePermission} onDecide={decide} />
      )}
    </div>
  );
}

function runnerSnapshotFrom(state: RunnerState | null): RunnerSnapshot {
  if (!state) return { kind: "idle" };
  return { kind: "running", state };
}