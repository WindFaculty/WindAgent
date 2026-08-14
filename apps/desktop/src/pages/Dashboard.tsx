import React, { useState } from "react";
import {
  Sparkles,
  Bot,
  Cpu,
  Activity,
  TrendingUp,
  RefreshCw,
  PlusCircle,
  Film,
  Zap,
  Clock,
  Layers,
  ArrowUpRight,
  Sliders,
  CheckCircle2,
  BarChart3,
} from "lucide-react";
import "./Dashboard.css";

export interface MetricState {
  cpu: number;
  ram: number;
  ramGb: number;
  ramTotalGb: number;
  gpu: number;
  gpuName: string;
  vram: number;
  vramGb: number;
  vramTotalGb: number;
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
  startNewAnalysis?: (userQuery: string) => void;
}

export function Dashboard({
  metrics,
  setMetrics,
  setActiveTab,
  refreshInterval,
  setRefreshInterval,
  startNewAnalysis = () => {},
}: DashboardProps) {
  const [activityFilter, setActivityFilter] = useState<"24h" | "7d" | "30d" | "90d">("7d");
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Simulated AI model distribution & token performance data
  const modelSegments = [
    {
      name: "Llama 3.3 70B",
      provider: "Local Ollama",
      percent: 44,
      color: "#4d8eff",
      speed: "68.4 tok/s",
      latency: "18ms",
    },
    {
      name: "Claude 3.5 Sonnet",
      provider: "Anthropic API",
      percent: 28,
      color: "#c0c1ff",
      speed: "52.1 tok/s",
      latency: "240ms",
    },
    {
      name: "DeepSeek R1",
      provider: "Hermes Inference",
      percent: 18,
      color: "#4edea3",
      speed: "41.6 tok/s",
      latency: "310ms",
    },
    {
      name: "Gemma 2 9B",
      provider: "Edge Accelerator",
      percent: 10,
      color: "#f59e0b",
      speed: "92.0 tok/s",
      latency: "12ms",
    },
  ];

  // Dynamic Chart Datasets for different timeframes
  const chartDatasets: Record<
    "24h" | "7d" | "30d" | "90d",
    { labels: string[]; points: number[]; ideas: number; outlines: number; scripts: number; renders: number }
  > = {
    "24h": {
      labels: ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "Now"],
      points: [24, 18, 45, 78, 62, 94, 85],
      ideas: 38,
      outlines: 21,
      scripts: 9,
      renders: 4,
    },
    "7d": {
      labels: ["T2", "T3", "T4", "T5", "T6", "T7", "CN"],
      points: [35, 52, 48, 70, 64, 91, 88],
      ideas: 142,
      outlines: 86,
      scripts: 34,
      renders: 18,
    },
    "30d": {
      labels: ["Tuần 1", "Tuần 2", "Tuần 3", "Tuần 4"],
      points: [42, 68, 85, 96],
      ideas: 512,
      outlines: 280,
      scripts: 124,
      renders: 64,
    },
    "90d": {
      labels: ["Tháng 1", "Tháng 2", "Tháng 3"],
      points: [55, 75, 98],
      ideas: 1480,
      outlines: 810,
      scripts: 350,
      renders: 192,
    },
  };

  const currentDataset = chartDatasets[activityFilter];

  // Generate SVG Path for Area & Line
  const generateSvgPath = (points: number[]) => {
    if (!points || points.length === 0) return { areaPath: "", linePath: "" };
    const maxVal = 100;
    const width = 1000;
    const height = 180;
    const step = width / (points.length - 1);

    const coords = points.map((val, idx) => {
      const x = idx * step;
      const y = height - (val / maxVal) * (height - 30) - 15;
      return { x, y };
    });

    let linePath = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 0; i < coords.length - 1; i++) {
      const p0 = coords[i];
      const p1 = coords[i + 1];
      const cx = (p0.x + p1.x) / 2;
      linePath += ` C ${cx} ${p0.y}, ${cx} ${p1.y}, ${p1.x} ${p1.y}`;
    }

    const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${height} L ${coords[0].x} ${height} Z`;
    return { areaPath, linePath, coords };
  };

  const { areaPath, linePath, coords } = generateSvgPath(currentDataset.points);

  const handleManualRefresh = () => {
    setIsRefreshing(true);
    setMetrics((prev) => ({
      ...prev,
      cpu: Math.max(14, Math.min(82, prev.cpu + Math.round(Math.random() * 8 - 4))),
      gpu: Math.max(20, Math.min(88, prev.gpu + Math.round(Math.random() * 10 - 5))),
      ram: Math.max(45, Math.min(78, prev.ram + Math.round(Math.random() * 4 - 2))),
      vram: Math.max(30, Math.min(65, prev.vram + Math.round(Math.random() * 4 - 2))),
    }));
    setTimeout(() => {
      setIsRefreshing(false);
    }, 600);
  };

  return (
    <div className="dashboard-container">
      {/* 1. Header Section */}
      <header className="dashboard-header">
        <div className="dashboard-title-group">
          <div className="dashboard-title-wrapper">
            <div className="dashboard-title-icon-badge">
              <Sparkles size={22} />
            </div>
            <h1 className="dashboard-title">Bảng Điều Khiển Studio</h1>
            <div className="dashboard-badge-live">
              <span className="pulse-dot" />
              Live Workspace
            </div>
          </div>
          <p className="dashboard-subtitle">
            Trung tâm giám sát tài nguyên phần cứng, điều phối Multi-Agent swarm và phân tích tác phẩm điện ảnh.
          </p>
        </div>

        <div className="dashboard-header-actions">
          <div className="refresh-control">
            <Clock size={14} />
            <span>Làm mới:</span>
            <select
              className="refresh-select"
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(e.target.value)}
            >
              <option value="10s">10 giây</option>
              <option value="30s">30 giây</option>
              <option value="1m">1 phút</option>
              <option value="5m">5 phút</option>
            </select>
          </div>

          <button
            className={`btn-icon-refresh ${isRefreshing ? "spinning" : ""}`}
            title="Làm mới thông số ngay"
            onClick={handleManualRefresh}
          >
            <RefreshCw size={16} />
          </button>

          <button
            className="btn-quick-new"
            onClick={() => {
              setActiveTab("studio");
              startNewAnalysis("Khởi tạo dự án phim mới");
            }}
          >
            <PlusCircle size={16} />
            <span>Tạo Kịch Bản Mới</span>
          </button>
        </div>
      </header>

      {/* 2. Top Metric Cards (KPI Deck) */}
      <section className="metrics-deck">
        {/* Card 1: Projects & Episodes */}
        <div
          className="metric-kpi-card"
          onClick={() => setActiveTab("projects")}
          style={{ cursor: "pointer" }}
        >
          <div
            className="metric-kpi-card-glow"
            style={{ background: "#4d8eff" }}
          />
          <div className="metric-kpi-header">
            <span className="metric-kpi-label">Dự Án & Tập Phim</span>
            <div className="metric-kpi-icon" style={{ color: "#4d8eff" }}>
              <Film size={18} />
            </div>
          </div>
          <div className="metric-kpi-content">
            <div className="metric-kpi-value-row">
              <span className="metric-kpi-value">12</span>
              <span className="metric-kpi-subval">48 Episodes</span>
            </div>
            <div className="metric-kpi-progress-track">
              <div
                className="metric-kpi-progress-bar"
                style={{ width: "75%", background: "linear-gradient(90deg, #4d8eff, #60a5fa)" }}
              />
            </div>
          </div>
          <div className="metric-kpi-footer">
            <span className="metric-kpi-trend positive">
              <TrendingUp size={14} />
              +3 tập mới
            </span>
            <span>trong tuần này</span>
          </div>
        </div>

        {/* Card 2: Active Agents Swarm */}
        <div
          className="metric-kpi-card"
          onClick={() => setActiveTab("workspace")}
          style={{ cursor: "pointer" }}
        >
          <div
            className="metric-kpi-card-glow"
            style={{ background: "#4edea3" }}
          />
          <div className="metric-kpi-header">
            <span className="metric-kpi-label">Agent Swarm Active</span>
            <div className="metric-kpi-icon" style={{ color: "#4edea3" }}>
              <Bot size={18} />
            </div>
          </div>
          <div className="metric-kpi-content">
            <div className="metric-kpi-value-row">
              <span className="metric-kpi-value">4 / 6</span>
              <span className="metric-kpi-subval">66.7% Uptime</span>
            </div>
            <div className="metric-kpi-progress-track">
              <div
                className="metric-kpi-progress-bar"
                style={{ width: "66.7%", background: "linear-gradient(90deg, #4edea3, #22c55e)" }}
              />
            </div>
          </div>
          <div className="metric-kpi-footer">
            <span className="metric-kpi-trend positive">
              <CheckCircle2 size={14} />
              Planner, GUI, Coder, Story AI
            </span>
          </div>
        </div>

        {/* Card 3: Memory / RAM Usage */}
        <div className="metric-kpi-card">
          <div
            className="metric-kpi-card-glow"
            style={{ background: "#c0c1ff" }}
          />
          <div className="metric-kpi-header">
            <span className="metric-kpi-label">Bộ Nhớ RAM Hệ Thống</span>
            <div className="metric-kpi-icon" style={{ color: "#c0c1ff" }}>
              <Activity size={18} />
            </div>
          </div>
          <div className="metric-kpi-content">
            <div className="metric-kpi-value-row">
              <span className="metric-kpi-value">{metrics.ram}%</span>
              <span className="metric-kpi-subval">
                {metrics.ramGb || "9.6"} / {metrics.ramTotalGb || "16"} GB
              </span>
            </div>
            <div className="metric-kpi-progress-track">
              <div
                className="metric-kpi-progress-bar"
                style={{
                  width: `${metrics.ram}%`,
                  background: "linear-gradient(90deg, #c0c1ff, #8083ff)",
                }}
              />
            </div>
          </div>
          <div className="metric-kpi-footer">
            <span className="metric-kpi-trend neutral">CPU Load {metrics.cpu}%</span>
            <span>• Ổn định</span>
          </div>
        </div>

        {/* Card 4: GPU & VRAM Acceleration */}
        <div className="metric-kpi-card">
          <div
            className="metric-kpi-card-glow"
            style={{ background: "#f59e0b" }}
          />
          <div className="metric-kpi-header">
            <span className="metric-kpi-label">Tải GPU & VRAM</span>
            <div className="metric-kpi-icon" style={{ color: "#f59e0b" }}>
              <Cpu size={18} />
            </div>
          </div>
          <div className="metric-kpi-content">
            <div className="metric-kpi-value-row">
              <span className="metric-kpi-value">{metrics.gpu}%</span>
              <span className="metric-kpi-subval">VRAM: {metrics.vram}%</span>
            </div>
            <div className="metric-kpi-progress-track">
              <div
                className="metric-kpi-progress-bar"
                style={{
                  width: `${metrics.gpu}%`,
                  background: "linear-gradient(90deg, #f59e0b, #fbbf24)",
                }}
              />
            </div>
          </div>
          <div className="metric-kpi-footer">
            <span className="metric-kpi-trend neutral" title={metrics.gpuName}>
              <Zap size={14} />
              {metrics.gpuName ? metrics.gpuName.slice(0, 20) : "NVIDIA Hardware"}
            </span>
          </div>
        </div>
      </section>

      {/* 3. Main Content Grid (2 Columns) */}
      <div className="dashboard-main-grid">
        {/* Left Column: Visual Analytics & Launchers */}
        <div className="dashboard-column">
          {/* Main Activity Chart Card */}
          <div className="studio-card">
            <div className="studio-card-header">
              <div className="studio-card-title-group">
                <BarChart3 size={20} color="#4d8eff" />
                <div>
                  <h3>Hoạt Động Sáng Tác & Phân Cảnh Điện Ảnh</h3>
                  <p>Tốc độ sinh Idea, Outline, Storyboard và Render kịch bản theo thời gian</p>
                </div>
              </div>

              <div className="time-filter-pill-group">
                {(["24h", "7d", "30d", "90d"] as const).map((filter) => (
                  <button
                    key={filter}
                    className={`time-filter-pill ${activityFilter === filter ? "active" : ""}`}
                    onClick={() => setActivityFilter(filter)}
                  >
                    {filter}
                  </button>
                ))}
              </div>
            </div>

            <div className="chart-container">
              <div className="chart-svg-wrapper">
                <svg
                  className="chart-svg"
                  viewBox="0 0 1000 180"
                  preserveAspectRatio="none"
                >
                  <defs>
                    <linearGradient id="studioAreaGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#4d8eff" stopOpacity="0.4" />
                      <stop offset="60%" stopColor="#4d8eff" stopOpacity="0.1" />
                      <stop offset="100%" stopColor="#4d8eff" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Horizontal grid lines */}
                  <line x1="0" y1="40" x2="1000" y2="40" className="chart-grid-line" />
                  <line x1="0" y1="90" x2="1000" y2="90" className="chart-grid-line" />
                  <line x1="0" y1="140" x2="1000" y2="140" className="chart-grid-line" />

                  {/* Filled Area */}
                  {areaPath && (
                    <path
                      d={areaPath}
                      fill="url(#studioAreaGradient)"
                    />
                  )}

                  {/* Line Stroke */}
                  {linePath && (
                    <path
                      d={linePath}
                      fill="none"
                      stroke="#4d8eff"
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                  )}

                  {/* Data Points */}
                  {coords?.map((c, i) => (
                    <g key={i}>
                      <circle
                        cx={c.x}
                        cy={c.y}
                        r="5"
                        fill="#060e20"
                        stroke="#4d8eff"
                        strokeWidth="2.5"
                      />
                      <circle
                        cx={c.x}
                        cy={c.y}
                        r="2.5"
                        fill="#adc6ff"
                      />
                    </g>
                  ))}
                </svg>

                {/* X-axis labels */}
                <div className="chart-x-labels">
                  {currentDataset.labels.map((lbl, i) => (
                    <span key={i}>{lbl}</span>
                  ))}
                </div>
              </div>

              {/* Chart Stats Summary */}
              <div className="chart-stats-summary">
                <div className="chart-stat-item">
                  <span className="chart-stat-title">Ý Tưởng (Ideas)</span>
                  <span className="chart-stat-count" style={{ color: "#adc6ff" }}>
                    {currentDataset.ideas}
                  </span>
                </div>
                <div className="chart-stat-item">
                  <span className="chart-stat-title">Đề Cương (Outlines)</span>
                  <span className="chart-stat-count" style={{ color: "#4edea3" }}>
                    {currentDataset.outlines}
                  </span>
                </div>
                <div className="chart-stat-item">
                  <span className="chart-stat-title">Kịch Bản (Scripts)</span>
                  <span className="chart-stat-count" style={{ color: "#c0c1ff" }}>
                    {currentDataset.scripts}
                  </span>
                </div>
                <div className="chart-stat-item">
                  <span className="chart-stat-title">Video Rendered</span>
                  <span className="chart-stat-count" style={{ color: "#f59e0b" }}>
                    {currentDataset.renders}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Quick Action Tiles */}
          <div className="quick-launcher-grid">
            <div
              className="launcher-tile"
              style={
                {
                  "--tile-accent": "rgba(77, 142, 255, 0.3)",
                  "--tile-bg": "rgba(77, 142, 255, 0.12)",
                  "--tile-border": "rgba(77, 142, 255, 0.4)",
                  "--tile-color": "#4d8eff",
                } as React.CSSProperties
              }
              onClick={() => {
                setActiveTab("studio");
                startNewAnalysis("Tạo dự án phim mới");
              }}
            >
              <div className="launcher-tile-icon-box">
                <Film size={20} />
              </div>
              <div className="launcher-tile-text">
                <div className="launcher-tile-heading">
                  Dự Án Studio
                  <ArrowUpRight size={14} color="#8c909f" />
                </div>
                <span className="launcher-tile-desc">
                  Biên kịch, phân cảnh và đạo diễn tập phim
                </span>
              </div>
            </div>

            <div
              className="launcher-tile"
              style={
                {
                  "--tile-accent": "rgba(78, 222, 163, 0.3)",
                  "--tile-bg": "rgba(78, 222, 163, 0.12)",
                  "--tile-border": "rgba(78, 222, 163, 0.4)",
                  "--tile-color": "#4edea3",
                } as React.CSSProperties
              }
              onClick={() => setActiveTab("workspace")}
            >
              <div className="launcher-tile-icon-box">
                <Bot size={20} />
              </div>
              <div className="launcher-tile-text">
                <div className="launcher-tile-heading">
                  Agent Swarm
                  <ArrowUpRight size={14} color="#8c909f" />
                </div>
                <span className="launcher-tile-desc">
                  Giao việc trực tiếp cho AI Planner & Coder
                </span>
              </div>
            </div>

            <div
              className="launcher-tile"
              style={
                {
                  "--tile-accent": "rgba(192, 193, 255, 0.3)",
                  "--tile-bg": "rgba(192, 193, 255, 0.12)",
                  "--tile-border": "rgba(192, 193, 255, 0.4)",
                  "--tile-color": "#c0c1ff",
                } as React.CSSProperties
              }
              onClick={() => setActiveTab("asset-library")}
            >
              <div className="launcher-tile-icon-box">
                <Layers size={20} />
              </div>
              <div className="launcher-tile-text">
                <div className="launcher-tile-heading">
                  Kho Tài Nguyên
                  <ArrowUpRight size={14} color="#8c909f" />
                </div>
                <span className="launcher-tile-desc">
                  Quản lý nhân vật 2D/3D, audio & background
                </span>
              </div>
            </div>

            <div
              className="launcher-tile"
              style={
                {
                  "--tile-accent": "rgba(245, 158, 11, 0.3)",
                  "--tile-bg": "rgba(245, 158, 11, 0.12)",
                  "--tile-border": "rgba(245, 158, 11, 0.4)",
                  "--tile-color": "#f59e0b",
                } as React.CSSProperties
              }
              onClick={() => setActiveTab("settings")}
            >
              <div className="launcher-tile-icon-box">
                <Sliders size={20} />
              </div>
              <div className="launcher-tile-text">
                <div className="launcher-tile-heading">
                  Cấu Hình Model
                  <ArrowUpRight size={14} color="#8c909f" />
                </div>
                <span className="launcher-tile-desc">
                  Thiết lập Ollama, Claude, Hermes API & Router
                </span>
              </div>
            </div>
          </div>

          {/* AI Model Performance & Token Distribution */}
          <div className="studio-card">
            <div className="studio-card-header">
              <div className="studio-card-title-group">
                <Cpu size={20} color="#4edea3" />
                <div>
                  <h3>Phân Bổ Mô Hình AI & Tốc Độ Suy Luận</h3>
                  <p>Tỷ lệ gọi Model, độ trễ và lưu lượng Tokens/giây trong phiên làm việc</p>
                </div>
              </div>
              <span
                style={{
                  fontSize: "0.74rem",
                  color: "#4edea3",
                  fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                }}
              >
                TOTAL: 1.84M TOKENS
              </span>
            </div>

            <div className="model-distribution-list">
              {modelSegments.map((model, idx) => (
                <div key={idx} className="model-bar-item">
                  <div className="model-bar-header">
                    <div className="model-bar-name">
                      <span
                        style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          backgroundColor: model.color,
                        }}
                      />
                      <span>{model.name}</span>
                      <span className="model-bar-badge">{model.provider}</span>
                    </div>

                    <div className="model-bar-meta">
                      <span style={{ color: model.color, fontWeight: 700 }}>
                        {model.percent}%
                      </span>
                      <span>•</span>
                      <span>{model.speed}</span>
                      <span>•</span>
                      <span>{model.latency}</span>
                    </div>
                  </div>

                  <div className="model-bar-track">
                    <div
                      className="model-bar-fill"
                      style={{
                        width: `${model.percent}%`,
                        backgroundColor: model.color,
                        boxShadow: `0 0 10px ${model.color}66`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: Swarm Status, Activity Timeline & System Meter */}
        <div className="dashboard-column">
          {/* Active AI Swarm Status */}
          <div className="studio-card">
            <div className="studio-card-header">
              <div className="studio-card-title-group">
                <Bot size={20} color="#adc6ff" />
                <div>
                  <h3>Agent Swarm Trực Tuyến</h3>
                  <p>Trạng thái phân bổ công việc</p>
                </div>
              </div>
              <span className="swarm-status-badge running">4 Running</span>
            </div>

            <div className="swarm-agent-list">
              {[
                {
                  name: "Planner Agent",
                  role: "Story Arc & Beat Sheet",
                  status: "running" as const,
                  color: "#4d8eff",
                  initials: "PL",
                },
                {
                  name: "GUI & Visual Agent",
                  role: "Storyboard & Concept Art",
                  status: "running" as const,
                  color: "#4edea3",
                  initials: "GU",
                },
                {
                  name: "Coder & Script AI",
                  role: "Dialogue & Tool Calling",
                  status: "busy" as const,
                  color: "#f59e0b",
                  initials: "CO",
                },
                {
                  name: "Reviewer AI",
                  role: "Continuity & QA Audit",
                  status: "running" as const,
                  color: "#c0c1ff",
                  initials: "RE",
                },
                {
                  name: "Audio & SFX Agent",
                  role: "Voice Dubbing & TTS",
                  status: "idle" as const,
                  color: "#8c909f",
                  initials: "AU",
                },
              ].map((agent, i) => (
                <div key={i} className="swarm-agent-row">
                  <div className="swarm-agent-info">
                    <div
                      className="swarm-agent-avatar"
                      style={{ backgroundColor: `${agent.color}25`, border: `1px solid ${agent.color}50` }}
                    >
                      <span style={{ color: agent.color }}>{agent.initials}</span>
                      <span
                        className="swarm-agent-avatar-led"
                        style={{
                          backgroundColor:
                            agent.status === "running"
                              ? "#4edea3"
                              : agent.status === "busy"
                              ? "#f59e0b"
                              : "#8c909f",
                        }}
                      />
                    </div>
                    <div className="swarm-agent-details">
                      <span className="swarm-agent-name">{agent.name}</span>
                      <span className="swarm-agent-role">{agent.role}</span>
                    </div>
                  </div>

                  <span className={`swarm-status-badge ${agent.status}`}>
                    {agent.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Activity Logs Timeline */}
          <div className="studio-card">
            <div className="studio-card-header">
              <div className="studio-card-title-group">
                <Clock size={20} color="#c0c1ff" />
                <div>
                  <h3>Nhật Ký Hoạt Động Studio</h3>
                  <p>Sự kiện thời gian thực</p>
                </div>
              </div>
            </div>

            <div className="activity-timeline">
              {[
                {
                  time: "10:42 AM",
                  actor: "GUI Agent",
                  text: "Hoàn tất render 16 concept storyboard cho Episode 03",
                  type: "green" as const,
                },
                {
                  time: "10:35 AM",
                  actor: "Planner",
                  text: "Cập nhật Character Arc & Emotional Beats cho tập 2",
                  type: "purple" as const,
                },
                {
                  time: "10:20 AM",
                  actor: "Coder Agent",
                  text: "Tích hợp và nạp 24 design tokens vào giao diện",
                  type: "purple" as const,
                },
                {
                  time: "10:05 AM",
                  actor: "Hermes Inference",
                  text: "Tự động kiểm tra sức khỏe hệ thống: Hoạt động ổn định",
                  type: "green" as const,
                },
                {
                  time: "09:50 AM",
                  actor: "System Storage",
                  text: "Sao lưu tự động bản thảo kịch bản Cyberpunk Saga",
                  type: "amber" as const,
                },
              ].map((ev, idx) => (
                <div key={idx} className="timeline-event-item">
                  <div className={`timeline-event-dot ${ev.type}`} />
                  <div className="timeline-event-meta">
                    <span className="timeline-event-actor">{ev.actor}</span>
                    <span>•</span>
                    <span>{ev.time}</span>
                  </div>
                  <div className="timeline-event-desc">{ev.text}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Storage / Model Cache Quota Widget */}
          <div className="storage-quota-widget">
            <div className="storage-quota-info">
              <span className="storage-quota-title">Dung Lượng Bộ Nhớ Đệm</span>
              <span className="storage-quota-numbers">42.8 GB / 100 GB (42.8%)</span>
            </div>
            <div className="storage-quota-meter-bar">
              <div className="storage-quota-fill" style={{ width: "42.8%" }} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
