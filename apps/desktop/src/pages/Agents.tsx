import { useState } from "react";

interface AgentItem {
  id: string;
  name: string;
  subName: string;
  status: "Running" | "Busy" | "Idle" | "Offline";
  model: string;
  currentTask: string;
  uptime: string;
  rt: string;
  sr: string;
  sparkPoints: string;
  description: string;
  tools: string[];
  memoryVal: string;
  memoryMax: string;
  memoryPct: number;
  recentActions: string[];
}

interface AgentsProps {
  setActiveTab: (tab: string) => void;
}

export function Agents({ setActiveTab }: AgentsProps) {
  const [selectedAgentId, setSelectedAgentId] = useState<string>("coder");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  // Agent Directory dataset
  const agentsData: AgentItem[] = [
    {
      id: "planner",
      name: "Planner",
      subName: "Task Planning",
      status: "Running",
      model: "Llama 3 70B",
      currentTask: "Decomposing project requirements",
      uptime: "2h 14m",
      rt: "1.12s",
      sr: "96%",
      sparkPoints: "0,20 15,18 30,22 45,12 60,6 68,14",
      description: "Decomposes complex requests into structured sub-tasks. Guides execution and verifies outcomes.",
      tools: ["File System", "Code Analyzer", "Docs"],
      memoryVal: "4.2 GB",
      memoryMax: "16 GB",
      memoryPct: 26,
      recentActions: [
        "Created execution plan",
        "Decomposed workspace requirements",
        "Read local README.md",
      ],
    },
    {
      id: "gui",
      name: "GUI Agent",
      subName: "UI/UX Automation",
      status: "Running",
      model: "Mixtral 8x7B Instruct",
      currentTask: "Building user interface components",
      uptime: "1h 42m",
      rt: "1.36s",
      sr: "94%",
      sparkPoints: "0,22 15,18 30,12 45,20 60,10 68,4",
      description: "Automates browser previews and compiles React UI layouts. Tests UI rendering against specifications.",
      tools: ["Browser", "File System", "Terminal"],
      memoryVal: "5.1 GB",
      memoryMax: "12 GB",
      memoryPct: 42,
      recentActions: [
        "Compiled LoginForm component",
        "Rendered browser overview card",
        "Fetched Google fonts bundle",
      ],
    },
    {
      id: "coder",
      name: "Coder",
      subName: "Code Generation",
      status: "Busy",
      model: "Codestral 22B",
      currentTask: "Implementing authentication module",
      uptime: "38m",
      rt: "1.78s",
      sr: "91%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Generates, refactors, and debugs code. Writes clean, testable, and well-documented solutions.",
      tools: ["File System", "Terminal", "Git", "Code Analyzer", "Docs", "Tests"],
      memoryVal: "6.2 GB",
      memoryMax: "10 GB",
      memoryPct: 62,
      recentActions: [
        "Updated auth_service.ts",
        "Ran unit tests (auth module)",
        "Created jwt_utils.ts",
        "Read requirements.md",
      ],
    },
    {
      id: "researcher",
      name: "Researcher",
      subName: "Web Research",
      status: "Running",
      model: "Perplexity Sonar Large",
      currentTask: "Ready for new research task",
      uptime: "45m",
      rt: "1.25s",
      sr: "95%",
      sparkPoints: "0,18 15,10 30,12 45,8 60,10 68,4",
      description: "Conducts web search and retrieves documentation. Synthesizes codebase context and external assets.",
      tools: ["Web Search", "Docs", "File System"],
      memoryVal: "3.8 GB",
      memoryMax: "8 GB",
      memoryPct: 47,
      recentActions: [
        "Completed web search for auth libraries",
        "Extracted JWT token guidelines",
        "Summarized oauth patterns",
      ],
    },
    {
      id: "browser",
      name: "Browser Agent",
      subName: "Web Automation",
      status: "Idle",
      model: "GPT-4o Mini",
      currentTask: "Waiting for tasks",
      uptime: "18m",
      rt: "0.98s",
      sr: "98%",
      sparkPoints: "0,22 15,14 30,18 45,8 60,12 68,6",
      description: "Controls active browser sessions, capturing logs, screenshots, and DOM states for visual validation.",
      tools: ["Browser", "File System", "Terminal"],
      memoryVal: "2.4 GB",
      memoryMax: "8 GB",
      memoryPct: 30,
      recentActions: [
        "Captured preview page screenshot",
        "Loaded localhost:3000 console logs",
        "Verified CSS styling compliance",
      ],
    },
    {
      id: "memory",
      name: "Memory Agent",
      subName: "Knowledge Manager",
      status: "Offline",
      model: "Phi-3 Medium 4K",
      currentTask: "—",
      uptime: "—",
      rt: "—",
      sr: "—",
      sparkPoints: "0,20 15,20 30,20 45,20 60,20 68,20",
      description: "Manages contextual memory vector graphs. Prunes stale dependencies and saves session states.",
      tools: ["Vector DB", "File System"],
      memoryVal: "0 GB",
      memoryMax: "8 GB",
      memoryPct: 0,
      recentActions: [
        "Indexed repository files structure",
        "Cleared temporary task buffer nodes",
        "Persisted local memory vectors",
      ],
    },
  ];

  // Helper counts
  const countRunning = agentsData.filter((a) => a.status === "Running").length;
  const countIdle = agentsData.filter((a) => a.status === "Idle").length;
  const countBusy = agentsData.filter((a) => a.status === "Busy").length;
  const countOffline = agentsData.filter((a) => a.status === "Offline").length;

  // Filter list
  const filteredAgents = agentsData.filter((agent) => {
    // Status filter
    if (activeFilterTab === "running" && agent.status !== "Running") return false;
    if (activeFilterTab === "idle" && agent.status !== "Idle") return false;
    if (activeFilterTab === "busy" && agent.status !== "Busy") return false;
    if (activeFilterTab === "offline" && agent.status !== "Offline") return false;

    // Search filter
    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        agent.name.toLowerCase().includes(q) ||
        agent.model.toLowerCase().includes(q) ||
        agent.subName.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedAgent = agentsData.find((a) => a.id === selectedAgentId) || agentsData[2];

  return (
    <main className="agents-view">
      {/* Header controls row */}
      <div className="agents-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Agents</h1>
          <p className="dashboard-subtitle-text">Manage your active AI agents, roles, models, and execution status.</p>
        </div>
        <div className="agents-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Add new Agent modal.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            Add Agent
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={() => alert("More options dropdown.")}>
            More Actions
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ marginLeft: '4px' }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          <button className="toggle-icon-btn">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Metrics Row Grid */}
      <div className="metrics-row-grid">
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <span>Total Agents</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{agentsData.length}</div>
              <div className="m-card-subtext">All registered agents</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Active</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{countRunning}</div>
              <div className="m-card-subtext">{((countRunning / agentsData.length) * 100).toFixed(1)}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Idle</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{countIdle}</div>
              <div className="m-card-subtext">Ready for tasks</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2H-2M9 5a2 2 0 002 2h2a2 2 0 002-2" />
              </svg>
              <span>Tasks Running</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">3</div>
              <div className="m-card-subtext">Currently executing</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Avg Response Time</span>
            </div>
            <div className="trend-indicator up">▼ 0.12s</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">1.42s</div>
              <div className="m-card-subtext">vs last hour</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,22 15,14 30,18 45,8 60,12 68,6" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Success Rate</span>
            </div>
            <div className="trend-indicator up">▲ 2.7%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">93.6%</div>
              <div className="m-card-subtext">vs last hour</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main Grid splitting into left directory pane and right selected info pane */}
      <div className="agents-main-layout">
        {/* Left column Directory Pane */}
        <div className="agents-directory-pane">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '12px 16px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
              <div className="agent-directory-header">
                <span className="panel-title">Agent Directory</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <div className="search-box-container">
                    <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Search agents..."
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                    />
                  </div>
                  <div className="grid-table-toggles">
                    <button className="toggle-icon-btn">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
                      </svg>
                    </button>
                    <button className="toggle-icon-btn active">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 6h16M4 12h16M4 18h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              {/* Status Tab buttons */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '3px' }}>
                <button
                  className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("all")}
                >
                  All <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{agentsData.length}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "running" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("running")}
                >
                  Running <span style={{ color: 'var(--color-success)', marginLeft: '2px' }}>{countRunning}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "idle" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("idle")}
                >
                  Idle <span style={{ color: 'var(--color-primary)', marginLeft: '2px' }}>{countIdle}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "busy" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("busy")}
                >
                  Busy <span style={{ color: 'var(--color-warning)', marginLeft: '2px' }}>{countBusy}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "offline" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("offline")}
                >
                  Offline <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{countOffline}</span>
                </button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Assigned Model</th>
                    <th>Current Task</th>
                    <th>Uptime</th>
                    <th>Performance</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAgents.map((agent) => (
                    <tr
                      key={agent.id}
                      className={selectedAgentId === agent.id ? "selected-row" : ""}
                      onClick={() => setSelectedAgentId(agent.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <span
                            className="agent-color-dot"
                            style={{
                              backgroundColor:
                                agent.id === "planner"
                                  ? "#3b82f6"
                                  : agent.id === "gui"
                                  ? "#a855f7"
                                  : agent.id === "coder"
                                  ? "#f59e0b"
                                  : agent.id === "researcher"
                                  ? "#10b981"
                                  : agent.id === "browser"
                                  ? "#06b6d4"
                                  : "#9ca3af",
                            }}
                          />
                          <div>
                            <div style={{ fontWeight: '700' }}>{agent.name}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>{agent.subName}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`agent-status-badge ${agent.status.toLowerCase()}`}
                        >
                          {agent.status}
                        </span>
                      </td>
                      <td style={{ fontWeight: '500' }}>{agent.model}</td>
                      <td style={{ color: 'var(--text-muted)', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {agent.currentTask}
                      </td>
                      <td>{agent.uptime}</td>
                      <td>
                        {agent.status !== "Offline" ? (
                          <div className="perf-cell-wrapper">
                            <div className="perf-text">
                              <div>RT {agent.rt}</div>
                              <div>SR {agent.sr}</div>
                            </div>
                            <svg className={`perf-sparkline ${agent.id === "coder" ? "orange" : agent.id === "gui" ? "orange" : "green"}`} viewBox="0 0 68 20">
                              <polyline points={agent.sparkPoints} />
                            </svg>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}>
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                            </svg>
                          </div>
                        ) : (
                          <span style={{ color: 'var(--text-dim)' }}>—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {filteredAgents.length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', padding: '30px', color: 'var(--text-dim)' }}>
                        No agents matched the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredAgents.length} of {filteredAgents.length} agents</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Grid for left column: Task Handoff & Recent Agent Activity */}
          <div className="agents-bottom-grid">
            {/* Task Handoff panel */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Task Handoff / Collaboration Flow</span>
                <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }} onClick={() => alert("Flow diagram visualizer.")}>
                  View Workflow
                </button>
              </header>
              <div className="panel-body" style={{ justifyContent: 'center' }}>
                <div className="collab-flow-container">
                  <div className="collab-flow-node active">
                    <div className="collab-node-header">
                      Planner
                      <span className="collab-node-dot active" />
                    </div>
                    <span className="collab-node-desc">Decomposes tasks</span>
                  </div>

                  <div className="collab-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="collab-flow-node active">
                    <div className="collab-node-header">
                      Researcher
                      <span className="collab-node-dot active" />
                    </div>
                    <span className="collab-node-desc">Gathers information</span>
                  </div>

                  <div className="collab-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="collab-flow-node active" style={{ border: '1px solid rgba(245, 158, 11, 0.4)' }}>
                    <div className="collab-node-header" style={{ color: '#fef08a' }}>
                      Coder
                      <span className="collab-node-dot busy" />
                    </div>
                    <span className="collab-node-desc">Implements solution</span>
                  </div>

                  <div className="collab-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="collab-flow-node active">
                    <div className="collab-node-header">
                      GUI Agent
                      <span className="collab-node-dot active" />
                    </div>
                    <span className="collab-node-desc">Builds interface</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Agent Activity panel */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Recent Agent Activity</span>
                <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
                  View All
                </button>
              </header>
              <div className="panel-body">
                <div className="timeline-logs-container">
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:21 AM</span>
                    <span className="t-event-node" style={{ backgroundColor: 'var(--color-warning)' }} />
                    <div className="t-event-details">
                      <span className="t-event-actor">Coder <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>updated auth_service.ts</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-warning)' }}>● Busy</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:20 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Planner <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>created execution plan</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Running</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:18 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Researcher <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>completed web search</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Running</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:16 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">GUI Agent <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>built LoginForm component</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Running</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:14 AM</span>
                    <span className="t-event-node" style={{ backgroundColor: 'var(--color-primary)' }} />
                    <div className="t-event-details">
                      <span className="t-event-actor">Browser Agent <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>captured page data</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-primary)' }}>● Idle</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right column Selected Agent details card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{
                    backgroundColor:
                      selectedAgent.id === "planner"
                        ? "rgba(59, 130, 246, 0.1)"
                        : selectedAgent.id === "gui"
                        ? "rgba(168, 85, 247, 0.1)"
                        : selectedAgent.id === "coder"
                        ? "rgba(245, 158, 11, 0.1)"
                        : selectedAgent.id === "researcher"
                        ? "rgba(16, 185, 129, 0.1)"
                        : selectedAgent.id === "browser"
                        ? "rgba(6, 182, 212, 0.1)"
                        : "rgba(156, 163, 175, 0.1)",
                    color:
                      selectedAgent.id === "planner"
                        ? "#3b82f6"
                        : selectedAgent.id === "gui"
                        ? "#a855f7"
                        : selectedAgent.id === "coder"
                        ? "#f59e0b"
                        : selectedAgent.id === "researcher"
                        ? "#10b981"
                        : selectedAgent.id === "browser"
                        ? "#06b6d4"
                        : "#9ca3af",
                  }}>
                    {selectedAgent.id === "coder" ? (
                      <span style={{ fontSize: '0.94rem', fontWeight: 'bold' }}>&lt;/&gt;</span>
                    ) : (
                      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    )}
                  </div>
                  <div>
                    <h2 className="details-title-name">{selectedAgent.name}</h2>
                  </div>
                </div>

                <span className={`details-status-badge ${selectedAgent.status.toLowerCase()}`}>
                  ● {selectedAgent.status}
                </span>
              </div>

              <div className="details-id-row">
                <span>Agent ID: AGT-{selectedAgent.name.toUpperCase()}-00{selectedAgent.name.length}</span>
                <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Agent ID to clipboard!")}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <span className="details-section-title">Role</span>
                <p className="details-section-desc">{selectedAgent.description}</p>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Assigned Model</span>
                <div className="details-model-row">
                  <span className="details-model-name">{selectedAgent.model}</span>
                  <button className="role-btn" style={{ padding: '3px 8px', fontSize: '0.74rem', height: 'auto' }} onClick={() => alert("Change Model options.")}>
                    Change Model
                  </button>
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Current Objective</span>
                <p className="details-section-desc" style={{ color: '#cbd5e1', fontWeight: '500' }}>
                  {selectedAgent.status !== "Offline"
                    ? `${selectedAgent.currentTask} with JWT tokens and local structures.`
                    : "No objective configured."}
                </p>
                {selectedAgent.status !== "Offline" && (
                  <div className="chat-progress-container" style={{ marginTop: '2px' }}>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedAgent.id === "coder" ? 68 : selectedAgent.id === "gui" ? 45 : 85}%` }} />
                    </div>
                  </div>
                )}
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Tools Access ({selectedAgent.tools.length})</span>
                <div className="details-tools-badges-grid">
                  {selectedAgent.tools.map((t, idx) => (
                    <span key={idx} className="details-tool-badge">{t}</span>
                  ))}
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Memory Usage</span>
                {selectedAgent.status !== "Offline" ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <div className="chat-progress-header" style={{ fontSize: '0.74rem' }}>
                      <span style={{ fontWeight: '500' }}>{selectedAgent.memoryVal} / {selectedAgent.memoryMax}</span>
                      <span>{selectedAgent.memoryPct}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedAgent.memoryPct}%`, background: 'linear-gradient(90deg, var(--color-accent), #a855f7)' }} />
                    </div>
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>0 GB / 8 GB</span>
                )}
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Recent Actions</span>
                <div className="recent-actions-list">
                  {selectedAgent.recentActions.map((action, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'center' }}>
                      <span className="action-time">10:21</span>
                      <svg width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)', flexShrink: 0 }}>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="action-text" style={{ fontSize: '0.8rem' }}>{action}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <footer className="agent-details-footer">
              <button className="details-footer-btn start" onClick={() => alert(`${selectedAgent.name} started.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                <span>Start</span>
              </button>
              <button className="details-footer-btn pause" onClick={() => alert(`${selectedAgent.name} paused.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Pause</span>
              </button>
              <button className="details-footer-btn restart" onClick={() => alert(`${selectedAgent.name} restarted.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                </svg>
                <span>Restart</span>
              </button>
              <button className="details-footer-btn logs" onClick={() => { setActiveTab("workspace"); alert(`Switched to workspace terminal logs for ${selectedAgent.name}.`); }}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>View Logs</span>
              </button>
            </footer>
          </div>
        </aside>
      </div>
    </main>
  );
}
