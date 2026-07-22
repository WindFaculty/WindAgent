import { useRef, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
// Use type from new global store
import type { ChatMessage } from "../../../state/agentSessionStore";
// Import agentSessionStore for draft
import { useAgentSessionStore } from "../../../state/agentSessionStore";

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  selectedAgentId: string;
  hermesOnline: boolean | null;
  backendOnline: boolean | null;
  onSend: (content: string) => void;
  isStreaming?: boolean;
}

const AGENT_OPTIONS = [
  { value: "coder", label: "Coder", color: "#6ee7b7" },
  { value: "planner", label: "Planner", color: "#93c5fd" },
  { value: "researcher", label: "Researcher", color: "#fbbf24" },
  { value: "browser", label: "Browser", color: "#c4b5fd" },
  { value: "gui", label: "GUI Agent", color: "#f9a8d4" },
];

function HermesAvatar({ agentId }: { agentId: string }) {
  const agent = AGENT_OPTIONS.find((a) => a.value === agentId);
  const color = agent?.color ?? "#6ee7b7";
  const label = agent?.label?.[0] ?? "H";
  return (
    <div
      style={{
        width: "30px",
        height: "30px",
        borderRadius: "8px",
        background: `linear-gradient(135deg, ${color}33, ${color}66)`,
        border: `1px solid ${color}55`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "0.75rem",
        fontWeight: "700",
        color: color,
        flexShrink: 0,
      }}
    >
      {label}
    </div>
  );
}

function UserAvatar() {
  return (
    <div
      style={{
        width: "30px",
        height: "30px",
        borderRadius: "8px",
        background: "linear-gradient(135deg, rgba(99,102,241,0.3), rgba(99,102,241,0.6))",
        border: "1px solid rgba(99,102,241,0.4)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "0.75rem",
        fontWeight: "700",
        color: "#818cf8",
        flexShrink: 0,
      }}
    >
      U
    </div>
  );
}

