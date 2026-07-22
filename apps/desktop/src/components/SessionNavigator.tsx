/**
 * SessionNavigator.tsx — Multi-session sidebar panel.
 *
 * Shows list of open sessions with:
 *  - Status badge (running / error / completed / idle)
 *  - Agent name
 *  - Running indicator (animated)
 *  - Unread event indicator (for background sessions)
 *  - New session button
 *  - Close (archive) / Delete actions
 */

import { useAgentSessionStore } from "../state/agentSessionStore";
import type { AgentSessionEntity, SessionStatus } from "../state/agentSessionStore";

interface SessionNavigatorProps {
  onSelectAgent?: (agentId: string) => void;
  selectedAgentId?: string;
  onDelete?: (sessionId: string) => void;
}

// Status color map
const STATUS_COLORS: Record<SessionStatus, string> = {
  idle: "#64748b",
  creating: "#94a3b8",
  connecting: "#60a5fa",
  running: "#34d399",
  waiting_input: "#fbbf24",
  paused: "#a78bfa",
  cancelling: "#f97316",
  cancelled: "#94a3b8",
  completed: "#10b981",
  error: "#f87171",
  disconnected: "#64748b",
  interrupted: "#f97316",
  reconnecting: "#60a5fa",
};

const STATUS_LABELS: Record<SessionStatus, string> = {
  idle: "Idle",
  creating: "Creating…",
  connecting: "Connecting…",
  running: "Running",
  waiting_input: "Waiting for input",
  paused: "Paused",
  cancelling: "Cancelling…",
  cancelled: "Cancelled",
  completed: "Completed",
  error: "Error",
  disconnected: "Disconnected",
  interrupted: "Interrupted",
  reconnecting: "Reconnecting…",
};

function RunningPulse() {
  return (
    <span
      style={{
        display: "inline-block",
        width: "7px",
        height: "7px",
        borderRadius: "50%",
        background: "#34d399",
        boxShadow: "0 0 6px #34d399",
        animation: "pulse-running 1.5s ease-in-out infinite",
        flexShrink: 0,
      }}
    />
  );
}

function StatusDot({ status }: { status: SessionStatus }) {
  const color = STATUS_COLORS[status] ?? "#64748b";
  const isRunning = status === "running" || status === "connecting" || status === "reconnecting" as any;

  if (isRunning) return <RunningPulse />;

  return (
    <span
      style={{
        display: "inline-block",
        width: "7px",
        height: "7px",
        borderRadius: "50%",
        background: color,
        flexShrink: 0,
      }}
    />
  );
}

