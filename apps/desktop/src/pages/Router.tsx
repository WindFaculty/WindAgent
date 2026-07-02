import { useState } from "react";

interface RoutingRuleItem {
  id: string;
  name: string;
  trigger: string;
  primary: string;
  fallback: string;
  status: "Active" | "Weighted" | "Fallback" | "Disabled";
  success: string;
  sparkPoints: string;
  description: string;
  routeId: string;
  tags: string[];
  primaryUsage: number;
  fallbackUsage: number;
  successRate: number;
  avgLatency: string;
  primaryModel: string;
  secondaryModel: string;
  finalFallbackModel: string;
  health: Array<{ name: string; latency: string; status: "Good" | "Warning" }>;
  activity: string[];
}

export function Router() {
  const [selectedRouteId, setSelectedRouteId] = useState<string>("planner_chat");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  const routingData: RoutingRuleItem[] = [
    {
      id: "planner_chat",
      name: "Planner → Local Chat",
      trigger: "chat_request",
      primary: "Qwen 3.5 4B Q4",
      fallback: "GPT-5.5",
      status: "Active",
      success: "98%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "Handles general local chat and lightweight planning requests, preferring the local model before escalating to cloud providers.",
      routeId: "route_8f21a6c3",
      tags: ["Planning", "Chat", "Local First", "Fallback Enabled", "High Priority"],
      primaryUsage: 72,
      fallbackUsage: 9,
      successRate: 98,
      avgLatency: "241ms",
      primaryModel: "Qwen 3.5 4B Q4",
      secondaryModel: "GPT-5.5",
      finalFallbackModel: "Claude Sonnet 4.6",
      health: [
        { name: "Ollama Local", latency: "32ms", status: "Good" },
        { name: "OpenAI API", latency: "112ms", status: "Good" },
        { name: "Anthropic API", latency: "145ms", status: "Good" },
        { name: "Mistral Local", latency: "38ms", status: "Good" },
        { name: "Meta Local", latency: "67ms", status: "Warning" },
        { name: "Memory Cache", latency: "12ms", status: "Good" },
      ],
      activity: [
        "Routed chat_request to Qwen 3.5 4B Q4 (10:24 AM)",
        "Fallback triggered for code_task → Claude Sonnet 4.6 (10:22 AM)",
        "Weighted route updated for GUI Agent (10:20 AM)",
        "Provider health check completed (10:18 AM)",
        "Simulation run passed for Planner route (10:16 AM)",
      ],
    },
    {
      id: "coder_model",
      name: "Coder → Code Model",
      trigger: "code_task",
      primary: "Codestral 22B",
      fallback: "Claude Sonnet 4.6",
      status: "Active",
      success: "96%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Route code autocompletion and structural parsing tasks to Codestral, with Sonnet as backup.",
      routeId: "route_3c1a8e2b",
      tags: ["Coding", "Autocomplete", "Standard"],
      primaryUsage: 88,
      fallbackUsage: 5,
      successRate: 96,
      avgLatency: "324ms",
      primaryModel: "Codestral 22B",
      secondaryModel: "Claude Sonnet 4.6",
      finalFallbackModel: "GPT-5.5",
      health: [
        { name: "Ollama Local", latency: "35ms", status: "Good" },
        { name: "OpenAI API", latency: "108ms", status: "Good" },
        { name: "Anthropic API", latency: "135ms", status: "Good" },
        { name: "Mistral Local", latency: "34ms", status: "Good" },
        { name: "Meta Local", latency: "62ms", status: "Good" },
        { name: "Memory Cache", latency: "10ms", status: "Good" },
      ],
      activity: [
        "Routed code_task to Codestral 22B (10:12 AM)",
      ],
    },
    {
      id: "researcher_web",
      name: "Researcher → Web Stack",
      trigger: "web_research",
      primary: "GPT-5.5",
      fallback: "Llama 3 70B",
      status: "Active",
      success: "94%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "Route structural information gathering and parsing tasks to GPT-5.5.",
      routeId: "route_9b2c1d8f",
      tags: ["Research", "Scraping", "Web"],
      primaryUsage: 90,
      fallbackUsage: 8,
      successRate: 94,
      avgLatency: "290ms",
      primaryModel: "GPT-5.5",
      secondaryModel: "Llama 3 70B",
      finalFallbackModel: "Claude Sonnet 4.6",
      health: [
        { name: "Ollama Local", latency: "38ms", status: "Good" },
        { name: "OpenAI API", latency: "115ms", status: "Good" },
        { name: "Anthropic API", latency: "140ms", status: "Good" },
        { name: "Mistral Local", latency: "36ms", status: "Good" },
        { name: "Meta Local", latency: "64ms", status: "Good" },
        { name: "Memory Cache", latency: "11ms", status: "Good" },
      ],
      activity: [
        "Routed web_research to GPT-5.5 (09:44 AM)",
      ],
    },
    {
      id: "gui_route",
      name: "GUI Agent → UI Route",
      trigger: "ui_automation",
      primary: "Mixtral 8x7B",
      fallback: "Qwen 3.5 4B",
      status: "Weighted",
      success: "92%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Weighted balancing of layout validation tasks between local models.",
      routeId: "route_2a3f8c4d",
      tags: ["GUI", "Testing", "Weighted"],
      primaryUsage: 60,
      fallbackUsage: 32,
      successRate: 92,
      avgLatency: "350ms",
      primaryModel: "Mixtral 8x7B",
      secondaryModel: "Qwen 3.5 4B Q4",
      finalFallbackModel: "Gemma 2 9B",
      health: [
        { name: "Ollama Local", latency: "42ms", status: "Good" },
        { name: "OpenAI API", latency: "122ms", status: "Good" },
        { name: "Anthropic API", latency: "155ms", status: "Good" },
        { name: "Mistral Local", latency: "40ms", status: "Good" },
        { name: "Meta Local", latency: "72ms", status: "Warning" },
        { name: "Memory Cache", latency: "14ms", status: "Good" },
      ],
      activity: [
        "Balanced UI testing execution chunks (09:20 AM)",
      ],
    },
    {
      id: "memory_recall",
      name: "Memory Agent → Recall",
      trigger: "memory_lookup",
      primary: "Llama 3 70B",
      fallback: "Gemma 2 9B",
      status: "Fallback",
      success: "95%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "Query contextual long-term vector indexes, using Gemma 2 if local memory sizes are constrained.",
      routeId: "route_6e9a8f2c",
      tags: ["Context", "Recall", "Fallback"],
      primaryUsage: 85,
      fallbackUsage: 10,
      successRate: 95,
      avgLatency: "480ms",
      primaryModel: "Llama 3 70B",
      secondaryModel: "Gemma 2 9B",
      finalFallbackModel: "Memory Cache",
      health: [
        { name: "Ollama Local", latency: "45ms", status: "Good" },
        { name: "OpenAI API", latency: "128ms", status: "Good" },
        { name: "Anthropic API", latency: "160ms", status: "Good" },
        { name: "Mistral Local", latency: "44ms", status: "Good" },
        { name: "Meta Local", latency: "78ms", status: "Good" },
        { name: "Memory Cache", latency: "15ms", status: "Good" },
      ],
      activity: [
        "Escalated lookup query to Gemma 2 Q8 (08:50 AM)",
      ],
    },
    {
      id: "browser_scrape",
      name: "Browser Agent → Scrape",
      trigger: "browser_task",
      primary: "GPT-5.5",
      fallback: "Qwen 3.5 4B",
      status: "Disabled",
      success: "83%",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Trigger scraper nodes using high intelligence cloud LLMs to handle dynamic elements.",
      routeId: "route_7a1b8c9d",
      tags: ["Browser", "Automation", "Disabled"],
      primaryUsage: 0,
      fallbackUsage: 0,
      successRate: 83,
      avgLatency: "—",
      primaryModel: "GPT-5.5",
      secondaryModel: "Qwen 3.5 4B Q4",
      finalFallbackModel: "Claude Sonnet 4.6",
      health: [
        { name: "Ollama Local", latency: "—", status: "Good" },
        { name: "OpenAI API", latency: "—", status: "Good" },
        { name: "Anthropic API", latency: "—", status: "Good" },
        { name: "Mistral Local", latency: "—", status: "Good" },
        { name: "Meta Local", latency: "—", status: "Warning" },
        { name: "Memory Cache", latency: "—", status: "Good" },
      ],
      activity: [
        "Scraper endpoint routes set to offline status (Yesterday)",
      ],
    },
  ];

  const totalRoutesCount = 28;
  const activeRulesCount = 16;
  const fallbackChainsCount = 9;
  const avgLatencyVal = "286ms";
  const successRatePct = "96.8%";
  const trafficBalancePct = "88%";

  const filteredRoutes = routingData.filter((r) => {
    if (activeFilterTab === "active" && r.status !== "Active") return false;
    if (activeFilterTab === "fallback" && r.status !== "Fallback") return false;
    if (activeFilterTab === "weighted" && r.status !== "Weighted") return false;
    if (activeFilterTab === "disabled" && r.status !== "Disabled") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        r.name.toLowerCase().includes(q) ||
        r.trigger.toLowerCase().includes(q) ||
        r.primary.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedRoute = routingData.find((r) => r.id === selectedRouteId) || routingData[0];

  return (
    <main className="models-view" style={{ overflow: 'hidden' }}>
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Router</h1>
          <p className="dashboard-subtitle-text">Control task routing, model selection, fallbacks, and provider orchestration across your agents.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Create New Routing Rule dialog.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            New Rule
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import JSON routing rules.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Import Rules
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Simulate routing paths.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            </svg>
            Simulation
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={() => alert("More Actions.")}>
            More Actions
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ marginLeft: '4px' }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 20l-5.447-2.724A2 2 0 013 15.483V7.517a2 2 0 011.553-1.957L9 4m0 16v-8m0 8l5.447-2.724A2 2 0 0015 15.483V7.517a2 2 0 00-1.553-1.957L9 4m0 0V2h8a2 2 0 012 2v10a2 2 0 01-2 2h-4" />
              </svg>
              <span>Total Routes</span>
            </div>
            <div className="trend-indicator up">▲ 14%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalRoutesCount}</div>
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
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4" />
              </svg>
              <span>Active Rules</span>
            </div>
            <div className="trend-indicator up">▲ 6%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{activeRulesCount}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5" />
              </svg>
              <span>Fallback Chains</span>
            </div>
            <div className="trend-indicator up" style={{ color: 'var(--color-warning)' }}>▲ 2</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{fallbackChainsCount}</div>
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
              <span>Avg Route Latency</span>
            </div>
            <div className="trend-indicator down" style={{ color: 'var(--color-success)' }}>▼ 7.8%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{avgLatencyVal}</div>
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
              <span>Routing Success Rate</span>
            </div>
            <div className="trend-indicator up">▲ 1.9%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{successRatePct}</div>
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
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2M7 19h10" />
              </svg>
              <span>Traffic Balance</span>
            </div>
            <div className="trend-indicator up">▲ 4.2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{trafficBalancePct}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Router page split grid */}
      <div className="router-console-layout">
        {/* Column 1: Routing Rules Library and Traffic Distribution Donut */}
        <div className="router-col">
          <div className="dashboard-panel" style={{ flex: 1.3 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '10px 12px', flexDirection: 'column', alignItems: 'stretch', gap: '8px' }}>
              <div className="agent-directory-header">
                <span className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A2 2 0 013 15.483V7.517a2 2 0 011.553-1.957L9 4m0 16v-8" />
                  </svg>
                  Routing Rules
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>⟳</button>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <div className="search-box-container" style={{ flex: 1 }}>
                  <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search routes..."
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                  />
                </div>
                <button className="toggle-icon-btn" style={{ padding: '6px' }}>
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                  </svg>
                </button>
              </div>

              {/* Filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '2px' }}>
                <button className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`} onClick={() => setActiveFilterTab("all")}>All</button>
                <button className={`tab-btn ${activeFilterTab === "active" ? "active" : ""}`} onClick={() => setActiveFilterTab("active")}>Active</button>
                <button className={`tab-btn ${activeFilterTab === "fallback" ? "active" : ""}`} onClick={() => setActiveFilterTab("fallback")}>Fallback</button>
                <button className={`tab-btn ${activeFilterTab === "weighted" ? "active" : ""}`} onClick={() => setActiveFilterTab("weighted")}>Weighted</button>
                <button className={`tab-btn ${activeFilterTab === "disabled" ? "active" : ""}`} onClick={() => setActiveFilterTab("disabled")}>Disabled</button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Route Name</th>
                    <th>Trigger</th>
                    <th>Primary Target</th>
                    <th>Fallback</th>
                    <th>Status</th>
                    <th>Success</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRoutes.map((r) => (
                    <tr
                      key={r.id}
                      className={selectedRouteId === r.id ? "selected-row" : ""}
                      onClick={() => setSelectedRouteId(r.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                          </svg>
                          <span style={{ fontWeight: '700' }}>{r.name}</span>
                        </div>
                      </td>
                      <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{r.trigger}</td>
                      <td>{r.primary}</td>
                      <td>{r.fallback}</td>
                      <td>
                        <span className={`agent-status-badge ${r.status === "Active" ? "running" : r.status === "Weighted" ? "busy" : r.status === "Fallback" ? "idle" : "offline"}`}>
                          ● {r.status}
                        </span>
                      </td>
                      <td>
                        <div className="perf-cell-wrapper">
                          <span style={{ fontWeight: 'bold' }}>{r.success}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderTop: '1px solid var(--border-color)', fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredRoutes.length} of 28 routes</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <span style={{ padding: '0 4px' }}>2</span>
                  <span style={{ padding: '0 4px' }}>3</span>
                  <span style={{ padding: '0 2px' }}>...</span>
                  <span style={{ padding: '0 4px' }}>5</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Traffic Distribution Donut Chart and legend list */}
          <div className="dashboard-panel" style={{ flex: 0.8 }}>
            <header className="panel-header">
              <span className="panel-title">Traffic Distribution</span>
            </header>
            <div className="panel-body" style={{ padding: '10px', display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div className="donut-chart-container" style={{ width: '90px', height: '90px', flexShrink: 0 }}>
                <svg width="90" height="90" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#162035" strokeWidth="3" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#a855f7" strokeWidth="3.2" strokeDasharray="24 76" strokeDashoffset="25" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#3b82f6" strokeWidth="3.2" strokeDasharray="22 78" strokeDashoffset="1" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f59e0b" strokeWidth="3.2" strokeDasharray="16 84" strokeDashoffset="79" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#ef4444" strokeWidth="3.2" strokeDasharray="14 86" strokeDashoffset="63" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#06b6d4" strokeWidth="3.2" strokeDasharray="12 88" strokeDashoffset="49" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#eab308" strokeWidth="3.2" strokeDasharray="7 93" strokeDashoffset="37" />
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#4b5563" strokeWidth="3.2" strokeDasharray="5 95" strokeDashoffset="30" />
                </svg>
                <div className="donut-inner-text">
                  <span className="donut-inner-value" style={{ fontSize: '0.94rem' }}>1,284</span>
                  <span className="donut-inner-label" style={{ fontSize: '0.54rem', marginTop: '0px' }}>routes</span>
                </div>
              </div>

              <div className="traffic-legend-container">
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#a855f7' }} />
                    Qwen 3.5 4B Q4
                  </div>
                  <span className="traffic-legend-right">24%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#3b82f6' }} />
                    GPT-5.5
                  </div>
                  <span className="traffic-legend-right">22%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#f59e0b' }} />
                    Codestral 22B
                  </div>
                  <span className="traffic-legend-right">16%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#ef4444' }} />
                    Mixtral 8x7B
                  </div>
                  <span className="traffic-legend-right">14%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#06b6d4' }} />
                    Llama 3 70B
                  </div>
                  <span className="traffic-legend-right">12%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#eab308' }} />
                    Claude Sonnet 4.6
                  </div>
                  <span className="traffic-legend-right">7%</span>
                </div>
                <div className="traffic-legend-row-item">
                  <div className="traffic-legend-left">
                    <span className="traffic-legend-dot" style={{ backgroundColor: '#4b5563' }} />
                    Other
                  </div>
                  <span className="traffic-legend-right">5%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: Routing Graph node map and Route Simulation horizontal flowchart */}
        <div className="router-col" style={{ flex: 1.3 }}>
          {/* Routing Graph */}
          <div className="dashboard-panel" style={{ flex: 1.3 }}>
            <header className="panel-header">
              <span className="panel-title">Routing Graph</span>
              <div style={{ display: 'flex', gap: '4px' }}>
                <button className="browser-nav-btn" style={{ padding: '3px' }}>🔍</button>
                <button className="browser-nav-btn" style={{ padding: '3px' }}>+</button>
                <button className="browser-nav-btn" style={{ padding: '3px' }}>-</button>
              </div>
            </header>
            <div className="panel-body" style={{ padding: '8px' }}>
              <div className="routing-graph-container">
                <div className="graph-role-nodes-col">
                  <div className="graph-node-box"><span style={{ color: '#3b82f6' }}>●</span> Planner</div>
                  <div className="graph-node-box"><span style={{ color: '#f59e0b' }}>●</span> Coder</div>
                  <div className="graph-node-box"><span style={{ color: '#10b981' }}>●</span> Researcher</div>
                  <div className="graph-node-box"><span style={{ color: '#a855f7' }}>●</span> GUI Agent</div>
                  <div className="graph-node-box"><span style={{ color: '#3b82f6' }}>●</span> Browser Agent</div>
                  <div className="graph-node-box"><span style={{ color: '#ec4899' }}>●</span> Memory Agent</div>
                </div>

                <div className="graph-center-hub-col">
                  <div className="graph-node-box hub">
                    <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)', margin: '0 auto 4px auto' }}>
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21V3m0 18a9 9 0 000-18m0 0a9.004 9.004 0 018.716 6.747M12 3a9.004 9.004 0 00-8.716 6.747" />
                    </svg>
                    Router Core
                  </div>
                </div>

                <div className="graph-model-nodes-col">
                  <div className="graph-node-box model">Qwen 3.5 4B Q4</div>
                  <div className="graph-node-box model">Codestral 22B</div>
                  <div className="graph-node-box model">GPT-5.5</div>
                  <div className="graph-node-box model">Claude Sonnet 4.6</div>
                  <div className="graph-node-box model">Mixtral 8x7B</div>
                  <div className="graph-node-box model">Llama 3 70B</div>
                  <div className="graph-node-box model">Gemma 2 9B</div>
                </div>

                {/* SVG Route Connector overlay lines */}
                <svg className="graph-connector-svg">
                  {/* Left lines connecting role nodes to central Router Core */}
                  <path d="M 90,26 C 130,26 130,78 156,78" stroke="#3b82f6" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 90,54 C 130,54 130,82 156,82" stroke="#f59e0b" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 90,82 L 156,86" stroke="#10b981" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 90,110 C 130,110 130,90 156,90" stroke="#a855f7" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 90,138 C 130,138 130,94 156,94" stroke="#3b82f6" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 90,166 C 130,166 130,98 156,98" stroke="#ec4899" strokeWidth="1" fill="none" opacity="0.6" />

                  {/* Right lines connecting Router Core to model nodes */}
                  <path d="M 266,78 C 300,78 300,24 322,24" stroke="#3b82f6" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 266,82 C 300,82 300,50 322,50" stroke="#f59e0b" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 266,86 L 322,76" stroke="#10b981" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 266,90 C 300,90 300,102 322,102" stroke="#eab308" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 266,94 C 300,94 300,128 322,128" stroke="#a855f7" strokeWidth="1" fill="none" opacity="0.6" />
                  <path d="M 266,98 C 300,98 300,154 322,154" stroke="#06b6d4" strokeWidth="1.5" strokeDasharray="3,3" fill="none" opacity="0.6" />
                </svg>
              </div>
              <div style={{ display: 'flex', gap: '16px', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto', color: 'var(--text-dim)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', backgroundColor: '#3b82f6', borderRadius: '50%' }} /> Chat</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', backgroundColor: '#f59e0b', borderRadius: '50%' }} /> Code</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', backgroundColor: '#10b981', borderRadius: '50%' }} /> Research</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '8px', height: '8px', backgroundColor: '#a855f7', borderRadius: '50%' }} /> GUI</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><span style={{ width: '10px', height: '2px', borderBottom: '2px dashed var(--text-dim)' }} /> Fallback Route</div>
              </div>
            </div>
          </div>

          {/* Route Simulation */}
          <div className="dashboard-panel" style={{ flex: 0.8 }}>
            <header className="panel-header">
              <span className="panel-title">Route Simulation</span>
            </header>
            <div className="panel-body" style={{ padding: '8px', gap: '10px' }}>
              <div className="browser-address-input-wrapper" style={{ height: '28px', padding: '2px 8px' }}>
                <span style={{ color: 'var(--text-dim)', fontSize: '0.74rem', marginRight: '4px' }}>Request Example:</span>
                <input
                  type="text"
                  className="browser-address-input"
                  value="Analyze repo and propose fixes"
                  readOnly
                  style={{ fontSize: '0.76rem' }}
                />
              </div>

              <div className="sim-flowchart-row">
                <div className="sim-step-node-item">User Request</div>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
                <div className="sim-step-node-item">Planner</div>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
                <div className="sim-step-node-item" style={{ borderColor: 'rgba(59, 130, 246, 0.4)' }}>Router Decision</div>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
                <div className="sim-step-node-item selected">Primary Model</div>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
                <div className="sim-step-node-item">Validation</div>
                <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ color: 'var(--text-dim)' }}><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="4" d="M9 5l7 7-7 7" /></svg>
                <div className="sim-step-node-item">Response</div>
              </div>

              <div className="sim-stats-cards-grid">
                <div className="sim-stat-box selected">
                  <span className="sim-stat-title">Primary</span>
                  <span className="sim-stat-value">Selected</span>
                </div>
                <div className="sim-stat-box fallback">
                  <span className="sim-stat-title">Fallback</span>
                  <span className="sim-stat-value" style={{ fontSize: '0.8rem' }}>Not Needed</span>
                </div>
                <div className="sim-stat-box confidence">
                  <span className="sim-stat-title">Confidence</span>
                  <span className="sim-stat-value">0.91</span>
                </div>
                <div className="sim-stat-box cost">
                  <span className="sim-stat-title">Estimated Cost</span>
                  <span className="sim-stat-value">$0.003</span>
                </div>
                <div className="sim-stat-box eta">
                  <span className="sim-stat-title">ETA</span>
                  <span className="sim-stat-value">2.1s</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 3: Route Details sidebar card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--color-primary)' }}>
                    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A2 2 0 013 15.483V7.517a2 2 0 011.553-1.957L9 4m0 16v-8" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="details-title-name" style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedRoute.name}>
                      {selectedRoute.name}
                    </h2>
                  </div>
                </div>
                <span className="details-status-badge running" style={{ color: 'var(--color-success)' }}>
                  Active
                </span>
              </div>

              <div className="details-id-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>Route ID: {selectedRoute.routeId}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Route ID!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1" />
                  </svg>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
                {selectedRoute.tags.map((tag, idx) => (
                  <span key={idx} className="mem-type-badge working" style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', color: '#93c5fd', borderColor: 'rgba(59, 130, 246, 0.15)' }}>{tag}</span>
                ))}
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <p className="details-section-desc">{selectedRoute.description}</p>
              </div>

              {/* Progress metrics bars */}
              <div className="details-section-box">
                <span className="details-section-title">Routing Performance</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Primary Usage</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedRoute.primaryUsage}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.primaryUsage}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Fallback Usage</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedRoute.fallbackUsage}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.fallbackUsage}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Success Rate</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedRoute.successRate}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.successRate}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Avg Latency</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedRoute.avgLatency}</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: selectedRoute.avgLatency !== "—" ? '24%' : '0%', background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Main Targets list */}
              <div className="details-section-box">
                <span className="details-section-title">Route Targets Details</span>
                <div className="assigned-routes-list">
                  <div className="assigned-route-row">
                    <span className="assigned-route-name" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="traffic-legend-dot" style={{ backgroundColor: '#a855f7' }} />
                      Primary Target
                    </span>
                    <span className="assigned-route-type" style={{ color: '#fff', fontWeight: 'bold' }}>{selectedRoute.primaryModel}</span>
                  </div>
                  <div className="assigned-route-row">
                    <span className="assigned-route-name" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="traffic-legend-dot" style={{ backgroundColor: '#3b82f6' }} />
                      Secondary (escalation)
                    </span>
                    <span className="assigned-route-type" style={{ color: '#fff', fontWeight: 'bold' }}>{selectedRoute.secondaryModel}</span>
                  </div>
                  <div className="assigned-route-row">
                    <span className="assigned-route-name" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span className="traffic-legend-dot" style={{ backgroundColor: '#eab308' }} />
                      Final Fallback
                    </span>
                    <span className="assigned-route-type" style={{ color: '#fff', fontWeight: 'bold' }}>{selectedRoute.finalFallbackModel}</span>
                  </div>
                </div>
              </div>

              {/* Controls row */}
              <footer className="agent-details-footer" style={{ borderTop: 'none', padding: '0px', gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <button className="details-footer-btn restart" onClick={() => alert("Edit Rule configuration.")}>
                  <span>Edit Rule</span>
                </button>
                <button className="details-footer-btn" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }} onClick={() => alert("Disable Rule.")}>
                  <span style={{ color: '#fca5a5' }}>Disable</span>
                </button>
                <button className="details-footer-btn" onClick={() => alert("Duplicate routing rule.")}>
                  <span>Duplicate</span>
                </button>
                <button className="details-footer-btn start" onClick={() => alert("Test Routing triggered.")}>
                  <span>Test Route</span>
                </button>
              </footer>

              {/* Provider Health list */}
              <div className="details-section-box">
                <span className="details-section-title">Provider Health</span>
                <div className="health-metrics-list">
                  {selectedRoute.health.map((item, idx) => (
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
                        {item.latency}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent Routing Activity log timeline */}
              <div className="details-section-box">
                <span className="details-section-title">Recent Routing Activity</span>
                <div className="recent-actions-list">
                  {selectedRoute.activity.map((act, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'flex-start' }}>
                      <span className="action-dot" style={{ backgroundColor: 'var(--color-primary)', width: '5px', height: '5px', marginTop: '6px' }} />
                      <span className="action-text" style={{ fontSize: '0.78rem' }}>
                        {act}
                      </span>
                    </div>
                  ))}
                </div>
                <a href="#logs" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={(e) => { e.preventDefault(); alert("Show full routing activity logs."); }}>
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
