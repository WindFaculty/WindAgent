import type { ReactNode } from "react";

export type StatusLevel = "ok" | "warn" | "error" | "idle";

const LEVEL_COLORS: Record<StatusLevel, string> = {
  ok: "var(--windagent-color-success)",
  warn: "var(--windagent-color-warning)",
  error: "var(--windagent-color-danger)",
  idle: "var(--windagent-color-text-muted)",
};

export interface StatusPillProps {
  level: StatusLevel;
  label: string;
  children?: ReactNode;
}

/** Smallest shared UI primitive; proves the React/TS/Vitest pipeline works. */
export function StatusPill({ level, label, children }: StatusPillProps) {
  return (
    <span
      data-testid="status-pill"
      data-level={level}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--windagent-space-1)",
        padding: "2px var(--windagent-space-2)",
        borderRadius: "var(--windagent-radius-md)",
        background: "var(--windagent-color-surface)",
        color: LEVEL_COLORS[level],
        fontFamily: "var(--windagent-font-sans)",
      }}
    >
      {label}
      {children}
    </span>
  );
}
