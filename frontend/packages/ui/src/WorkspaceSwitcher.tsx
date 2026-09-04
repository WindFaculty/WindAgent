import { useState } from "react";
import { Badge } from "./Badge.tsx";

export interface WorkspaceOption {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended" | "archived";
}

export function WorkspaceSwitcher({
  workspaces,
  activeWorkspaceId,
  onSelect,
  onCreateNew,
}: {
  workspaces: WorkspaceOption[];
  activeWorkspaceId?: string;
  onSelect: (id: string) => void;
  onCreateNew?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const current = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          padding: "6px 12px",
          background: "var(--windagent-color-surface)",
          border: "1px solid var(--windagent-border-default)",
          borderRadius: "var(--windagent-radius-md)",
          color: "var(--windagent-color-text)",
          cursor: "pointer",
          fontSize: "0.85rem",
          fontWeight: 500,
        }}
      >
        <span style={{ color: "var(--windagent-color-accent)" }}>📁</span>
        <span>{current ? current.name : "Select Workspace"}</span>
        <span style={{ fontSize: "0.7rem", color: "var(--windagent-color-text-dim)" }}>▼</span>
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            marginTop: "6px",
            width: "220px",
            background: "var(--windagent-color-surface)",
            border: "1px solid var(--windagent-border-strong)",
            borderRadius: "var(--windagent-radius-md)",
            boxShadow: "var(--windagent-shadow-lg)",
            zIndex: 100,
            padding: "4px",
          }}
        >
          <div style={{ maxHeight: "180px", overflowY: "auto" }}>
            {workspaces.map((w) => (
              <button
                key={w.id}
                type="button"
                onClick={() => {
                  onSelect(w.id);
                  setOpen(false);
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "8px 10px",
                  borderRadius: "var(--windagent-radius-sm)",
                  border: "none",
                  background: w.id === activeWorkspaceId ? "var(--windagent-color-surface-hover)" : "transparent",
                  color: "var(--windagent-color-text)",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span>{w.name}</span>
                {w.id === activeWorkspaceId && <Badge level="info">Active</Badge>}
              </button>
            ))}
          </div>

          {onCreateNew && (
            <div style={{ borderTop: "1px solid var(--windagent-border-subtle)", marginTop: "4px", paddingTop: "4px" }}>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onCreateNew();
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  width: "100%",
                  padding: "6px 10px",
                  borderRadius: "var(--windagent-radius-sm)",
                  border: "none",
                  background: "transparent",
                  color: "var(--windagent-color-accent)",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                  fontWeight: 500,
                }}
              >
                <span>+ New Workspace</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