function TypingIndicator() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "8px 0",
      }}
    >
      <HermesAvatar agentId="coder" />
      <div
        style={{
          display: "flex",
          gap: "4px",
          alignItems: "center",
          background: "rgba(255,255,255,0.04)",
          padding: "8px 12px",
          borderRadius: "8px",
        }}
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "#6ee7b7",
              animation: `bounce 1.2s ease-in-out ${i * 0.2}s infinite`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function ChatPanel({
  sessionId,
  messages,
  selectedAgentId,
  hermesOnline,
  backendOnline,
  onSend,
  isStreaming,
}: Props) {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [isInputFocused, setIsInputFocused] = useState(false);

  // Draft state is per-session and stored in global store (persists across tab switches)
  const draft = useAgentSessionStore(
    (state) => (sessionId ? state.draftBySessionId[sessionId] ?? "" : ""),
  );
  const setDraft = useAgentSessionStore((state) => state.setDraft);

  const handleDraftChange = (value: string) => {
    if (sessionId) setDraft(sessionId, value);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isStreaming]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (draft.trim()) {
        onSend(draft);
        if (sessionId) setDraft(sessionId, "");
      }
    }
  };

  const handleSendClick = () => {
    if (draft.trim()) {
      onSend(draft);
      if (sessionId) setDraft(sessionId, "");
    }
  };

  const isOnline = hermesOnline === true || backendOnline === true;
  const statusText =
    hermesOnline === null && backendOnline === null
      ? "Checking..."
      : hermesOnline === true
        ? "Hermes Connected"
        : backendOnline === true
          ? "Backend Connected"
          : "Offline";

  const statusColor =
    hermesOnline === true
      ? "#6ee7b7"
      : backendOnline === true
        ? "#93c5fd"
        : hermesOnline === null && backendOnline === null
          ? "#94a3b8"
          : "#ef4444";

  return (
    <div className="workspace-panel chat-panel">
      {/* Header */}
      <div className="panel-header">
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            style={{ color: "#6ee7b7" }}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
          <span className="panel-title">Hermes Chat</span>
          <span
            style={{
              display: "inline-block",
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: statusColor,
              boxShadow: isOnline ? `0 0 6px ${statusColor}` : "none",
            }}
          />
          <span style={{ fontSize: "0.65rem", color: statusColor, opacity: 0.8 }}>
            {statusText}
          </span>
        </div>
      </div>

      {/* Messages */}
      <div
        className="chat-messages"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "12px",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        {messages.length === 0 && (
          <div
            style={{
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "0.8rem",
              marginTop: "40px",
              opacity: 0.6,
            }}
          >
            Start a conversation with your agent…
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            style={{
              display: "flex",
              gap: "8px",
              alignItems: "flex-start",
              flexDirection: msg.sender === "user" ? "row-reverse" : "row",
            }}
          >
            {msg.sender === "user" ? <UserAvatar /> : <HermesAvatar agentId={selectedAgentId} />}

            <div
              style={{
                maxWidth: "80%",
                background:
                  msg.sender === "user"
                    ? "rgba(99,102,241,0.15)"
                    : "rgba(255,255,255,0.04)",
                border:
                  msg.sender === "user"
                    ? "1px solid rgba(99,102,241,0.3)"
                    : "1px solid rgba(255,255,255,0.08)",
                borderRadius: msg.sender === "user" ? "12px 4px 12px 12px" : "4px 12px 12px 12px",
                padding: "8px 12px",
                fontSize: "0.82rem",
                lineHeight: "1.5",
                color: "#e2e8f0",
              }}
            >
              {msg.sender === "assistant" ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
              ) : (
                <span style={{ whiteSpace: "pre-wrap" }}>{msg.content}</span>
              )}
            </div>
          </div>
        ))}

        {isStreaming && <TypingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div
        style={{
          padding: "16px",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          background: "transparent",
        }}
      >
        <div
          style={{
            background: "rgba(13, 18, 32, 0.4)",
            border: isInputFocused
              ? "1px solid rgba(59, 130, 246, 0.5)"
              : "1px solid rgba(255, 255, 255, 0.08)",
            boxShadow: isInputFocused
              ? "0 0 14px rgba(59, 130, 246, 0.15)"
              : "none",
            borderRadius: "12px",
            display: "flex",
            flexDirection: "column",
            transition: "all 0.2s ease-in-out",
            overflow: "hidden",
          }}
        >
          <textarea
            value={draft}
            onChange={(e) => handleDraftChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsInputFocused(true)}
            onBlur={() => setIsInputFocused(false)}
            placeholder="Message your agent... (Enter to send, Shift+Enter for newline)"
            rows={2}
            style={{
              width: "100%",
              background: "transparent",
              border: "none",
              outline: "none",
              color: "#f3f4f6",
              fontSize: "0.85rem",
              padding: "12px 14px 8px 14px",
              resize: "none",
              lineHeight: "1.5",
              fontFamily: "inherit",
            }}
          />

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "6px 12px 10px 12px",
              background: "transparent",
            }}
          >
            {/* Left side actions (Attachment and char counts) */}
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <button
                type="button"
                style={{
                  background: "transparent",
                  border: "none",
                  color: "rgba(255, 255, 255, 0.4)",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "4px",
                  borderRadius: "4px",
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = "rgba(255, 255, 255, 0.8)"}
                onMouseLeave={(e) => e.currentTarget.style.color = "rgba(255, 255, 255, 0.4)"}
                title="Add attachment"
                onClick={() => alert("Upload file capability is under development.")}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 5.636l-3.536 3.536m0 0A3 3 0 1012.7 7.05l-3.536 3.536m0 0A3 3 0 108.45 14.12l3.536-3.536" />
                </svg>
              </button>
              
              {draft.length > 0 && (
                <span style={{ fontSize: "0.7rem", color: "rgba(255, 255, 255, 0.3)" }}>
                  {draft.length} chars
                </span>
              )}
            </div>

            {/* Right side: Send button */}
            <button
              className="chat-send-btn-premium"
              onClick={handleSendClick}
              disabled={!draft.trim()}
              title="Send message (Enter)"
              style={{
                height: "32px",
                width: "32px",
                borderRadius: "8px",
                background: draft.trim()
                  ? "linear-gradient(135deg, #3b82f6, #6366f1)"
                  : "rgba(255, 255, 255, 0.04)",
                border: "none",
                color: draft.trim() ? "#fff" : "rgba(255, 255, 255, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: draft.trim() ? "pointer" : "not-allowed",
                transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
                boxShadow: draft.trim()
                  ? "0 4px 12px rgba(59, 130, 246, 0.25)"
                  : "none",
              }}
              onMouseEnter={(e) => {
                if (draft.trim()) {
                  e.currentTarget.style.transform = "scale(1.06)";
                  e.currentTarget.style.boxShadow = "0 4px 16px rgba(59, 130, 246, 0.4)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "none";
                e.currentTarget.style.boxShadow = draft.trim()
                  ? "0 4px 12px rgba(59, 130, 246, 0.25)"
                  : "none";
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M22 2L11 13M22 2l-7 20-4-9-9-4L22 2z" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
