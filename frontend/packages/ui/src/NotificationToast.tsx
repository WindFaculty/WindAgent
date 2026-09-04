import { Card } from "./Card.tsx";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info" | "warning";
  title: string;
  message?: string;
}

export function NotificationToast({
  toasts,
  onDismiss,
}: {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}) {
  if (toasts.length === 0) return null;

  const typeStyles = {
    success: { border: "var(--windagent-color-success)", icon: "✓" },
    error: { border: "var(--windagent-color-danger)", icon: "✕" },
    warning: { border: "var(--windagent-color-warning)", icon: "⚠" },
    info: { border: "var(--windagent-color-info)", icon: "ℹ" },
  };

  return (
    <div
      style={{
        position: "fixed",
        bottom: "20px",
        right: "20px",
        zIndex: 2000,
        display: "flex",
        flexDirection: "column",
        gap: "10px",
        maxWidth: "360px",
      }}
    >
      {toasts.map((toast) => (
        <Card
          key={toast.id}
          variant="glass"
          padding="sm"
          style={{
            borderLeft: `4px solid ${typeStyles[toast.type].border}`,
            boxShadow: "var(--windagent-shadow-lg)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "10px",
          }}
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--windagent-color-text)" }}>
              <span style={{ marginRight: "6px" }}>{typeStyles[toast.type].icon}</span>
              {toast.title}
            </div>
            {toast.message && (
              <div style={{ fontSize: "0.8rem", color: "var(--windagent-color-text-muted)", marginTop: "2px" }}>
                {toast.message}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => onDismiss(toast.id)}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--windagent-color-text-dim)",
              cursor: "pointer",
              padding: "2px 4px",
            }}
          >
            ✕
          </button>
        </Card>
      ))}
    </div>
  );
}
