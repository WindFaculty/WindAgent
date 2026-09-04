import React from "react";
import { Card } from "./Card.tsx";

export interface MetricCardProps {
  label: string;
  value: string | number;
  subtext?: string;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  icon?: React.ReactNode;
  accentColor?: string;
}

export function MetricCard({
  label,
  value,
  subtext,
  trend,
  icon,
  accentColor = "var(--windagent-color-accent)",
}: MetricCardProps) {
  return (
    <Card variant="glass" padding="md" style={{ position: "relative", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "4px",
          height: "100%",
          backgroundColor: accentColor,
        }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <span style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)", fontWeight: 500 }}>
            {label}
          </span>
          <div
            style={{
              fontSize: "1.75rem",
              fontWeight: 700,
              color: "var(--windagent-color-text)",
              margin: "6px 0 4px 0",
              fontFamily: "var(--windagent-font-mono)",
            }}
          >
            {value}
          </div>
          {(subtext || trend) && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "0.8rem" }}>
              {trend && (
                <span
                  style={{
                    color: trend.isPositive ? "var(--windagent-color-success)" : "var(--windagent-color-danger)",
                    fontWeight: 600,
                  }}
                >
                  {trend.isPositive ? "↑" : "↓"} {trend.value}
                </span>
              )}
              {subtext && <span style={{ color: "var(--windagent-color-text-dim)" }}>{subtext}</span>}
            </div>
          )}
        </div>
        {icon && (
          <div
            style={{
              padding: "8px",
              borderRadius: "var(--windagent-radius-md)",
              background: "var(--windagent-color-surface-hover)",
              color: accentColor,
            }}
          >
            {icon}
          </div>
        )}
      </div>
    </Card>
  );
}
