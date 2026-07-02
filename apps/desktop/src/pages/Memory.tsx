import { useState } from "react";

interface MemoryItem {
  id: string;
  name: string;
  type: "Working" | "Long-term" | "Session" | "Archived";
  source: string;
  size: string;
  lastAccessed: string;
  priority: "High" | "Medium" | "Low";
  status: "Active" | "Indexed" | "Archived";
  relevance: string;
  sparkPoints: string;
  description: string;
  tags: string[];
  sizePct: number;
  accessFreq: number;
  retrievalScore: number;
  linkedRoutes: Array<{ name: string; type: string }>;
  recentAccess: string[];
}

interface MemoryProps {
  setActiveTab: (tab: string) => void;
}

export function Memory({ setActiveTab }: MemoryProps) {
  const [selectedMemoryId, setSelectedMemoryId] = useState<string>("requirements");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  const memoryData: MemoryItem[] = [
    {
      id: "requirements",
      name: "Project Requirements Summary",
      type: "Working",
      source: "Chat Session",
      size: "1.2 MB",
      lastAccessed: "2 min ago",
      priority: "High",
      status: "Active",
      relevance: "98%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "Stores the latest project scope, architecture notes, and active task context from ongoing planning discussions and stakeholder conversations.",
      tags: ["Planning", "Project", "Context", "Active", "High Priority"],
      sizePct: 15,
      accessFreq: 84,
      retrievalScore: 98,
      linkedRoutes: [
        { name: "Planner", type: "Primary" },
        { name: "Coder", type: "Secondary" },
        { name: "Researcher", type: "Fallback" },
      ],
      recentAccess: [
        "Viewed by Planner (2 min ago)",
        "Retrieved by Coder (6 min ago)",
        "Updated from chat (12 min ago)",
        "Synced to long-term cache (18 min ago)",
      ],
    },
    {
      id: "kronos",
      name: "Kronos Training Notes",
      type: "Long-term",
      source: "Research",
      size: "4.8 MB",
      lastAccessed: "14 min ago",
      priority: "High",
      status: "Indexed",
      relevance: "94%",
      sparkPoints: "0,10 15,14 30,8 45,12 60,6 68,4",
      description: "Contains background documentation on the Kronos codebase API protocols and server endpoint mappings.",
      tags: ["Research", "Documentation", "API", "Kronos"],
      sizePct: 60,
      accessFreq: 65,
      retrievalScore: 94,
      linkedRoutes: [
        { name: "Researcher", type: "Primary" },
        { name: "Coder", type: "Secondary" },
      ],
      recentAccess: [
        "Retrieved by Researcher (14 min ago)",
        "Indexed from docs folder (45 min ago)",
      ],
    },
    {
      id: "routing",
      name: "Agent Routing Rules",
      type: "Session",
      source: "System",
      size: "640 KB",
      lastAccessed: "6 min ago",
      priority: "Medium",
      status: "Active",
      relevance: "91%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "Dynamic agent workflow graphs mapping dispatcher decisions, weights, and latency benchmarks.",
      tags: ["System", "Routing", "Rules"],
      sizePct: 8,
      accessFreq: 92,
      retrievalScore: 91,
      linkedRoutes: [
        { name: "Planner", type: "Primary" },
        { name: "Coder", type: "Fallback" },
      ],
      recentAccess: [
        "Checked by Planner (6 min ago)",
        "Updated by Dispatcher (10 min ago)",
      ],
    },
    {
      id: "ui_patterns",
      name: "UI Component Patterns",
      type: "Long-term",
      source: "Browser Capture",
      size: "2.1 MB",
      lastAccessed: "1 hour ago",
      priority: "Medium",
      status: "Indexed",
      relevance: "88%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Cached UI styling rules, components alignments, and glassmorphism styling patterns from browser validation loops.",
      tags: ["UI", "CSS", "Patterns", "Browser"],
      sizePct: 26,
      accessFreq: 45,
      retrievalScore: 88,
      linkedRoutes: [
        { name: "GUI Agent", type: "Primary" },
      ],
      recentAccess: [
        "Synced from GUI Agent (1 hour ago)",
        "Created from DOM logs (2 hours ago)",
      ],
    },
    {
      id: "preferences",
      name: "User Preferences",
      type: "Working",
      source: "Profile",
      size: "220 KB",
      lastAccessed: "3 min ago",
      priority: "High",
      status: "Active",
      relevance: "96%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "Stores active session preferences, theme limits, API keys permissions, and safe execution settings.",
      tags: ["Profile", "Config", "Preferences"],
      sizePct: 3,
      accessFreq: 95,
      retrievalScore: 96,
      linkedRoutes: [
        { name: "Planner", type: "Primary" },
        { name: "Coder", type: "Primary" },
        { name: "Researcher", type: "Primary" },
        { name: "GUI Agent", type: "Primary" },
      ],
      recentAccess: [
        "Read by Planner (3 min ago)",
        "Verified permissions settings (12 min ago)",
      ],
    },
    {
      id: "test_logs",
      name: "Archived Test Logs",
      type: "Archived",
      source: "Files",
      size: "9.6 MB",
      lastAccessed: "2 days ago",
      priority: "Low",
      status: "Archived",
      relevance: "62%",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Historical build runs, coverage logs, and compiler messages preserved for auditing and long-term comparisons.",
      tags: ["Logs", "Builds", "Auditing", "History"],
      sizePct: 100,
      accessFreq: 12,
      retrievalScore: 62,
      linkedRoutes: [
        { name: "Memory Agent", type: "Primary" },
      ],
      recentAccess: [
        "Synced to long-term archives (2 days ago)",
        "Archive created (3 days ago)",
      ],
    },
  ];

  // Tab counters
  const countWorking = memoryData.filter((m) => m.type === "Working").length;
  const countLongterm = memoryData.filter((m) => m.type === "Long-term").length;
  const countSession = memoryData.filter((m) => m.type === "Session").length;
  const countArchived = memoryData.filter((m) => m.type === "Archived").length;

  const filteredMemory = memoryData.filter((item) => {
    // Tab filtering
    if (activeFilterTab === "working" && item.type !== "Working") return false;
    if (activeFilterTab === "longterm" && item.type !== "Long-term") return false;
    if (activeFilterTab === "session" && item.type !== "Session") return false;
    if (activeFilterTab === "archived" && item.type !== "Archived") return false;

    // Search query filtering
    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        item.name.toLowerCase().includes(q) ||
        item.source.toLowerCase().includes(q) ||
        item.type.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedMemory = memoryData.find((m) => m.id === selectedMemoryId) || memoryData[0];

  return (
    <main className="models-view">
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Memory</h1>
          <p className="dashboard-subtitle-text">Monitor, organize, and optimize working memory, long-term memory, and contextual knowledge.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("New Memory node created.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            New Memory
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import files dialog.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Import
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

      {/* Metric Cards Row */}
      <div className="metrics-row-grid">
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2M7 19h10" />
              </svg>
              <span>Total Memory Nodes</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">8,192</div>
              <div className="m-card-subtext">Active vector indices</div>
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
              <span>Working Memory</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">72%</div>
              <div className="m-card-subtext">Active session buffer</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2" />
              </svg>
              <span>Long-term Memory</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">24%</div>
              <div className="m-card-subtext">Knowledge base footprint</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#06b6d4' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2H-2M9 5a2 2 0 002 2h2a2 2 0 002-2" />
              </svg>
              <span>Context Window Usage</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">68%</div>
              <div className="m-card-subtext">Tokens processed</div>
            </div>
            <svg className="m-card-sparkline-svg cyan" viewBox="0 0 68 24">
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
              <span>Retrieval Latency</span>
            </div>
            <div className="trend-indicator up">▼ 18ms</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">148ms</div>
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
              <span>Memory Health</span>
            </div>
            <div className="trend-indicator up">▲ 2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">96%</div>
              <div className="m-card-subtext">vs last hour</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main split grid */}
      <div className="agents-main-layout">
        {/* Left Pane Memory Library */}
        <div className="agents-directory-pane">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '12px 16px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
              <div className="agent-directory-header">
                <span className="panel-title">Memory Library</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <div className="search-box-container">
                    <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Search memory..."
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

              {/* Status filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '3px' }}>
                <button
                  className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("all")}
                >
                  All <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{memoryData.length}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "working" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("working")}
                >
                  Working <span style={{ color: 'var(--color-success)', marginLeft: '2px' }}>{countWorking}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "longterm" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("longterm")}
                >
                  Long-term <span style={{ color: 'var(--color-accent)', marginLeft: '2px' }}>{countLongterm}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "session" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("session")}
                >
                  Session <span style={{ color: 'var(--color-primary)', marginLeft: '2px' }}>{countSession}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "archived" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("archived")}
                >
                  Archived <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{countArchived}</span>
                </button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Memory Item</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Size</th>
                    <th>Last Accessed</th>
                    <th>Priority</th>
                    <th>Status</th>
                    <th>Relevance</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMemory.map((item) => (
                    <tr
                      key={item.id}
                      className={selectedMemoryId === item.id ? "selected-row" : ""}
                      onClick={() => setSelectedMemoryId(item.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                          <span style={{ fontWeight: '700' }}>{item.name}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`mem-type-badge ${item.type.toLowerCase().replace(" ", "-")}`}>
                          {item.type}
                        </span>
                      </td>
                      <td style={{ fontWeight: '500' }}>{item.source}</td>
                      <td>{item.size}</td>
                      <td>{item.lastAccessed}</td>
                      <td>
                        <span className={`priority-badge ${item.priority.toLowerCase()}`}>
                          {item.priority}
                        </span>
                      </td>
                      <td>
                        <span className={`agent-status-badge ${item.status.toLowerCase()}`}>
                          {item.status}
                        </span>
                      </td>
                      <td>
                        <div className="perf-cell-wrapper">
                          <span style={{ fontWeight: '600' }}>{item.relevance}</span>
                          <svg className="perf-sparkline" viewBox="0 0 68 20" style={{ stroke: 'var(--color-primary)' }}>
                            <polyline points={item.sparkPoints} />
                          </svg>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
                          </svg>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredMemory.length} of {filteredMemory.length} memory items</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Grid for left column: Memory Usage by Type & Memory Flow map & timeline activity logs */}
          <div className="bottom-tables-grid" style={{ minHeight: '220px' }}>
            {/* Memory Usage by Type */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Memory Usage by Type</span>
              </header>
              <div className="panel-body" style={{ padding: '10px' }}>
                <div className="type-compare-chart-container">
                  <div className="latency-grid-lines">
                    <div className="latency-grid-line-row"><span>6 GB</span></div>
                    <div className="latency-grid-line-row"><span>4 GB</span></div>
                    <div className="latency-grid-line-row"><span>2 GB</span></div>
                    <div className="latency-grid-line-row"><span>0 GB</span></div>
                  </div>

                  <div className="type-bars-row">
                    <div className="type-bar-col">
                      <span className="type-bar-val">3.8 GB</span>
                      <div className="type-bar-column working" style={{ height: '70px' }} />
                      <span className="type-bar-label">Working</span>
                    </div>
                    <div className="type-bar-col">
                      <span className="type-bar-val">2.1 GB</span>
                      <div className="type-bar-column long-term" style={{ height: '39px' }} />
                      <span className="type-bar-label">Long-term</span>
                    </div>
                    <div className="type-bar-col">
                      <span className="type-bar-val">0.9 GB</span>
                      <div className="type-bar-column session" style={{ height: '17px' }} />
                      <span className="type-bar-label">Session</span>
                    </div>
                    <div className="type-bar-col">
                      <span className="type-bar-val">1.4 GB</span>
                      <div className="type-bar-column archived" style={{ height: '26px' }} />
                      <span className="type-bar-label">Archived</span>
                    </div>
                    <div className="type-bar-col">
                      <span className="type-bar-val">0.6 GB</span>
                      <div className="type-bar-column cache" style={{ height: '11px' }} />
                      <span className="type-bar-label">Cache</span>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto', fontWeight: '500' }}>
                  <span style={{ color: 'var(--text-main)' }}>Total Memory Usage: 8.8 GB / 16 GB (55%)</span>
                </div>
              </div>
            </div>

            {/* Memory Flow diagram */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Memory Flow</span>
              </header>
              <div className="panel-body" style={{ padding: '8px' }}>
                <div className="mem-flow-container">
                  <div className="mem-flow-node-item">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    Chat
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="mem-flow-node-item working">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5" />
                    </svg>
                    Working Memory
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="mem-flow-node-item retrieval">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    Retrieval
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="mem-flow-node-item" style={{ borderColor: 'rgba(139, 92, 246, 0.4)' }}>
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5" />
                    </svg>
                    Long-term Store
                  </div>

                  {/* Absolute node down bottom for context */}
                  <div className="mem-flow-node-item agent-context" style={{ position: 'absolute', left: '124px', bottom: '6px' }}>
                    Agent Context
                  </div>

                  <svg className="mem-flow-svg-overlay">
                    {/* Dotted paths representing background sync */}
                    <path d="M 206,80 L 206,120 L 165,120" stroke="var(--color-primary)" strokeWidth="1.5" strokeDasharray="3,3" fill="none" />
                    <path d="M 124,120 L 80,120 L 80,80" stroke="var(--color-success)" strokeWidth="1.5" strokeDasharray="3,3" fill="none" />
                  </svg>
                </div>
                <div style={{ display: 'flex', gap: '16px', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto', color: 'var(--text-dim)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '10px', height: '2px', backgroundColor: 'var(--text-dim)', display: 'inline-block' }} /> Primary Flow
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '10px', height: '2px', borderBottom: '2px dashed var(--text-dim)', display: 'inline-block' }} /> Background Sync
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Memory Activity timeline */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Recent Memory Activity</span>
                <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
                  View All
                </button>
              </header>
              <div className="panel-body">
                <div className="timeline-logs-container">
                  <div className="timeline-event-row">
                    <span className="t-event-time">2 min ago</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Memory created <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Project Requirements Summary</span></span>
                      <span className="mem-type-badge working" style={{ fontSize: '0.68rem', alignSelf: 'flex-start' }}>Working</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">6 min ago</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Memory retrieved <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Kronos Training Notes</span></span>
                      <span className="mem-type-badge long-term" style={{ fontSize: '0.68rem', alignSelf: 'flex-start' }}>Long-term</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">12 min ago</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Context compressed <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Session context optimized</span></span>
                      <span className="mem-type-badge session" style={{ fontSize: '0.68rem', alignSelf: 'flex-start' }}>Session</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">18 min ago</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Archive synced <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Archived Test Logs</span></span>
                      <span className="mem-type-badge archived" style={{ fontSize: '0.68rem', alignSelf: 'flex-start' }}>Archived</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right column Selected Memory details card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--color-primary)' }}>
                    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="details-title-name" style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedMemory.name}>
                      {selectedMemory.name}
                    </h2>
                  </div>
                </div>

                <span className="details-status-badge running" style={{ color: 'var(--color-success)' }}>
                  ● Active
                </span>
              </div>

              <div className="details-id-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>Memory ID: {selectedMemory.id === "requirements" ? "mem-7f34c2d1" : `mem-${selectedMemory.id}`}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Memory ID to clipboard!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                <span className={`mem-type-badge ${selectedMemory.type.toLowerCase().replace(" ", "-")}`}>{selectedMemory.type}</span>
                <span className="priority-badge" style={{ backgroundColor: 'var(--bg-darker)', color: 'var(--text-muted)' }}>{selectedMemory.source}</span>
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <p className="details-section-desc">{selectedMemory.description}</p>
              </div>

              <div className="details-section-box">
                <div className="details-tools-badges-grid">
                  {selectedMemory.tags.map((tag, idx) => (
                    <span key={idx} className="details-tool-badge" style={{ backgroundColor: 'rgba(139, 92, 246, 0.05)', color: '#c084fc', borderColor: 'rgba(139, 92, 246, 0.15)' }}>{tag}</span>
                  ))}
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Resource Metrics</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Usage Size</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedMemory.size} / 8 MB ({selectedMemory.sizePct}%)</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedMemory.sizePct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>

                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Access Frequency</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedMemory.accessFreq}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedMemory.accessFreq}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>

                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Retrieval Score</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedMemory.retrievalScore}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedMemory.retrievalScore}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Linked Agents / Routes</span>
                <div className="assigned-routes-list">
                  {selectedMemory.linkedRoutes.map((route, idx) => (
                    <div key={idx} className="assigned-route-row">
                      <span className="assigned-route-name">{route.name}</span>
                      <span className="assigned-route-type">{route.type}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Recent Access Logs</span>
                <div className="recent-actions-list">
                  {selectedMemory.recentAccess.map((access, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'center' }}>
                      <span className="action-dot" style={{ backgroundColor: 'var(--color-primary)', width: '5px', height: '5px' }} />
                      <span className="action-text" style={{ fontSize: '0.8rem' }}>{access}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <footer className="agent-details-footer" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
              <button className="details-footer-btn" onClick={() => alert(`${selectedMemory.name} pinned.`)}>
                {/* Pin icon */}
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.414m-5.656-5.656l6.414-6.414a2 2 0 112.828 2.828L15 11" />
                </svg>
                <span>Pin</span>
              </button>
              <button className="details-footer-btn" onClick={() => alert(`${selectedMemory.name} archived.`)}>
                {/* Archive icon */}
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                </svg>
                <span>Archive</span>
              </button>
              <button className="details-footer-btn restart" onClick={() => alert(`${selectedMemory.name} database entries refreshed.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                </svg>
                <span>Refresh</span>
              </button>
              <button className="details-footer-btn logs" onClick={() => { setActiveTab("workspace"); alert(`Switched to workspace logs for ${selectedMemory.name}.`); }}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>Logs</span>
              </button>
            </footer>
          </div>
        </aside>
      </div>
    </main>
  );
}