function SessionItem({
  session,
  isActive,
  onClick,
  onClose,
}: {
  session: AgentSessionEntity;
  isActive: boolean;
  onClick: () => void;
  onClose: () => void;
}) {
  const agentLabel = session.agentId ?? "Agent";
  const title = session.title ?? agentLabel;
  const msgCount = session.messages.length;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "8px 10px",
        borderRadius: "8px",
        cursor: "pointer",
        background: isActive ? "rgba(99,102,241,0.12)" : "transparent",
        border: isActive ? "1px solid rgba(99,102,241,0.25)" : "1px solid transparent",
        transition: "all 0.15s ease",
        position: "relative",
      }}
      onMouseEnter={(e) => {
        if (!isActive) (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
      }}
      onMouseLeave={(e) => {
        if (!isActive) (e.currentTarget as HTMLElement).style.background = "transparent";
      }}
    >
      <StatusDot status={session.status} />

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "0.78rem",
            fontWeight: 500,
            color: isActive ? "#c7d2fe" : "#e2e8f0",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: "0.65rem",
            color: STATUS_COLORS[session.status],
            marginTop: "1px",
          }}
        >
          {STATUS_LABELS[session.status]} · {msgCount} msg{msgCount !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Action buttons (visible on hover) */}
      <div
        className="session-item-actions"
        style={{
          display: "flex",
          gap: "4px",
          opacity: 0,
          transition: "opacity 0.1s",
        }}
        onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.opacity = "1"}
      >
        {/* Close (archive) */}
        <button
          onClick={(e) => { e.stopPropagation(); onClose(); }}
          title="Close session (session continues running)"
          style={{
            background: "rgba(255,255,255,0.08)",
            border: "none",
            borderRadius: "4px",
            color: "#94a3b8",
            cursor: "pointer",
            padding: "2px 5px",
            fontSize: "0.65rem",
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}

export function SessionNavigator({ onSelectAgent, selectedAgentId }: SessionNavigatorProps) {
  const sessionOrder = useAgentSessionStore((state: any) => state.sessionOrder);
  const sessionsById = useAgentSessionStore((state: any) => state.sessionsById);
  const activeSessionId = useAgentSessionStore((state: any) => state.activeSessionId);
  const setActiveSession = useAgentSessionStore((state: any) => state.setActiveSession);
  const removeSessionLocal = useAgentSessionStore((state: any) => state.removeSessionLocal);
  const createSession = useAgentSessionStore((state: any) => state.createSession);

  const runningSessions = sessionOrder.filter(
    (id: string) => sessionsById[id]?.status === "running" || sessionsById[id]?.connectionStatus === "connected",
  ).length;

  const handleNewSession = async () => {
    if (!selectedAgentId) return;
    try {
      await createSession(selectedAgentId);
    } catch (err) {
      console.error("[SessionNavigator] Failed to create session:", err);
    }
  };

  const handleSelectSession = (session: AgentSessionEntity) => {
    setActiveSession(session.id);
    if (onSelectAgent && session.agentId) {
      onSelectAgent(session.agentId);
    }
  };

  const handleCloseSession = (sessionId: string) => {
    // Close UI — execution continues in background
    // Socket remains open if session is running
    removeSessionLocal(sessionId);
  };

  if (sessionOrder.length === 0) {
    return (
      <div style={{ padding: "8px" }}>
        <div
          style={{
            fontSize: "0.7rem",
            color: "#475569",
            textAlign: "center",
            padding: "12px 0",
          }}
        >
          No sessions open
        </div>
        <button
          onClick={handleNewSession}
          disabled={!selectedAgentId}
          style={{
            width: "100%",
            background: "rgba(99,102,241,0.1)",
            border: "1px dashed rgba(99,102,241,0.3)",
            borderRadius: "6px",
            color: "#818cf8",
            cursor: selectedAgentId ? "pointer" : "not-allowed",
            padding: "6px",
            fontSize: "0.72rem",
          }}
        >
          + New Session
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "2px", padding: "4px 0" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "4px 10px 6px",
        }}
      >
        <span
          style={{
            fontSize: "0.65rem",
            fontWeight: 600,
            color: "#475569",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          Sessions
        </span>
        {runningSessions.length > 0 && (
          <span
            style={{
              fontSize: "0.6rem",
              color: "#34d399",
              background: "rgba(52,211,153,0.1)",
              border: "1px solid rgba(52,211,153,0.2)",
              borderRadius: "10px",
              padding: "1px 6px",
            }}
          >
            {runningSessions.length} running
          </span>
        )}
      </div>

      {/* Session list */}
      {sessionOrder.map((id: string) => {
        const session = sessionsById[id];
        if (!session) return null;
        return (
          <SessionItem
            key={id}
            session={session}
            isActive={id === activeSessionId}
            onClick={() => handleSelectSession(session)}
            onClose={() => handleCloseSession(id)}
          />
        );
      })}

      {/* New session button */}
      <div style={{ padding: "4px 8px 0" }}>
        <button
          onClick={handleNewSession}
          disabled={!selectedAgentId}
          style={{
            width: "100%",
            background: "transparent",
            border: "1px dashed rgba(99,102,241,0.25)",
            borderRadius: "6px",
            color: "#4f46e5",
            cursor: selectedAgentId ? "pointer" : "not-allowed",
            padding: "5px",
            fontSize: "0.68rem",
            transition: "all 0.15s",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.background = "rgba(99,102,241,0.08)";
            (e.currentTarget as HTMLElement).style.color = "#818cf8";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.background = "transparent";
            (e.currentTarget as HTMLElement).style.color = "#4f46e5";
          }}
        >
          + New Session
        </button>
      </div>
    </div>
  );
}
