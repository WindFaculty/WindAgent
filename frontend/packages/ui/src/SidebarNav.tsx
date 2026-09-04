export interface NavItem {
  id: string;
  label: string;
  icon: string;
  badge?: string | number;
  category?: string;
}

export function SidebarNav({
  items,
  activeId,
  onSelect,
  collapsed = false,
}: {
  items: NavItem[];
  activeId: string;
  onSelect: (id: string) => void;
  collapsed?: boolean;
}) {
  return (
    <aside
      style={{
        width: collapsed ? "64px" : "240px",
        background: "var(--windagent-color-bg-subtle)",
        borderRight: "1px solid var(--windagent-border-subtle)",
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        transition: "width var(--windagent-transition-normal)",
        userSelect: "none",
      }}
    >
      <div
        style={{
          padding: "var(--windagent-space-4)",
          borderBottom: "1px solid var(--windagent-border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
        }}
      >
        <div
          style={{
            width: "28px",
            height: "28px",
            borderRadius: "var(--windagent-radius-md)",
            background: "var(--windagent-color-brand-gradient)",
            display: "grid",
            placeItems: "center",
            fontWeight: 800,
            fontSize: "0.85rem",
            color: "#ffffff",
          }}
        >
          W
        </div>
        {!collapsed && (
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--windagent-color-text)" }}>
              WindAgent <span style={{ color: "var(--windagent-color-accent)", fontSize: "0.8rem" }}>V2</span>
            </div>
          </div>
        )}
      </div>

      <nav
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "var(--windagent-space-3) var(--windagent-space-2)",
          display: "flex",
          flexDirection: "column",
          gap: "4px",
        }}
      >
        {items.map((item) => {
          const isActive = item.id === activeId;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "12px",
                width: "100%",
                padding: "8px 12px",
                borderRadius: "var(--windagent-radius-md)",
                border: "none",
                background: isActive ? "var(--windagent-color-surface-active)" : "transparent",
                color: isActive ? "var(--windagent-color-text)" : "var(--windagent-color-text-secondary)",
                fontWeight: isActive ? 600 : 400,
                fontSize: "0.875rem",
                cursor: "pointer",
                transition: "all var(--windagent-transition-fast)",
                textAlign: "left",
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.background = "var(--windagent-color-surface-hover)";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.background = "transparent";
              }}
            >
              <span style={{ fontSize: "1.1rem", width: "20px", textAlign: "center" }}>{item.icon}</span>
              {!collapsed && <span style={{ flex: 1 }}>{item.label}</span>}
              {!collapsed && item.badge !== undefined && (
                <span
                  style={{
                    fontSize: "0.75rem",
                    padding: "1px 6px",
                    borderRadius: "var(--windagent-radius-full)",
                    background: "var(--windagent-color-accent-subtle)",
                    color: "var(--windagent-color-accent)",
                    fontWeight: 600,
                  }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div
        style={{
          padding: "var(--windagent-space-3)",
          borderTop: "1px solid var(--windagent-border-subtle)",
          fontSize: "0.75rem",
          color: "var(--windagent-color-text-dim)",
          textAlign: "center",
        }}
      >
        {!collapsed && <div>Milestone 4 Platform</div>}
      </div>
    </aside>
  );
}
