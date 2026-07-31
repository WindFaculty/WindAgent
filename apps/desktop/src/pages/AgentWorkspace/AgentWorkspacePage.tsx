/**
 * AgentWorkspacePage.tsx — Main workspace layout.
 *
 * - Uses local selectedAgentId state
 * - Does NOT reset state on unmount
 * - session state persists across tab switches
 * - Uses narrow selectors to avoid unnecessary rerenders
 */
import { useState } from "react";
import { useAgentSessionStore } from "../../state/agentSessionStore";
import { useAgentSessionByAgentId } from "../../state/useAgentSession";
import { ChatPanel } from "./components/ChatPanel";
import { TaskPanel } from "./components/TaskPanel";
import { TerminalPanel } from "./components/TerminalPanel";
import { AgentBrowserPanel } from "./components/AgentBrowserPanel";
import { RuntimeSidebar } from "./components/RuntimeSidebar";
import { PermissionDialog } from "./components/PermissionDialog";

// Stable refs for selector fallbacks — returning a fresh `[]` each call
// breaks Zustand's snapshot caching and causes an infinite render loop.
const EMPTY_ARRAY: never[] = [];

interface AgentWorkspaceProps {
  hermesOnline?: boolean | null;
  backendOnline?: boolean | null;
}

export function AgentWorkspacePage({
  hermesOnline = null,
  backendOnline = null,
}: AgentWorkspaceProps) {
  const selectedAgentIdState = useState<string>("coder");
  const selectedAgentId = selectedAgentIdState[0];
  const { session: _session, sessionId, handleSend, resolvePermission, clearTerminal, updateBrowserState } =
    useAgentSessionByAgentId(selectedAgentId);

  // Narrow selectors for performance — only re-render when specific slice changes
  const messages = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.messages ?? EMPTY_ARRAY : EMPTY_ARRAY),
  );
  const workflow = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.workflow ?? null : null),
  );
  const terminalLines = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.terminalLines ?? EMPTY_ARRAY : EMPTY_ARRAY),
  );
  const permissionQueue = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.permissionQueue ?? EMPTY_ARRAY : EMPTY_ARRAY),
  );
  const toolCalls = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.toolCalls ?? EMPTY_ARRAY : EMPTY_ARRAY),
  );
  const recentActions = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.recentActions ?? EMPTY_ARRAY : EMPTY_ARRAY),
  );
  const browserState = useAgentSessionStore(
    (state) => (sessionId ? state.sessionsById[sessionId]?.browser ?? null : null),
  );

  // Detect if assistant is currently streaming
  const lastMsg = messages[messages.length - 1];
  const isStreaming =
    !!lastMsg &&
    lastMsg.sender === "assistant" &&
    Date.now() - lastMsg.createdAt < 5000 &&
    messages.length > 0 &&
    toolCalls.some((tc) => tc.status === "pending");

  const handleResolvePermission = async (requestId: string, decision: "granted" | "denied") => {
    await resolvePermission(requestId, decision);
  };

  // Dispatch for browser panel (convert store action to dispatch-like interface)
  const dispatch = (action: any) => {
    if (!sessionId) return;
    if (action.type === "updateBrowserState") {
      updateBrowserState(action.browser);
    } else if (action.type === "clearTerminal") {
      clearTerminal();
    }
  };

  return (
    <main className="central-workspace">
      <div className="workspace-body">
        <div className="workspace-grid">
          {/* Top Left Panel: Hermes Chat */}
          <ChatPanel
            sessionId={sessionId}
            messages={messages}
            selectedAgentId={selectedAgentId}
            hermesOnline={hermesOnline}
            backendOnline={backendOnline}
            onSend={handleSend}
            isStreaming={isStreaming}
          />

          {/* Top Right Panel: Current Task */}
          <TaskPanel workflow={workflow} />

          {/* Bottom Left Panel: Terminal Logs */}
          <TerminalPanel
            terminalLines={terminalLines}
            onClear={clearTerminal}
          />

          {/* Bottom Right Panel: Interactive Browser Preview */}
          <AgentBrowserPanel
            sessionId={sessionId}
            browserState={browserState ?? {
              url: "about:blank",
              title: "New Tab",
              loading: false,
              screenshotUrl: null,
              controlledBy: "agent" as const,
              extractedText: "",
              contentChars: 0,
              error: null,
              authenticated: false,
              profile: null,
            }}
            dispatch={dispatch}
          />
        </div>

        {/* Far Right Sidebar */}
        <RuntimeSidebar
          sessionId={sessionId}
          toolCalls={toolCalls}
          permissionQueue={permissionQueue}
          recentActions={recentActions}
        />
      </div>

      {/* Floating Permission Gating Overlay */}
      <PermissionDialog
        permissionQueue={permissionQueue}
        resolvePermission={handleResolvePermission}
      />
    </main>
  );
}
