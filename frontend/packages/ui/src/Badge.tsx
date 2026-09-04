import React from "react";

export type BadgeLevel = "neutral" | "info" | "success" | "warning" | "danger" | "purple";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  level?: BadgeLevel;
  dot?: boolean;
}

export function Badge({
  level = "neutral",
  dot = false,
  children,
  style,
  className = "",
  ...props
}: BadgeProps) {
  const levelStyles: Record<BadgeLevel, { bg: string; text: string; border: string; dotColor: string }> = {
    neutral: {
      bg: "var(--windagent-color-surface-hover)",
      text: "var(--windagent-color-text-secondary)",
      border: "var(--windagent-border-subtle)",
      dotColor: "var(--windagent-color-text-muted)",
    },
    info: {
      bg: "var(--windagent-color-info-bg)",
      text: "var(--windagent-color-info)",
      border: "rgba(88, 166, 255, 0.25)",
      dotColor: "var(--windagent-color-info)",
    },
    success: {
      bg: "var(--windagent-color-success-bg)",
      text: "var(--windagent-color-success)",
      border: "rgba(63, 185, 80, 0.25)",
      dotColor: "var(--windagent-color-success)",
    },
    warning: {
      bg: "var(--windagent-color-warning-bg)",
      text: "var(--windagent-color-warning)",
      border: "rgba(210, 153, 34, 0.25)",
      dotColor: "var(--windagent-color-warning)",
    },
    danger: {
      bg: "var(--windagent-color-danger-bg)",
      text: "var(--windagent-color-danger)",
      border: "rgba(248, 81, 73, 0.25)",
      dotColor: "var(--windagent-color-danger)",
    },
    purple: {
      bg: "rgba(121, 40, 202, 0.15)",
      text: "#d2a8ff",
      border: "rgba(121, 40, 202, 0.35)",
      dotColor: "#d2a8ff",
    },
  };

  const current = levelStyles[level];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "2px 8px",
        borderRadius: "var(--windagent-radius-full)",
        fontSize: "0.75rem",
        fontWeight: 500,
        lineHeight: 1.4,
        background: current.bg,
        color: current.text,
        border: `1px solid ${current.border}`,
        ...style,
      }}
      className={`windagent-badge ${className}`}
      {...props}
    >
      {dot && (
        <span
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            backgroundColor: current.dotColor,
          }}
        />
      )}
      {children}
    </span>
  );
}
