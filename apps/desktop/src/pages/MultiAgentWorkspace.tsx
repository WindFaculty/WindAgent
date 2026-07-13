import { useEffect, useRef, useState } from "react";
import { useMultiAgent, useMultiAgentStore } from "../state/multiAgentStore";
import {
  sendMessage,
  controlSession,
  fetchSessionMessages,
  connectWs,
  createTaskEdge,
  createTaskNode,
  deleteTaskEdge,
  deleteTaskNode,
  updateTaskNode,
  pauseTask,
  resumeTask,
  cancelTask,
  retryTask,
} from "../api/client";
import type { AgentBoardRow } from "../api/client";

function useOrchestratorChat(conversationId: string) {
  const [messages, setMessages] = useState<{ sender: string; text: string }[]>([]);
  const [input, setInput] = useState("");

  useEffect(() => {
    let cancelled = false;

    // Fetch initial chat history
    const load = async () => {
      try {
        const msgs = await fetchSessionMessages(conversationId);
        if (!cancelled) {
          setMessages(
            msgs.map((m: any) => ({
              sender: m.sender ?? "assistant",
              text: m.content ?? "",
            })),
          );
        }
      } catch (err) {
        // Orchestrator session may not exist yet
      }
    };

    load();

    // Stream live typing/deltas from Orchestrator via WebSocket
    const ws = connectWs(conversationId, {
      onEvent: (env) => {
        if (cancelled) return;
        if (env.event === "message_received") {
          const data = env.data as { content: string };
          setMessages((prev) => {
            // Avoid duplicate user messages if already appended locally
            const last = prev[prev.length - 1];
            if (last && last.sender === "user" && last.text === data.content) {
              return prev;
            }
            return [...prev, { sender: "user", text: data.content }];
          });
        } else if (env.event === "assistant_message_delta") {
          const data = env.data as { delta: string };
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.sender === "assistant") {
              // Append delta to existing typing bubble
              return [
                ...next.slice(0, -1),
                { ...last, text: last.text + data.delta },
              ];
            } else {
              return [...next, { sender: "assistant", text: data.delta }];
            }
          });
        } else if (env.event === "replan_notification") {
          useMultiAgentStore.getState().refresh();
        }
      },
    });

    return () => {
      cancelled = true;
      ws.close();
    };
  }, [conversationId]);

  const send = async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    
    // Optimistic append
    setMessages((m) => [...m, { sender: "user", text }]);
    try {
      await sendMessage(conversationId, text);
    } catch (err) {
      console.warn("Failed to send message to orchestrator:", err);
    }
  };

  return { messages, input, setInput, send };
}

