import type { ChatMessage, ToolCallLog } from "../state/sessionStore";

interface Props {
  messages: ChatMessage[];
  toolCalls: ToolCallLog[];
}

export function MessageList({ messages, toolCalls }: Props) {
  const sortedCalls = [...toolCalls].sort((a, b) => a.at - b.at);
  return (
    <div className="message-list">
      {messages.length === 0 && <p className="muted">Chưa có message.</p>}
      {messages.map((m) => (
        <div key={m.id} className={`message message-${m.sender}`}>
          <div className="message-meta">
            <span className="badge">{m.sender}</span>
            <time>{new Date(m.createdAt).toLocaleTimeString()}</time>
          </div>
          <div className="message-body">{m.content}</div>
        </div>
      ))}
      {sortedCalls.length > 0 && (
        <details className="tool-log" open>
          <summary>Tool call log ({sortedCalls.length})</summary>
          <ul>
            {sortedCalls.map((c, idx) => (
              <li key={idx} className={`tool-row tool-${c.status}`}>
                <div className="tool-row-main">
                  <code>{c.toolName}</code> · {c.status} · {c.durationMs}ms
                </div>
                {c.status === "failed" && c.errorMessage && (
                  <div className="tool-row-error" title={c.errorMessage}>
                    {c.errorMessage}
                  </div>
                )}
                {c.resolvedPoint && (
                  <div className="tool-row-point">
                    → click_xy x=<code>{c.resolvedPoint.x}</code>{" "}
                    y=<code>{c.resolvedPoint.y}</code>{" "}
                    ({c.resolvedPoint.method}, conf{" "}
                    {c.resolvedPoint.confidence.toFixed(2)})
                  </div>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}