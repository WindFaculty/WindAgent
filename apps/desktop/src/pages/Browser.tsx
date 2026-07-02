import { useState } from "react";

interface SessionItem {
  id: string;
  name: string;
  url: string;
  type: string;
  owner: string;
  lastActive: string;
  status: "Active" | "Automated" | "Idle" | "Archived";
  success: string;
  sparkPoints: string;
  description: string;
  tags: string[];
  memoryVal: string;
  memoryPct: number;
  tabCount: number;
  tabMax: number;
  tabPct: number;
  completionPct: number;
  health: Array<{ name: string; status: "Good" | "In Progress" }>;
  activity: Array<{ time: string; text: string; inProgress?: boolean }>;
  steps: Array<{ num: number; title: string; desc: string; status: "Success" | "In Progress" }>;
  previewTitle: string;
  previewUrl: string;
}

export function Browser() {
  const [selectedSessionId, setSelectedSessionId] = useState<string>("kronos");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  const sessionsData: SessionItem[] = [
    {
      id: "kronos",
      name: "Kronos Docs Research",
      url: "docs.kronos.ai",
      type: "Research",
      owner: "WindUser",
      lastActive: "2m ago",
      status: "Active",
      success: "96%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "Research and extract analytics dashboard data from Kronos Docs platform for weekly report.",
      tags: ["Research", "Browser Automation", "Active", "High Priority"],
      memoryVal: "412 MB",
      memoryPct: 41,
      tabCount: 5,
      tabMax: 20,
      tabPct: 25,
      completionPct: 68,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "In Progress" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "10:24 AM", text: "Page opened: /analytics/overview" },
        { time: "10:24 AM", text: "Content extracted: Analytics metrics table" },
        { time: "10:25 AM", text: "Screenshot captured: overview_2025-05-11.png" },
        { time: "10:25 AM", text: "Agent notified: Data sent to workspace" },
        { time: "10:26 AM", text: "Automation step: Extract data - started", inProgress: true },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Navigate to URL https://docs.kronos.ai", status: "Success" },
        { num: 2, title: "Inspect Elements", desc: "Extract DOM content & structure", status: "Success" },
        { num: 3, title: "Extract Data", desc: "Pull analytics metrics & tables", status: "Success" },
        { num: 4, title: "Take Screenshot", desc: "Capture page screenshot", status: "Success" },
        { num: 5, title: "Submit Result", desc: "Send data to agent workspace", status: "In Progress" },
      ],
      previewTitle: "Kronos Docs - Analytics Overview",
      previewUrl: "https://docs.kronos.ai/analytics/overview",
    },
    {
      id: "openai",
      name: "OpenAI Console",
      url: "platform.openai.com",
      type: "Billing",
      owner: "WindUser",
      lastActive: "8m ago",
      status: "Active",
      success: "93%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Authenticate console platform sessions, scrape model token pricing details, and update active routing configurations.",
      tags: ["Billing", "Models", "Active"],
      memoryVal: "320 MB",
      memoryPct: 32,
      tabCount: 2,
      tabMax: 20,
      tabPct: 10,
      completionPct: 100,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "08:14 AM", text: "Page opened: /billing/overview" },
        { time: "08:16 AM", text: "Rate limit stats retrieved" },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Navigate to URL https://platform.openai.com", status: "Success" },
        { num: 2, title: "Extract Data", desc: "Scrape token costs", status: "Success" },
      ],
      previewTitle: "OpenAI - Platform Console",
      previewUrl: "https://platform.openai.com/billing/overview",
    },
    {
      id: "binance",
      name: "Binance Market Monitor",
      url: "www.binance.com",
      type: "Finance",
      owner: "MarketBot",
      lastActive: "15m ago",
      status: "Automated",
      success: "97%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "Continuous monitoring of ticker variance limits and trigger safety warning events on rapid fluctuations.",
      tags: ["Finance", "Monitoring", "Automated"],
      memoryVal: "512 MB",
      memoryPct: 51,
      tabCount: 8,
      tabMax: 20,
      tabPct: 40,
      completionPct: 100,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "09:12 AM", text: "WebSocket connection opened" },
        { time: "09:15 AM", text: "Ticker stream sync active" },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Connect WebSocket feed", status: "Success" },
        { num: 2, title: "Monitor Feeds", desc: "Sync live prices", status: "Success" },
      ],
      previewTitle: "Binance Market Trading Feeds",
      previewUrl: "https://www.binance.com/en/markets",
    },
    {
      id: "github",
      name: "GitHub Repo Review",
      url: "github.com/org/repo",
      type: "Git",
      owner: "CoderAgent",
      lastActive: "22m ago",
      status: "Idle",
      success: "91%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Scrape PR changes list, audit code diff line structures, and draft initial peer review messages.",
      tags: ["Git", "Auditing", "Review"],
      memoryVal: "180 MB",
      memoryPct: 18,
      tabCount: 3,
      tabMax: 20,
      tabPct: 15,
      completionPct: 100,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "11:20 AM", text: "PR branch diff generated" },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Scrape repo PR index", status: "Success" },
        { num: 2, title: "Pull Diff", desc: "Analyze files changed", status: "Success" },
      ],
      previewTitle: "GitHub PR Index Review",
      previewUrl: "https://github.com/windfaculty/WindAgent/pulls",
    },
    {
      id: "ui_test",
      name: "UI Test Session",
      url: "app.kronos.ai/dashboard",
      type: "Testing",
      owner: "TestAgent",
      lastActive: "35m ago",
      status: "Idle",
      success: "89%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "Execute automated visual testing script across dashboard elements to identify overlapping layers.",
      tags: ["Testing", "UI", "Visual-QA"],
      memoryVal: "256 MB",
      memoryPct: 25,
      tabCount: 1,
      tabMax: 20,
      tabPct: 5,
      completionPct: 100,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "10:05 AM", text: "Test script loaded" },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Render test staging app", status: "Success" },
        { num: 2, title: "Assert Elements", desc: "Verify dashboard layouts", status: "Success" },
      ],
      previewTitle: "UI Staging Visual Test App",
      previewUrl: "https://app.kronos.ai/dashboard/visual-test",
    },
    {
      id: "news",
      name: "News Scraper",
      url: "news.ycombinator.com",
      type: "Scraper",
      owner: "Researcher",
      lastActive: "1h ago",
      status: "Automated",
      success: "95%",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Hourly scraping of top stories to filter updates related to active engineering tools and dependencies.",
      tags: ["Scraper", "Research", "Automated"],
      memoryVal: "120 MB",
      memoryPct: 12,
      tabCount: 1,
      tabMax: 20,
      tabPct: 5,
      completionPct: 100,
      health: [
        { name: "Network", status: "Good" },
        { name: "DOM Access", status: "Good" },
        { name: "Screenshot Capture", status: "Good" },
        { name: "Extraction", status: "Good" },
        { name: "Notifications", status: "Good" },
      ],
      activity: [
        { time: "09:30 AM", text: "Front page scraped" },
      ],
      steps: [
        { num: 1, title: "Open Page", desc: "Fetch HackerNews index", status: "Success" },
        { num: 2, title: "Extract List", desc: "Parse titles and links", status: "Success" },
      ],
      previewTitle: "Hacker News Staging Feed",
      previewUrl: "https://news.ycombinator.com/news",
    },
  ];

  const totalSessionsCount = 42;
  const activeTabsCount = 18;
  const runningAutomationsCount = 7;
  const avgLoadTime = "1.42s";
  const successRate = "94.3%";
  const browserHealth = "98%";

  const filteredSessions = sessionsData.filter((s) => {
    if (activeFilterTab === "active" && s.status !== "Active") return false;
    if (activeFilterTab === "idle" && s.status !== "Idle") return false;
    if (activeFilterTab === "automated" && s.status !== "Automated") return false;
    if (activeFilterTab === "archived" && s.status === "Archived") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        s.name.toLowerCase().includes(q) ||
        s.url.toLowerCase().includes(q) ||
        s.owner.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedSession = sessionsData.find((s) => s.id === selectedSessionId) || sessionsData[0];

  return (
    <main className="models-view" style={{ overflow: 'hidden' }}>
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Browser</h1>
          <p className="dashboard-subtitle-text">Browse, inspect, and automate web sessions across your agents.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("New Browser session created.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            New Session
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import session data.")}>
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
              <span>Total Sessions</span>
            </div>
            <div className="trend-indicator up">▲ 12%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalSessionsCount}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6z" />
              </svg>
              <span>Active Tabs</span>
            </div>
            <div className="trend-indicator up">▲ 8%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{activeTabsCount}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Running Automations</span>
            </div>
            <div className="trend-indicator up">▲ 2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{runningAutomationsCount}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3" />
              </svg>
              <span>Avg Load Time</span>
            </div>
            <div className="trend-indicator down" style={{ color: 'var(--color-success)' }}>▼ 6%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{avgLoadTime}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4" />
              </svg>
              <span>Success Rate</span>
            </div>
            <div className="trend-indicator up">▲ 3.2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{successRate}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,14 30,18 45,8 60,12 68,6" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4" />
              </svg>
              <span>Browser Health</span>
            </div>
            <div className="trend-indicator up">▲ 2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{browserHealth}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Rebuilt Browser 3 column layout */}
      <div className="browser-console-layout">
        {/* Column 1: Session Library and Automation flowchart */}
        <div className="browser-col">
          <div className="dashboard-panel" style={{ flex: 1.3 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '10px 12px', flexDirection: 'column', alignItems: 'stretch', gap: '8px' }}>
              <div className="agent-directory-header">
                <span className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  Session Library
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button className="browser-nav-btn" style={{ padding: '4px' }} onClick={() => alert("Refreshed Session Library.")}>⟳</button>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <div className="search-box-container" style={{ flex: 1 }}>
                  <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search sessions..."
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                  />
                </div>
                <button className="toggle-icon-btn" style={{ padding: '6px' }}>
                  {/* Filter icon */}
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                  </svg>
                </button>
              </div>

              {/* Status filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '2px' }}>
                <button className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`} onClick={() => setActiveFilterTab("all")}>All</button>
                <button className={`tab-btn ${activeFilterTab === "active" ? "active" : ""}`} onClick={() => setActiveFilterTab("active")}>Active</button>
                <button className={`tab-btn ${activeFilterTab === "idle" ? "active" : ""}`} onClick={() => setActiveFilterTab("idle")}>Idle</button>
                <button className={`tab-btn ${activeFilterTab === "automated" ? "active" : ""}`} onClick={() => setActiveFilterTab("automated")}>Automated</button>
                <button className={`tab-btn ${activeFilterTab === "archived" ? "active" : ""}`} onClick={() => setActiveFilterTab("archived")}>Archived</button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Session Name</th>
                    <th>Type</th>
                    <th>Owner</th>
                    <th>Last Active</th>
                    <th>Status</th>
                    <th>Success</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSessions.map((s) => (
                    <tr
                      key={s.id}
                      className={selectedSessionId === s.id ? "selected-row" : ""}
                      onClick={() => setSelectedSessionId(s.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9" />
                          </svg>
                          <div>
                            <div style={{ fontWeight: '700' }}>{s.name}</div>
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>{s.url}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>{s.type}</td>
                      <td>{s.owner}</td>
                      <td>{s.lastActive}</td>
                      <td>
                        <span className={`agent-status-badge ${s.status === "Active" ? "running" : s.status === "Automated" ? "busy" : "offline"}`}>
                          ● {s.status}
                        </span>
                      </td>
                      <td>
                        <div className="perf-cell-wrapper">
                          <span style={{ fontWeight: 'bold' }}>{s.success}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderTop: '1px solid var(--border-color)', fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredSessions.length} of 42 sessions</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <span style={{ padding: '0 4px' }}>2</span>
                  <span style={{ padding: '0 4px' }}>3</span>
                  <span style={{ padding: '0 2px' }}>...</span>
                  <span style={{ padding: '0 4px' }}>7</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Automation flowchart steps */}
          <div className="dashboard-panel" style={{ flex: 0.8 }}>
            <header className="panel-header">
              <span className="panel-title">Automation Flow: {selectedSession.name}</span>
              <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--text-dim)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
              </svg>
            </header>
            <div className="panel-body" style={{ padding: '8px' }}>
              <div className="automation-flowchart-row">
                {selectedSession.steps.map((step, idx) => (
                  <div key={idx} className={`automation-step-card ${step.status === "Success" ? "success" : "progress"}`}>
                    <span className="automation-step-num">{step.num} {step.title}</span>
                    <span className="automation-step-desc">{step.desc}</span>
                    <span className={`automation-step-status-chip ${step.status === "Success" ? "success" : "progress"}`}>
                      {step.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Live Browser Preview */}
        <div className="browser-col" style={{ flex: 1.3 }}>
          <div className="live-browser-frame">
            {/* Top Toolbar address bar */}
            <div className="browser-top-address-bar">
              <div className="address-bar-row-1">
                <div className="browser-nav-actions">
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>&lt;</button>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>&gt;</button>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>⟳</button>
                </div>

                <div className="browser-address-input-wrapper" style={{ height: '28px', padding: '2px 8px' }}>
                  <svg fill="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)', width: '12px', height: '12px' }}>
                    <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" />
                  </svg>
                  <input
                    type="text"
                    className="browser-address-input"
                    value={selectedSession.previewUrl}
                    readOnly
                    style={{ fontSize: '0.76rem' }}
                  />
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.74rem' }}>☆</span>
                </div>

                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>+</button>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>📱</button>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>💻</button>
                  <button className="browser-nav-btn" style={{ padding: '3px' }}>🖥️</button>
                </div>
              </div>

              {/* Tab options bar */}
              <div className="address-bar-row-2" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', height: '24px' }}>
                <div className="address-bar-tabs">
                  <div className="address-bar-tab-item active">
                    <span>{selectedSession.previewTitle}</span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>×</span>
                  </div>
                  <div className="address-bar-tab-item">
                    <span>Getting Started</span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>×</span>
                  </div>
                  <button className="browser-nav-btn" style={{ width: '18px', height: '18px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>+</button>
                </div>
                <div style={{ color: 'var(--text-dim)', fontSize: '0.72rem', display: 'flex', gap: '8px', paddingBottom: '3px' }}>
                  <span style={{ color: 'var(--color-success)', fontWeight: 'bold' }}>● Live</span>
                </div>
              </div>
            </div>

            {/* Inner view simulator */}
            <div className="mock-preview-viewport">
              <div className="mock-website-sidebar">
                <span className="mock-website-sidebar-logo">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.25z" />
                  </svg>
                  Kronos Docs
                </span>
                <span className="mock-website-nav-item active">Overview</span>
                <span className="mock-website-nav-item">Analytics</span>
                <span className="mock-website-nav-item">Projects</span>
                <span className="mock-website-nav-item">Documents</span>
                <span className="mock-website-nav-item">Datasets</span>
                <span className="mock-website-nav-item">Integrations</span>
                <span className="mock-website-nav-item">API Reference</span>
                <span className="mock-website-nav-item">Settings</span>
              </div>

              <div className="mock-website-main-content">
                <div className="mock-website-header">
                  <span className="mock-website-title">Analytics Overview</span>
                  <span className="mock-website-date">May 5 – May 11, 2025</span>
                </div>

                <div className="mock-website-metrics-grid">
                  <div className="mock-website-metric-card">
                    <span className="mock-website-metric-title">Total Views</span>
                    <span className="mock-website-metric-val">24,892</span>
                    <span className="mock-website-metric-subtext">▲ 18.6% <span style={{ color: '#64748b', fontSize: '0.58rem' }}>last 7d</span></span>
                  </div>
                  <div className="mock-website-metric-card">
                    <span className="mock-website-metric-title">Unique Visitors</span>
                    <span className="mock-website-metric-val">8,457</span>
                    <span className="mock-website-metric-subtext">▲ 12.3% <span style={{ color: '#64748b', fontSize: '0.58rem' }}>last 7d</span></span>
                  </div>
                  <div className="mock-website-metric-card">
                    <span className="mock-website-metric-title">Avg. Time</span>
                    <span className="mock-website-metric-val">3m 24s</span>
                    <span className="mock-website-metric-subtext">▲ 7.8% <span style={{ color: '#64748b', fontSize: '0.58rem' }}>last 7d</span></span>
                  </div>
                  <div className="mock-website-metric-card">
                    <span className="mock-website-metric-title">Bounce Rate</span>
                    <span className="mock-website-metric-val">32.1%</span>
                    <span className="mock-website-metric-subtext down">▼ 5.4% <span style={{ color: '#64748b', fontSize: '0.58rem' }}>last 7d</span></span>
                  </div>
                </div>

                {/* Traffic Chart SVG */}
                <div style={{ border: '1px solid #1e293b', background: '#090d16', borderRadius: '6px', padding: '10px', height: '110px', display: 'flex', flexDirection: 'column' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.66rem', color: '#64748b', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 'bold' }}>Traffic Over Time</span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <span style={{ color: '#3b82f6' }}>● Views</span>
                      <span style={{ color: '#10b981' }}>● Visitors</span>
                    </div>
                  </div>
                  <svg style={{ width: '100%', height: '70px' }}>
                    <path d="M 0,55 Q 50,45 100,50 T 200,20 T 300,35" stroke="#3b82f6" strokeWidth="1.5" fill="none" />
                    <path d="M 0,60 Q 50,55 100,52 T 200,38 T 300,45" stroke="#10b981" strokeWidth="1.5" fill="none" />
                  </svg>
                </div>

                {/* Top pages table */}
                <div style={{ border: '1px solid #1e293b', background: '#090d16', borderRadius: '6px', padding: '8px' }}>
                  <span style={{ fontSize: '0.74rem', fontWeight: 'bold', color: '#fff', display: 'block', marginBottom: '4px' }}>Top Pages</span>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.66rem', textAlign: 'left', color: '#64748b' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #1e293b' }}>
                        <th style={{ padding: '2px 4px' }}>Page</th>
                        <th style={{ padding: '2px 4px', textAlign: 'right' }}>Views</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td style={{ padding: '4px', color: '#fff' }}>/docs/overview</td>
                        <td style={{ padding: '4px', textAlign: 'right', color: '#fff' }}>6,421</td>
                      </tr>
                      <tr>
                        <td style={{ padding: '4px', color: '#fff' }}>/docs/getting-started</td>
                        <td style={{ padding: '4px', textAlign: 'right', color: '#fff' }}>4,289</td>
                      </tr>
                      <tr>
                        <td style={{ padding: '4px', color: '#fff' }}>/docs/analytics</td>
                        <td style={{ padding: '4px', textAlign: 'right', color: '#fff' }}>3,945</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 3: Browser Details */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--color-primary)' }}>
                    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="details-title-name" style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedSession.name}>
                      {selectedSession.name}
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
                  <span>Session ID: {selectedSession.id === "kronos" ? "sess_8f2a7c6d-4b91-4f1e-b0de-7a9b2c8e6d11" : `sess_${selectedSession.id}`}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Session ID!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1" />
                  </svg>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
                {selectedSession.tags.map((tag, idx) => (
                  <span key={idx} className={`mem-type-badge ${tag === "Research" ? "working" : tag === "Browser Automation" ? "session" : tag === "Active" ? "long-term" : "archived"}`}>{tag}</span>
                ))}
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <p className="details-section-desc">{selectedSession.description}</p>
              </div>

              {/* Progress Resource usage */}
              <div className="details-section-box">
                <span className="details-section-title">Resource Usage</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Memory Usage</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedSession.memoryVal} / 1.0 GB ({selectedSession.memoryPct}%)</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedSession.memoryPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Tab Count</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedSession.tabCount} / {selectedSession.tabMax} ({selectedSession.tabPct}%)</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedSession.tabPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Automation Completion</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedSession.completionPct}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedSession.completionPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Run Health Checklist */}
              <div className="details-section-box">
                <span className="details-section-title">Run Health</span>
                <div className="health-metrics-list">
                  {selectedSession.health.map((item, idx) => (
                    <div key={idx} className="health-metric-row">
                      <div className="health-metric-left">
                        <span style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: item.status === "Good" ? 'var(--color-success)' : 'var(--color-warning)',
                          boxShadow: item.status === "Good" ? '0 0 6px var(--color-success)' : '0 0 6px var(--color-warning)',
                        }} />
                        {item.name}
                      </div>
                      <span className={`health-metric-right ${item.status === "Good" ? "good" : "progress"}`}>
                        {item.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent Browser Activity logs */}
              <div className="details-section-box">
                <span className="details-section-title">Recent Browser Activity</span>
                <div className="recent-actions-list">
                  {selectedSession.activity.map((act, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'flex-start' }}>
                      <span className="action-dot" style={{ backgroundColor: act.inProgress ? 'var(--color-warning)' : 'var(--color-primary)', width: '5px', height: '5px', marginTop: '6px', boxShadow: act.inProgress ? '0 0 6px var(--color-warning)' : 'none' }} />
                      <span className="action-text" style={{ fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-dim)', marginRight: '6px' }}>{act.time}</span>
                        {act.text}
                      </span>
                    </div>
                  ))}
                </div>
                <a href="#logs" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={(e) => { e.preventDefault(); alert("Show full browser activity logs."); }}>
                  View all activity logs →
                </a>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
