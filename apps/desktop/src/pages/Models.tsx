import { useState, useEffect } from "react";

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  providerId: string;
  apiSource: string;
  modelId: string;
  baseUrl: string;
  type: "Local" | "API";
  billingMode: string;
  context: string;
  status: "Running" | "Ready" | "Loading" | "Idle" | "Offline";
  hasKey: boolean;
  roles: string;
  rt: string;
  sr: string;
  sparkPoints: string;
  description: string;
  deployment: string;
  quantization: string | null;
  vram: string;
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
  capabilities: string[];
  latencyP50Ms: number | null;
  latencyP90Ms: number | null;
  successRate: number | null;
  quota: {
    mode: string;
    rpmLimit: number | null;
    rpdLimit: number | null;
    tpmLimit: number | null;
    dailyTokenLimit: number | null;
    monthlyTokenLimit: number | null;
    remainingRequestsToday: number | null;
    remainingTokensToday: number | null;
    remainingCredit: number | null;
    resetAt: string | null;
    source: string;
  } | null;
}

interface ModelsProps {
  setActiveTab: (tab: string) => void;
}

export function Models({ setActiveTab: _ }: ModelsProps) {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  // Inline-editing States
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [tempModelId, setTempModelId] = useState<string>("");
  const [editingApiKey, setEditingApiKey] = useState<string | null>(null);
  const [tempApiKey, setTempApiKey] = useState<string>("");

  const handleSaveModelId = async (id: string, newId: string) => {
    try {
      const res = await fetch(`/api/models/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: newId }),
      });
      if (res.ok) {
        setEditingModelId(null);
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Failed to update Model ID: " + body.detail);
      }
    } catch (err) {
      alert("Error: " + err);
    }
  };

  const handleSaveApiKey = async (providerId: string, newKey: string) => {
    try {
      const res = await fetch(`/api/models/providers/${providerId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: newKey }),
      });
      if (res.ok) {
        setEditingApiKey(null);
        await fetchAllData();
        alert("API Key updated successfully in database!");
      } else {
        const body = await res.json();
        alert("Failed to update API Key: " + body.detail);
      }
    } catch (err) {
      alert("Error: " + err);
    }
  };

  // Routing and Activity States
  const [activities, setActivities] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);

  // Modal States
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isEditRulesOpen, setIsEditRulesOpen] = useState<boolean>(false);

  // Form Fields
  const [newModel, setNewModel] = useState({
    name: "",
    provider_id: "google_ai_studio",
    model_id: "",
    type: "API",
    base_url: "",
    capabilities: "chat",
    tags: "Cloud",
    roles: "Planner",
  });
  const [importConfig, setImportConfig] = useState({
    source: "ollama",
    model_name: "",
  });
  const [editedRules, setEditedRules] = useState<Record<string, { primary: string; fallback: string }>>({});

  const fetchAllData = async () => {
    try {
      const [modelsRes, routingRes, activityRes, providersRes] = await Promise.all([
        fetch("/api/models"),
        fetch("/api/models/routing"),
        fetch("/api/models/activity"),
        fetch("/api/models/providers"),
      ]);

      if (!modelsRes.ok) throw new Error("Failed to load models list");

      const modelsData = await modelsRes.json();
      setModels(modelsData);

      if (routingRes.ok) {
        const rData = await routingRes.json();
        // Sync rules form state
        const initialFormRules: Record<string, { primary: string; fallback: string }> = {};
        Object.keys(rData).forEach((role) => {
          initialFormRules[role] = {
            primary: rData[role].primary || "",
            fallback: rData[role].fallback || "",
          };
        });
        setEditedRules(initialFormRules);
      }
      if (activityRes.ok) setActivities(await activityRes.json());
      if (providersRes.ok) setProviders(await providersRes.json());

      // Auto select first model if none selected
      if (modelsData.length > 0 && !selectedModelId) {
        setSelectedModelId(modelsData[0].id);
      }
      setError(null);
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Cannot load model registry from backend sidecar.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();

    // Set polling interval for updates
    const timer = setInterval(() => {
      fetch("/api/models")
        .then((res) => res.json())
        .then((data) => setModels(data))
        .catch(console.error);

      fetch("/api/models/activity")
        .then((res) => res.json())
        .then((data) => setActivities(data))
        .catch(console.error);
    }, 15000);

    return () => clearInterval(timer);
  }, []);

  const handleStart = async (modelId: string) => {
    try {
      const res = await fetch(`/api/models/${modelId}/start`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to start model: " + err);
    }
  };

  const handleStop = async (modelId: string) => {
    try {
      const res = await fetch(`/api/models/${modelId}/stop`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to stop model: " + err);
    }
  };

  const handleRestart = async (modelId: string) => {
    try {
      const res = await fetch(`/api/models/${modelId}/restart`, { method: "POST" });
      if (res.ok) await fetchAllData();
    } catch (err) {
      alert("Failed to restart model: " + err);
    }
  };

  const handleSetDefault = async (modelId: string) => {
    try {
      const res = await fetch(`/api/models/${modelId}/set-default`, { method: "POST" });
      if (res.ok) {
        alert("Set default model fallback successfully!");
        await fetchAllData();
      }
    } catch (err) {
      alert("Failed to set default: " + err);
    }
  };

  const handleAddModel = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...newModel,
          capabilities: newModel.capabilities.split(",").map((s) => s.trim()),
          tags: newModel.tags.split(",").map((s) => s.trim()),
          roles: newModel.roles.split(",").map((s) => s.trim()),
        }),
      });
      if (res.ok) {
        setIsAddModalOpen(false);
        setNewModel({
          name: "",
          provider_id: "google_ai_studio",
          model_id: "",
          type: "API",
          base_url: "",
          capabilities: "chat",
          tags: "Cloud",
          roles: "Planner",
        });
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Error adding model: " + body.detail);
      }
    } catch (err) {
      alert("Failed to add model: " + err);
    }
  };

  const handleImportModel = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/models/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(importConfig),
      });
      if (res.ok) {
        setIsImportModalOpen(false);
        setImportConfig({ source: "ollama", model_name: "" });
        await fetchAllData();
        alert("Model import job queued successfully in background.");
      } else {
        const body = await res.json();
        alert("Error importing model: " + body.detail);
      }
    } catch (err) {
      alert("Failed to import model: " + err);
    }
  };

  const handleSaveRoutingRules = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload: Record<string, { primary: string | null; fallback: string | null }> = {};
      Object.keys(editedRules).forEach((role) => {
        payload[role] = {
          primary: editedRules[role].primary || null,
          fallback: editedRules[role].fallback || null,
        };
      });

      const res = await fetch("/api/models/routing", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setIsEditRulesOpen(false);
        await fetchAllData();
        alert("Routing rules updated successfully.");
      }
    } catch (err) {
      alert("Failed to update rules: " + err);
    }
  };

  const _handleSyncProvider = async (providerId: string) => {
    try {
      const res = await fetch(`/api/models/providers/${providerId}/sync`, { method: "POST" });
      if (res.ok) {
        alert(`Synchronized provider ${providerId} successfully!`);
        await fetchAllData();
      } else {
        const body = await res.json();
        alert("Sync failed: " + body.detail);
      }
    } catch (err) {
      alert("Failed to sync provider: " + err);
    }
  };

  const handleRunAllBenchmarks = async () => {
    try {
      const modelIds = models.filter((m) => m.hasKey && m.status !== "Offline").map((m) => m.id);
      if (modelIds.length === 0) {
        alert("No online models configured with API Keys to benchmark.");
        return;
      }
      alert(`Running quick latency benchmark on ${modelIds.length} models in the background.`);
      const res = await fetch("/api/models/benchmarks/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_ids: modelIds,
          test_name: "smoke",
          prompt: "Say OK in one sentence.",
          max_tokens: 16,
        }),
      });
      if (res.ok) {
        await fetchAllData();
      }
    } catch (err) {
      alert("Failed to run benchmarks: " + err);
    }
  };

  // Metrics calculations
  const totalModels = models.length;
  const activeModels = models.filter((m) => m.status === "Running" || m.status === "Ready").length;
  const localModels = models.filter((m) => m.type === "Local").length;
  const apiModels = models.filter((m) => m.type === "API").length;
  const avgLatency = models.filter((m) => m.latencyP50Ms).reduce((acc, curr) => acc + (curr.latencyP50Ms || 0), 0) / (models.filter((m) => m.latencyP50Ms).length || 1);
  const memoryFootprint = "N/A"; // Resource metrics

  // Filters logic
  const filteredModels = models.filter((model) => {
    if (activeFilterTab === "running" && (model.status !== "Running" && model.status !== "Ready")) return false;
    if (activeFilterTab === "local" && model.type !== "Local") return false;
    if (activeFilterTab === "api" && model.type !== "API") return false;
    if (activeFilterTab === "quantized" && !model.name.includes("Q4") && !model.name.includes("Q5") && !model.name.includes("Q8") && !model.quantization) return false;
    if (activeFilterTab === "offline" && model.status !== "Offline") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        model.name.toLowerCase().includes(q) ||
        model.provider.toLowerCase().includes(q) ||
        model.roles.toLowerCase().includes(q) ||
        model.capabilities.some((c) => c.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const selectedModel = models.find((m) => m.id === selectedModelId) || models[0];

  if (loading) {
    return (
      <main className="models-view" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <div style={{ color: 'var(--text-dim)', fontSize: '1.2rem' }}>Loading Model Registry Sidecar...</div>
      </main>
    );
  }

  return (
    <main className="models-view">
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Models</h1>
          <p className="dashboard-subtitle-text">Manage local and cloud models, routing, health, and performance.</p>
        </div>
        {error && (
          <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5', padding: '8px 16px', borderRadius: '6px', border: '1px solid rgba(239, 68, 68, 0.2)', fontSize: '0.86rem' }}>
            ⚠ {error}
          </div>
        )}
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => setIsAddModalOpen(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            Add Model
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => setIsImportModalOpen(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Import Model
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={() => setIsEditRulesOpen(true)}>
            Edit Routing
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={handleRunAllBenchmarks}>
            ⚡ Run Benchmark
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
              <div className="m-card-subtext">All registered models</div>
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
              <div className="m-card-subtext">{totalModels ? ((activeModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
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
              <div className="m-card-subtext">{totalModels ? ((localModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
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
              <div className="m-card-subtext">{totalModels ? ((apiModels / totalModels) * 100).toFixed(1) : 0}% of total</div>
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
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{avgLatency ? `${Math.round(avgLatency)}ms` : "—"}</div>
              <div className="m-card-subtext">p50 benchmark avg</div>
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
              <span>Local Resource</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{memoryFootprint}</div>
              <div className="m-card-subtext">Ollama load state</div>
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
                      placeholder="Search name, provider, capabilities..."
                      value={searchText}
                      onChange={(e) => setSearchText(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              {/* Status filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '3px' }}>
                <button className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`} onClick={() => setActiveFilterTab("all")}>All</button>
                <button className={`tab-btn ${activeFilterTab === "running" ? "active" : ""}`} onClick={() => setActiveFilterTab("running")}>Running</button>
                <button className={`tab-btn ${activeFilterTab === "local" ? "active" : ""}`} onClick={() => setActiveFilterTab("local")}>Local</button>
                <button className={`tab-btn ${activeFilterTab === "api" ? "active" : ""}`} onClick={() => setActiveFilterTab("api")}>API</button>
                <button className={`tab-btn ${activeFilterTab === "quantized" ? "active" : ""}`} onClick={() => setActiveFilterTab("quantized")}>Quantized</button>
                <button className={`tab-btn ${activeFilterTab === "offline" ? "active" : ""}`} onClick={() => setActiveFilterTab("offline")}>Offline</button>
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
                    <th>Status</th>
                    <th>API Key</th>
                    <th>Capabilities</th>
                    <th>Latency (p50)</th>
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
                          <span className="agent-color-dot" style={{ backgroundColor: model.type === "Local" ? "#3b82f6" : "#10b981" }} />
                          <div>
                            <div style={{ fontWeight: '700' }}>
                              {model.name}
                              {model.quantization && (
                                <span className="model-quant-tag" style={{ marginLeft: '4px', fontSize: '0.64rem', padding: '1px 4px', backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: '3px' }}>
                                  {model.quantization}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td style={{ fontWeight: '500' }}>{model.provider}</td>
                      <td>
                        <span style={{ color: model.type === "Local" ? "var(--color-primary)" : "var(--color-warning)", fontWeight: '600', fontSize: '0.74rem' }}>
                          {model.type}
                        </span>
                      </td>
                      <td>{model.context}</td>
                      <td>
                        <span className={`agent-status-badge ${model.status.toLowerCase()}`}>
                          {model.status}
                        </span>
                      </td>
                      <td>
                        {model.type === "API" ? (
                          model.hasKey ? (
                            <span style={{ color: 'var(--color-success)', fontSize: '0.72rem' }}>✔ Configured</span>
                          ) : (
                            <span style={{ color: '#eab308', fontSize: '0.72rem', fontWeight: 'bold' }}>⚠ Needs key</span>
                          )
                        ) : (
                          <span style={{ color: 'var(--text-dim)', fontSize: '0.72rem' }}>— Local</span>
                        )}
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '0.76rem' }}>
                        {model.capabilities.join(", ")}
                      </td>
                      <td>{model.rt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border-color)', fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredModels.length} of {models.length} models</span>
              </div>
            </div>
          </div>

        </div>

        {/* Right column Model details card */}
        {selectedModel && (
          <aside className="agent-details-pane">
            <div className="agent-details-card">
              <header className="agent-details-header">
                <div className="details-header-top">
                  <div className="details-title-box">
                    <div className="details-title-icon-box" style={{ backgroundColor: selectedModel.type === "Local" ? "rgba(59, 130, 246, 0.1)" : "rgba(16, 185, 129, 0.1)" }}>
                      <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                      </svg>
                    </div>
                    <div>
                      <h2 className="details-title-name">{selectedModel.name}</h2>
                    </div>
                  </div>

                  <span className={`details-status-badge ${selectedModel.status.toLowerCase()}`}>
                    ● {selectedModel.status}
                  </span>
                </div>

                <div className="details-id-row" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'stretch', width: '100%' }}>
                  {/* Model ID row */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {editingModelId === selectedModel.id ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <span style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>Model ID:</span>
                          <input
                            type="text"
                            value={tempModelId}
                            onChange={(e) => setTempModelId(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === "Enter") {
                                await handleSaveModelId(selectedModel.id, tempModelId);
                              } else if (e.key === "Escape") {
                                setEditingModelId(null);
                              }
                            }}
                            onBlur={() => setEditingModelId(null)}
                            autoFocus
                            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--color-primary)', color: 'var(--text-main)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.78rem', width: '220px' }}
                          />
                        </div>
                      ) : (
                        <span
                          onClick={() => {
                            setEditingModelId(selectedModel.id);
                            setTempModelId(selectedModel.modelId);
                          }}
                          style={{ cursor: 'pointer', borderBottom: '1px dashed var(--text-dim)', fontSize: '0.78rem' }}
                          title="Click to edit Model ID"
                        >
                          Model ID: <strong style={{ color: 'var(--text-main)' }}>{selectedModel.modelId}</strong> ✎
                        </span>
                      )}
                    </div>
                    {!selectedModel.hasKey && selectedModel.type === "API" && (
                      <span style={{ color: '#f59e0b', fontWeight: 'bold', fontSize: '0.74rem' }}>Needs API Key</span>
                    )}
                  </div>

                  {/* API Key row (only for API models) */}
                  {selectedModel.type === "API" && (
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem' }}>
                        <span style={{ color: 'var(--text-dim)' }}>API Key:</span>
                        {editingApiKey === selectedModel.providerId ? (
                          <input
                            type="password"
                            value={tempApiKey}
                            onChange={(e) => setTempApiKey(e.target.value)}
                            onKeyDown={async (e) => {
                              if (e.key === "Enter") {
                                await handleSaveApiKey(selectedModel.providerId, tempApiKey);
                              } else if (e.key === "Escape") {
                                setEditingApiKey(null);
                              }
                            }}
                            onBlur={() => setEditingApiKey(null)}
                            placeholder="Type new API key & press Enter"
                            autoFocus
                            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--color-primary)', color: 'var(--text-main)', padding: '2px 6px', borderRadius: '4px', fontSize: '0.78rem', width: '220px' }}
                          />
                        ) : (
                          <span
                            onClick={() => {
                              setEditingApiKey(selectedModel.providerId);
                              setTempApiKey("");
                            }}
                            style={{ cursor: 'pointer', borderBottom: '1px dashed var(--text-dim)', color: selectedModel.hasKey ? 'var(--color-success)' : '#f59e0b', fontWeight: '600' }}
                            title="Click to set/change API Key"
                          >
                            {selectedModel.hasKey ? "•••••••• (Click to edit)" : "Needs key (Click to edit)"} ✎
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </header>

              <div className="agent-details-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '0.8rem' }}>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Provider</span>
                    <span style={{ fontWeight: '600', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {selectedModel.provider}
                      {selectedModel.type === "API" && (
                        <button
                          onClick={() => _handleSyncProvider(selectedModel.providerId)}
                          style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer', padding: '0 2px', fontSize: '0.7rem', textDecoration: 'underline' }}
                          title="Sync provider models catalog"
                        >
                          Sync
                        </button>
                      )}
                    </span>
                  </div>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Deployment</span>
                    <span style={{ fontWeight: '600' }}>{selectedModel.deployment}</span>
                  </div>
                  <div>
                    <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Billing Mode</span>
                    <span style={{ fontWeight: '600', fontFamily: 'var(--font-mono)' }}>{selectedModel.billingMode}</span>
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
                  <span className="details-section-title">Quota Details</span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.78rem' }}>
                    {selectedModel.quota && (
                      <>
                        {selectedModel.quota.rpmLimit && <div>RPM Limit: <strong>{selectedModel.quota.rpmLimit}</strong></div>}
                        {selectedModel.quota.rpdLimit && <div>RPD Limit: <strong>{selectedModel.quota.rpdLimit}</strong></div>}
                        {selectedModel.quota.remainingRequestsToday !== null && (
                          <div>Requests Remaining Today: <strong>{selectedModel.quota.remainingRequestsToday}</strong></div>
                        )}
                        {selectedModel.quota.remainingTokensToday !== null && (
                          <div>Tokens Remaining Today: <strong>{selectedModel.quota.remainingTokensToday}</strong></div>
                        )}
                        {selectedModel.quota.resetAt && <div>Reset Time: <strong>{new Date(selectedModel.quota.resetAt).toLocaleTimeString()}</strong></div>}
                      </>
                    )}
                  </div>
                </div>

                <div className="details-section-box">
                  <span className="details-section-title">Performance Metrics</span>
                  <div className="details-health-stats-grid">
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Latency (p50)</span>
                      <span className="details-health-stat-val">{selectedModel.rt}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Tokens / Sec</span>
                      <span className="details-health-stat-val">{selectedModel.tokensPerSec}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Success Rate</span>
                      <span className="details-health-stat-val">{selectedModel.sr}</span>
                    </div>
                    <div className="details-health-stat-card">
                      <span className="details-health-stat-title">Uptime</span>
                      <span className="details-health-stat-val">{selectedModel.uptime}</span>
                    </div>
                  </div>
                </div>
              </div>

              <footer className="agent-details-footer">
                <button
                  className="details-footer-btn start"
                  onClick={() => handleStart(selectedModel.id)}
                  disabled={!selectedModel.hasKey && selectedModel.type === "API"}
                  style={{ opacity: (!selectedModel.hasKey && selectedModel.type === "API") ? 0.5 : 1 }}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  </svg>
                  <span>Start</span>
                </button>
                <button
                  className="details-footer-btn"
                  style={{ borderColor: 'rgba(239, 68, 68, 0.4)' }}
                  onClick={() => handleStop(selectedModel.id)}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-danger)' }}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H10a1 1 0 01-1-1v-4z" />
                  </svg>
                  <span style={{ color: '#fca5a5' }}>Stop</span>
                </button>
                <button
                  className="details-footer-btn restart"
                  onClick={() => handleRestart(selectedModel.id)}
                  disabled={!selectedModel.hasKey && selectedModel.type === "API"}
                  style={{ opacity: (!selectedModel.hasKey && selectedModel.type === "API") ? 0.5 : 1 }}
                >
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                  </svg>
                  <span>Restart</span>
                </button>
              </footer>
              <button
                className="role-btn"
                style={{ margin: '0 16px 16px 16px', height: '32px', fontSize: '0.8rem', justifyContent: 'center' }}
                onClick={() => handleSetDefault(selectedModel.id)}
              >
                ★ Set as Default
              </button>
            </div>
          </aside>
        )}
      </div>

      {/* Model Activity logs panel at the bottom */}
      <div className="dashboard-panel" style={{ marginTop: '16px' }}>
        <header className="panel-header">
          <span className="panel-title">Recent Model Registry Activity Logs</span>
        </header>
        <div className="panel-body" style={{ maxHeight: '180px', overflowY: 'auto' }}>
          <div className="timeline-logs-container">
            {activities.slice(0, 8).map((act, idx) => (
              <div key={idx} className="timeline-event-row" style={{ fontSize: '0.78rem' }}>
                <span className="t-event-time">{act.time}</span>
                <span className="t-event-node completed" style={{ backgroundColor: act.level === "error" ? "var(--color-danger)" : (act.level === "warning" ? "#eab308" : "var(--color-success)") }} />
                <div className="t-event-details">
                  <span className="t-event-actor" style={{ fontWeight: 'bold' }}>{act.modelId || act.providerId}</span>
                  <span className="t-event-desc" style={{ color: 'var(--text-main)', marginLeft: '6px' }}>{act.message}</span>
                </div>
              </div>
            ))}
            {activities.length === 0 && <div style={{ color: 'var(--text-dim)', textAlign: 'center', padding: '12px' }}>No activity records.</div>}
          </div>
        </div>
      </div>

      {/* Modals/Form dialog structures */}
      {isAddModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(3px)' }}>
          <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '24px', width: '450px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '1.2rem' }}>Add Model Configuration</h3>
            <form onSubmit={handleAddModel} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Name</label>
                <input type="text" value={newModel.name} onChange={(e) => setNewModel({ ...newModel, name: e.target.value })} required style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Provider</label>
                <select value={newModel.provider_id} onChange={(e) => setNewModel({ ...newModel, provider_id: e.target.value })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }}>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id} style={{ background: 'var(--bg-darker)' }}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Model ID (provider model string)</label>
                <input type="text" value={newModel.model_id} onChange={(e) => setNewModel({ ...newModel, model_id: e.target.value })} required style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Capabilities (comma-separated: chat, reasoning, coding, vision)</label>
                <input type="text" value={newModel.capabilities} onChange={(e) => setNewModel({ ...newModel, capabilities: e.target.value })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Tags (comma-separated: Free, Fast, Large)</label>
                <input type="text" value={newModel.tags} onChange={(e) => setNewModel({ ...newModel, tags: e.target.value })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Roles (comma-separated: Planner, Coder, Researcher)</label>
                <input type="text" value={newModel.roles} onChange={(e) => setNewModel({ ...newModel, roles: e.target.value })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="role-btn" onClick={() => setIsAddModalOpen(false)} style={{ padding: '6px 16px' }}>Cancel</button>
                <button type="submit" className="chat-send-btn" style={{ padding: '6px 16px' }}>Add</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isImportModalOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(3px)' }}>
          <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '24px', width: '400px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '1.2rem' }}>Import Local Model</h3>
            <form onSubmit={handleImportModel} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Source</label>
                <select value={importConfig.source} onChange={(e) => setImportConfig({ ...importConfig, source: e.target.value })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }}>
                  <option value="ollama" style={{ background: 'var(--bg-darker)' }}>Ollama Library</option>
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '0.74rem', color: 'var(--text-dim)' }}>Model Name (e.g. qwen3.5:4b-q4, phi3:medium)</label>
                <input type="text" value={importConfig.model_name} onChange={(e) => setImportConfig({ ...importConfig, model_name: e.target.value })} required style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '6px', color: 'var(--text-main)', fontSize: '0.86rem' }} />
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="role-btn" onClick={() => setIsImportModalOpen(false)} style={{ padding: '6px 16px' }}>Cancel</button>
                <button type="submit" className="chat-send-btn" style={{ padding: '6px 16px' }}>Import</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {isEditRulesOpen && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(3px)' }}>
          <div style={{ background: 'var(--bg-darker)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '24px', width: '500px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <h3 style={{ margin: 0, color: 'var(--text-main)', fontSize: '1.2rem' }}>Edit Routing Rules</h3>
            <form onSubmit={handleSaveRoutingRules} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ maxHeight: '300px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px', paddingRight: '6px' }}>
                {Object.keys(editedRules).map((role) => (
                  <div key={role} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <span style={{ fontWeight: 'bold', fontSize: '0.82rem', color: '#93c5fd' }}>{role}</span>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Primary Model</span>
                        <select value={editedRules[role].primary} onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], primary: e.target.value } })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px', color: 'var(--text-main)', fontSize: '0.8rem', width: '100%' }}>
                          <option value="" style={{ background: 'var(--bg-darker)' }}>None</option>
                          {models.map((m) => (
                            <option key={m.id} value={m.id} style={{ background: 'var(--bg-darker)' }}>{m.name}</option>
                          ))}
                        </select>
                      </div>
                      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Fallback Model</span>
                        <select value={editedRules[role].fallback} onChange={(e) => setEditedRules({ ...editedRules, [role]: { ...editedRules[role], fallback: e.target.value } })} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '4px', padding: '4px', color: 'var(--text-main)', fontSize: '0.8rem', width: '100%' }}>
                          <option value="" style={{ background: 'var(--bg-darker)' }}>None</option>
                          {models.map((m) => (
                            <option key={m.id} value={m.id} style={{ background: 'var(--bg-darker)' }}>{m.name}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button type="button" className="role-btn" onClick={() => setIsEditRulesOpen(false)} style={{ padding: '6px 16px' }}>Cancel</button>
                <button type="submit" className="chat-send-btn" style={{ padding: '6px 16px' }}>Save Rules</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
