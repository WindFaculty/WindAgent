import React from "react";

export interface TabItem {
  id: string;
  label: string;
  count?: number;
  icon?: React.ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
  style?: React.CSSProperties;
}

export function Tabs({ tabs, activeTab, onChange, style }: TabsProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: "var(--windagent-space-1)",
        borderBottom: "1px solid var(--windagent-border-subtle)",
        paddingBottom: "var(--windagent-space-1)",
        overflowX: "auto",
        ...style,
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 14px",
              borderRadius: "var(--windagent-radius-md)",
              border: "none",
              background: isActive ? "var(--windagent-color-surface-hover)" : "transparent",
              color: isActive ? "var(--windagent-color-text)" : "var(--windagent-color-text-muted)",
              fontWeight: isActive ? 600 : 400,
              fontSize: "0.875rem",
              cursor: "pointer",
              transition: "all var(--windagent-transition-fast)",
              whiteSpace: "nowrap",
            }}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span
                style={{
                  fontSize: "0.75rem",
                  padding: "1px 6px",
                  borderRadius: "var(--windagent-radius-full)",
                  background: isActive ? "var(--windagent-color-accent-subtle)" : "var(--windagent-color-surface)",
                  color: isActive ? "var(--windagent-color-accent)" : "var(--windagent-color-text-dim)",
                }}
              >
                {tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
