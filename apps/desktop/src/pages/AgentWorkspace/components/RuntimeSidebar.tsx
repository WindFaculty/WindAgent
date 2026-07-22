import type { ToolCallLog } from "../../../state/agentSessionStore";
import type { PermissionRequestPayload, RecentAction } from "../../../api/types";

interface Props {
  sessionId: string | null;
  toolCalls: ToolCallLog[];
  permissionQueue: PermissionRequestPayload[];
  recentActions: RecentAction[];
}

export function RuntimeSidebar({
  sessionId,
  toolCalls,
  permissionQueue,
  recentActions,
}: Props) {
  // Derive tools in use: last 4 tool calls, marking the most recent running one active.
  const toolsInUse: { name: string; active: boolean }[] = toolCalls
    .slice(-4)
    .map((c, idx, arr) => ({
      name: c.toolName,
      active: idx === arr.length - 1 && c.status === ("pending" as any),
    }));

  return (
    <aside className="right-sidebar">
      {/* Agent State */}
      <div className="agent-state-box">
        <div className="agent-state-circle">
          <svg>
            <circle className="state-ring-bg" cx="16" cy="16" r="13" />
          </svg>
        </div>
        <div className="agent-state-right">
          <span className="state-title">Agent State</span>
          <span
            className="state-desc"
            style={{
              color: sessionId ? "var(--color-success)" : "var(--text-dim)",
            }}
          >
            {sessionId ? "Connected — live session" : "Idle — no session"}
          </span>
        </div>
      </div>

      {/* Tools in Use */}
      <div className="goal-box">
        <div className="section-label">
          Tools in Use
          <span style={{ fontSize: "0.72rem", background: "#1e293b", padding: "2px 6px", borderRadius: "4px" }}>
            live
          </span>
        </div>
        <div className="tools-in-use-list">
          {toolsInUse.length === 0 ? (
            <div className="tool-in-use-item">
              <div className="tool-in-use-left">
                <span className="tool-use-dot" />
                <span className="tool-use-label">No active tools</span>
              </div>
              <span className="tool-use-state inactive">Idle</span>
            </div>
          ) : (
            toolsInUse.map((t, idx) => (
              <div className="tool-in-use-item" key={idx}>
                <div className="tool-in-use-left">
                  <span className="tool-use-dot" style={t.active ? { background: "#f59e0b", boxShadow: "0 0 8px #f59e0b" } : undefined} />
                  <span className="tool-use-label">{t.name}</span>
                </div>
                <span className={`tool-use-state ${t.active ? "" : "inactive"}`}>
                  {t.active ? "Running" : "Idle"}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Permissions */}
      <div className="goal-box">
        <div className="section-label">Permissions</div>
        <div className="permissions-summary-box">
          {permissionQueue.length === 0 ? (
            <>
              <span>No permissions blocked</span>
              <span className="perms-badge">All Allowed ›</span>
            </>
          ) : (
            <>
              <span style={{ color: "#f59e0b" }}>{permissionQueue.length} awaiting approval</span>
              <span className="perms-badge" style={{ color: "#f59e0b" }}>Review ›</span>
            </>
          )}
        </div>
      </div>

      {/* Recent Actions */}
      <div className="goal-box">
        <div className="section-label">Recent Actions</div>
        <div className="recent-actions-list" style={{ maxHeight: "250px", overflowY: "auto" }}>
          {recentActions.length === 0 ? (
            <div className="action-row">
              <span className="action-dot" />
              <span className="action-text">No activity yet</span>
            </div>
          ) : (
            recentActions.map((a) => (
              <div
                className={`action-row ${a.kind === "step" || a.kind === "tool_call" ? "active" : ""}`}
                key={a.id}
                title={a.detail || undefined}
              >
                <span className="action-time">{a.timestamp ? new Date(Date.parse(a.timestamp)).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}</span>
                <span className={`action-dot ${a.kind === "error" ? "" : a.kind === "step" || a.kind === "tool_call" ? "active" : ""}`} style={a.kind === "error" ? { background: "#ef4444" } : undefined} />
                <span className="action-text">{a.label}{a.detail ? `: ${a.detail}` : ""}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}