export function MultiAgentWorkspace({ conversationId }: { conversationId: string }) {
  const { state, select, permissionQueue, resolvePermission } = useMultiAgent();
  const chat = useOrchestratorChat(conversationId);
  
  const [inspectorTab, setInspectorTab] = useState<"terminal" | "browser">("terminal");
  const [browserTab, setBrowserTab] = useState<string>("overview");
  const [browserUrl, setBrowserUrl] = useState<string>("http://localhost:3000");

  const [isEditingPlan, setIsEditingPlan] = useState(false);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editAgentType, setEditAgentType] = useState("coder");
  const [editStatus, setEditStatus] = useState("blocked");
  const [editAssignee, setEditAssignee] = useState("");

  const [isAddingNode, setIsAddingNode] = useState(false);
  const [newNodeTitle, setNewNodeTitle] = useState("");
  const [newNodeDesc, setNewNodeDesc] = useState("");
  const [newNodeAgentType, setNewNodeAgentType] = useState("coder");
  const [newNodeStatus, setNewNodeStatus] = useState("blocked");

  const [isAddingEdge, setIsAddingEdge] = useState(false);
  const [edgeFrom, setEdgeFrom] = useState("");
  const [edgeTo, setEdgeTo] = useState("");

  const [conflictError, setConflictError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleAddNode = async () => {
    if (!newNodeTitle.trim()) return;
    try {
      setValidationError(null);
      await createTaskNode(conversationId, {
        title: newNodeTitle,
        description: newNodeDesc || null,
        agent_type: newNodeAgentType,
        status: newNodeStatus,
        version: state.version,
      });
      setNewNodeTitle("");
      setNewNodeDesc("");
      setIsAddingNode(false);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      if (err.message.includes("conflict") || err.message.includes("Conflict")) {
        setConflictError("Plan version conflict");
      } else {
        setValidationError(err.message);
      }
    }
  };

  const handleSaveNode = async () => {
    if (!editingNodeId || !editTitle.trim()) return;
    try {
      setValidationError(null);
      await updateTaskNode(conversationId, editingNodeId, {
        title: editTitle,
        description: editDesc || null,
        agent_type: editAgentType,
        status: editStatus,
        assigned_agent_instance_id: editAssignee || null,
        version: state.version,
      });
      setEditingNodeId(null);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      if (err.message.includes("conflict") || err.message.includes("Conflict")) {
        setConflictError("Plan version conflict");
      } else {
        setValidationError(err.message);
      }
    }
  };

  const handleDeleteNode = async (nodeId: string) => {
    if (!window.confirm("Are you sure you want to delete this task?")) return;
    try {
      setValidationError(null);
      await deleteTaskNode(conversationId, nodeId, state.version);
      if (editingNodeId === nodeId) setEditingNodeId(null);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      if (err.message.includes("conflict") || err.message.includes("Conflict")) {
        setConflictError("Plan version conflict");
      } else {
        setValidationError(err.message);
      }
    }
  };

  const handleAddEdge = async () => {
    if (!edgeFrom || !edgeTo) return;
    if (edgeFrom === edgeTo) {
      setValidationError("Cannot create a self-dependency link");
      return;
    }
    try {
      setValidationError(null);
      await createTaskEdge(conversationId, {
        from_task_id: edgeFrom,
        to_task_id: edgeTo,
        version: state.version,
      });
      setIsAddingEdge(false);
      setEdgeFrom("");
      setEdgeTo("");
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      if (err.message.includes("conflict") || err.message.includes("Conflict")) {
        setConflictError("Plan version conflict");
      } else {
        setValidationError(err.message);
      }
    }
  };

  const handleDeleteEdge = async (fromId: string, toId: string) => {
    try {
      setValidationError(null);
      await deleteTaskEdge(conversationId, fromId, toId, state.version);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      if (err.message.includes("conflict") || err.message.includes("Conflict")) {
        setConflictError("Plan version conflict");
      } else {
        setValidationError(err.message);
      }
    }
  };

  const handlePauseTask = async (nodeId: string) => {
    try {
      await pauseTask(nodeId);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      console.error("Pause task failed:", err);
    }
  };

  const handleResumeTask = async (nodeId: string) => {
    try {
      await resumeTask(nodeId);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      console.error("Resume task failed:", err);
    }
  };

  const handleRetryTask = async (nodeId: string) => {
    try {
      await retryTask(nodeId);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      console.error("Retry task failed:", err);
    }
  };

  const handleCancelTask = async (nodeId: string) => {
    if (!window.confirm("Are you sure you want to cancel this task run?")) return;
    try {
      await cancelTask(nodeId);
      useMultiAgentStore.getState().refresh();
    } catch (err: any) {
      console.error("Cancel task failed:", err);
    }
  };

  const chatEndRef = useRef<HTMLDivElement>(null);
  const termEndRef = useRef<HTMLDivElement>(null);

  const selected: AgentBoardRow | undefined = state.selectedAgentId
    ? state.agents[state.selectedAgentId]
    : undefined;

  const termLines = selected ? state.events[selected.id]?.lines ?? [] : [];

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages]);

  // Auto-scroll terminal log
  useEffect(() => {
    termEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [termLines, inspectorTab]);

  // Parse terminal line formats for color styling
  const colorizeLine = (line: string, idx: number) => {
    let className = "term-line";
    if (
      line.startsWith("git ") ||
      line.startsWith("cd ") ||
      line.startsWith("npm ") ||
      line.startsWith("uv ") ||
      line.startsWith("pip ") ||
      line.startsWith("$ ") ||
      line.startsWith("> ")
    ) {
      className += " cmd-line";
    } else if (line.startsWith("PASS") || line.toLowerCase().includes("success") || line.includes("passed")) {
      className += " success-line";
    } else if (line.startsWith("FAIL") || line.toLowerCase().includes("error") || line.includes("failed")) {
      className += " error-line";
    } else if (line.toLowerCase().includes("warning") || line.toLowerCase().includes("scanning")) {
      className += " warning-line";
    }

    return (
      <div key={idx} className={className}>
        {line}
      </div>
    );
  };

  // Helper to trace task prerequisites in DAG
  const getPrerequisites = (nodeId: string): string[] => {
    const parentIds = state.taskEdges
      .filter((edge) => edge.to === nodeId)
      .map((edge) => edge.from);
    return parentIds
      .map((id) => state.taskNodes[id]?.title)
      .filter(Boolean);
  };

  return (
    <main className="central-workspace multi-agent-wrapper">
      <div className="multi-agent-grid">
        {/* COLUMN 1: Orchestrator Chat */}
        <section className="dashboard-panel chat-panel-glass">
          <header className="panel-header chat-header-glass">
            <div className="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Orchestrator Chat
            </div>
            <span className="live-status-pulse">Active</span>
          </header>

          <div className="panel-body chat-container">
            {chat.messages.length === 0 && (
              <div className="chat-empty-state">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.3 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                <p>Welcome to WindAgent Workspace.</p>
                <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "4px" }}>
                  Ask Orchestrator to begin planning your tasks.
                </p>
              </div>
            )}
            {chat.messages.map((m, i) => (
              <div key={i} className={`chat-bubble ${m.sender}`}>
                <div className="bubble-header">
                  <span className="avatar-initial">
                    {m.sender === "user" ? "U" : "O"}
                  </span>
                  <span className="sender-name">
                    {m.sender === "user" ? "You" : "Orchestrator"}
                  </span>
                </div>
                <div className="bubble-content" style={{ whiteSpace: "pre-line" }}>
                  {m.text}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>

          <div className="chat-input-bar glass-input-bar">
            <input
              value={chat.input}
              onChange={(e) => chat.setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && chat.send()}
              placeholder="Prompt orchestrator..."
              className="chat-input-field"
            />
            <button className="chat-send-btn" onClick={chat.send}>
              Send
            </button>
          </div>
        </section>

        {/* COLUMN 2: Sub-agent Board & Task Graph */}
        <div className="middle-layout-panel">
          {/* Sub-agent Board */}
          <section className="dashboard-panel flex-panel-half">
            <header className="panel-header">
              <div className="panel-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-1.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4 4 4 0 004 4z" />
                </svg>
                Sub-agent Board
              </div>
              <span className="panel-badge-count">
                {state.agentOrder.length} active
              </span>
            </header>

            <div className="panel-body list-scrollable">
              {state.agentOrder.length === 0 && (
                <div className="empty-panel-text">No active agents spawned.</div>
              )}
              <div className="agent-cards-container">
                {state.agentOrder.map((id) => {
                  const a = state.agents[id];
                  const isActive = id === state.selectedAgentId;
                  const isRunning = a.run_status === "running";
                  return (
                    <div
                      key={id}
                      onClick={() => select(id)}
                      className={`agent-card-item ${isActive ? "active" : ""} ${isRunning ? "running" : ""}`}
                    >
                      <div className="agent-card-left">
                        <div className={`agent-status-ring ${isRunning ? "ring-pulse" : a.status}`}>
                          {isRunning ? (
                            <div className="ring-spinner" />
                          ) : (
                            <span className="ring-dot" />
                          )}
                        </div>
                        <div className="agent-info-text">
                          <span className="agent-name">{a.agent_type}</span>
                          <span className="agent-profile">{a.permission_profile} Profile</span>
                        </div>
                      </div>
                      <div className="agent-card-right">
                        <span className={`status-badge-pill ${a.status}`}>
                          {a.status}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>

          {/* Task Graph (DAG visualization) */}
          <section className="dashboard-panel flex-panel-half">
            <header className="panel-header" style={{ display: 'flex', alignItems: 'center' }}>
              <div className="panel-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                Task Graph
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '8px' }}>
                  v{state.version}
                </span>
              </div>
              <button
                className="role-btn"
                style={{
                  marginLeft: 'auto',
                  fontSize: '0.75rem',
                  padding: '4px 10px',
                  height: 'auto',
                  borderColor: isEditingPlan ? 'var(--color-primary)' : 'var(--border-color)',
                  backgroundColor: isEditingPlan ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                }}
                onClick={() => {
                  setIsEditingPlan(!isEditingPlan);
                  setEditingNodeId(null);
                  setIsAddingNode(false);
                  setIsAddingEdge(false);
                  setValidationError(null);
                }}
              >
                {isEditingPlan ? "View Mode" : "Edit Plan"}
              </button>
            </header>

            <div className="panel-body list-scrollable">
              {validationError && (
                <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', border: '1px solid #ef4444', borderRadius: '6px', padding: '10px 12px', marginBottom: '12px', fontSize: '0.78rem', color: '#fca5a5', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{validationError}</span>
                  <button onClick={() => setValidationError(null)} style={{ background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer', fontSize: '1rem', fontWeight: 'bold' }}>&times;</button>
                </div>
              )}

              {isEditingPlan && (
                <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                  <button
                    className="chat-send-btn"
                    style={{ fontSize: '0.75rem', padding: '6px 12px', height: 'auto', background: isAddingNode ? 'var(--bg-panel-active)' : 'linear-gradient(135deg, var(--color-primary), var(--color-accent))' }}
                    onClick={() => {
                      setIsAddingNode(!isAddingNode);
                      setIsAddingEdge(false);
                      setEditingNodeId(null);
                    }}
                  >
                    + Add Task
                  </button>
                  <button
                    className="role-btn"
                    style={{ fontSize: '0.75rem', padding: '6px 12px', height: 'auto' }}
                    onClick={() => {
                      setIsAddingEdge(!isAddingEdge);
                      setIsAddingNode(false);
                      setEditingNodeId(null);
                    }}
                  >
                    + Add Link
                  </button>
                </div>
              )}

              {/* Add Node Form */}
              {isEditingPlan && isAddingNode && (
                <div style={{ backgroundColor: 'var(--bg-panel-light)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontWeight: '600', fontSize: '0.8rem', color: 'var(--text-main)' }}>Add Task Node</div>
                  <input
                    type="text"
                    placeholder="Task Title (e.g. Run tests)"
                    value={newNodeTitle}
                    onChange={(e) => setNewNodeTitle(e.target.value)}
                    style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 10px', fontSize: '0.78rem', color: '#fff' }}
                  />
                  <textarea
                    placeholder="Description..."
                    value={newNodeDesc}
                    onChange={(e) => setNewNodeDesc(e.target.value)}
                    style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 10px', fontSize: '0.78rem', color: '#fff', minHeight: '50px', resize: 'vertical' }}
                  />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <select
                      value={newNodeAgentType}
                      onChange={(e) => setNewNodeAgentType(e.target.value)}
                      style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="coder">Coder</option>
                      <option value="planner">Planner</option>
                      <option value="tester">Tester</option>
                      <option value="browser">Browser Agent</option>
                    </select>
                    <select
                      value={newNodeStatus}
                      onChange={(e) => setNewNodeStatus(e.target.value)}
                      style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="blocked">Blocked</option>
                      <option value="ready">Ready</option>
                      <option value="draft">Draft</option>
                    </select>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
                    <button className="role-btn" style={{ padding: '4px 10px', fontSize: '0.72rem', height: 'auto' }} onClick={() => setIsAddingNode(false)}>Cancel</button>
                    <button className="chat-send-btn" style={{ padding: '4px 12px', fontSize: '0.72rem', height: 'auto' }} onClick={handleAddNode}>Add Node</button>
                  </div>
                </div>
              )}

              {/* Add Edge Form */}
              {isEditingPlan && isAddingEdge && (
                <div style={{ backgroundColor: 'var(--bg-panel-light)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontWeight: '600', fontSize: '0.8rem', color: 'var(--text-main)' }}>Add Dependency Link</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                    <label>Prerequisite Task:</label>
                    <select
                      value={edgeFrom}
                      onChange={(e) => setEdgeFrom(e.target.value)}
                      style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="">-- Select Prerequisite --</option>
                      {Object.values(state.taskNodes).map((node) => (
                        <option key={node.id} value={node.id}>{node.title} ({node.id})</option>
                      ))}
                    </select>
                    <label style={{ marginTop: '4px' }}>Dependent Task:</label>
                    <select
                      value={edgeTo}
                      onChange={(e) => setEdgeTo(e.target.value)}
                      style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="">-- Select Target --</option>
                      {Object.values(state.taskNodes).map((node) => (
                        <option key={node.id} value={node.id}>{node.title} ({node.id})</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '4px' }}>
                    <button className="role-btn" style={{ padding: '4px 10px', fontSize: '0.72rem', height: 'auto' }} onClick={() => setIsAddingEdge(false)}>Cancel</button>
                    <button className="chat-send-btn" style={{ padding: '4px 12px', fontSize: '0.72rem', height: 'auto' }} onClick={handleAddEdge}>Add Link</button>
                  </div>
                </div>
              )}

              {/* Edit Node Form */}
              {isEditingPlan && editingNodeId && (
                <div style={{ backgroundColor: 'var(--bg-panel-light)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '12px', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontWeight: '600', fontSize: '0.8rem', color: 'var(--color-primary)' }}>Edit Task Node: {editingNodeId}</div>
                  <input
                    type="text"
                    placeholder="Title"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 10px', fontSize: '0.78rem', color: '#fff' }}
                  />
                  <textarea
                    placeholder="Description..."
                    value={editDesc}
                    onChange={(e) => setEditDesc(e.target.value)}
                    style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px 10px', fontSize: '0.78rem', color: '#fff', minHeight: '50px', resize: 'vertical' }}
                  />
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <select
                      value={editAgentType}
                      onChange={(e) => setEditAgentType(e.target.value)}
                      style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="coder">Coder</option>
                      <option value="planner">Planner</option>
                      <option value="tester">Tester</option>
                      <option value="browser">Browser Agent</option>
                    </select>
                    <select
                      value={editStatus}
                      onChange={(e) => setEditStatus(e.target.value)}
                      style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="draft">Draft</option>
                      <option value="blocked">Blocked</option>
                      <option value="ready">Ready</option>
                      <option value="assigned">Assigned</option>
                      <option value="running">Running</option>
                      <option value="completed">Completed</option>
                      <option value="failed">Failed</option>
                      <option value="cancelled">Cancelled</option>
                    </select>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Assigned Agent Instance:</label>
                    <select
                      value={editAssignee}
                      onChange={(e) => setEditAssignee(e.target.value)}
                      style={{ backgroundColor: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', fontSize: '0.78rem', color: '#fff' }}
                    >
                      <option value="">-- Unassigned --</option>
                      {state.agentOrder.map((aId) => (
                        <option key={aId} value={aId}>{state.agents[aId]?.agent_type} ({aId})</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', marginTop: '4px' }}>
                    <button className="btn-danger-action" style={{ padding: '4px 10px', fontSize: '0.72rem', height: 'auto' }} onClick={() => handleDeleteNode(editingNodeId)}>Delete Node</button>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="role-btn" style={{ padding: '4px 10px', fontSize: '0.72rem', height: 'auto' }} onClick={() => setEditingNodeId(null)}>Cancel</button>
                      <button className="chat-send-btn" style={{ padding: '4px 12px', fontSize: '0.72rem', height: 'auto' }} onClick={handleSaveNode}>Save</button>
                    </div>
                  </div>
                </div>
              )}

              {state.taskEdges.length === 0 && Object.keys(state.taskNodes).length === 0 && (
                <div className="empty-panel-text">No active task plan.</div>
              )}

              <div className="task-graph-nodes-container">
                {Object.values(state.taskNodes).map((n) => {
                  const prereqs = getPrerequisites(n.id);
                  const isNodeEditing = editingNodeId === n.id;
                  
                  return (
                    <div
                      key={n.id}
                      className={`task-graph-node-card ${n.status} ${isEditingPlan ? 'editable' : ''}`}
                      style={isEditingPlan ? {
                        cursor: 'pointer',
                        border: isNodeEditing ? '1px solid var(--color-primary)' : '1px solid var(--border-color)',
                        boxShadow: isNodeEditing ? '0 0 10px var(--border-glow)' : 'none'
                      } : undefined}
                      onClick={isEditingPlan ? () => {
                        setEditingNodeId(n.id);
                        setEditTitle(n.title);
                        setEditDesc(n.description || "");
                        setEditAgentType(n.agent_type || "coder");
                        setEditStatus(n.status);
                        setEditAssignee(n.assigned_agent || "");
                        setIsAddingNode(false);
                        setIsAddingEdge(false);
                      } : undefined}
                    >
                      <div className="node-top-bar">
                        <div className="node-title-group">
                          <span className={`node-status-indicator ${n.status}`} />
                          <span className="node-title">{n.title}</span>
                        </div>
                        <span className={`node-status-text ${n.status}`}>{n.status}</span>
                      </div>

                      {n.description && (
                        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', margin: '6px 0 2px 0' }}>
                          {n.description}
                        </div>
                      )}

                      <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '0.72rem' }}>
                        {n.assigned_agent && (
                          <div className="node-assignee" style={{ margin: 0 }}>
                            <span className="assignee-label">Assignee:</span>
                            <span className="assignee-value">{state.agents[n.assigned_agent]?.agent_type || n.assigned_agent}</span>
                          </div>
                        )}
                        {n.agent_type && (
                          <div style={{ color: 'var(--text-muted)' }}>
                            <span style={{ fontWeight: '500' }}>Role:</span> <span style={{ color: 'var(--text-main)' }}>{n.agent_type}</span>
                          </div>
                        )}
                      </div>

                      {prereqs.length > 0 && (
                        <div className="node-prerequisites">
                          <span className="prereq-label">Prerequisites:</span>
                          <div className="prereq-pills">
                            {prereqs.map((title, pidx) => (
                              <span key={pidx} className="prereq-pill">
                                {title}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Inline Task Execution Control Buttons */}
                      {!isEditingPlan && (
                        <div className="node-controls" style={{ display: 'flex', gap: '6px', marginTop: '10px', borderTop: '1px dashed var(--border-color)', paddingTop: '8px', justifyContent: 'flex-end' }}>
                          {n.status === "running" && (
                            <button
                              className="role-btn"
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: 'auto', borderColor: '#f59e0b', color: '#f59e0b' }}
                              onClick={(e) => { e.stopPropagation(); handlePauseTask(n.id); }}
                            >
                              Pause
                            </button>
                          )}
                          {n.status === "paused" && (
                            <button
                              className="role-btn"
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: 'auto', borderColor: '#10b981', color: '#10b981' }}
                              onClick={(e) => { e.stopPropagation(); handleResumeTask(n.id); }}
                            >
                              Resume
                            </button>
                          )}
                          {(n.status === "running" || n.status === "ready") && (
                            <button
                              className="btn-danger-action"
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: 'auto' }}
                              onClick={(e) => { e.stopPropagation(); handleCancelTask(n.id); }}
                            >
                              Cancel
                            </button>
                          )}
                          {n.status === "failed" && (
                            <button
                              className="role-btn"
                              style={{ padding: '2px 8px', fontSize: '0.7rem', height: 'auto', borderColor: '#f59e0b', color: '#f59e0b' }}
                              onClick={(e) => { e.stopPropagation(); handleRetryTask(n.id); }}
                            >
                              Retry
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Dependency Edges List */}
              {isEditingPlan && state.taskEdges.length > 0 && (
                <div style={{ marginTop: '20px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
                  <div style={{ fontWeight: '600', fontSize: '0.82rem', marginBottom: '8px', color: 'var(--text-main)' }}>Prerequisite Link List</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {state.taskEdges.map((e, idx) => {
                      const fromNode = state.taskNodes[e.from];
                      const toNode = state.taskNodes[e.to];
                      return (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '6px 10px', fontSize: '0.76rem' }}>
                          <span>
                            <strong style={{ color: 'var(--color-warning)' }}>{fromNode?.title || e.from}</strong>
                            <span style={{ color: 'var(--text-muted)', margin: '0 6px' }}>&rarr;</span>
                            <strong style={{ color: 'var(--color-success)' }}>{toNode?.title || e.to}</strong>
                          </span>
                          <button
                            className="btn-danger-action"
                            style={{ padding: '2px 6px', fontSize: '0.7rem', height: 'auto', border: 'none', background: 'transparent' }}
                            onClick={(evt) => {
                              evt.stopPropagation();
                              if (window.confirm("Remove this dependency link?")) {
                                handleDeleteEdge(e.from, e.to);
                              }
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        {/* COLUMN 3: Agent Inspector */}
        <section className="dashboard-panel inspector-panel-glass">
          {!selected ? (
            <div className="inspector-empty-state">
              <div className="empty-icon-wrapper">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.3 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              </div>
              <h3>No Agent Selected</h3>
              <p>Select a sub-agent from the board to inspect logs and browser preview.</p>
            </div>
          ) : (
            <>
              <header className="panel-header inspector-header-glass">
                <div className="panel-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                  </svg>
                  Inspector: {selected.agent_type}
                </div>

                <div className="inspector-controls">
                  {selected.session_id && (
                    <button
                      className="terminal-control-btn btn-danger-action"
                      title="Stop execution session"
                      onClick={() => controlSession(selected.session_id!, "stop")}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                      Stop
                    </button>
                  )}
                </div>
              </header>

              <div className="inspector-sub-header">
                <div className="inspector-meta-row">
                  <div className="meta-badge-item">
                    <span className="meta-label">Status:</span>
                    <span className={`meta-value status-pill ${selected.status}`}>
                      {selected.status}
                    </span>
                  </div>
                  <div className="meta-badge-item">
                    <span className="meta-label">Run:</span>
                    <span className="meta-value text-capitalize">
                      {selected.run_status ?? "idle"}
                    </span>
                  </div>
                </div>

                {/* Tab Navigation */}
                <div className="tab-nav-container">
                  <button
                    className={`tab-nav-btn ${inspectorTab === "terminal" ? "active" : ""}`}
                    onClick={() => setInspectorTab("terminal")}
                  >
                    Terminal Logs
                  </button>
                  <button
                    className={`tab-nav-btn ${inspectorTab === "browser" ? "active" : ""}`}
                    onClick={() => setInspectorTab("browser")}
                  >
                    Web Browser
                  </button>
                </div>
              </div>

              {/* Viewport Content */}
              {inspectorTab === "terminal" ? (
                <div className="panel-body terminal-body retro-terminal">
                  <div className="terminal-scanlines" />
                  <div className="terminal-lines-scroll">
                    {termLines.map((line, i) => colorizeLine(line, i))}
                    {termLines.length === 0 && (
                      <div className="term-line dimmed-text">Waiting for terminal streams...</div>
                    )}
                    <div ref={termEndRef} />
                  </div>
                </div>
              ) : (
                <div className="panel-body browser-mock-viewport">
                  {/* Browser Mock Wrapper */}
                  <div className="browser-header">
                    <div className="browser-actions">
                      <button className="browser-nav-btn">◀</button>
                      <button className="browser-nav-btn">▶</button>
                      <button className="browser-nav-btn">↻</button>
                    </div>
                    <div className="browser-address-bar">
                      <input
                        type="text"
                        value={browserUrl}
                        onChange={(e) => setBrowserUrl(e.target.value)}
                        className="browser-url-input"
                      />
                    </div>
                  </div>

                  <div className="browser-viewport">
                    <div className="awesome-app">
                      <aside className="aa-sidebar">
                        <div>
                          <div className="aa-brand">Awesome App</div>
                          <nav className="aa-nav">
                            <div
                              className={`aa-nav-item ${browserTab === "overview" ? "active" : ""}`}
                              onClick={() => setBrowserTab("overview")}
                            >
                              Overview
                            </div>
                            <div
                              className={`aa-nav-item ${browserTab === "projects" ? "active" : ""}`}
                              onClick={() => setBrowserTab("projects")}
                            >
                              Projects
                            </div>
                            <div
                              className={`aa-nav-item ${browserTab === "analytics" ? "active" : ""}`}
                              onClick={() => setBrowserTab("analytics")}
                            >
                              Analytics
                            </div>
                            <div
                              className={`aa-nav-item ${browserTab === "settings" ? "active" : ""}`}
                              onClick={() => setBrowserTab("settings")}
                            >
                              Settings
                            </div>
                          </nav>
                        </div>
                      </aside>

                      <main className="aa-content">
                        {browserTab === "overview" && (
                          <>
                            <div className="aa-header">
                              <div className="aa-title">Overview</div>
                              <div className="aa-desc">Active agent dashboard preview.</div>
                            </div>
                            <div className="aa-cards">
                              <div className="aa-card">
                                <div className="aa-card-label">Total Users</div>
                                <div className="aa-card-value">12,842</div>
                              </div>
                              <div className="aa-card">
                                <div className="aa-card-label">Active Session</div>
                                <div className="aa-card-value">1</div>
                              </div>
                            </div>
                            <div className="aa-chart-panel" style={{ border: "1px dashed rgba(255,255,255,0.08)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
                              <span style={{ color: "var(--text-muted)", fontSize: "0.74rem" }}>Visual Canvas render complete</span>
                            </div>
                          </>
                        )}
                        {browserTab === "projects" && (
                          <>
                            <div className="aa-header">
                              <div className="aa-title">Projects</div>
                              <div className="aa-desc">WindAgent generated node instances.</div>
                            </div>
                            <div className="aa-card">
                              <div className="aa-card-value" style={{ fontSize: "0.85rem" }}>windagent-api</div>
                              <div className="aa-card-label">FastAPI backend engine</div>
                            </div>
                          </>
                        )}
                        {browserTab === "analytics" && (
                          <div style={{ padding: 16, color: "var(--text-muted)" }}>
                            Performance indices are parsed inside Terminal console.
                          </div>
                        )}
                        {browserTab === "settings" && (
                          <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 6 }}>
                            <label style={{ display: "flex", gap: 6 }}>
                              <input type="checkbox" defaultChecked /> Safe script execution
                            </label>
                            <label style={{ display: "flex", gap: 6 }}>
                              <input type="checkbox" defaultChecked /> Event loop logging
                            </label>
                          </div>
                        )}
                      </main>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>

      {/* Floating Permission Gating Overlay */}
      {permissionQueue && permissionQueue.length > 0 && (
        <div
          style={{
            position: 'fixed',
            bottom: '24px',
            right: '24px',
            width: '360px',
            backgroundColor: 'rgba(30, 41, 59, 0.95)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '12px',
            padding: '16px',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.6), 0 10px 10px -5px rgba(0, 0, 0, 0.6)',
            zIndex: 1000,
            animation: 'slideUp 0.3s ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <svg width="20" height="20" fill="none" stroke="#f59e0b" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span style={{ fontWeight: '600', color: 'var(--text-main)', fontSize: '0.9rem' }}>Permission Required</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div>The agent is requesting permission to execute:</div>
            <div style={{ color: 'var(--text-main)', fontWeight: 'bold', fontSize: '0.85rem' }}>{String(permissionQueue[0].tool_name)}</div>
            
            {permissionQueue[0].params && (permissionQueue[0].params as Record<string, unknown>).command ? (
              <pre
                style={{
                  backgroundColor: 'rgba(0,0,0,0.4)',
                  padding: '8px',
                  borderRadius: '6px',
                  fontFamily: 'monospace',
                  fontSize: '0.72rem',
                  color: '#34d399',
                  overflowX: 'auto',
                  whiteSpace: 'pre-wrap',
                  maxHeight: '100px',
                  border: '1px solid rgba(255,255,255,0.05)',
                  margin: '4px 0',
                }}
              >
                {String((permissionQueue[0].params as Record<string, unknown>).command)}
              </pre>
            ) : null}
            
            <div style={{ marginTop: '4px', fontSize: '0.74rem' }}>
              Risk Level: <span style={{ color: permissionQueue[0].risk_level === 'high' ? '#ef4444' : '#f59e0b', fontWeight: '600' }}>{String(permissionQueue[0].risk_level).toUpperCase()}</span>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button
              className="btn-danger-action"
              style={{ padding: '6px 12px', fontSize: '0.75rem', height: 'auto', backgroundColor: 'rgba(255,255,255,0.05)', color: 'var(--text-main)' }}
              onClick={() => resolvePermission(permissionQueue[0].request_id, "denied")}
            >
              Deny
            </button>
            <button
              className="chat-send-btn"
              style={{ padding: '6px 16px', fontSize: '0.75rem', height: 'auto', background: 'linear-gradient(135deg, #f59e0b, #d97706)', border: 'none', color: '#fff' }}
              onClick={() => resolvePermission(permissionQueue[0].request_id, "granted")}
            >
              Approve
            </button>
          </div>
        </div>
      )}

      {/* Conflict UI Overlay */}
      {conflictError && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            backgroundColor: 'rgba(0, 0, 0, 0.8)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 10000,
          }}
        >
          <div
            style={{
              width: '400px',
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid #ef4444',
              borderRadius: '12px',
              padding: '24px',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px',
              textAlign: 'center',
            }}
          >
            <div style={{ color: '#ef4444', display: 'flex', justifyContent: 'center' }}>
              <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 style={{ fontSize: '1.2rem', fontWeight: 'bold', color: 'var(--text-main)' }}>Plan Edit Conflict</h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
              Bản kế hoạch trên hệ thống đã bị chỉnh sửa bởi một tiến trình khác. Vui lòng đồng bộ hóa để cập nhật các thay đổi mới nhất.
            </p>
            <button
              className="chat-send-btn"
              style={{ width: '100%', padding: '10px', fontSize: '0.85rem', height: 'auto', background: 'linear-gradient(135deg, var(--color-primary), var(--color-accent))', border: 'none', color: '#fff' }}
              onClick={() => {
                setConflictError(null);
                setValidationError(null);
                setIsEditingPlan(false);
                setEditingNodeId(null);
                useMultiAgentStore.getState().refresh();
              }}
            >
              Sync Latest Plan
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
