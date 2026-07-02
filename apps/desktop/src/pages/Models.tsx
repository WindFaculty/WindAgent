import { useState } from "react";

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  type: "Local" | "API";
  context: string;
  vram: string;
  status: "Running" | "Ready" | "Loading" | "Idle" | "Offline";
  roles: string;
  rt: string;
  sr: string;
  sparkPoints: string;
  description: string;
  deployment: string;
  quantization: string;
  vramVal: string;
  vramMax: string;
  vramPct: number;
  ramVal: string;
  ramMax: string;
  ramPct: number;
  contextVal: string;
  contextMax: string;
  contextPct: number;
  tokensPerSec: string;
  uptime: string;
  assignedRoles: Array<{ name: string; type: string }>;
  tags: string[];
}

interface ModelsProps {
  setActiveTab: (tab: string) => void;
}

export function Models({ setActiveTab }: ModelsProps) {
  const [selectedModelId, setSelectedModelId] = useState<string>("qwen");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  // Models dataset matching the screenshot details
  const modelsData: ModelItem[] = [
    {
      id: "qwen",
      name: "Qwen 3.5 4B Q4",
      provider: "Alibaba",
      type: "Local",
      context: "32K",
      vram: "2.6 GB VRAM",
      status: "Running",
      roles: "Planner, Local Chat",
      rt: "312ms",
      sr: "96%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "High-quality 4B parameter model excelling at reasoning, coding, and instruction following. Efficient and optimized for local deployment with excellent performance.",
      deployment: "Local (Ollama)",
      quantization: "Q4_K_M",
      vramVal: "2.6 GB",
      vramMax: "16 GB",
      vramPct: 16,
      ramVal: "5.1 GB",
      ramMax: "16 GB",
      ramPct: 32,
      contextVal: "10.2K",
      contextMax: "32K",
      contextPct: 32,
      tokensPerSec: "78.4",
      uptime: "2d 14h",
      assignedRoles: [
        { name: "Planner", type: "Primary" },
        { name: "Local Chat", type: "Primary" },
        { name: "Dispatcher", type: "Fallback" },
      ],
      tags: ["Coding", "Planning", "Chat", "Tool Use", "UI Control"],
    },
    {
      id: "codestral",
      name: "Codestral 22B",
      provider: "Mistral AI",
      type: "Local",
      context: "32K",
      vram: "13.2 GB VRAM",
      status: "Ready",
      roles: "Coder",
      rt: "421ms",
      sr: "93%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Specially designed model for code generation and development tasks. Strong autocomplete and repository understanding capabilities.",
      deployment: "Local (Ollama)",
      quantization: "Q5_K_M",
      vramVal: "13.2 GB",
      vramMax: "16 GB",
      vramPct: 82,
      ramVal: "6.4 GB",
      ramMax: "16 GB",
      ramPct: 40,
      contextVal: "8.4K",
      contextMax: "32K",
      contextPct: 26,
      tokensPerSec: "42.1",
      uptime: "5d 8h",
      assignedRoles: [
        { name: "Coder", type: "Primary" },
      ],
      tags: ["Coding", "Autocomplete", "Refactoring"],
    },
    {
      id: "mixtral",
      name: "Mixtral 8x7B Instruct",
      provider: "Mistral AI",
      type: "Local",
      context: "32K",
      vram: "26.1 GB VRAM",
      status: "Running",
      roles: "Dispatcher, Planner",
      rt: "356ms",
      sr: "95%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "High performance MoE architecture. Excels at planning and orchestration across multiple sub-agents.",
      deployment: "Local (Ollama)",
      quantization: "Q4_K_M",
      vramVal: "26.1 GB",
      vramMax: "32 GB",
      vramPct: 81,
      ramVal: "8.2 GB",
      ramMax: "16 GB",
      ramPct: 51,
      contextVal: "12.5K",
      contextMax: "32K",
      contextPct: 39,
      tokensPerSec: "58.2",
      uptime: "1d 12h",
      assignedRoles: [
        { name: "Dispatcher", type: "Primary" },
        { name: "Planner", type: "Fallback" },
      ],
      tags: ["Planning", "Routing", "MoE"],
    },
    {
      id: "llama",
      name: "Llama 3 70B",
      provider: "Meta",
      type: "Local",
      context: "128K",
      vram: "42.8 GB VRAM",
      status: "Loading",
      roles: "Researcher",
      rt: "512ms",
      sr: "91%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Large-scale parameter model offering state-of-the-art general reasoning. Ideal for complex synthesis and multi-document search.",
      deployment: "Local (Ollama)",
      quantization: "Q4_K_M",
      vramVal: "42.8 GB",
      vramMax: "48 GB",
      vramPct: 89,
      ramVal: "12.1 GB",
      ramMax: "16 GB",
      ramPct: 75,
      contextVal: "45.2K",
      contextMax: "128K",
      contextPct: 35,
      tokensPerSec: "24.5",
      uptime: "—",
      assignedRoles: [
        { name: "Researcher", type: "Primary" },
      ],
      tags: ["Reasoning", "Synthesis", "RAG"],
    },
    {
      id: "gemma",
      name: "Gemma 2 9B",
      provider: "Google",
      type: "Local",
      context: "32K",
      vram: "5.1 GB VRAM",
      status: "Idle",
      roles: "Coder, Local Chat",
      rt: "389ms",
      sr: "92%",
      sparkPoints: "0,18 15,14 30,16 45,12 60,10 68,8",
      description: "Google's lightweight 9B parameter model optimized for fast responses and general text operations.",
      deployment: "Local (Ollama)",
      quantization: "Q8_0",
      vramVal: "5.1 GB",
      vramMax: "16 GB",
      vramPct: 32,
      ramVal: "4.2 GB",
      ramMax: "16 GB",
      ramPct: 26,
      contextVal: "2.1K",
      contextMax: "32K",
      contextPct: 6,
      tokensPerSec: "64.2",
      uptime: "12h",
      assignedRoles: [
        { name: "Coder", type: "Fallback" },
        { name: "Local Chat", type: "Fallback" },
      ],
      tags: ["Fast", "Lightweight", "Text"],
    },
    {
      id: "gpt",
      name: "GPT-5.5",
      provider: "OpenAI",
      type: "API",
      context: "128K",
      vram: "—",
      status: "Ready",
      roles: "Planner, Researcher",
      rt: "284ms",
      sr: "97%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "OpenAI's latest generation cloud model. Highly intelligent, extremely low latency and comprehensive tool integration.",
      deployment: "API (Cloud)",
      quantization: "FP16",
      vramVal: "—",
      vramMax: "—",
      vramPct: 0,
      ramVal: "2.1 GB",
      ramMax: "16 GB",
      ramPct: 13,
      contextVal: "24.2K",
      contextMax: "128K",
      contextPct: 18,
      tokensPerSec: "112.5",
      uptime: "30d",
      assignedRoles: [
        { name: "Planner", type: "Primary" },
        { name: "Researcher", type: "Primary" },
      ],
      tags: ["API", "Cloud", "Premium"],
    },
    {
      id: "claude",
      name: "Claude Sonnet 4.6",
      provider: "Anthropic",
      type: "API",
      context: "200K",
      vram: "—",
      status: "Ready",
      roles: "Researcher, Writer",
      rt: "331ms",
      sr: "96%",
      sparkPoints: "0,14 15,10 30,12 45,8 60,6 68,4",
      description: "Anthropic's flagship reasoning model. Perfect for code refactoring, structural analysis, and document parsing.",
      deployment: "API (Cloud)",
      quantization: "FP16",
      vramVal: "—",
      vramMax: "—",
      vramPct: 0,
      ramVal: "1.8 GB",
      ramMax: "16 GB",
      ramPct: 11,
      contextVal: "18.4K",
      contextMax: "200K",
      contextPct: 9,
      tokensPerSec: "98.6",
      uptime: "30d",
      assignedRoles: [
        { name: "Researcher", type: "Fallback" },
        { name: "Writer", type: "Primary" },
      ],
      tags: ["Reasoning", "API", "Long Context"],
    },
    {
      id: "phi",
      name: "Phi-3 Medium 4K",
      provider: "Microsoft",
      type: "Local",
      context: "4K",
      vram: "2.0 GB VRAM",
      status: "Offline",
      roles: "—",
      rt: "—",
      sr: "—",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Microsoft's small footprint model, ideal for local tests or fallback context translation layers.",
      deployment: "Local (Ollama)",
      quantization: "Q4_K_M",
      vramVal: "0 GB",
      vramMax: "8 GB",
      vramPct: 0,
      ramVal: "0 GB",
      ramMax: "8 GB",
      ramPct: 0,
      contextVal: "0K",
      contextMax: "4K",
      contextPct: 0,
      tokensPerSec: "—",
      uptime: "—",
      assignedRoles: [],
      tags: ["Local", "Offline", "Small"],
    },
  ];

  // Metrics counters
  const totalModels = 16;
  const activeModels = modelsData.filter((m) => m.status === "Running" || m.status === "Ready").length;
  const localModels = 9;
  const apiModels = 7;

  // Filters logic
  const filteredModels = modelsData.filter((model) => {
    // Status tab filter
    if (activeFilterTab === "running" && (model.status !== "Running" && model.status !== "Ready")) return false;
    if (activeFilterTab === "local" && model.type !== "Local") return false;
    if (activeFilterTab === "api" && model.type !== "API") return false;
    if (activeFilterTab === "quantized" && !model.name.includes("Q4") && !model.name.includes("Q5") && !model.name.includes("Q8")) return false;
    if (activeFilterTab === "offline" && model.status !== "Offline") return false;

    // Text search filter
    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        model.name.toLowerCase().includes(q) ||
        model.provider.toLowerCase().includes(q) ||
        model.roles.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedModel = modelsData.find((m) => m.id === selectedModelId) || modelsData[0];

  return (
    <main className="models-view">
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Models</h1>
          <p className="dashboard-subtitle-text">Manage local and cloud models, routing, health, and performance.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Add Model modal.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            Add Model
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import Model modal.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Import Model
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

      {/* Metric row grid */}
      <div className="metrics-row-grid">
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              <span>Total Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalModels}</div>
              <div className="m-card-subtext">All available models</div>
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
              <span>Active Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{activeModels}</div>
              <div className="m-card-subtext">{((activeModels / totalModels) * 100).toFixed(1)}% of total</div>
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              <span>Local Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{localModels}</div>
              <div className="m-card-subtext">{((localModels / totalModels) * 100).toFixed(1)}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,22 30,14 45,18 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-warning)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9" />
              </svg>
              <span>API Models</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{apiModels}</div>
              <div className="m-card-subtext">{((apiModels / totalModels) * 100).toFixed(1)}% of total</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>Avg Latency</span>
            </div>
            <div className="trend-indicator up">▼ 8.6%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">342ms</div>
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
              <span>Memory Footprint</span>
            </div>
            <div className="trend-indicator purple">▲ 1.3 GB</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">21.4 GB</div>
              <div className="m-card-subtext">vs last hour</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main layout splitted */}
      <div className="agents-main-layout">
        {/* Left Pane Model Library */}
        <div className="agents-directory-pane">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '12px 16px', flexDirection: 'column', alignItems: 'stretch', gap: '10px' }}>
              <div className="agent-directory-header">
                <span className="panel-title">Model Library</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <div className="search-box-container">
                    <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input
                      type="text"
                      placeholder="Search models..."
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
                  All <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>{totalModels}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "running" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("running")}
                >
                  Running <span style={{ color: 'var(--color-success)', marginLeft: '2px' }}>{activeModels}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "local" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("local")}
                >
                  Local <span style={{ color: 'var(--color-primary)', marginLeft: '2px' }}>{localModels}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "api" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("api")}
                >
                  API <span style={{ color: 'var(--color-warning)', marginLeft: '2px' }}>{apiModels}</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "quantized" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("quantized")}
                >
                  Quantized <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>6</span>
                </button>
                <button
                  className={`tab-btn ${activeFilterTab === "offline" ? "active" : ""}`}
                  onClick={() => setActiveFilterTab("offline")}
                >
                  Offline <span style={{ color: 'var(--text-dim)', marginLeft: '2px' }}>2</span>
                </button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0px' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Provider</th>
                    <th>Type</th>
                    <th>Context</th>
                    <th>VRAM / RAM</th>
                    <th>Status</th>
                    <th>Assigned Roles</th>
                    <th>Performance</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredModels.map((model) => (
                    <tr
                      key={model.id}
                      className={selectedModelId === model.id ? "selected-row" : ""}
                      onClick={() => setSelectedModelId(model.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <span
                            className="agent-color-dot"
                            style={{
                              backgroundColor:
                                model.id === "qwen"
                                  ? "#3b82f6"
                                  : model.id === "codestral"
                                  ? "#f59e0b"
                                  : model.id === "mixtral"
                                  ? "#a855f7"
                                  : model.id === "llama"
                                  ? "#ec4899"
                                  : model.id === "gemma"
                                  ? "#3b82f6"
                                  : model.id === "gpt"
                                  ? "#10b981"
                                  : model.id === "claude"
                                  ? "#06b6d4"
                                  : "#9ca3af",
                            }}
                          />
                          <div>
                            <div style={{ fontWeight: '700' }}>
                              {model.name}
                              {(model.name.includes("Q4") || model.name.includes("Q5") || model.name.includes("Q8")) && (
                                <span className="model-quant-tag">
                                  {model.name.includes("Q4") ? "Q4" : model.name.includes("Q5") ? "Q5" : "Q8"}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td style={{ fontWeight: '500' }}>{model.provider}</td>
                      <td>
                        <span style={{
                          color: model.type === "Local" ? "var(--color-primary)" : "var(--color-warning)",
                          fontWeight: '600',
                          fontSize: '0.74rem'
                        }}>
                          {model.type}
                        </span>
                      </td>
                      <td>{model.context}</td>
                      <td>{model.vram}</td>
                      <td>
                        <span className={`agent-status-badge ${model.status.toLowerCase()}`}>
                          {model.status}
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.76rem' }}>{model.roles}</td>
                      <td>
                        {model.status !== "Offline" ? (
                          <div className="perf-cell-wrapper">
                            <div className="perf-text">
                              <div>{model.rt}</div>
                              <div>{model.sr}</div>
                            </div>
                            <svg className={`perf-sparkline ${model.id === "qwen" ? "green" : model.id === "mixtral" ? "green" : "orange"}`} viewBox="0 0 68 20">
                              <polyline points={model.sparkPoints} />
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
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredModels.length} of {filteredModels.length} models</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>2</button>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom Grid for left column: Latency comparisons & routing visual mappings & activity logs */}
          <div className="bottom-tables-grid" style={{ minHeight: '220px' }}>
            {/* Performance Comparison Bar Graph */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <div>
                  <span className="panel-title">Performance Comparison</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginLeft: '4px' }}>(Lower is better)</span>
                </div>
                <select className="refresh-select" style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '2px 8px', fontSize: '0.74rem' }}>
                  <option>Latency (p50)</option>
                  <option>Tokens per sec</option>
                </select>
              </header>
              <div className="panel-body" style={{ padding: '10px' }}>
                <div className="latency-compare-chart-container">
                  <div className="latency-grid-lines">
                    <div className="latency-grid-line-row"><span>1000ms</span></div>
                    <div className="latency-grid-line-row"><span>750ms</span></div>
                    <div className="latency-grid-line-row"><span>500ms</span></div>
                    <div className="latency-grid-line-row"><span>250ms</span></div>
                    <div className="latency-grid-line-row"><span>0ms</span></div>
                  </div>

                  <div className="latency-bars-row">
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">284</span>
                      <div className="latency-bar-column dark-grey" style={{ height: '28px' }} />
                      <span className="latency-bar-label">GPT-5.5</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">312</span>
                      <div className="latency-bar-column blue" style={{ height: '31px' }} />
                      <span className="latency-bar-label">Qwen 3.5</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">331</span>
                      <div className="latency-bar-column blue" style={{ height: '33px' }} />
                      <span className="latency-bar-label">Claude 4.6</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">356</span>
                      <div className="latency-bar-column blue" style={{ height: '36px' }} />
                      <span className="latency-bar-label">Mixtral</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">389</span>
                      <div className="latency-bar-column blue" style={{ height: '39px' }} />
                      <span className="latency-bar-label">Gemma 2</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">421</span>
                      <div className="latency-bar-column orange" style={{ height: '42px' }} />
                      <span className="latency-bar-label">Codestral</span>
                    </div>
                    <div className="latency-bar-col">
                      <span className="latency-bar-val">512</span>
                      <div className="latency-bar-column dark-grey" style={{ height: '51px' }} />
                      <span className="latency-bar-label">Llama 3</span>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto' }}>
                  <span style={{ color: 'var(--text-dim)' }}>Based on recent 24h metrics</span>
                  <a href="#bench" className="view-timeline-link" style={{ fontSize: '0.74rem', marginTop: '0px' }} onClick={(e) => { e.preventDefault(); alert("Show details benchmarks."); }}>
                    View full benchmarks →
                  </a>
                </div>
              </div>
            </div>

            {/* Routing Overview curves map */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Routing Overview</span>
                <button className="role-btn" style={{ padding: '2px 6px', fontSize: '0.72rem', height: 'auto' }}>
                  Edit Rules
                </button>
              </header>
              <div className="panel-body" style={{ padding: '8px' }}>
                <div className="routing-overview-container">
                  <div className="routing-left-roles">
                    <div className="routing-role-node-item">
                      <span className="routing-dot-connector planner" />
                      Planner
                    </div>
                    <div className="routing-role-node-item">
                      <span className="routing-dot-connector gui" />
                      GUI Agent
                    </div>
                    <div className="routing-role-node-item">
                      <span className="routing-dot-connector coder" />
                      Coder
                    </div>
                    <div className="routing-role-node-item">
                      <span className="routing-dot-connector researcher" />
                      Researcher
                    </div>
                    <div className="routing-role-node-item">
                      <span className="routing-dot-connector memory" />
                      Memory Agent
                    </div>
                  </div>

                  <svg className="routing-svg-lines">
                    {/* Draw curved connections matching roles to models */}
                    <path d="M 90,24 C 130,24 130,24 165,24" stroke="var(--color-success)" strokeWidth="1.5" fill="none" opacity="0.6" />
                    <path d="M 90,56 C 130,56 130,56 165,56" stroke="var(--color-accent)" strokeWidth="1.5" fill="none" opacity="0.6" />
                    <path d="M 90,88 C 130,88 130,88 165,88" stroke="var(--color-warning)" strokeWidth="1.5" fill="none" opacity="0.6" />
                    <path d="M 90,120 C 130,120 130,120 165,120" stroke="var(--color-primary)" strokeWidth="1.5" fill="none" opacity="0.6" />
                    <path d="M 90,152 C 130,152 130,152 165,152" stroke="#06b6d4" strokeWidth="1.5" fill="none" opacity="0.6" />
                  </svg>

                  <div className="routing-right-models">
                    <div className="routing-model-node-item">Qwen 3.5 4B Q4</div>
                    <div className="routing-model-node-item">Mixtral 8x7B Instruct</div>
                    <div className="routing-model-node-item" style={{ borderColor: 'rgba(245, 158, 11, 0.4)' }}>Codestral 22B</div>
                    <div className="routing-model-node-item">GPT-5.5</div>
                    <div className="routing-model-node-item">Llama 3 70B</div>
                    <div className="routing-model-node-item fallback">Fallback Model</div>
                  </div>
                </div>
                <div style={{ display: 'flex', fontSize: '0.74rem', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: 'auto' }}>
                  <a href="#rules" className="view-timeline-link" style={{ fontSize: '0.74rem', marginTop: '0px' }} onClick={(e) => { e.preventDefault(); alert("Routing rules configurations."); }}>
                    Edit routing rules →
                  </a>
                </div>
              </div>
            </div>

            {/* Recent Model Activity list */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Recent Model Activity</span>
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
                      <span className="t-event-actor">Qwen 3.5 4B Q4 <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Model started</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Running</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:14 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Codestral 22B <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Model updated to v1.2.1</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Ready</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:07 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">Llama 3 70B <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Route changed: Researcher</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Running</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">10:02 AM</span>
                    <span className="t-event-node completed" />
                    <div className="t-event-details">
                      <span className="t-event-actor">GPT-5.5 <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Benchmark completed</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-success)' }}>● Ready</span>
                    </div>
                  </div>
                  <div className="timeline-event-row">
                    <span className="t-event-time">09:58 AM</span>
                    <span className="t-event-node" style={{ backgroundColor: 'var(--color-primary)' }} />
                    <div className="t-event-details">
                      <span className="t-event-actor">Gemma 2 9B <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)', fontWeight: 'normal' }}>Model pulled</span></span>
                      <span className="t-event-desc" style={{ fontSize: '0.72rem', color: 'var(--color-primary)' }}>● Idle</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right column Model details card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{
                    backgroundColor:
                      selectedModel.id === "qwen"
                        ? "rgba(59, 130, 246, 0.1)"
                        : selectedModel.id === "codestral"
                        ? "rgba(245, 158, 11, 0.1)"
                        : selectedModel.id === "mixtral"
                        ? "rgba(168, 85, 247, 0.1)"
                        : selectedModel.id === "llama"
                        ? "rgba(236, 72, 153, 0.1)"
                        : selectedModel.id === "gemma"
                        ? "rgba(59, 130, 246, 0.1)"
                        : selectedModel.id === "gpt"
                        ? "rgba(16, 185, 129, 0.1)"
                        : selectedModel.id === "claude"
                        ? "rgba(6, 182, 212, 0.1)"
                        : "rgba(156, 163, 175, 0.1)",
                    color:
                      selectedModel.id === "qwen"
                        ? "#3b82f6"
                        : selectedModel.id === "codestral"
                        ? "#f59e0b"
                        : selectedModel.id === "mixtral"
                        ? "#a855f7"
                        : selectedModel.id === "llama"
                        ? "#ec4899"
                        : selectedModel.id === "gemma"
                        ? "#3b82f6"
                        : selectedModel.id === "#10b981"
                        ? "#10b981"
                        : selectedModel.id === "claude"
                        ? "#06b6d4"
                        : "#9ca3af",
                  }}>
                    {selectedModel.id === "codestral" ? (
                      <span style={{ fontSize: '0.94rem', fontWeight: 'bold' }}>&lt;/&gt;</span>
                    ) : (
                      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                      </svg>
                    )}
                  </div>
                  <div>
                    <h2 className="details-title-name">{selectedModel.name}</h2>
                  </div>
                </div>

                <span className={`details-status-badge ${selectedModel.status.toLowerCase()}`}>
                  ● {selectedModel.status}
                </span>
              </div>

              <div className="details-id-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>Model ID: {selectedModel.id}3.5-{selectedModel.name.includes("Q4") ? "4b-q4" : "model-id"}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied Model ID to clipboard!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                </div>
                <span className="sh-row-right good" style={{ fontSize: '0.74rem' }}>
                  Health: <span style={{ color: 'var(--color-success)', fontWeight: 'bold' }}>• Healthy</span>
                </span>
              </div>
            </header>

            <div className="agent-details-body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '0.8rem' }}>
                <div>
                  <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Provider</span>
                  <span style={{ fontWeight: '600' }}>{selectedModel.provider}</span>
                </div>
                <div>
                  <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Deployment</span>
                  <span style={{ fontWeight: '600' }}>{selectedModel.deployment}</span>
                </div>
                <div>
                  <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Quantization</span>
                  <span style={{ fontWeight: '600', fontFamily: 'var(--font-mono)' }}>{selectedModel.quantization}</span>
                </div>
              </div>

              <div className="details-section-box">
                <p className="details-section-desc">{selectedModel.description}</p>
              </div>

              <div className="details-section-box">
                <div className="details-tools-badges-grid">
                  {selectedModel.tags.map((tag, idx) => (
                    <span key={idx} className="details-tool-badge" style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', color: '#93c5fd', borderColor: 'rgba(59, 130, 246, 0.15)' }}>{tag}</span>
                  ))}
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Resource Usage</span>
                {selectedModel.status !== "Offline" ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {selectedModel.type === "Local" && (
                      <div className="memory-bar-item">
                        <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                          <span>VRAM</span>
                          <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedModel.vramVal} / {selectedModel.vramMax} ({selectedModel.vramPct}%)</span>
                        </div>
                        <div className="progress-bar-bg" style={{ height: '4px' }}>
                          <div className="progress-bar-fill" style={{ width: `${selectedModel.vramPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                        </div>
                      </div>
                    )}
                    <div className="memory-bar-item">
                      <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                        <span>RAM</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedModel.ramVal} / {selectedModel.ramMax} ({selectedModel.ramPct}%)</span>
                      </div>
                      <div className="progress-bar-bg" style={{ height: '4px' }}>
                        <div className="progress-bar-fill" style={{ width: `${selectedModel.ramPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                    </div>
                    <div className="memory-bar-item">
                      <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                        <span>Context Usage</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedModel.contextVal} / {selectedModel.contextMax} ({selectedModel.contextPct}%)</span>
                      </div>
                      <div className="progress-bar-bg" style={{ height: '4px' }}>
                        <div className="progress-bar-fill" style={{ width: `${selectedModel.contextPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                      </div>
                    </div>
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>Model is offline.</span>
                )}
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Performance / Health</span>
                {selectedModel.status !== "Offline" ? (
                  <div className="details-health-stats-grid">
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Latency (p50)</span>
                      <span className="details-health-stat-val">{selectedModel.rt}</span>
                      <span className="details-health-stat-trend">↓ 8.6%</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Tokens / Sec</span>
                      <span className="details-health-stat-val">{selectedModel.tokensPerSec}</span>
                      <span className="details-health-stat-trend">↑ 5.2%</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Success Rate</span>
                      <span className="details-health-stat-val">{selectedModel.sr}</span>
                      <span className="details-health-stat-trend">↑ 2.3%</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Uptime</span>
                      <span className="details-health-stat-val">{selectedModel.uptime}</span>
                      <span className="details-health-stat-trend">100%</span>
                    </div>
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>—</span>
                )}
              </div>

              <div className="details-section-box">
                <span className="details-section-title">Assigned Roles / Routes</span>
                {selectedModel.assignedRoles.length > 0 ? (
                  <div className="assigned-routes-list">
                    {selectedModel.assignedRoles.map((role, idx) => (
                      <div key={idx} className="assigned-route-row">
                        <span className="assigned-route-name">{role.name}</span>
                        <span className="assigned-route-type">{role.type}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>No active routing configurations.</span>
                )}
              </div>
            </div>

            <footer className="agent-details-footer">
              <button className="details-footer-btn start" onClick={() => alert(`${selectedModel.name} started.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                <span>Start</span>
              </button>
              <button className="details-footer-btn" style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }} onClick={() => alert(`${selectedModel.name} stopped.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-danger)' }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H10a1 1 0 01-1-1v-4z" />
                </svg>
                <span style={{ color: '#fca5a5' }}>Stop</span>
              </button>
              <button className="details-footer-btn restart" onClick={() => alert(`${selectedModel.name} restarted.`)}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                </svg>
                <span>Restart</span>
              </button>
              <button className="details-footer-btn logs" onClick={() => { setActiveTab("workspace"); alert(`Switched to workspace terminal logs for ${selectedModel.name}.`); }}>
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <span>Logs</span>
              </button>
            </footer>
            <button className="role-btn" style={{ margin: '0 16px 16px 16px', height: '32px', fontSize: '0.8rem', justifyContent: 'center' }} onClick={() => alert(`${selectedModel.name} set as default model routing fallback.`)}>
              ★ Set as Default
            </button>
          </div>
        </aside>
      </div>
    </main>
  );
}
