import { useState } from "react";

interface WorkflowItem {
  id: string;
  name: string;
  type: string;
  trigger: string;
  owner: string;
  lastRun: string;
  status: "Running" | "Ready" | "Active" | "Draft" | "Archived";
  success: string;
  sparkPoints: string;
  description: string;
  tags: string[];
  stepsCount: number;
  completedSteps: number;
  failedSteps: number;
  eta: string;
  progressVal: number;
  health: Array<{ name: string; status: "Good" | "In Progress" }>;
  activity: string[];
}

export function Workflows() {
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>("kronos");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  const workflowsData: WorkflowItem[] = [
    {
      id: "kronos",
      name: "Kronos Training Pipeline",
      type: "ML Pipeline",
      trigger: "Scheduled",
      owner: "Researcher",
      lastRun: "14 min ago",
      status: "Running",
      success: "96%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "End-to-end pipeline for preparing market data, training Kronos, validating results, and generating a final report.",
      tags: ["ML", "Automation", "Scheduled", "High Priority"],
      stepsCount: 12,
      completedSteps: 8,
      failedSteps: 0,
      eta: "11m",
      progressVal: 68,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "Good" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "In Progress" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Workflow run started by Researcher (14 min ago)",
        "Dataset prepared (1.2M rows) (12 min ago)",
        "Model load successful (v2.3.1) (10 min ago)",
        "Tests passed (142/142) (6 min ago)",
        "Notifying Planner with results (3 min ago)",
      ],
    },
    {
      id: "release",
      name: "Release QA + Deploy",
      type: "DevOps",
      trigger: "Manual",
      owner: "Coder",
      lastRun: "1 hour ago",
      status: "Ready",
      success: "98%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Trigger production verification checks, compile bundle components, execute integration tests suites and deploy live.",
      tags: ["DevOps", "Manual", "Deployments"],
      stepsCount: 8,
      completedSteps: 8,
      failedSteps: 0,
      eta: "0m",
      progressVal: 100,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "Good" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Bundle built successfully (1 hour ago)",
        "Integration tests completed with 0 errors (1 hour ago)",
      ],
    },
    {
      id: "lab",
      name: "Agent Lab Auto Research",
      type: "Research",
      trigger: "Event-based",
      owner: "Planner",
      lastRun: "7 min ago",
      status: "Running",
      success: "93%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "Instruct model search loops, crawl latest literature documents, scrape web logs, and update knowledge vector indexes.",
      tags: ["Research", "Automated", "Vector-Sync"],
      stepsCount: 15,
      completedSteps: 9,
      failedSteps: 1,
      eta: "14m",
      progressVal: 60,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "In Progress" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Web crawl sync completed for 12 websites (7 min ago)",
        "Failed parsing layout on 1 site (retry scheduled) (5 min ago)",
      ],
    },
    {
      id: "bug",
      name: "Bug Intake Triage",
      type: "Support",
      trigger: "Scheduled",
      owner: "GUI Agent",
      lastRun: "22 min ago",
      status: "Active",
      success: "91%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Poll active issue logs, categorize based on logs severity stacks, draft bug reports, and forward notifications.",
      tags: ["Support", "Triage", "Auto-tickets"],
      stepsCount: 5,
      completedSteps: 5,
      failedSteps: 0,
      eta: "0m",
      progressVal: 100,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "Good" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Triaged 14 incoming tickets (22 min ago)",
        "Forwarded 3 high priority items to developers (20 min ago)",
      ],
    },
    {
      id: "market",
      name: "Market Data Sync",
      type: "Data",
      trigger: "Cron",
      owner: "Browser Agent",
      lastRun: "3 min ago",
      status: "Running",
      success: "99%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "Fetch live exchange endpoints, refresh session caches, compute moving variance indices, and update database charts.",
      tags: ["Data-Sync", "Cron", "Cache"],
      stepsCount: 10,
      completedSteps: 9,
      failedSteps: 0,
      eta: "1m",
      progressVal: 90,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "Good" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Live stock feeds updated (3 min ago)",
        "Caches index populated (2 min ago)",
      ],
    },
    {
      id: "report",
      name: "Report Generator",
      type: "Analytics",
      trigger: "Manual",
      owner: "Memory Agent",
      lastRun: "Yesterday",
      status: "Draft",
      success: "87%",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Compile weekly performance charts, query system benchmark logs, compile HTML email summaries, and draft send rules.",
      tags: ["Analytics", "Manual", "Email-draft"],
      stepsCount: 4,
      completedSteps: 0,
      failedSteps: 0,
      eta: "—",
      progressVal: 0,
      health: [
        { name: "Queue", status: "Good" },
        { name: "Agents", status: "Good" },
        { name: "Compute", status: "Good" },
        { name: "Data Access", status: "Good" },
        { name: "Validation", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        "Report template compiled in drafts (Yesterday)",
      ],
    },
  ];

  const totalWorkflowsCount = 24;
  const activeRunsCount = 8;
  const completedTodayCount = 126;
  const successRatePct = "94.8%";

  const filteredWorkflows = workflowsData.filter((wf) => {
    if (activeFilterTab === "active" && (wf.status !== "Running" && wf.status !== "Active")) return false;
    if (activeFilterTab === "scheduled" && wf.trigger !== "Scheduled" && wf.trigger !== "Cron") return false;
    if (activeFilterTab === "draft" && wf.status !== "Draft") return false;
    if (activeFilterTab === "archived" && wf.status === "Archived") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        wf.name.toLowerCase().includes(q) ||
        wf.type.toLowerCase().includes(q) ||
        wf.owner.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedWorkflow = workflowsData.find((w) => w.id === selectedWorkflowId) || workflowsData[0];

  return (
    <main className="models-view">
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Workflows</h1>
          <p className="dashboard-subtitle-text">Design, monitor, and automate multi-step agent workflows.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("New Workflow builder opened.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            New Workflow
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import JSON workflow file.")}>
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2" />
              </svg>
              <span>Total Workflows</span>
            </div>
            <div className="trend-indicator up">▲ 12%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalWorkflowsCount}</div>
              <div className="m-card-subtext">All designed sequences</div>
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              </svg>
              <span>Active Runs</span>
            </div>
            <div className="trend-indicator up">▲ 33%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{activeRunsCount}</div>
              <div className="m-card-subtext">Running in background</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Completed Today</span>
            </div>
            <div className="trend-indicator up">▲ 18%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{completedTodayCount}</div>
              <div className="m-card-subtext">Runs executed successfully</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#06b6d4' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Success Rate</span>
            </div>
            <div className="trend-indicator up">▲ 2.6%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{successRatePct}</div>
              <div className="m-card-subtext">Average run stability</div>
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
              <span>Avg Runtime</span>
            </div>
            <div className="trend-indicator down" style={{ color: 'var(--color-success)' }}>▼ 8%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">3m 42s</div>
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
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2M7 19h10" />
              </svg>
              <span>Automation Coverage</span>
            </div>
            <div className="trend-indicator up">▲ 9%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">71%</div>
              <div className="m-card-subtext">vs last hour</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main split layout */}
      <div className="agents-main-layout">
        {/* Left Pane: Workflow Library */}
        <div className="agents-directory-pane">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '12px 16px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
              <div className="agent-directory-header">
                <span className="panel-title">Workflow Library</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <div className="search-box-container">
                    <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Search workflows..."
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

              {/* Filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '3px' }}>
                <button
                  className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("all")}
                >
                  All <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{totalWorkflowsCount}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "active" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("active")}
                >
                  Active <span style={{ color: 'var(--color-success)', marginLeft: '2px' }}>{activeRunsCount}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "scheduled" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("scheduled")}
                >
                  Scheduled <span style={{ color: 'var(--color-warning)', marginLeft: '2px' }}>6</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "draft" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("draft")}
                >
                  Draft <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>5</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "archived" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("archived")}
                >
                  Archived <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>5</span>
                </button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Workflow</th>
                    <th>Type</th>
                    <th>Trigger</th>
                    <th>Owner</th>
                    <th>Last Run</th>
                    <th>Status</th>
                    <th>Success</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredWorkflows.map((wf) => (
                    <tr
                      key={wf.id}
                      className={selectedWorkflowId === wf.id ? "selected-row" : ""}
                      onClick={() => setSelectedWorkflowId(wf.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2" />
                          </svg>
                          <span style={{ fontWeight: '700' }}>{wf.name}</span>
                        </div>
                      </td>
                      <td style={{ fontWeight: '500', color: 'var(--text-muted)' }}>{wf.type}</td>
                      <td>{wf.trigger}</td>
                      <td>{wf.owner}</td>
                      <td>{wf.lastRun}</td>
                      <td>
                        <span className={`agent-status-badge ${wf.status === "Running" ? "running" : wf.status === "Ready" ? "running" : wf.status === "Active" ? "busy" : "offline"}`}>
                          ● {wf.status}
                        </span>
                      </td>
                      <td>
                        <div className="perf-cell-wrapper">
                          <span style={{ fontWeight: '600' }}>{wf.success}</span>
                          <svg className="perf-sparkline" viewBox="0 0 68 20" style={{ stroke: 'var(--color-primary)' }}>
                            <polyline points={wf.sparkPoints} />
                          </svg>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredWorkflows.length} of 24 workflows</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>2</button>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Grid for left: Workflow Builder flowchart and Execution Timeline logs */}
          <div className="bottom-tables-grid" style={{ minHeight: '340px', gridTemplateColumns: '1.2fr 1fr' }}>
            {/* Visual Builder Diagram */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Workflow Builder</span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 8V4h4m12 4V4h-4M4 16v4h4m12-4v4h-4" />
                    </svg>
                  </button>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>+</button>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>-</button>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>⟳</button>
                </div>
              </header>
              <div className="panel-body" style={{ padding: '12px' }}>
                <div className="workflows-builder-container">
                  <div className="flow-builder-node trigger">
                    <span style={{ color: 'var(--color-primary)' }}>●</span>
                    Trigger
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="flow-builder-node planning">
                    Planner
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="flow-builder-node research">
                    Researcher
                  </div>

                  <div className="mem-flow-arrow">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3.5" d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="flow-builder-node coding active" style={{ borderColor: 'var(--color-warning)' }}>
                    Coder
                  </div>

                  {/* Nodes tests/deploy/notify shifted in layout */}
                  <div className="flow-builder-node qa" style={{ position: 'absolute', right: '110px', bottom: '26px' }}>
                    Tests
                  </div>

                  <div className="flow-builder-node ops" style={{ position: 'absolute', right: '46px', bottom: '26px' }}>
                    Deploy
                  </div>

                  <div className="flow-builder-node notify" style={{ position: 'absolute', right: '8px', bottom: '26px' }}>
                    Notify
                  </div>

                  <svg className="flow-builder-svg-overlay">
                    <path d="M 334,70 C 374,70 374,70 374,104" stroke="var(--color-warning)" strokeWidth="1.5" fill="none" />
                    <path d="M 338,114 Q 320,114 300,114" stroke="var(--border-color)" strokeWidth="1.5" strokeDasharray="3,3" fill="none" />
                    <path d="M 220,114 Q 220,114 220,80" stroke="var(--border-color)" strokeWidth="1.5" fill="none" />
                    <path d="M 338,114 C 374,114 374,114 394,114" stroke="var(--color-warning)" strokeWidth="1.5" fill="none" />
                    <path d="M 436,114 L 460,114" stroke="var(--color-success)" strokeWidth="1.5" fill="none" />
                  </svg>
                </div>
                <div style={{ display: 'flex', gap: '16px', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto', color: 'var(--text-dim)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(6,182,212,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Trigger
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(59,130,246,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Planning
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(16,185,129,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Research
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(245,158,11,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Coding
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(168,85,247,0.4)', borderRadius: '2px', display: 'inline-block' }} /> QA
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(16,185,129,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Ops
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span style={{ width: '8px', height: '8px', backgroundColor: 'rgba(234,179,8,0.4)', borderRadius: '2px', display: 'inline-block' }} /> Notify
                  </div>
                </div>
              </div>
            </div>

            {/* Execution Timeline logs */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Execution Timeline</span>
              </header>
              <div className="panel-body">
                <div className="timeline-logs-container" style={{ paddingLeft: '8px' }}>
                  <div className="timeline-event-row">
                    <span className="t-event-time">00:00</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-main)' }}>Initialized</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Workflow run started</span>
                    </div>
                    <span style={{ color: 'var(--color-success)', fontSize: '0.74rem', fontWeight: 'bold' }}>Completed</span>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">00:45</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-main)' }}>Fetched dataset</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Market data pulled from Data Lake</span>
                    </div>
                    <span style={{ color: 'var(--color-success)', fontSize: '0.74rem', fontWeight: 'bold' }}>Completed</span>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">01:38</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-main)' }}>Prepared config</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Training config generated</span>
                    </div>
                    <span style={{ color: 'var(--color-success)', fontSize: '0.74rem', fontWeight: 'bold' }}>Completed</span>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">02:22</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-main)' }}>Training started</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Model training in progress</span>
                    </div>
                    <span style={{ color: 'var(--color-success)', fontSize: '0.74rem', fontWeight: 'bold' }}>Completed</span>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">06:54</span>
                    <span className="t-event-node" style={{ backgroundColor: 'var(--color-warning)' }} />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-main)' }}>Validation running</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Validating model performance</span>
                    </div>
                    <span style={{ color: 'var(--color-warning)', fontSize: '0.74rem', fontWeight: 'bold' }}>In Progress</span>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">--:--</span>
                    <span className="t-event-node" style={{ backgroundColor: 'var(--text-dim)' }} />
                    <div className="t-event-details">
                      <span className="t-event-actor" style={{ color: 'var(--text-dim)' }}>Awaiting report</span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>Report generation queued</span>
                    </div>
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.74rem' }}>Pending</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right column Selected Workflow details card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(139, 92, 246, 0.1)', color: 'var(--color-accent)' }}>
                    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="details-title-name" style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedWorkflow.name}>
                      {selectedWorkflow.name}
                    </h2>
                  </div>
                </div>
                <button className="toggle-icon-btn" style={{ border: 'none', background: 'transparent' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
                  </svg>
                </button>
              </div>

              <div className="details-id-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>ID: {selectedWorkflow.id === "kronos" ? "wf_8f4d2b7s" : `wf_${selectedWorkflow.id}`}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Workflow ID!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1" />
                  </svg>
                </div>
                <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                  Owner: <span style={{ color: 'var(--text-main)', fontWeight: 'bold' }}>{selectedWorkflow.owner}</span>
                </span>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
                {selectedWorkflow.tags.map((tag, idx) => (
                  <span key={idx} className={`mem-type-badge ${tag === "ML" ? "working" : tag === "Automation" ? "session" : tag === "Scheduled" ? "long-term" : "archived"}`}>{tag}</span>
                ))}
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <p className="details-section-desc">{selectedWorkflow.description}</p>
              </div>

              {/* Progress */}
              <div className="details-section-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', marginBottom: '4px' }}>
                  <span className="details-section-title" style={{ margin: '0' }}>Progress</span>
                  <span style={{ fontWeight: 'bold', color: 'var(--text-main)' }}>{selectedWorkflow.progressVal}%</span>
                </div>
                <div className="progress-bar-bg" style={{ height: '6px' }}>
                  <div className="progress-bar-fill" style={{ width: `${selectedWorkflow.progressVal}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)', borderRadius: '3px' }} />
                </div>
              </div>

              {/* Step info metrics grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', fontSize: '0.8rem', textAlign: 'center' }}>
                <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '8px 4px' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Steps</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: '800', color: '#fff', marginTop: '4px' }}>{selectedWorkflow.stepsCount}</div>
                </div>
                <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '8px 4px' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Completed</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: '800', color: 'var(--color-success)', marginTop: '4px' }}>{selectedWorkflow.completedSteps}</div>
                </div>
                <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '8px 4px' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 'bold' }}>Failed</div>
                  <div style={{ fontSize: '1.2rem', fontWeight: '800', color: 'var(--color-danger)', marginTop: '4px' }}>{selectedWorkflow.failedSteps}</div>
                </div>
                <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '8px 4px' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem', textTransform: 'uppercase', fontWeight: 'bold' }}>ETA</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: '800', color: 'var(--color-primary)', marginTop: '4px' }}>{selectedWorkflow.eta}</div>
                </div>
              </div>

              {/* Run Health checkers list */}
              <div className="details-section-box">
                <span className="details-section-title">Run Health</span>
                <div className="run-health-list">
                  {selectedWorkflow.health.map((item, idx) => (
                    <div key={idx} className="health-item-row">
                      <div className="health-item-left">
                        <span style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: item.status === "Good" ? 'var(--color-success)' : 'var(--color-warning)',
                          boxShadow: item.status === "Good" ? '0 0 6px var(--color-success)' : '0 0 6px var(--color-warning)',
                        }} />
                        {item.name}
                      </div>
                      <span className={`health-item-right ${item.status === "Good" ? "good" : "progress"}`}>
                        {item.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Activity log timeline */}
              <div className="details-section-box">
                <span className="details-section-title">Recent Workflow Activity</span>
                <div className="recent-actions-list">
                  {selectedWorkflow.activity.map((act, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'flex-start' }}>
                      <span className="action-dot" style={{ backgroundColor: 'var(--color-primary)', width: '5px', height: '5px', marginTop: '6px' }} />
                      <span className="action-text" style={{ fontSize: '0.78rem' }}>{act}</span>
                    </div>
                  ))}
                </div>
                <a href="#logs" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={(e) => { e.preventDefault(); alert("View full activity logs."); }}>
                  View all activity logs →
                </a>
              </div>
            </div>

            <footer className="agent-details-footer" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <button className="details-footer-btn start" style={{ flexDirection: 'row', gap: '8px', padding: '10px' }} onClick={() => alert(`${selectedWorkflow.name} execution triggered manually.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                Run Workflow
              </button>
              <button className="details-footer-btn" style={{ flexDirection: 'row', gap: '8px', padding: '10px' }} onClick={() => alert("Open scheduler configurations.")}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                Schedule Run
              </button>
            </footer>
          </div>
        </aside>
      </div>
    </main>
  );
}
