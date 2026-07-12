import type { PermissionRequestPayload } from "../../../api/types";

interface Props {
  permissionQueue: PermissionRequestPayload[];
  resolvePermission: (requestId: string, decision: "granted" | "denied") => Promise<void>;
}

export function PermissionDialog({ permissionQueue, resolvePermission }: Props) {
  if (!permissionQueue || permissionQueue.length === 0) return null;

  const current = permissionQueue[0];
  const command = (current.params as Record<string, unknown>)?.command;

  return (
    <div
      style={{
        position: "fixed",
        bottom: "80px",
        right: "24px",
        width: "360px",
        backgroundColor: "rgba(30, 41, 59, 0.95)",
        backdropFilter: "blur(16px)",
        border: "1px solid rgba(255, 255, 255, 0.15)",
        borderRadius: "12px",
        padding: "16px",
        boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 10px 10px -5px rgba(0, 0, 0, 0.6)",
        zIndex: 1000,
        animation: "slideUp 0.3s ease",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
        <svg width="20" height="20" fill="none" stroke="#f59e0b" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span style={{ fontWeight: "600", color: "var(--text-main)", fontSize: "0.9rem" }}>Permission Required</span>
      </div>
      <div style={{ fontSize: "0.8rem", color: "var(--text-dim)", marginBottom: "12px", display: "flex", flexDirection: "column", gap: "6px" }}>
        <div>The agent is requesting permission to execute:</div>
        <div style={{ color: "var(--text-main)", fontWeight: "bold", fontSize: "0.85rem" }}>{current.tool_name}</div>

        {command ? (
          <pre
            style={{
              backgroundColor: "rgba(0,0,0,0.4)",
              padding: "8px",
              borderRadius: "6px",
              fontFamily: "monospace",
              fontSize: "0.72rem",
              color: "#34d399",
              overflowX: "auto",
              whiteSpace: "pre-wrap",
              maxHeight: "100px",
              border: "1px solid rgba(255,255,255,0.05)",
              margin: "4px 0",
            }}
          >
            {String(command)}
          </pre>
        ) : null}

        <div style={{ marginTop: "4px", fontSize: "0.74rem" }}>
          Risk Level: <span style={{ color: current.risk_level === "high" ? "#ef4444" : "#f59e0b", fontWeight: "600" }}>{String(current.risk_level).toUpperCase()}</span>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
        <button
          className="role-btn"
          style={{ padding: "6px 12px", fontSize: "0.75rem", height: "auto", backgroundColor: "rgba(255,255,255,0.05)", color: "var(--text-main)" }}
          onClick={() => resolvePermission(current.request_id, "denied")}
        >
          Deny
        </button>
        <button
          className="chat-send-btn"
          style={{ padding: "6px 16px", fontSize: "0.75rem", height: "auto", background: "linear-gradient(135deg, #f59e0b, #d97706)", border: "none", color: "#fff" }}
          onClick={() => resolvePermission(current.request_id, "granted")}
        >
          Approve
        </button>
      </div>
    </div>
  );
}
