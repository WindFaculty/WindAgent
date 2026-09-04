import { useRef, useEffect } from "react";

export interface LogEntry {
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  message: string;
  source?: string;
}

export function LogViewer({
  logs,
  autoScroll = true,
  maxHeight = "320px",
}: {
  logs: LogEntry[];
  autoScroll?: boolean;
  maxHeight?: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const levelColor = {
    info: "var(--windagent-color-info)",
    warn: "var(--windagent-color-warning)",
    error: "var(--windagent-color-danger)",
    debug: "var(--windagent-color-text-dim)",
  };

  return (
    <div
      ref={containerRef}
      style={{
        background: "var(--windagent-color-bg)",
        border: "1px solid var(--windagent-border-subtle)",
        borderRadius: "var(--windagent-radius-md)",
        padding: "10px 14px",
        maxHeight,
        overflowY: "auto",
        fontFamily: "var(--windagent-font-mono)",
        fontSize: "0.8rem",
        lineHeight: 1.5,
      }}
    >
      {logs.length === 0 ? (
        <div style={{ color: "var(--windagent-color-text-dim)", textAlign: "center", padding: "16px" }}>
          No stream logs available
        </div>
      ) : (
        logs.map((log, idx) => (
          <div key={idx} style={{ display: "flex", gap: "10px", marginBottom: "4px" }}>
            <span style={{ color: "var(--windagent-color-text-dim)", flexShrink: 0 }}>
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
            <span
              style={{
                color: levelColor[log.level],
                fontWeight: 600,
                width: "48px",
                flexShrink: 0,
                textTransform: "uppercase",
              }}
            >
              [{log.level}]
            </span>
            {log.source && (
              <span style={{ color: "var(--windagent-color-text-muted)", flexShrink: 0 }}>
                {log.source}:
              </span>
            )}
            <span style={{ color: "var(--windagent-color-text)", wordBreak: "break-all" }}>
              {log.message}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
