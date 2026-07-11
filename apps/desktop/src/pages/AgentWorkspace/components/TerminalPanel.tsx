import { VirtualizedList } from "./VirtualizedList";

interface Props {
  terminalLines: string[];
  onClear: () => void;
}

export function TerminalPanel({ terminalLines, onClear }: Props) {
  const renderRow = (line: string, index: number) => {
    let className = "term-line";
    if (
      line.startsWith("git clone") ||
      line.startsWith("cd ") ||
      line.startsWith("npm install") ||
      line.startsWith("npm test") ||
      line.startsWith("> ")
    ) {
      className += " cmd";
    } else if (line.startsWith("[Finished]")) {
      className += " green";
    } else if (line.startsWith("[Error]")) {
      className += " red";
    } else if (line.includes("Scanning") || line.includes("Cloning")) {
      className += " yellow";
    } else if (line.startsWith("added") || line.includes("passed")) {
      className += " green";
    }

    return (
      <div key={index} className={className} style={{ height: "20px", lineHeight: "20px", fontFamily: "var(--font-mono)", fontSize: "0.8rem", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {line}
      </div>
    );
  };

  return (
    <section className="dashboard-panel">
      <header className="panel-header">
        <div className="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          Terminal / Logs
        </div>
        <div className="terminal-header-controls">
          <span className="live-indicator">
            <span className="live-dot" />
            LIVE
          </span>
          <button
            className="terminal-control-btn"
            onClick={onClear}
            title="Clear logs"
            style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </header>
      <div className="panel-body terminal-body" style={{ padding: "8px 12px", height: "280px" }}>
        {terminalLines.length === 0 ? (
          <div className="empty-state" style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            textAlign: "center",
            color: "var(--text-muted)",
            gap: "8px",
          }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.4 }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p style={{ fontSize: "0.82rem" }}>Terminal Idle. Active tools' stdout logs will stream here.</p>
          </div>
        ) : (
          <VirtualizedList
            items={terminalLines}
            rowHeight={20}
            height={264}
            renderRow={renderRow}
            className="terminal-virtualized-scroller"
          />
        )}
      </div>
    </section>
  );
}
