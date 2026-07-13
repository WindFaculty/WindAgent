import { useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "../../../state/sessionStore";

interface Props {
  messages: ChatMessage[];
  selectedAgentId: string;
  setSelectedAgentId: (id: string) => void;
  hermesOnline: boolean | null;
  backendOnline: boolean | null;
}

export function ChatPanel({
  messages,
  selectedAgentId,
  setSelectedAgentId,
  hermesOnline,
  backendOnline,
}: Props) {
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const renderStatusBanner = () => {
    if (backendOnline === false) {
      return (
        <div className="status-banner error" style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          backgroundColor: "rgba(239, 68, 68, 0.15)",
          borderBottom: "1px solid rgba(239, 68, 68, 0.25)",
          padding: "10px 16px",
          color: "#ef4444",
          fontSize: "0.85rem",
        }}>
          <span style={{ display: "inline-block", width: "8px", height: "8px", backgroundColor: "#ef4444", borderRadius: "50%" }} />
          <span><strong>Backend is offline</strong>. The control plane is disconnected.</span>
        </div>
      );
    }
    if (hermesOnline === false) {
      return (
        <div className="status-banner warning" style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          borderBottom: "1px solid rgba(245, 158, 11, 0.25)",
          padding: "10px 16px",
          color: "#f59e0b",
          fontSize: "0.85rem",
        }}>
          <span style={{ display: "inline-block", width: "8px", height: "8px", backgroundColor: "#f59e0b", borderRadius: "50%" }} />
          <span><strong>Hermes runtime is offline</strong>. Agent execution capabilities are disabled.</span>
        </div>
      );
    }
    return null;
  };

  return (
    <section className="dashboard-panel">
      <header className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div className="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          Agent Workspace / Chat
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "0.72rem", color: "var(--text-dim)" }}>Runtime:</span>
          <select
            value={selectedAgentId}
            onChange={(e) => setSelectedAgentId(e.target.value)}
            style={{
              backgroundColor: "rgba(30, 41, 59, 0.6)",
              border: "1px solid rgba(255, 255, 255, 0.1)",
              color: "var(--text-main)",
              borderRadius: "4px",
              fontSize: "0.72rem",
              padding: "2px 6px",
              outline: "none",
              cursor: "pointer",
            }}
          >
            <option value="coder">Coder (Hermes)</option>
            <option value="planner">Planner (Hermes)</option>
            <option value="researcher">Researcher (Hermes)</option>
            <option value="browser">Browser Agent (Hermes)</option>
            <option value="gui">GUI Agent (Native)</option>
          </select>
        </div>
      </header>

      {renderStatusBanner()}

      <div className="panel-body chat-container">
        {messages.length === 0 ? (
          <div className="empty-state" style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            height: "100%",
            textAlign: "center",
            padding: "40px",
            color: "var(--text-muted)",
            gap: "12px",
          }}>
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.4 }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            <h3 style={{ fontSize: "1.1rem", fontWeight: "600", color: "var(--text-main)" }}>Start a Conversation</h3>
            <p style={{ fontSize: "0.82rem", maxWidth: "280px" }}>Ask WindAgent to run terminal commands, inspect files, or edit codes.</p>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-bubble ${msg.sender}`}>
              <div className="bubble-header">
                <span className="avatar-initial">
                  {msg.sender === "user" ? "U" : "WA"}
                </span>
                <span className="sender-name">
                  {msg.sender === "user" ? "You" : "WindAgent"}
                </span>
                <span className="chat-time">
                  {new Date(msg.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
              <div className="bubble-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              </div>
            </div>
          ))
        )}
        <div ref={chatEndRef} />
      </div>
    </section>
  );
}
