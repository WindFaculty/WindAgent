import { useState } from "react";
import { useAgentSession } from "../../state/useAgentSession";
import { ChatPanel } from "./components/ChatPanel";
import { TaskPanel } from "./components/TaskPanel";
import { TerminalPanel } from "./components/TerminalPanel";
import { AgentBrowserPanel } from "./components/AgentBrowserPanel";
import { RuntimeSidebar } from "./components/RuntimeSidebar";
import { PermissionDialog } from "./components/PermissionDialog";

interface AgentWorkspaceProps {
  selectedAgentId: string;
  setSelectedAgentId: (id: string) => void;
  browserUrl?: string;
  setBrowserUrl?: (url: string) => void;
  browserTab?: string;
  setBrowserTab?: (tab: string) => void;
  hermesOnline?: boolean | null;
  backendOnline?: boolean | null;
}

export function AgentWorkspace({
  selectedAgentId,
  setSelectedAgentId,
  hermesOnline = null,
  backendOnline = null,
}: AgentWorkspaceProps) {
  const { state, dispatch, handleSend, resolvePermission } = useAgentSession(selectedAgentId);
  const [chatInput, setChatInput] = useState<string>("");

  const onSendSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || hermesOnline === false || backendOnline === false) return;
    handleSend(chatInput);
    setChatInput("");
  };

  const isInputDisabled = hermesOnline === false || backendOnline === false;

  return (
    <main className="central-workspace">
      <div className="workspace-body">
        <div className="workspace-grid">
          {/* Top Left Panel: Agent Chat */}
          <ChatPanel
            messages={state.messages}
            selectedAgentId={selectedAgentId}
            setSelectedAgentId={setSelectedAgentId}
            hermesOnline={hermesOnline}
            backendOnline={backendOnline}
          />

          {/* Top Right Panel: Current Task */}
          <TaskPanel workflow={state.workflow} />

          {/* Bottom Left Panel: Terminal Logs */}
          <TerminalPanel
            terminalLines={state.terminalLines}
            onClear={() => dispatch({ type: "clearTerminal" })}
          />

          {/* Bottom Right Panel: Interactive Browser Preview */}
          <AgentBrowserPanel
            sessionId={state.sessionId}
            browserState={state.browser}
            dispatch={dispatch}
          />
        </div>

        {/* Far Right Sidebar */}
        <RuntimeSidebar
          sessionId={state.sessionId}
          toolCalls={state.toolCalls}
          permissionQueue={state.permissionQueue}
          recentActions={state.recentActions}
        />
      </div>

      {/* Floating Permission Gating Overlay */}
      <PermissionDialog
        permissionQueue={state.permissionQueue}
        resolvePermission={resolvePermission}
      />

      {/* Interactive Bottom Chat Input inside workspace */}
      <form className="chat-input-bar" onSubmit={onSendSubmit}>
        <input
          type="text"
          className="chat-input-field"
          placeholder={
            backendOnline === false
              ? "Backend is offline. Action disabled."
              : hermesOnline === false
              ? "Hermes runtime is offline. Action disabled."
              : "Ask WindAgent to run terminal commands, inspect files, or edit codes..."
          }
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          disabled={isInputDisabled}
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={isInputDisabled}
          style={isInputDisabled ? { opacity: 0.5, cursor: "not-allowed", background: "var(--text-dim)" } : {}}
        >
          Send Query
        </button>
      </form>
    </main>
  );
}
