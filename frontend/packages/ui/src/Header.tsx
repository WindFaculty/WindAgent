import React from "react";
import { Badge } from "./Badge.tsx";

export interface HeaderProps {
  title: string;
  subtitle?: string;
  workspaceSlot?: React.ReactNode;
  actions?: React.ReactNode;
  apiHealthy?: boolean;
}

export function Header({
  title,
  subtitle,
  workspaceSlot,
  actions,
  apiHealthy = true,
}: HeaderProps) {
  return (
    <header
      style={{
        height: "64px",
        padding: "0 var(--windagent-space-6)",
        background: "var(--windagent-color-bg-subtle)",
        borderBottom: "1px solid var(--windagent-border-subtle)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "var(--windagent-space-4)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--windagent-space-4)" }}>
        {workspaceSlot}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <h1 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--windagent-color-text)" }}>
              {title}
            </h1>
            <Badge level={apiHealthy ? "success" : "danger"} dot>
              {apiHealthy ? "API v4 Connected" : "API Offline"}
            </Badge>
          </div>
          {subtitle && (
            <p style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)", margin: 0 }}>
              {subtitle}
            </p>
          )}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "var(--windagent-space-3)" }}>
        {actions}
        <div
          style={{
            width: "32px",
            height: "32px",
            borderRadius: "50%",
            background: "var(--windagent-color-surface-hover)",
            border: "1px solid var(--windagent-border-default)",
            display: "grid",
            placeItems: "center",
            fontSize: "0.85rem",
            color: "var(--windagent-color-accent)",
            fontWeight: 600,
          }}
        >
          AD
        </div>
      </div>
    </header>
  );
}
