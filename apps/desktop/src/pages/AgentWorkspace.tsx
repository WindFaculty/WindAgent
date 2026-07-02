import React, { useRef, useEffect } from "react";

interface ChecklistState {
  repoDiscovered: "success" | "pending" | "running";
  scanningStructure: "success" | "pending" | "running";
  runningTests: "success" | "pending" | "running";
  summarizingResults: "success" | "pending" | "running";
  summarizingProgress: number;
}

interface CurrentTaskStep {
  name: string;
  status: "success" | "pending" | "running";
  duration: string;
}

interface AgentWorkspaceProps {
  chatMessages: Array<{
    sender: "user" | "assistant";
    time: string;
    text: string;
    checklist?: ChecklistState;
  }>;
  currentTaskSteps: CurrentTaskStep[];
  terminalLines: string[];
  setTerminalLines: React.Dispatch<React.SetStateAction<string[]>>;
  browserUrl: string;
  setBrowserUrl: (url: string) => void;
  browserTab: string;
  setBrowserTab: (tab: string) => void;
  chatInput: string;
  setChatInput: (val: string) => void;
  handleSend: (e: React.FormEvent) => void;
}

export function AgentWorkspace({
  chatMessages,
  currentTaskSteps,
  terminalLines,
  setTerminalLines,
  browserUrl,
  setBrowserUrl,
  browserTab,
  setBrowserTab,
  chatInput,
  setChatInput,
  handleSend,
}: AgentWorkspaceProps) {
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll terminal and chat
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [terminalLines]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  return (
    <main className="central-workspace">
      <div className="workspace-grid">
        {/* Top Left Panel: Agent Chat */}
        <section className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              Agent Workspace / Chat
            </div>
            <span className="live-indicator">
              <span className="live-dot" />
              LIVE
            </span>
          </header>
          <div className="panel-body chat-container">
            {chatMessages.map((msg, idx) => (
              <div key={idx} className={`chat-bubble ${msg.sender}`}>
                <div className="bubble-header">
                  <span className="avatar-initial">
                    {msg.sender === "user" ? "U" : "WA"}
                  </span>
                  <span className="sender-name">
                    {msg.sender === "user" ? "You" : "WindAgent"}
                  </span>
                  <span className="chat-time">{msg.time}</span>
                </div>
                <div className="bubble-content" style={{ whiteSpace: "pre-line" }}>
                  {msg.text}

                  {/* Checklist structure */}
                  {msg.checklist && (
                    <div className="chat-checklist">
                      <div className="checklist-item">
                        <div className="checklist-left">
                          {msg.checklist.repoDiscovered === "success" ? (
                            <svg className="check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <div className="check-spinner" />
                          )}
                          Repository discovered
                        </div>
                        <span className="checklist-time">1.2s</span>
                      </div>
                      <div className="checklist-item">
                        <div className="checklist-left">
                          {msg.checklist.scanningStructure === "success" ? (
                            <svg className="check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : msg.checklist.scanningStructure === "running" ? (
                            <div className="check-spinner" />
                          ) : (
                            <svg className="check-icon pending" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          )}
                          Scanning file structure
                        </div>
                        <span className="checklist-time">
                          {msg.checklist.scanningStructure === "pending" ? "--" : "2.1s"}
                        </span>
                      </div>
                      <div className="checklist-item">
                        <div className="checklist-left">
                          {msg.checklist.runningTests === "success" ? (
                            <svg className="check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : msg.checklist.runningTests === "running" ? (
                            <div className="check-spinner" />
                          ) : (
                            <svg className="check-icon pending" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          )}
                          Running tests
                        </div>
                        <span className="checklist-time">
                          {msg.checklist.runningTests === "pending" ? "--" : "4.8s"}
                        </span>
                      </div>
                      <div className="checklist-item">
                        <div className="checklist-left">
                          {msg.checklist.summarizingResults === "success" ? (
                            <svg className="check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : msg.checklist.summarizingResults === "running" ? (
                            <div className="check-spinner" />
                          ) : (
                            <svg className="check-icon pending" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          )}
                          Summarizing results
                        </div>
                        <span className="checklist-time">
                          {msg.checklist.summarizingResults === "running"
                            ? `Streaming... ${msg.checklist.summarizingProgress}%`
                            : msg.checklist.summarizingResults === "success"
                            ? "100%"
                            : "--"}
                        </span>
                      </div>

                      {/* Blue Glowing Progress bar */}
                      <div className="chat-progress-container">
                        <div className="progress-bar-bg">
                          <div
                            className="progress-bar-fill"
                            style={{ width: `${msg.checklist.summarizingProgress}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        </section>

        {/* Top Right Panel: Current Task */}
        <section className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
              Current Task
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="role-btn" style={{ padding: '4px 8px', fontSize: '0.75rem', height: 'auto' }}>
                View Details
              </button>
              <button className="terminal-control-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </header>
          <div className="panel-body">
            <div className="current-task-info">
              <div className="current-task-name">Project Analysis</div>
              <div className="current-task-desc">Full repository analysis and insights</div>
            </div>

            <div className="task-steps-list">
              {currentTaskSteps.map((step, idx) => (
                <div
                  key={idx}
                  className={`task-step ${step.status === "running" ? "active" : ""} ${
                    step.status === "pending" ? "pending" : ""
                  }`}
                >
                  <div className="task-step-left">
                    <div className={`step-chk ${step.status}`}>
                      {step.status === "success" && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                        </svg>
                      )}
                      {step.status === "running" && (
                        <div className="check-spinner" style={{ width: '10px', height: '10px' }} />
                      )}
                      {step.status === "pending" && <span style={{ width: '4px', height: '4px', background: 'var(--text-dim)', borderRadius: '50%' }} />}
                    </div>
                    <span className="step-label">{step.name}</span>
                  </div>

                  <div className="step-meta-right">
                    <span className={`step-badge ${step.status}`}>
                      {step.status === "success"
                        ? "Completed"
                        : step.status === "running"
                        ? "In Progress"
                        : "Pending"}
                    </span>
                    <span className={`step-duration ${step.status === "running" ? "active" : ""}`}>
                      {step.duration}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Bottom Left Panel: Terminal Logs */}
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
              <button className="terminal-control-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
              </button>
              <button className="terminal-control-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16m-7 6h7" />
                </svg>
              </button>
              <button
                className="terminal-control-btn"
                onClick={() => setTerminalLines([])}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </header>
          <div className="panel-body terminal-body">
            {terminalLines.map((line, idx) => {
              let className = "term-line";
              if (
                line.startsWith("git clone") ||
                line.startsWith("cd ") ||
                line.startsWith("npm install") ||
                line.startsWith("npm test")
              ) {
                className += " cmd";
              } else if (line.startsWith("PASS")) {
                return (
                  <div key={idx} className="term-line green">
                    <span className="term-line pass">PASS</span>
                    {line.replace("PASS", "").trim()}
                  </div>
                );
              } else if (line.includes("Scanning") || line.includes("Cloning")) {
                className += " yellow";
              } else if (line.startsWith("added") || line.includes("passed")) {
                className += " green";
              }
              return (
                <div key={idx} className={className}>
                  {line}
                </div>
              );
            })}
            <div ref={terminalEndRef} />
          </div>
        </section>

        {/* Bottom Right Panel: Interactive Browser Preview */}
        <section className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              Browser / App Preview
            </div>
          </header>
          <div className="browser-header">
            <div className="browser-actions" style={{ gap: '2px' }}>
              <button className="browser-nav-btn">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
                </svg>
              </button>
              <button className="browser-nav-btn">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                </svg>
              </button>
              <button
                className="browser-nav-btn"
                onClick={() => {
                  setTerminalLines((prev) => [...prev, "Reloading App Preview viewport..."]);
                }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                </svg>
              </button>
            </div>

            <div className="browser-address-bar">
              <input
                type="text"
                value={browserUrl}
                onChange={(e) => setBrowserUrl(e.target.value)}
                style={{
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "inherit",
                  fontFamily: "inherit",
                  fontSize: "inherit",
                  width: "100%",
                }}
              />
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>

            <div className="browser-actions">
              <button className="browser-nav-btn">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </button>
              <button className="browser-nav-btn">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
              </button>
              <button className="browser-nav-btn">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </button>
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
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                      </svg>
                      Overview
                    </div>
                    <div
                      className={`aa-nav-item ${browserTab === "projects" ? "active" : ""}`}
                      onClick={() => setBrowserTab("projects")}
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                      </svg>
                      Projects
                    </div>
                    <div
                      className={`aa-nav-item ${browserTab === "analytics" ? "active" : ""}`}
                      onClick={() => setBrowserTab("analytics")}
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 00-2 2h-2a2 2 0 00-2-2z" />
                      </svg>
                      Analytics
                    </div>
                    <div
                      className={`aa-nav-item ${browserTab === "settings" ? "active" : ""}`}
                      onClick={() => setBrowserTab("settings")}
                    >
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      </svg>
                      Settings
                    </div>
                  </nav>
                </div>
                <div className="aa-profile">
                  <div className="aa-profile-name">Admin</div>
                  <div className="aa-profile-email" title="admin@example.com">
                    admin@example.com
                  </div>
                </div>
              </aside>

              <main className="aa-content">
                {browserTab === "overview" && (
                  <>
                    <div className="aa-header">
                      <div className="aa-title">Overview</div>
                      <div className="aa-desc">Welcome back! Here's what's happening.</div>
                    </div>

                    <div className="aa-cards">
                      <div className="aa-card">
                        <div className="aa-card-label">Total Users</div>
                        <div className="aa-card-value">12,842</div>
                        <div className="aa-card-trend trend-up">▲ 12.5% vs last month</div>
                      </div>
                      <div className="aa-card">
                        <div className="aa-card-label">Active Users</div>
                        <div className="aa-card-value">2,431</div>
                        <div className="aa-card-trend trend-up">▲ 8.2% vs last month</div>
                      </div>
                      <div className="aa-card">
                        <div className="aa-card-label">Revenue</div>
                        <div className="aa-card-value">$24,780</div>
                        <div className="aa-card-trend trend-up">▲ 15.3% vs last month</div>
                      </div>
                      <div className="aa-card">
                        <div className="aa-card-label">Conversion</div>
                        <div className="aa-card-value">3.24%</div>
                        <div className="aa-card-trend trend-down">▼ 0.4% vs last month</div>
                      </div>
                    </div>

                    <div className="aa-chart-panel">
                      <div className="aa-chart-header">
                        <div className="aa-chart-title">Activity Overview</div>
                        <select className="aa-chart-select">
                          <option>This Week</option>
                        </select>
                      </div>
                      <svg className="aa-chart-svg" viewBox="0 0 300 50">
                        <defs>
                          <linearGradient id="chart-grad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
                            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                          </linearGradient>
                        </defs>
                        <path
                          className="aa-chart-path"
                          d="M 0,38 Q 30,20 60,35 T 120,15 T 180,40 T 240,18 T 300,28"
                        />
                        <path
                          className="aa-chart-area"
                          d="M 0,38 Q 30,20 60,35 T 120,15 T 180,40 T 240,18 T 300,28 L 300,50 L 0,50 Z"
                        />
                      </svg>
                    </div>
                  </>
                )}

                {browserTab === "projects" && (
                  <>
                    <div className="aa-header">
                      <div className="aa-title">Projects</div>
                      <div className="aa-desc">Manage your workspace development nodes.</div>
                    </div>
                    <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: '1fr 1fr' }}>
                      <div className="aa-card">
                        <div className="aa-card-value" style={{ fontSize: '0.9rem' }}>awesome-app-api</div>
                        <div className="aa-card-label" style={{ marginTop: '2px' }}>Node / Express API Server</div>
                      </div>
                      <div className="aa-card">
                        <div className="aa-card-value" style={{ fontSize: '0.9rem' }}>awesome-app-db</div>
                        <div className="aa-card-label" style={{ marginTop: '2px' }}>PostgreSQL Cluster</div>
                      </div>
                    </div>
                  </>
                )}

                {browserTab === "analytics" && (
                  <>
                    <div className="aa-header">
                      <div className="aa-title">Analytics</div>
                      <div className="aa-desc">Detailed usage rates and traffic flow.</div>
                    </div>
                    <div className="aa-card" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Interactive logs generated in main Terminal.</span>
                    </div>
                  </>
                )}

                {browserTab === "settings" && (
                  <>
                    <div className="aa-header">
                      <div className="aa-title">Settings</div>
                      <div className="aa-desc">Configuration and webhook routes.</div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input type="checkbox" defaultChecked /> Safe mode limits
                      </label>
                      <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input type="checkbox" defaultChecked /> Auto Refresh Preview
                      </label>
                    </div>
                  </>
                )}
              </main>
            </div>
          </div>
        </section>
      </div>

      {/* Interactive Bottom Chat Input inside workspace */}
      <form className="chat-input-bar" onSubmit={handleSend}>
        <input
          type="text"
          className="chat-input-field"
          placeholder="Ask WindAgent to run terminal commands, inspect files, or edit codes..."
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
        />
        <button type="submit" className="chat-send-btn">
          Send Query
        </button>
      </form>
    </main>
  );
}
