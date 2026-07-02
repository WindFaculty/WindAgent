import React, { useState } from "react";

export interface MetricState {
  cpu: number;
  ram: number;
  ramGb: number;
  gpu: number;
  vram: number;
  vramGb: number;
  cpuHistory: number[];
  ramHistory: number[];
  gpuHistory: number[];
  vramHistory: number[];
}

interface DashboardProps {
  metrics: MetricState;
  setMetrics: React.Dispatch<React.SetStateAction<MetricState>>;
  setActiveTab: (tab: string) => void;
  refreshInterval: string;
  setRefreshInterval: (interval: string) => void;
  startNewAnalysis: (userQuery: string) => void;
}

export function Dashboard({
  metrics,
  setMetrics,
  setActiveTab,
  refreshInterval,
  setRefreshInterval,
  startNewAnalysis,
}: DashboardProps) {
  // Chart filter tab clicks (local state to the dashboard page)
  const [activityFilter, setActivityFilter] = useState<string>("24h");
  const [throughputFilter, setThroughputFilter] = useState<string>("24h");

  // SVG donut math calculations
  const donutSegments = [
    { percent: 38, color: "#3b82f6", label: "Llama 3 70B" },
    { percent: 24, color: "#a855f7", label: "Mistral 7B Instruct" },
    { percent: 16, color: "#10b981", label: "Code Llama 34B" },
    { percent: 12, color: "#f59e0b", label: "Gemma 2 9B" },
    { percent: 10, color: "#9ca3af", label: "Other" },
  ];
  let accumulatedPercent = 0;

  return (
    <main className="dashboard-view">
      {/* Header row */}
      <div className="dashboard-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Dashboard</h1>
          <p className="dashboard-subtitle-text">Monitor your agents, tasks, and system health at a glance.</p>
        </div>

        <div className="dashboard-header-controls">
          <div className="refresh-toggle-container">
            <span>Auto refresh</span>
            <select
              className="refresh-select"
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(e.target.value)}
            >
              <option value="10s">10s</option>
              <option value="30s">30s</option>
              <option value="1m">1m</option>
            </select>
          </div>
          <button
            className="refresh-btn"
            onClick={() => {
              setMetrics((prev) => ({
                ...prev,
                cpu: Math.max(10, Math.min(60, prev.cpu + Math.round(Math.random() * 4 - 2))),
              }));
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
            </svg>
          </button>
        </div>
      </div>

      {/* Metric cards deck */}
      <div className="metrics-row-grid">
        {/* Card 1: Active Agents */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <span>Active Agents</span>
            </div>
            <div className="trend-indicator up">▲ 1</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">4</div>
              <div className="m-card-subtext">of 6 online</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        {/* Card 2: Running Tasks */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
              </svg>
              <span>Running Tasks</span>
            </div>
            <div className="trend-indicator warning">▲ 2</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">7</div>
              <div className="m-card-subtext">in progress</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        {/* Card 3: Completed Runs Today */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
              <span>Completed Runs Today</span>
            </div>
            <div className="trend-indicator up">▲ 18%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">128</div>
              <div className="m-card-subtext">total runs</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        {/* Card 4: Success Rate */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#06b6d4' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Success Rate</span>
            </div>
            <div className="trend-indicator up">▲ 4.2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">93.6%</div>
              <div className="m-card-subtext">last 24h</div>
            </div>
            <svg className="m-card-sparkline-svg cyan" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        {/* Card 5: Avg. Response Time */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Avg. Response Time</span>
            </div>
            <div className="trend-indicator up">▼ -0.18s</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">1.42s</div>
              <div className="m-card-subtext">per task</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,22 15,14 30,18 45,8 60,12 68,6" />
            </svg>
          </div>
        </div>

        {/* Card 6: Memory Usage */}
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              <span>Memory Usage</span>
            </div>
            <div className="trend-indicator purple">▲ 5%</div>
          </div>
          <div className="m-card-body" style={{ alignItems: 'stretch', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span className="m-card-value">{metrics.ram}%</span>
              <span className="m-card-subtext" style={{ fontSize: '0.68rem' }}>{metrics.ramGb} / 16 GB</span>
            </div>
            <div className="progress-bar-bg" style={{ height: '5px', marginTop: '2px' }}>
              <div className="progress-bar-fill" style={{ width: `${metrics.ram}%`, background: 'linear-gradient(90deg, #3b82f6, #6366f1)' }} />
            </div>
          </div>
        </div>
      </div>

      {/* Mid row grid: charts & system health */}
      <div className="mid-row-grid">
        {/* Chart 1: Agent Activity */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Agent Activity Over Time</div>
            <div className="chart-header-tabs">
              <button
                className={`tab-btn ${activityFilter === "24h" ? "active" : ""}`}
                onClick={() => setActivityFilter("24h")}
              >
                24h
              </button>
              <button
                className={`tab-btn ${activityFilter === "7d" ? "active" : ""}`}
                onClick={() => setActivityFilter("7d")}
              >
                7d
              </button>
              <button
                className={`tab-btn ${activityFilter === "30d" ? "active" : ""}`}
                onClick={() => setActivityFilter("30d")}
              >
                30d
              </button>
            </div>
          </header>
          <div className="panel-body">
            <div className="chart-legend">
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: '#3b82f6' }} /> Planner
              </div>
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: '#a855f7' }} /> GUI Agent
              </div>
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: '#10b981' }} /> Coder
              </div>
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: '#f97316' }} /> Researcher
              </div>
            </div>

            <svg className="svg-line-chart">
              <line className="grid-line" x1="0" y1="20" x2="300" y2="20" />
              <line className="grid-line" x1="0" y1="55" x2="300" y2="55" />
              <line className="grid-line" x1="0" y1="90" x2="300" y2="90" />
              <line className="grid-line" x1="0" y1="125" x2="300" y2="125" />

              {activityFilter === "24h" ? (
                <>
                  <path className="chart-path" stroke="#3b82f6" d="M 0,110 Q 50,60 100,85 T 200,45 T 300,70" />
                  <path className="chart-path" stroke="#a855f7" d="M 0,120 Q 50,85 100,95 T 200,60 T 300,85" />
                  <path className="chart-path" stroke="#10b981" d="M 0,90 Q 50,40 100,70 T 200,30 T 300,50" />
                  <path className="chart-path" stroke="#f97316" d="M 0,130 Q 50,110 100,105 T 200,85 T 300,110" />
                </>
              ) : (
                <>
                  <path className="chart-path" stroke="#3b82f6" d="M 0,80 Q 50,90 100,55 T 200,85 T 300,30" />
                  <path className="chart-path" stroke="#a855f7" d="M 0,100 Q 50,110 100,75 T 200,95 T 300,50" />
                  <path className="chart-path" stroke="#10b981" d="M 0,60 Q 50,50 100,35 T 200,60 T 300,20" />
                  <path className="chart-path" stroke="#f97316" d="M 0,110 Q 50,120 100,95 T 200,115 T 300,80" />
                </>
              )}
            </svg>
          </div>
        </div>

        {/* Chart 2: Task Throughput */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Task Throughput</div>
            <div className="chart-header-tabs">
              <button
                className={`tab-btn ${throughputFilter === "24h" ? "active" : ""}`}
                onClick={() => setThroughputFilter("24h")}
              >
                24h
              </button>
              <button
                className={`tab-btn ${throughputFilter === "7d" ? "active" : ""}`}
                onClick={() => setThroughputFilter("7d")}
              >
                7d
              </button>
              <button
                className={`tab-btn ${throughputFilter === "30d" ? "active" : ""}`}
                onClick={() => setThroughputFilter("30d")}
              >
                30d
              </button>
            </div>
          </header>
          <div className="panel-body">
            <div className="chart-legend">
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: 'var(--color-success)' }} /> Completed
              </div>
              <div className="legend-dot-item">
                <span className="legend-dot" style={{ backgroundColor: 'var(--color-danger)' }} /> Failed
              </div>
            </div>

            <svg className="svg-bar-chart">
              <line className="grid-line" x1="0" y1="20" x2="300" y2="20" />
              <line className="grid-line" x1="0" y1="60" x2="300" y2="60" />
              <line className="grid-line" x1="0" y1="100" x2="300" y2="100" />
              <line className="grid-line" x1="0" y1="140" x2="300" y2="140" />

              {throughputFilter === "24h" ? (
                <>
                  <rect className="bar-completed" x="15" y="50" width="8" height="90" rx="2" />
                  <rect className="bar-failed" x="25" y="110" width="8" height="30" rx="2" />
                  <rect className="bar-completed" x="55" y="30" width="8" height="110" rx="2" />
                  <rect className="bar-failed" x="65" y="120" width="8" height="20" rx="2" />
                  <rect className="bar-completed" x="95" y="40" width="8" height="100" rx="2" />
                  <rect className="bar-failed" x="105" y="100" width="8" height="40" rx="2" />
                  <rect className="bar-completed" x="135" y="20" width="8" height="120" rx="2" />
                  <rect className="bar-failed" x="145" y="130" width="8" height="10" rx="2" />
                  <rect className="bar-completed" x="175" y="60" width="8" height="80" rx="2" />
                  <rect className="bar-failed" x="185" y="115" width="8" height="25" rx="2" />
                  <rect className="bar-completed" x="215" y="45" width="8" height="95" rx="2" />
                  <rect className="bar-failed" x="225" y="110" width="8" height="30" rx="2" />
                </>
              ) : (
                <>
                  <rect className="bar-completed" x="15" y="70" width="8" height="70" rx="2" />
                  <rect className="bar-failed" x="25" y="120" width="8" height="20" rx="2" />
                  <rect className="bar-completed" x="55" y="40" width="8" height="100" rx="2" />
                  <rect className="bar-failed" x="65" y="110" width="8" height="30" rx="2" />
                  <rect className="bar-completed" x="95" y="60" width="8" height="80" rx="2" />
                  <rect className="bar-failed" x="105" y="125" width="8" height="15" rx="2" />
                  <rect className="bar-completed" x="135" y="30" width="8" height="110" rx="2" />
                  <rect className="bar-failed" x="145" y="120" width="8" height="20" rx="2" />
                  <rect className="bar-completed" x="175" y="50" width="8" height="90" rx="2" />
                  <rect className="bar-failed" x="185" y="100" width="8" height="40" rx="2" />
                  <rect className="bar-completed" x="215" y="35" width="8" height="105" rx="2" />
                  <rect className="bar-failed" x="225" y="130" width="8" height="10" rx="2" />
                </>
              )}
            </svg>
          </div>
        </div>

        {/* Chart 3: Model Usage Distribution */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Model Usage Distribution</div>
          </header>
          <div className="panel-body" style={{ justifyContent: 'center' }}>
            <div className="donut-chart-container">
              <svg width="100" height="100" viewBox="0 0 100 100">
                {donutSegments.map((seg, idx) => {
                  const strokeDasharray = `${(seg.percent / 100) * 251.32} 251.32`;
                  const strokeDashoffset = `${-(accumulatedPercent / 100) * 251.32}`;
                  accumulatedPercent += seg.percent;
                  return (
                    <circle
                      key={idx}
                      cx="50"
                      cy="50"
                      r="40"
                      fill="transparent"
                      stroke={seg.color}
                      strokeWidth="10"
                      strokeDasharray={strokeDasharray}
                      strokeDashoffset={strokeDashoffset}
                    />
                  );
                })}
              </svg>
              <div className="donut-inner-text">
                <span className="donut-inner-value">512</span>
                <span className="donut-inner-label">requests</span>
              </div>
            </div>

            <div className="donut-details-list">
              {donutSegments.map((seg, idx) => (
                <div key={idx} className="donut-detail-row">
                  <div className="detail-label-left">
                    <span className="legend-dot" style={{ backgroundColor: seg.color }} />
                    {seg.label}
                  </div>
                  <div className="detail-value-right">{seg.percent}%</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Column 4: System Health */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">System Health</div>
            <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
              View All
            </button>
          </header>
          <div className="panel-body">
            <div className="system-health-list">
              <div className="system-health-row">
                <span className="sh-row-left">CPU</span>
                <span className="sh-row-right good">
                  {metrics.cpu}%
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
              <div className="system-health-row">
                <span className="sh-row-left">RAM</span>
                <span className="sh-row-right good">
                  {metrics.ram}%
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
              <div className="system-health-row">
                <span className="sh-row-left">GPU</span>
                <span className="sh-row-right good">
                  {metrics.gpu}%
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
              <div className="system-health-row">
                <span className="sh-row-left">VRAM</span>
                <span className="sh-row-right good">
                  {metrics.vram}%
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
              <div className="system-health-row">
                <span className="sh-row-left">Disk</span>
                <span className="sh-row-right good">
                  46%
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
              <div className="system-health-row">
                <span className="sh-row-left">Network</span>
                <span className="sh-row-right good" style={{ fontSize: '0.74rem' }}>
                  32 Mbps
                  <svg className="sh-check-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row grid: custom tables */}
      <div className="bottom-tables-grid">
        {/* Grid block 1: Active Agents */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Active Agents</div>
            <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
              View All
            </button>
          </header>
          <div className="panel-body" style={{ padding: '8px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Status</th>
                  <th>Current Job</th>
                  <th>Uptime</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <div className="agent-name-cell">
                      <span className="agent-color-dot" style={{ backgroundColor: '#3b82f6' }} />
                      Planner
                    </div>
                  </td>
                  <td><span className="agent-status-badge running">Running</span></td>
                  <td style={{ color: 'var(--text-muted)' }}>Breaking down requirements</td>
                  <td>2h 14m</td>
                </tr>
                <tr>
                  <td>
                    <div className="agent-name-cell">
                      <span className="agent-color-dot" style={{ backgroundColor: '#a855f7' }} />
                      GUI Agent
                    </div>
                  </td>
                  <td><span className="agent-status-badge running">Running</span></td>
                  <td style={{ color: 'var(--text-muted)' }}>Building UI components</td>
                  <td>1h 47m</td>
                </tr>
                <tr>
                  <td>
                    <div className="agent-name-cell">
                      <span className="agent-color-dot" style={{ backgroundColor: '#f59e0b' }} />
                      Coder
                    </div>
                  </td>
                  <td><span className="agent-status-badge busy">Busy</span></td>
                  <td style={{ color: 'var(--text-muted)' }}>Implementing auth flow</td>
                  <td>2h 58m</td>
                </tr>
                <tr>
                  <td>
                    <div className="agent-name-cell">
                      <span className="agent-color-dot" style={{ backgroundColor: '#10b981' }} />
                      Researcher
                    </div>
                  </td>
                  <td><span className="agent-status-badge idle">Idle</span></td>
                  <td style={{ color: 'var(--text-dim)' }}>Ready for new task</td>
                  <td>45m</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Grid block 2: Recent Activity */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Recent Activity</div>
            <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
              View All
            </button>
          </header>
          <div className="panel-body">
            <div className="timeline-logs-container">
              <div className="timeline-event-row">
                <span className="t-event-time">10:21 AM</span>
                <span className="t-event-node completed" />
                <div className="t-event-details">
                  <span className="t-event-actor">GUI Agent</span>
                  <span className="t-event-desc">Compiled UI bundle successfully</span>
                </div>
              </div>
              <div className="timeline-event-row">
                <span className="t-event-time">10:18 AM</span>
                <span className="t-event-node completed" />
                <div className="t-event-details">
                  <span className="t-event-actor">Coder</span>
                  <span className="t-event-desc">Pushed changes to repository</span>
                </div>
              </div>
              <div className="timeline-event-row">
                <span className="t-event-time">10:14 AM</span>
                <span className="t-event-node completed" />
                <div className="t-event-details">
                  <span className="t-event-actor">Planner</span>
                  <span className="t-event-desc">Created task plan: Authentication</span>
                </div>
              </div>
              <div className="timeline-event-row">
                <span className="t-event-time">10:09 AM</span>
                <span className="t-event-node completed" />
                <div className="t-event-details">
                  <span className="t-event-actor">Researcher</span>
                  <span className="t-event-desc">Completed market analysis report</span>
                </div>
              </div>
              <div className="timeline-event-row">
                <span className="t-event-time">10:05 AM</span>
                <span className="t-event-node info" />
                <div className="t-event-details">
                  <span className="t-event-actor">System</span>
                  <span className="t-event-desc">Model router updated routing rules</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Grid block 3: Task Queue */}
        <div className="dashboard-panel">
          <header className="panel-header">
            <div className="panel-title">Task Queue</div>
            <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
              View All
            </button>
          </header>
          <div className="panel-body" style={{ padding: '8px' }}>
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Progress</th>
                  <th>ETA</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>
                    <div className="t-queue-task-name">Generate API Docs</div>
                    <div className="t-queue-task-actor">Researcher</div>
                  </td>
                  <td className="t-queue-bar-cell">
                    <div className="t-queue-bar-wrapper">
                      <div className="progress-bar-bg" style={{ height: '4px', flex: 1 }}>
                        <div className="progress-bar-fill" style={{ width: '64%', background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                      <span className="t-queue-percentage">64%</span>
                    </div>
                  </td>
                  <td>12m</td>
                </tr>
                <tr>
                  <td>
                    <div className="t-queue-task-name">Refactor Auth Service</div>
                    <div className="t-queue-task-actor">Coder</div>
                  </td>
                  <td className="t-queue-bar-cell">
                    <div className="t-queue-bar-wrapper">
                      <div className="progress-bar-bg" style={{ height: '4px', flex: 1 }}>
                        <div className="progress-bar-fill" style={{ width: '42%', background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                      <span className="t-queue-percentage">42%</span>
                    </div>
                  </td>
                  <td>18m</td>
                </tr>
                <tr>
                  <td>
                    <div className="t-queue-task-name">UI: Settings Page</div>
                    <div className="t-queue-task-actor">GUI Agent</div>
                  </td>
                  <td className="t-queue-bar-cell">
                    <div className="t-queue-bar-wrapper">
                      <div className="progress-bar-bg" style={{ height: '4px', flex: 1 }}>
                        <div className="progress-bar-fill" style={{ width: '75%', background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                      <span className="t-queue-percentage">75%</span>
                    </div>
                  </td>
                  <td>8m</td>
                </tr>
                <tr>
                  <td>
                    <div className="t-queue-task-name">Data Pipeline Review</div>
                    <div className="t-queue-task-actor">Researcher</div>
                  </td>
                  <td className="t-queue-bar-cell">
                    <div className="t-queue-bar-wrapper">
                      <div className="progress-bar-bg" style={{ height: '4px', flex: 1 }}>
                        <div className="progress-bar-fill" style={{ width: '33%', background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                      <span className="t-queue-percentage">33%</span>
                    </div>
                  </td>
                  <td>25m</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Grid block 4: Permissions & Storage */}
        <div className="dashboard-panel" style={{ gap: '12px', padding: '12px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div className="section-label" style={{ padding: '0 4px' }}>
              Permissions
              <button className="role-btn" style={{ padding: '1px 4px', fontSize: '0.68rem', height: 'auto' }}>
                View All
              </button>
            </div>
            <div className="permission-status-deck">
              <div className="perm-deck-row allowed">
                <span>All Allowed</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div className="perm-deck-row blocked">
                <span>Blocked</span>
                <span>3</span>
              </div>
              <div className="perm-deck-row pending">
                <span>Pending</span>
                <span>1</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', borderTop: '1px solid var(--border-color)', paddingTop: '10px' }}>
            <div className="section-label" style={{ padding: '0 4px' }}>
              Storage
            </div>
            <div className="storage-box-container">
              <div className="storage-circle-svg">
                <svg>
                  <circle className="state-ring-bg" cx="26" cy="26" r="22" strokeWidth="4" />
                  <circle
                    className="state-ring-fill"
                    cx="26"
                    cy="26"
                    r="22"
                    strokeWidth="4"
                    stroke="#06b6d4"
                    strokeDasharray="138.23"
                    strokeDashoffset="74.6"
                  />
                </svg>
                <div className="storage-circle-text">46%</div>
              </div>
              <div className="storage-desc-right">
                <span className="storage-desc-title">Used</span>
                <span className="storage-desc-numbers">221 GB</span>
                <span className="storage-desc-title" style={{ fontSize: '0.68rem', marginTop: '2px' }}>Total 500 GB</span>
              </div>
            </div>
            <button className="role-btn" style={{ fontSize: '0.76rem', justifyContent: 'center', width: '100%', marginTop: '6px' }}>
              View Details
            </button>
          </div>
        </div>
      </div>

      {/* Quick Actions Card Row */}
      <div className="quick-actions-grid">
        <div
          className="quick-action-tile"
          onClick={() => {
            setActiveTab("workspace");
            startNewAnalysis("Create a brand new repository task");
          }}
        >
          <div className="qa-tile-left">
            <div className="qa-tile-icon-box blue">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
              </svg>
            </div>
            <div className="qa-tile-text-box">
              <span className="qa-tile-title">New Task</span>
              <span className="qa-tile-desc">Create a new task</span>
            </div>
          </div>
          <svg className="qa-tile-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        <div
          className="quick-action-tile"
          onClick={() => setActiveTab("workspace")}
        >
          <div className="qa-tile-left">
            <div className="qa-tile-icon-box purple">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="qa-tile-text-box">
              <span className="qa-tile-title">Open Workspace</span>
              <span className="qa-tile-desc">Work with your agents</span>
            </div>
          </div>
          <svg className="qa-tile-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        <div
          className="quick-action-tile"
          onClick={() => {
            setActiveTab("workspace");
            startNewAnalysis("Execute pre-defined workflows");
          }}
        >
          <div className="qa-tile-left">
            <div className="qa-tile-icon-box green">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <div className="qa-tile-text-box">
              <span className="qa-tile-title">Run Workflow</span>
              <span className="qa-tile-desc">Execute a workflow</span>
            </div>
          </div>
          <svg className="qa-tile-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
          </svg>
        </div>

        <div
          className="quick-action-tile"
          onClick={() => {
            setActiveTab("workspace");
            alert("Switched to Workspace. Check the bottom Terminal/Logs panel for logs.");
          }}
        >
          <div className="qa-tile-left">
            <div className="qa-tile-icon-box orange">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <div className="qa-tile-text-box">
              <span className="qa-tile-title">View Logs</span>
              <span className="qa-tile-desc">System and agent logs</span>
            </div>
          </div>
          <svg className="qa-tile-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>

      {/* Active Model Routing Pipeline */}
      <div className="routing-pipeline-panel">
        <div className="pipeline-left">
          <span className="toolbar-label" style={{ fontSize: '0.8rem' }}>Active Model Routing</span>
          <div className="pipeline-nodes-row">
            <div className="pipeline-node-box">
              <svg className="pipeline-node-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#3b82f6' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              <div className="pipeline-node-details">
                <span className="pl-node-role">Planner</span>
                <span className="pl-node-model">Llama 3 70B</span>
              </div>
            </div>

            <div className="pipeline-arrow">
              <span className="pl-arrow-dot" />
              <svg className="pl-arrow-svg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
              </svg>
            </div>

            <div className="pipeline-node-box">
              <svg className="pipeline-node-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#a855f7' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <div className="pipeline-node-details">
                <span className="pl-node-role">GUI Agent</span>
                <span className="pl-node-model">Mistral 7B Instruct</span>
              </div>
            </div>

            <div className="pipeline-arrow">
              <span className="pl-arrow-dot" />
              <svg className="pl-arrow-svg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
              </svg>
            </div>

            <div className="pipeline-node-box" style={{ border: '1px solid rgba(234, 179, 8, 0.4)', background: 'rgba(234, 179, 8, 0.02)' }}>
              <svg className="pipeline-node-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#eab308' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
              </svg>
              <div className="pipeline-node-details">
                <span className="pl-node-role" style={{ color: '#fef08a' }}>Coder</span>
                <span className="pl-node-model">Code Llama 34B</span>
              </div>
            </div>

            <div className="pipeline-arrow">
              <span className="pl-arrow-dot" />
              <svg className="pl-arrow-svg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
              </svg>
            </div>

            <div className="pipeline-node-box">
              <svg className="pipeline-node-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: '#10b981' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              <div className="pipeline-node-details">
                <span className="pl-node-role">Researcher</span>
                <span className="pl-node-model">Gemma 2 9B</span>
              </div>
            </div>
          </div>
        </div>

        <div className="pipeline-right">
          <button
            className="role-btn"
            onClick={() => alert("Model routing management panel.")}
            style={{ height: '36px', padding: '0 16px' }}
          >
            Manage Routing
          </button>
          <svg className="settings-gear" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ width: '20px', height: '20px' }}>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          </svg>
        </div>
      </div>
    </main>
  );
}
