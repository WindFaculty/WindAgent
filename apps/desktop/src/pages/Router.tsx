import { useState, useEffect, useRef } from "react";

interface RoutingRuleItem {
  id: string;
  name: string;
  trigger: string;
  primaryModel: string;
  secondaryModel: string;
  finalFallbackModel: string;
  status: "Active" | "Weighted" | "Fallback" | "Disabled";
  description: string;
  routeId: string;
  tags: string[];
  primaryUsage: number;
  fallbackUsage: number;
  successRate: number;
  avgLatency: string;
  health: Array<{ name: string; latency: string; status: "Good" | "Warning" }>;
  activity: string[];
}

interface ModelItem {
  id: string;
  name: string;
  provider: string;
  type: string;
}

interface WebAudioSound {
  playSwim: () => void;
  playBubble: () => void;
  playFish: () => void;
  playShield: () => void;
  playHit: () => void;
  playGameOver: () => void;
}

// Simple Web Audio API Synthesizer for retro sounds
class SoundSynth implements WebAudioSound {
  private ctx: AudioContext | null = null;

  private init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
  }

  playSwim() {
    this.init();
    if (!this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(120, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(40, this.ctx.currentTime + 0.12);
      
      gain.gain.setValueAtTime(0.15, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.12);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.12);
    } catch (e) {
      // Ignored if audio blocked
    }
  }

  playBubble() {
    this.init();
    if (!this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.type = 'sine';
      osc.frequency.setValueAtTime(400, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1000, this.ctx.currentTime + 0.1);
      
      gain.gain.setValueAtTime(0.1, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.1);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.1);
    } catch (e) {}
  }

  playFish() {
    this.init();
    if (!this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.type = 'sine';
      osc.frequency.setValueAtTime(700, this.ctx.currentTime);
      osc.frequency.setValueAtTime(1100, this.ctx.currentTime + 0.08);
      
      gain.gain.setValueAtTime(0.1, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.22);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.22);
    } catch (e) {}
  }

  playShield() {
    this.init();
    if (!this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(300, this.ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(900, this.ctx.currentTime + 0.25);
      
      gain.gain.setValueAtTime(0.08, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.25);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.25);
    } catch (e) {}
  }

  playHit() {
    this.init();
    if (!this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(150, this.ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(50, this.ctx.currentTime + 0.2);
      
      gain.gain.setValueAtTime(0.3, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, this.ctx.currentTime + 0.2);
      
      osc.start();
      osc.stop(this.ctx.currentTime + 0.2);
    } catch (e) {}
  }

  playGameOver() {
    this.init();
    if (!this.ctx) return;
    try {
      const now = this.ctx.currentTime;
      const playNote = (freq: number, start: number, duration: number) => {
        if (!this.ctx) return;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.type = 'sine';
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0.15, start);
        gain.gain.exponentialRampToValueAtTime(0.01, start + duration - 0.02);
        osc.start(start);
        osc.stop(start + duration);
      };
      playNote(300, now, 0.18);
      playNote(250, now + 0.18, 0.18);
      playNote(200, now + 0.36, 0.18);
      playNote(150, now + 0.54, 0.4);
    } catch (e) {}
  }
}

const sound = new SoundSynth();

export function Router() {
  const [rules, setRules] = useState<RoutingRuleItem[]>([]);
  const [selectedRouteId, setSelectedRouteId] = useState<string>("");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, _setSearchText] = useState<string>("");

  // Statistics
  const [stats, setStats] = useState({
    totalRoutes: 0,
    activeRules: 0,
    fallbackChains: 0,
    avgLatency: "0ms",
    successRate: "0%",
    trafficBalance: "0%"
  });

  // Traffic
  const [trafficDistribution, setTrafficDistribution] = useState<any[]>([]);

  // Graph
  const [graphData, setGraphData] = useState<{roles: string[], models: string[], links: any[]}>({ roles: [], models: [], links: [] });

  // Creation / Editing states
  const [availableModels, setAvailableModels] = useState<ModelItem[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingRule, setEditingRule] = useState<Partial<RoutingRuleItem> | null>(null);

  // Form values
  const [formRole, setFormRole] = useState("");
  const [formName, setFormName] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formPrimary, setFormPrimary] = useState("");
  const [formFallback, setFormFallback] = useState("");
  const [formFinalFallback, setFormFinalFallback] = useState("");

  // Simulation
  const [simRole, setSimRole] = useState("Planner");
  const [simPrompt, setSimPrompt] = useState("Explain quantum physics to a 5 year old");
  const [simResult, setSimResult] = useState<any>(null);
  const [simulating, setSimulating] = useState(false);

  // Game state
  const [isGameOpen, setIsGameOpen] = useState(false);
  const [_gameScore, _setGameScore] = useState(0);
  const [_gameShrimps, _setGameShrimps] = useState(0);
  const [_gameHighScore, _setGameHighScore] = useState(0);
  const [_totalShrimps, _setTotalShrimps] = useState(0);
  const [_selectedSkin, _setSelectedSkin] = useState("classic");
  const [_ownedSkins, _setOwnedSkins] = useState<string[]>(["classic"]);

  const [apiError, setApiError] = useState<string | null>(null);

  // Load Initial Data
  const fetchAllData = async () => {
    try {
      // 1. Fetch Rules
      const rulesRes = await fetch("/api/models/routing/rules");
      if (!rulesRes.ok) throw new Error("Backend offline");
      const rulesJson = await rulesRes.json();
      
      const formattedRules: RoutingRuleItem[] = rulesJson.map((r: any) => ({
        id: r.role,
        name: r.name,
        trigger: r.role,
        primaryModel: r.primary_model_id || "None",
        secondaryModel: r.fallback_model_id || "None",
        finalFallbackModel: r.final_fallback_model_id || "None",
        status: r.status || "Active",
        description: r.description || "",
        routeId: `route_${r.role.toLowerCase()}`,
        tags: r.tags || [],
        primaryUsage: r.stats?.primary_ratio !== undefined ? Math.round(r.stats.primary_ratio * 100) : 100,
        fallbackUsage: r.stats?.fallback_ratio !== undefined ? Math.round(r.stats.fallback_ratio * 100) : 0,
        successRate: r.stats?.success_rate !== undefined ? Math.round(r.stats.success_rate * 100) : 100,
        avgLatency: r.stats?.avg_latency_ms !== undefined ? `${Math.round(r.stats.avg_latency_ms)}ms` : "—",
        health: [
          { name: "Primary Model", latency: r.stats?.avg_latency_ms ? `${Math.round(r.stats.avg_latency_ms)}ms` : "32ms", status: "Good" },
          { name: "Secondary Model", latency: "115ms", status: "Good" },
        ],
        activity: r.recent_logs?.map((l: any) => `${l.message} (${new Date(l.timestamp).toLocaleTimeString()})`) || [
          `Rule loaded for ${r.role}`
        ]
      }));

      setRules(formattedRules);
      if (formattedRules.length > 0 && !selectedRouteId) {
        setSelectedRouteId(formattedRules[0].id);
      }

      // 2. Fetch Stats
      const statsRes = await fetch("/api/models/routing/stats");
      if (statsRes.ok) {
        const statsJson = await statsRes.ok ? await statsRes.json() : null;
        if (statsJson) {
          setStats({
            totalRoutes: statsJson.total_routes || 0,
            activeRules: statsJson.active_rules || 0,
            fallbackChains: statsJson.fallback_chains || 0,
            avgLatency: `${Math.round(statsJson.avg_latency_ms || 0)}ms`,
            successRate: `${( (statsJson.success_rate || 0) * 100 ).toFixed(1)}%`,
            trafficBalance: `${( (statsJson.traffic_balance || 0) * 100 ).toFixed(0)}%`
          });
        }
      }

      // 3. Fetch Traffic
      const trafficRes = await fetch("/api/models/routing/traffic");
      if (trafficRes.ok) {
        const trafficJson = await trafficRes.json();
        if (trafficJson && trafficJson.distribution) {
          setTrafficDistribution(trafficJson.distribution);
        }
      }

      // 4. Fetch Graph
      const graphRes = await fetch("/api/models/routing/graph");
      if (graphRes.ok) {
        const graphJson = await graphRes.json();
        setGraphData(graphJson);
      }

      // 5. Fetch Available Models
      const modelsRes = await fetch("/api/models");
      if (modelsRes.ok) {
        const modelsJson = await modelsRes.json();
        setAvailableModels(modelsJson.map((m: any) => ({
          id: m.id,
          name: m.display_name || m.model_id,
          provider: m.provider_id,
          type: m.type
        })));
      }

      setApiError(null);
    } catch (e) {
      setApiError("Could not connect to the Backend API. Showing simulated/offline data.");
      // Fallback with mock data to keep UI functional
      const mockRules: RoutingRuleItem[] = [
        {
          id: "Planner",
          name: "Planner → Local Chat",
          trigger: "Planner",
          primaryModel: "google_gemini_2.5_flash",
          secondaryModel: "openrouter_free",
          finalFallbackModel: "ollama_qwen",
          status: "Active",
          description: "Handles general local chat and lightweight planning requests, preferring the local model.",
          routeId: "route_planner",
          tags: ["Planning", "Chat", "Local First"],
          primaryUsage: 80,
          fallbackUsage: 15,
          successRate: 98,
          avgLatency: "154ms",
          health: [{ name: "Google Gemini 2.5 Flash", latency: "140ms", status: "Good" }],
          activity: ["Routed Planner request to Gemini 2.5 Flash"]
        },
        {
          id: "Coder",
          name: "Coder → Code Model",
          trigger: "Coder",
          primaryModel: "mistral_codestral",
          secondaryModel: "qwen_coder_free",
          finalFallbackModel: "None",
          status: "Active",
          description: "Route code autocompletion and structural parsing tasks to Codestral, with Sonnet as backup.",
          routeId: "route_coder",
          tags: ["Coding", "Autocomplete"],
          primaryUsage: 92,
          fallbackUsage: 8,
          successRate: 96,
          avgLatency: "310ms",
          health: [{ name: "Mistral Codestral", latency: "290ms", status: "Good" }],
          activity: ["Routed Coder request to Codestral"]
        }
      ];
      setRules(mockRules);
      if (!selectedRouteId) setSelectedRouteId("Planner");
      setStats({
        totalRoutes: 2,
        activeRules: 2,
        fallbackChains: 1,
        avgLatency: "232ms",
        successRate: "97.0%",
        trafficBalance: "85%"
      });
      setTrafficDistribution([
        { name: "Google Gemini 2.5 Flash", count: 120, percentage: 65 },
        { name: "Mistral Codestral", count: 65, percentage: 35 }
      ]);
    }
  };

  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 6000);
    return () => clearInterval(interval);
  }, []);

  // Handle Save (Create/Update)
  const handleSaveRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formRole || !formName || !formPrimary) {
      alert("Role, Name and Primary Model are required.");
      return;
    }

    const payload = {
      role: formRole,
      name: formName,
      description: formDesc,
      primary_model_id: formPrimary || null,
      fallback_model_id: formFallback || null,
      final_fallback_model_id: formFinalFallback || null,
      status: editingRule ? editingRule.status : "Active"
    };

    try {
      let res;
      if (showEditModal && editingRule) {
        res = await fetch(`/api/models/routing/rules/${editingRule.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      } else {
        res = await fetch("/api/models/routing/rules", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      }

      if (res.ok) {
        setShowCreateModal(false);
        setShowEditModal(false);
        setEditingRule(null);
        resetForm();
        fetchAllData();
      } else {
        const errJson = await res.json();
        alert("Error saving rule: " + (errJson.detail || "Unknown error"));
      }
    } catch (err: any) {
      alert("Network error: " + err.message);
    }
  };

  const resetForm = () => {
    setFormRole("");
    setFormName("");
    setFormDesc("");
    setFormPrimary("");
    setFormFallback("");
    setFormFinalFallback("");
  };

  // Delete Rule
  const handleDeleteRule = async (role: string) => {
    if (!confirm(`Are you sure you want to delete the routing rule for "${role}"?`)) return;
    try {
      const res = await fetch(`/api/models/routing/rules/${role}`, {
        method: "DELETE"
      });
      if (res.ok) {
        fetchAllData();
        setSelectedRouteId("");
      } else {
        alert("Failed to delete rule.");
      }
    } catch (e) {
      alert("Error: " + e);
    }
  };

  // Test Route
  const handleTestRoute = async (role: string) => {
    try {
      const res = await fetch(`/api/models/routing/rules/${role}/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "Quick diagnostic probe." })
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Route Tested Successfully!\n\nResolved Model: ${data.selectedModel}\nLatency: ${data.latencyMs}ms\nSuccess: ${data.success}`);
        fetchAllData();
      } else {
        alert("Error testing route.");
      }
    } catch (e) {
      alert("Failed to connect to backend test endpoint.");
    }
  };

  // Run Simulation
  const handleRunSimulation = async () => {
    setSimulating(true);
    try {
      const res = await fetch("/api/models/routing/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: simRole, prompt: simPrompt })
      });
      if (res.ok) {
        const data = await res.json();
        setSimResult(data);
      } else {
        setSimResult({ error: "Failed to run simulation." });
      }
    } catch (e) {
      setSimResult({ error: "Connection lost to the simulation engine." });
    } finally {
      setSimulating(false);
    }
  };

  // Open Edit Modal with Pre-filled values
  const openEditModal = (rule: RoutingRuleItem) => {
    setEditingRule(rule);
    setFormRole(rule.id);
    setFormName(rule.name);
    setFormDesc(rule.description);
    setFormPrimary(rule.primaryModel);
    setFormFallback(rule.secondaryModel === "None" ? "" : rule.secondaryModel);
    setFormFinalFallback(rule.finalFallbackModel === "None" ? "" : rule.finalFallbackModel);
    setShowEditModal(true);
  };

  // Filter logic
  const filteredRoutes = rules.filter((r) => {
    if (activeFilterTab === "active" && r.status !== "Active") return false;
    if (activeFilterTab === "fallback" && r.status !== "Fallback") return false;
    if (activeFilterTab === "weighted" && r.status !== "Weighted") return false;
    if (activeFilterTab === "disabled" && r.status !== "Disabled") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        r.name.toLowerCase().includes(q) ||
        r.id.toLowerCase().includes(q) ||
        r.primaryModel.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedRoute = rules.find((r) => r.id === selectedRouteId) || rules[0];

  // Colors for donut chart
  const donutColors = ["#00f2fe", "#ff007f", "#10b981", "#fbbf24", "#3b82f6", "#a855f7"];

  return (
    <main className="models-view" style={{ overflow: "hidden", display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header controls row */}
      <div className="models-header-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 24px" }}>
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text" style={{ fontSize: "1.4rem", fontWeight: 700, margin: 0 }}>Model Router Console</h1>
          <p className="dashboard-subtitle-text" style={{ fontSize: "0.78rem", color: "#94a3b8", margin: 0 }}>
            Manage AI Router rules & monitor agent traffic in real time.
          </p>
        </div>
        {apiError && (
          <div style={{ background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5", padding: "6px 12px", borderRadius: "6px", border: "1px solid rgba(239, 68, 68, 0.2)", fontSize: "0.8rem" }}>
            {apiError}
          </div>
        )}
        <div className="models-header-right" style={{ display: "flex", gap: "8px" }}>
          <button className="chat-send-btn" style={{ height: "36px", padding: "0 16px", display: "flex", alignItems: "center", gap: "6px", background: "linear-gradient(135deg, #ff007f, #b91c1c)", border: "none", color: "#fff", cursor: "pointer", borderRadius: "20px", fontWeight: "bold" }} onClick={() => setIsGameOpen(true)}>
            🎮 Play Scuba Ostrich
          </button>
          <button className="chat-send-btn" style={{ height: "36px", padding: "0 16px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }} onClick={() => { resetForm(); setShowCreateModal(true); }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            New Rule
          </button>
        </div>
      </div>

      {/* Metric Cards Row */}
      <div className="metrics-row-grid" style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "12px", padding: "12px 24px" }}>
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Total Routes</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.totalRoutes}</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Active Rules</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.activeRules}</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,15 15,12 30,10 45,8 60,4 68,2" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Fallback Chains</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.fallbackChains}</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,18 15,14 30,16 45,10 60,12 68,8" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Avg Latency</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.avgLatency}</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,22 15,20 30,18 45,12 60,8 68,10" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Success Rate</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.successRate}</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,4 15,3 30,3 45,2 60,2 68,2" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <span>Traffic Balance</span>
            </div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{stats.trafficBalance}</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,15 15,16 30,14 45,18 60,10 68,12" />
            </svg>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="router-console-layout" style={{ display: "flex", flex: 1, overflow: "hidden", padding: "0 24px 24px 24px", gap: "16px" }}>
        
        {/* Left Side: Rules List & Donut Chart */}
        <div className="router-col" style={{ flex: 1.3, display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
          
          {/* Rules List Panel */}
          <div className="dashboard-panel" style={{ flex: 1, display: "flex", flexDirection: "column" }}>
            <header className="panel-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="panel-title">Active Routing Rules</span>
              <div style={{ display: "flex", gap: "6px" }}>
                {["all", "active", "fallback", "disabled"].map(tab => (
                  <button
                    key={tab}
                    className={`tab-btn ${activeFilterTab === tab ? "active" : ""}`}
                    onClick={() => setActiveFilterTab(tab)}
                    style={{ textTransform: "capitalize" }}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </header>
            <div className="panel-body" style={{ flex: 1, overflowY: "auto" }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Primary Model</th>
                    <th>Fallback</th>
                    <th>Status</th>
                    <th style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRoutes.map((rule) => (
                    <tr
                      key={rule.id}
                      className={selectedRouteId === rule.id ? "selected-row" : ""}
                      onClick={() => setSelectedRouteId(rule.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          <span style={{ fontWeight: 600 }}>{rule.name}</span>
                          <span style={{ fontSize: "0.75rem", color: "#64748b" }}>({rule.id})</span>
                        </div>
                      </td>
                      <td>
                        <code style={{ background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: "4px", fontSize: "0.8rem" }}>
                          {rule.primaryModel}
                        </code>
                      </td>
                      <td>
                        <code style={{ background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: "4px", fontSize: "0.8rem" }}>
                          {rule.secondaryModel}
                        </code>
                      </td>
                      <td>
                        <span className={`agent-status-badge ${rule.status === "Active" ? "running" : rule.status === "Disabled" ? "offline" : "idle"}`}>
                          ● {rule.status}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }} onClick={(e) => e.stopPropagation()}>
                        <button className="role-btn" style={{ marginRight: "4px", padding: "2px 8px" }} onClick={() => handleTestRoute(rule.id)}>Test</button>
                        <button className="role-btn" style={{ marginRight: "4px", padding: "2px 8px" }} onClick={() => openEditModal(rule)}>Edit</button>
                        <button className="role-btn" style={{ padding: "2px 8px", color: "#fca5a5" }} onClick={() => handleDeleteRule(rule.id)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                  {filteredRoutes.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", color: "#64748b", padding: "20px" }}>No rules found matching criteria.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Traffic Distribution Panel */}
          <div className="dashboard-panel" style={{ height: "180px", display: "flex", flexDirection: "column" }}>
            <header className="panel-header">
              <span className="panel-title">Model Traffic Distribution (24h)</span>
            </header>
            <div className="panel-body" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "space-around", padding: "12px" }}>
              <div className="donut-chart-container" style={{ width: "80px", height: "80px", position: "relative" }}>
                <svg width="80" height="80" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="15.915" fill="none" stroke="#1e293b" strokeWidth="3" />
                  {(() => {
                    let accumulated = 0;
                    return trafficDistribution.map((item, idx) => {
                      const strokeDasharray = `${item.percentage} ${100 - item.percentage}`;
                      const strokeDashoffset = 100 - accumulated + 25;
                      accumulated += item.percentage;
                      return (
                        <circle
                          key={idx}
                          cx="18"
                          cy="18"
                          r="15.915"
                          fill="none"
                          stroke={donutColors[idx % donutColors.length]}
                          strokeWidth="3.2"
                          strokeDasharray={strokeDasharray}
                          strokeDashoffset={strokeDashoffset}
                        />
                      );
                    });
                  })()}
                </svg>
              </div>
              <div className="traffic-legend-container" style={{ flex: 1, marginLeft: "24px", overflowY: "auto", maxHeight: "120px" }}>
                {trafficDistribution.map((item, idx) => (
                  <div key={idx} className="traffic-legend-row-item" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "4px" }}>
                    <div className="traffic-legend-left" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span className="traffic-legend-dot" style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", backgroundColor: donutColors[idx % donutColors.length] }}></span>
                      <span style={{ color: "#cbd5e1" }}>{item.name}</span>
                    </div>
                    <span className="traffic-legend-right" style={{ fontWeight: "bold", color: "#fff" }}>{item.percentage}% ({item.count || 0})</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

        </div>

        {/* Center/Right: Route Map & Simulation */}
        <div className="router-col" style={{ flex: 1.2, display: "flex", flexDirection: "column", gap: "16px", minWidth: 0 }}>
          
          {/* Active Connections Map */}
          <div className="dashboard-panel" style={{ flex: 1.2, display: "flex", flexDirection: "column", minHeight: "250px" }}>
            <header className="panel-header">
              <span className="panel-title">Active Connections Map</span>
            </header>
            <div className="panel-body" style={{ flex: 1, position: "relative" }}>
              <div className="routing-graph-container" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", height: "100%", padding: "10px 20px" }}>
                <div className="graph-role-nodes-col" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {graphData.roles && graphData.roles.map((role, idx) => (
                    <div key={idx} className="graph-node-box">
                      <span style={{ color: "#3b82f6", marginRight: "4px" }}>●</span> {role}
                    </div>
                  ))}
                </div>
                <div className="graph-center-hub-col">
                  <div className="graph-node-box hub" style={{ border: "2px solid #00f2fe" }}>Router Core</div>
                </div>
                <div className="graph-model-nodes-col" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  {graphData.models && graphData.models.map((model, idx) => (
                    <div key={idx} className="graph-node-box model" style={{ borderColor: "#64748b" }}>
                      {model}
                    </div>
                  ))}
                </div>
                <svg className="graph-connector-svg" style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 1, pointerEvents: "none" }}>
                  {graphData.links && graphData.links.map((link, idx) => {
                    const roleIdx = graphData.roles.indexOf(link.source);
                    const modelIdx = graphData.models.indexOf(link.target);
                    if (roleIdx === -1 || modelIdx === -1) return null;

                    const leftY = 26 + roleIdx * 28;
                    const rightY = 24 + modelIdx * 26;
                    const coreLeftY = 78 + (roleIdx % 6) * 4;
                    const coreRightY = 78 + (modelIdx % 7) * 4;
                    const color = link.type === "primary" ? "#10b981" : link.type === "fallback" ? "#f59e0b" : "#ef4444";

                    return (
                      <g key={idx}>
                        <path d={`M 90,${leftY} C 130,${leftY} 130,${coreLeftY} 156,${coreLeftY}`} stroke={color} strokeWidth="1.2" fill="none" opacity="0.65" />
                        <path d={`M 266,${coreRightY} C 300,${coreRightY} 300,${rightY} 322,${rightY}`} stroke={color} strokeWidth="1.2" fill="none" opacity="0.65" />
                      </g>
                    );
                  })}
                </svg>
              </div>
            </div>
          </div>

          {/* Route Simulator Panel */}
          <div className="dashboard-panel" style={{ flex: 0.8, display: "flex", flexDirection: "column" }}>
            <header className="panel-header">
              <span className="panel-title">Route Simulator</span>
            </header>
            <div className="panel-body" style={{ flex: 1, padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <div style={{ display: "flex", gap: "8px" }}>
                <select
                  value={simRole}
                  onChange={(e) => setSimRole(e.target.value)}
                  style={{ background: "#1e293b", color: "#fff", border: "1px solid var(--border-color)", borderRadius: "6px", padding: "8px", fontSize: "0.85rem" }}
                >
                  <option value="Planner">Planner</option>
                  <option value="Coder">Coder</option>
                  <option value="Researcher">Researcher</option>
                  <option value="Memory Agent">Memory Agent</option>
                  <option value="GUI Agent">GUI Agent</option>
                </select>
                <input
                  type="text"
                  value={simPrompt}
                  onChange={(e) => setSimPrompt(e.target.value)}
                  placeholder="Enter test prompt..."
                  style={{ flex: 1, background: "#1e293b", color: "#fff", border: "1px solid var(--border-color)", borderRadius: "6px", padding: "8px 12px", fontSize: "0.85rem" }}
                />
                <button
                  className="chat-send-btn"
                  onClick={handleRunSimulation}
                  disabled={simulating}
                  style={{ padding: "8px 18px", fontSize: "0.85rem", height: "38px" }}
                >
                  {simulating ? "Simulating..." : "Simulate"}
                </button>
              </div>

              {simResult && (
                <div style={{ flex: 1, background: "rgba(0,0,0,0.25)", padding: "12px", borderRadius: "8px", border: "1px solid var(--border-color)", fontSize: "0.8rem", overflowY: "auto" }}>
                  {simResult.error ? (
                    <div style={{ color: "var(--color-danger)" }}>{simResult.error}</div>
                  ) : (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                        <span style={{ fontWeight: "bold", color: "var(--color-primary)" }}>Selected Model: {simResult.selectedModel}</span>
                        <span style={{ color: "var(--text-dim)" }}>Confidence: {simResult.confidence}</span>
                      </div>
                      <div style={{ marginBottom: "6px" }}><span style={{ color: "var(--text-dim)" }}>Decision rationale:</span> {simResult.decision}</div>
                      <div style={{ display: "flex", gap: "15px", color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "8px" }}>
                        <span>Cost: ${simResult.estimatedCost}</span>
                        <span>Est. Time: {simResult.etaSeconds}s</span>
                      </div>
                      <div className="sim-flowchart-row" style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                        {simResult.flowSteps && simResult.flowSteps.map((step: string, index: number) => (
                          <span key={index} className={`sim-step-node-item ${index === simResult.flowSteps.length - 1 ? 'selected' : ''}`} style={{ fontSize: "0.72rem" }}>
                            {step}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Right Sidebar: Selected Route Detail */}
        {selectedRoute && (
          <aside className="agent-details-pane" style={{ width: "320px", display: "flex", flexDirection: "column", flexShrink: 0 }}>
            <div className="agent-details-card" style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: "16px" }}>
              <header className="agent-details-header" style={{ paddingBottom: "12px", borderBottom: "1px solid var(--border-color)" }}>
                <h3 className="agent-details-title" style={{ fontSize: "1.1rem", fontWeight: "700" }}>{selectedRoute.name}</h3>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  <span>ID: {selectedRoute.routeId}</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "8px" }}>
                  {selectedRoute.tags.map((tag, idx) => (
                    <span key={idx} className="mem-type-badge working" style={{ fontSize: "0.7rem", padding: "1px 6px" }}>{tag}</span>
                  ))}
                </div>
              </header>

              <div className="details-section-box">
                <span className="details-section-title" style={{ fontWeight: 600, fontSize: "0.8rem" }}>Description</span>
                <p className="details-section-desc" style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: "4px" }}>
                  {selectedRoute.description}
                </p>
              </div>

              <div className="details-section-box">
                <span className="details-section-title" style={{ fontWeight: 600, fontSize: "0.8rem" }}>Routing Performance (24h)</span>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginTop: "6px" }}>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
                      <span>Primary Usage</span>
                      <span style={{ fontWeight: "600" }}>{selectedRoute.primaryUsage}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: "4px", background: "rgba(255,255,255,0.05)", borderRadius: "2px" }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.primaryUsage}%`, height: "100%", background: "var(--color-primary)" }}></div>
                    </div>
                  </div>

                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
                      <span>Fallback Usage</span>
                      <span style={{ fontWeight: "600" }}>{selectedRoute.fallbackUsage}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: "4px", background: "rgba(255,255,255,0.05)", borderRadius: "2px" }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.fallbackUsage}%`, height: "100%", background: "var(--color-warning)" }}></div>
                    </div>
                  </div>

                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem" }}>
                      <span>Success Rate</span>
                      <span style={{ fontWeight: "600" }}>{selectedRoute.successRate}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: "4px", background: "rgba(255,255,255,0.05)", borderRadius: "2px" }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedRoute.successRate}%`, height: "100%", background: "var(--color-success)" }}></div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title" style={{ fontWeight: 600, fontSize: "0.8rem" }}>Escalation Chain</span>
                <div className="assigned-routes-list" style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "6px" }}>
                  <div className="assigned-route-row" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", padding: "4px 8px", background: "rgba(255,255,255,0.02)", borderRadius: "4px" }}>
                    <span>Primary</span>
                    <strong style={{ color: "#fff" }}>{selectedRoute.primaryModel}</strong>
                  </div>
                  <div className="assigned-route-row" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", padding: "4px 8px", background: "rgba(255,255,255,0.02)", borderRadius: "4px" }}>
                    <span>Fallback</span>
                    <strong style={{ color: "#fff" }}>{selectedRoute.secondaryModel}</strong>
                  </div>
                  <div className="assigned-route-row" style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", padding: "4px 8px", background: "rgba(255,255,255,0.02)", borderRadius: "4px" }}>
                    <span>Final</span>
                    <strong style={{ color: "#fff" }}>{selectedRoute.finalFallbackModel}</strong>
                  </div>
                </div>
              </div>

              <div className="details-section-box">
                <span className="details-section-title" style={{ fontWeight: 600, fontSize: "0.8rem" }}>Recent Activity Logs</span>
                <div className="recent-actions-list" style={{ marginTop: "6px", display: "flex", flexDirection: "column", gap: "6px" }}>
                  {selectedRoute.activity.map((act, idx) => (
                    <div key={idx} className="action-row" style={{ display: "flex", gap: "6px", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                      <span style={{ color: "var(--color-primary)" }}>•</span>
                      <span>{act}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>

      {/* CREATE RULE MODAL */}
      {showCreateModal && (
        <div className="modal-backdrop" style={{ position: "fixed", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: "rgba(0,0,0,0.6)", zIndex: 1000, display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
          <div className="panel-modal" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)", borderRadius: "12px", padding: "24px", width: "400px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <h3 style={{ margin: 0, color: "#fff" }}>Create New Rule</h3>
            <form onSubmit={handleSaveRule} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Role / Trigger Name *</label>
                <input type="text" value={formRole} onChange={(e) => setFormRole(e.target.value)} required placeholder="e.g. CodeReviewer" style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Rule Display Name *</label>
                <input type="text" value={formName} onChange={(e) => setFormName(e.target.value)} required placeholder="e.g. Code Review Router" style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Description</label>
                <textarea value={formDesc} onChange={(e) => setFormDesc(e.target.value)} placeholder="Enter details..." style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff", resize: "none", height: "60px" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Primary Model *</label>
                <select value={formPrimary} onChange={(e) => setFormPrimary(e.target.value)} required style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- Choose Model --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Secondary Fallback</label>
                <select value={formFallback} onChange={(e) => setFormFallback(e.target.value)} style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- None --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Tertiary Final Fallback</label>
                <select value={formFinalFallback} onChange={(e) => setFormFinalFallback(e.target.value)} style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- None --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
                <button type="button" className="role-btn" onClick={() => { setShowCreateModal(false); resetForm(); }}>Cancel</button>
                <button type="submit" className="chat-send-btn">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* EDIT RULE MODAL */}
      {showEditModal && (
        <div className="modal-backdrop" style={{ position: "fixed", top: 0, left: 0, width: "100%", height: "100%", backgroundColor: "rgba(0,0,0,0.6)", zIndex: 1000, display: "flex", alignItems: "center", justifyItems: "center", justifyContent: "center" }}>
          <div className="panel-modal" style={{ background: "var(--bg-panel)", border: "1px solid var(--border-color)", borderRadius: "12px", padding: "24px", width: "400px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <h3 style={{ margin: 0, color: "#fff" }}>Edit Rule</h3>
            <form onSubmit={handleSaveRule} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Role / Trigger Name (ReadOnly)</label>
                <input type="text" value={formRole} disabled style={{ width: "100%", padding: "8px", background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#888" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Rule Display Name *</label>
                <input type="text" value={formName} onChange={(e) => setFormName(e.target.value)} required style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Description</label>
                <textarea value={formDesc} onChange={(e) => setFormDesc(e.target.value)} style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff", resize: "none", height: "60px" }} />
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Primary Model *</label>
                <select value={formPrimary} onChange={(e) => setFormPrimary(e.target.value)} required style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- Choose Model --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Secondary Fallback</label>
                <select value={formFallback} onChange={(e) => setFormFallback(e.target.value)} style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- None --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label style={{ fontSize: "0.75rem", color: "var(--text-dim)", display: "block", marginBottom: "4px" }}>Tertiary Final Fallback</label>
                <select value={formFinalFallback} onChange={(e) => setFormFinalFallback(e.target.value)} style={{ width: "100%", padding: "8px", background: "var(--bg-darker)", border: "1px solid var(--border-color)", borderRadius: "6px", color: "#fff" }}>
                  <option value="">-- None --</option>
                  {availableModels.map(m => (
                    <option key={m.id} value={m.id}>{m.provider} - {m.name}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
                <button type="button" className="role-btn" onClick={() => { setShowEditModal(false); resetForm(); }}>Cancel</button>
                <button type="submit" className="chat-send-btn">Save Changes</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* GAME MODAL (EASTER EGG) */}
      {isGameOpen && (
        <ScubaOstrichGame onClose={() => setIsGameOpen(false)} />
      )}
    </main>
  );
}

/* ========================================================
   SCUBA OSTRICH GAME COMPONENT (Pure HTML/CSS/JS in React)
   ======================================================== */
interface GameProps {
  onClose: () => void;
}

function ScubaOstrichGame({ onClose }: GameProps) {
  const arenaRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [score, setScore] = useState(0);
  const [shrimps, setShrimps] = useState(0);
  const [highScore, setHighScore] = useState(0);
  const [totalShrimpsOwned, setTotalShrimpsOwned] = useState(0);
  const [activeSkin, setActiveSkin] = useState("classic");
  const [ownedSkinsList, setOwnedSkinsList] = useState<string[]>(["classic"]);
  
  const [isGameOver, setIsGameOver] = useState(false);
  const [gameOverReason, setGameOverReason] = useState("");

  const gameStateRef = useRef({
    y: 150,
    velocity: 0,
    gravity: 950,
    lift: -1300,
    oxygen: 100,
    health: 3,
    invulnerableTimer: 0,
    shieldTimer: 0,
    entities: [] as any[],
    particles: [] as any[],
    spawnTimer: 0,
    lastTime: 0,
    keys: {} as Record<string, boolean>
  });

  const availableSkins = [
    { id: 'classic', name: 'Classic Pink', color: '#ff7b91', cost: 0 },
    { id: 'neon', name: 'Neon Diver', color: '#00f2fe', cost: 10 },
    { id: 'pirate', name: 'Pirate Ostrich', color: '#eab308', cost: 25 },
    { id: 'cosmic', name: 'Cosmic Voyager', color: '#a855f7', cost: 50 }
  ];

  // Initialize and load saved values
  useEffect(() => {
    const savedBest = parseInt(localStorage.getItem('best_distance') || '0');
    const savedShrimps = parseInt(localStorage.getItem('total_shrimps') || '0');
    const savedSkin = localStorage.getItem('selected_skin') || 'classic';
    const savedOwned = JSON.parse(localStorage.getItem('owned_skins') || '["classic"]');

    setHighScore(savedBest);
    setTotalShrimpsOwned(savedShrimps);
    setActiveSkin(savedSkin);
    setOwnedSkinsList(savedOwned);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === "Space" || e.code === "ArrowUp") {
        gameStateRef.current.keys['swim'] = true;
        e.preventDefault();
      }
    };
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space" || e.code === "ArrowUp") {
        gameStateRef.current.keys['swim'] = false;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, []);

  const handleSelectSkin = (skin: typeof availableSkins[0]) => {
    const isOwned = ownedSkinsList.includes(skin.id);
    if (!isOwned) {
      if (totalShrimpsOwned >= skin.cost) {
        const newTotal = totalShrimpsOwned - skin.cost;
        const newOwned = [...ownedSkinsList, skin.id];
        localStorage.setItem('total_shrimps', newTotal.toString());
        localStorage.setItem('owned_skins', JSON.stringify(newOwned));
        localStorage.setItem('selected_skin', skin.id);
        
        setTotalShrimpsOwned(newTotal);
        setOwnedSkinsList(newOwned);
        setActiveSkin(skin.id);
        sound.playShield();
      } else {
        alert("Not enough Shrimps!");
      }
    } else {
      localStorage.setItem('selected_skin', skin.id);
      setActiveSkin(skin.id);
      sound.playBubble();
    }
  };

  const handleStartDive = () => {
    setIsPlaying(true);
    setIsPaused(false);
    setIsGameOver(false);
    
    // Clear dom
    if (arenaRef.current) {
      arenaRef.current.innerHTML = '';
    }

    gameStateRef.current = {
      y: 200,
      velocity: 0,
      gravity: 950,
      lift: -1300,
      oxygen: 100,
      health: 3,
      invulnerableTimer: 0,
      shieldTimer: 0,
      entities: [],
      particles: [],
      spawnTimer: 0,
      lastTime: performance.now(),
      keys: {}
    };

    // Spawn player element
    const playerEl = document.createElement("div");
    playerEl.id = "player";
    playerEl.style.position = "absolute";
    playerEl.style.width = "90px";
    playerEl.style.height = "90px";
    playerEl.style.transformOrigin = "center center";
    playerEl.style.zIndex = "5";
    playerEl.style.transition = "transform 0.05s linear";
    
    const skin = availableSkins.find(s => s.id === activeSkin) || availableSkins[0];
    let suitColor = skin.color;
    let helmetColor = "rgba(0, 242, 254, 0.4)";
    let extraDecor = "";

    if (skin.id === 'neon') {
      helmetColor = "rgba(255, 0, 127, 0.5)";
    } else if (skin.id === 'pirate') {
      extraDecor = `<path d="M 30 20 L 60 20 L 45 10 Z" fill="black" /> <circle cx="43" cy="27" r="4" fill="black"/>`;
    } else if (skin.id === 'cosmic') {
      helmetColor = "rgba(236, 72, 153, 0.6)";
    }

    playerEl.innerHTML = `
      <svg viewBox="0 0 100 100" width="90" height="90">
        <rect x="15" y="45" width="22" height="40" rx="6" fill="#e2e8f0" stroke="#475569" stroke-width="2"/>
        <rect x="22" y="38" width="8" height="8" fill="#cbd5e1"/>
        <path d="M 20 60 L 32 60 M 20 72 L 32 72" stroke="#94a3b8" stroke-width="2"/>
        <path d="M 26 38 C 30 20, 50 20, 56 34" fill="none" stroke="#1e293b" stroke-width="3" stroke-linecap="round"/>
        <line x1="38" y1="75" x2="30" y2="92" stroke="#f472b6" stroke-width="5" stroke-linecap="round"/>
        <path d="M 22 92 L 32 92 L 28 97 Z" fill="#eab308" />
        <circle cx="48" cy="62" r="20" fill="${suitColor}"/>
        <circle cx="48" cy="62" r="16" fill="#f472b6" opacity="0.3"/>
        <path d="M 58 62 Q 72 50, 68 32" fill="none" stroke="#f472b6" stroke-width="8" stroke-linecap="round"/>
        <g class="ostrich-flipper">
          <line x1="48" y1="75" x2="42" y2="92" stroke="#f472b6" stroke-width="5" stroke-linecap="round"/>
          <path d="M 32 92 L 44 92 L 38 97 Z" fill="#eab308" />
        </g>
        <circle cx="68" cy="28" r="11" fill="#f472b6"/>
        <circle cx="70" cy="26" r="3.5" fill="white"/>
        <circle cx="71" cy="26" r="1.5" fill="black"/>
        <rect x="63" y="20" width="13" height="11" rx="4" fill="${helmetColor}" stroke="#0f172a" stroke-width="1.5"/>
        <path d="M 72 20 L 78 26 L 72 26 Z" fill="rgba(255,255,255,0.6)" />
        <path d="M 77 28 L 88 31 L 76 34 Z" fill="#fbbf24"/>
        ${extraDecor}
      </svg>
      <div class="ostrich-bubble-stream"></div>
      <div class="shield-bubble" id="player-shield" style="display: none;"></div>
    `;

    arenaRef.current?.appendChild(playerEl);
    sound.playBubble();
    requestAnimationFrame(updateGame);
  };

  const triggerExplosion = (x: number, y: number, color: string) => {
    for (let i = 0; i < 15; i++) {
      const p = document.createElement("div");
      p.className = "particle";
      p.style.position = "absolute";
      p.style.backgroundColor = color;
      p.style.borderRadius = "50%";
      p.style.pointerEvents = "none";
      const size = 4 + Math.random() * 6;
      p.style.width = `${size}px`;
      p.style.height = `${size}px`;
      p.style.left = `${x}px`;
      p.style.top = `${y}px`;
      arenaRef.current?.appendChild(p);

      const angle = Math.random() * Math.PI * 2;
      const speed = 50 + Math.random() * 150;

      gameStateRef.current.particles.push({
        x, y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 1.0,
        decay: 0.02 + Math.random() * 0.03,
        element: p
      });
    }
  };

  const checkCollision = (rect1: any, rect2: any) => {
    return (
      rect1.x < rect2.x + rect2.width &&
      rect1.x + rect1.width > rect2.x &&
      rect1.y < rect2.y + rect2.height &&
      rect1.y + rect1.height > rect2.y
    );
  };

  const updateGame = (time: number) => {
    const state = gameStateRef.current;
    if (isGameOver || isPaused || !isPlaying) return;

    const dt = (time - state.lastTime) / 1000;
    state.lastTime = time;

    // Apply physics
    if (state.keys['swim']) {
      state.velocity += state.lift * dt;
      sound.playSwim();
    } else {
      state.velocity += state.gravity * dt;
    }

    state.velocity *= 0.98;
    state.y += state.velocity * dt;

    const heightLimit = (arenaRef.current?.clientHeight || 450) - 90;
    if (state.y < 0) {
      state.y = 0;
      state.velocity = 0;
    } else if (state.y > heightLimit) {
      state.y = heightLimit;
      state.velocity = 0;
    }

    // Render player
    const playerEl = document.getElementById("player");
    if (playerEl) {
      playerEl.style.transform = `translate3d(100px, ${state.y}px, 0) rotate(${state.velocity * 0.05}deg)`;
    }

    // Update oxygen
    state.oxygen -= dt * 5.0;
    if (state.oxygen <= 0) {
      state.oxygen = 0;
      handleGameOver("Drowned! Out of Oxygen.");
      return;
    }
    const oxBar = document.getElementById("oxygen-bar");
    if (oxBar) oxBar.style.width = `${state.oxygen}%`;

    // Timers
    if (state.invulnerableTimer > 0) {
      state.invulnerableTimer -= dt;
      if (state.invulnerableTimer <= 0) {
        playerEl?.classList.remove("invulnerable");
      }
    }

    const shieldEl = document.getElementById("player-shield");
    if (state.shieldTimer > 0) {
      state.shieldTimer -= dt;
      if (shieldEl) shieldEl.style.display = "block";
      if (state.shieldTimer <= 0) {
        if (shieldEl) shieldEl.style.display = "none";
      }
    }

    // Background parallax movement
    const xOffset = -(time * 0.05);
    const bgBack = document.getElementById("bg-back");
    const bgMid = document.getElementById("bg-mid");
    const bgFront = document.getElementById("bg-front");
    if (bgBack) bgBack.style.transform = `translate3d(${xOffset % 800}px, 0, 0)`;
    if (bgMid) bgMid.style.transform = `translate3d(${(xOffset * 1.8) % 600}px, 0, 0)`;
    if (bgFront) bgFront.style.transform = `translate3d(${(xOffset * 3) % 400}px, 0, 0)`;

    // Spawn entities
    state.spawnTimer += dt;
    if (state.spawnTimer > 1.8) {
      state.spawnTimer = 0;
      const rand = Math.random();
      const height = arenaRef.current?.clientHeight || 450;
      const spawnY = Math.random() * (height - 120) + 40;
      
      let newEntity: any = {
        x: (arenaRef.current?.clientWidth || 800) + 100,
        y: spawnY,
      };

      if (rand < 0.25) {
        newEntity.type = 'bubble';
        newEntity.width = 30;
        newEntity.height = 30;
        newEntity.speed = 180 + Math.random() * 80;
      } else if (rand < 0.45) {
        newEntity.type = 'fish';
        newEntity.width = 35;
        newEntity.height = 25;
        newEntity.speed = 220 + Math.random() * 80;
      } else if (rand < 0.50) {
        newEntity.type = 'shield';
        newEntity.width = 40;
        newEntity.height = 40;
        newEntity.speed = 200;
      } else if (rand < 0.70) {
        newEntity.type = 'jellyfish';
        newEntity.width = 60;
        newEntity.height = 70;
        newEntity.speed = 130 + Math.random() * 50;
        newEntity.amplitude = 40 + Math.random() * 40;
        newEntity.frequency = 2 + Math.random() * 3;
        newEntity.baseY = spawnY;
      } else if (rand < 0.85) {
        newEntity.type = 'mine';
        newEntity.width = 50;
        newEntity.height = 50;
        newEntity.speed = 160 + Math.random() * 40;
      } else {
        newEntity.type = 'shark';
        newEntity.width = 105;
        newEntity.height = 55;
        newEntity.speed = 320 + Math.random() * 100;
      }

      const el = document.createElement("div");
      el.className = `entity ${newEntity.type}`;
      el.style.position = "absolute";
      el.style.width = `${newEntity.width}px`;
      el.style.height = `${newEntity.height}px`;

      if (newEntity.type === 'jellyfish') {
        el.innerHTML = `
          <svg viewBox="0 0 60 70" width="100%" height="100%">
            <path d="M 5 35 C 5 10, 55 10, 55 35 C 55 40, 5 40, 5 35" fill="rgba(255, 100, 200, 0.7)" stroke="#ff64c8" stroke-width="1.5"/>
            <path d="M 12 35 Q 15 55, 10 70 M 22 35 Q 20 60, 24 70 M 32 35 Q 35 55, 30 70 M 42 35 Q 40 60, 45 70" stroke="rgba(255, 100, 200, 0.5)" stroke-width="2" fill="none"/>
            <circle cx="20" cy="25" r="3" fill="white" opacity="0.6"/>
            <circle cx="35" cy="23" r="2" fill="white" opacity="0.6"/>
          </svg>
        `;
      } else if (newEntity.type === 'shark') {
        el.innerHTML = `
          <svg viewBox="0 0 100 50" width="100%" height="100%">
            <path d="M 90 25 C 75 10, 45 12, 10 20 C 5 22, 5 28, 10 30 C 45 38, 75 40, 90 25 Z" fill="#64748b"/>
            <path d="M 80 23 L 70 20 L 78 26 Z" fill="#475569"/>
            <path d="M 45 15 Q 35 0, 30 5 Q 35 15, 45 18 Z" fill="#475569"/>
            <circle cx="80" cy="22" r="2" fill="red"/>
            <path d="M 75 32 L 72 29 L 69 32 L 66 29 L 63 32" stroke="white" stroke-width="1.5" fill="none"/>
          </svg>
        `;
      } else if (newEntity.type === 'mine') {
        el.innerHTML = `
          <svg viewBox="0 0 50 50" width="100%" height="100%">
            <circle cx="25" cy="25" r="18" fill="#334155" stroke="#1e293b" stroke-width="2"/>
            <path d="M 25 2 L 25 48 M 2 25 L 48 25 M 8 8 L 42 42 M 8 42 L 42 8" stroke="#1e293b" stroke-width="4" stroke-linecap="round"/>
            <circle cx="25" cy="25" r="5" fill="red" />
          </svg>
        `;
      } else if (newEntity.type === 'fish') {
        el.innerHTML = `
          <svg viewBox="0 0 35 25" width="100%" height="100%">
            <path d="M 5 12 C 10 5, 25 5, 30 12 C 25 20, 10 20, 5 12 Z" fill="#ff7f50"/>
            <path d="M 5 12 L 0 7 L 0 17 Z" fill="#ff6347"/>
            <circle cx="25" cy="10" r="1.5" fill="white"/>
            <circle cx="25" cy="10" r="0.5" fill="black"/>
          </svg>
        `;
      } else if (newEntity.type === 'bubble') {
        el.className = "entity bubble-collectible";
      } else if (newEntity.type === 'shield') {
        el.className = "entity shield-collectible";
      }

      newEntity.element = el;
      arenaRef.current?.appendChild(el);
      state.entities.push(newEntity);
    }

    // Process entities
    for (let i = state.entities.length - 1; i >= 0; i--) {
      const entity = state.entities[i];
      entity.x -= entity.speed * dt;

      if (entity.type === 'jellyfish') {
        entity.y = entity.baseY + Math.sin(time * 0.003 * entity.frequency) * entity.amplitude;
      }

      entity.element.style.transform = `translate3d(${entity.x}px, ${entity.y}px, 0)`;

      // AABB Box
      const playerBox = { x: 100 + 15, y: state.y + 15, width: 60, height: 60 };
      const entityBox = { x: entity.x, y: entity.y, width: entity.width, height: entity.height };

      if (checkCollision(playerBox, entityBox)) {
        if (entity.type === 'bubble') {
          state.oxygen = Math.min(100, state.oxygen + 25);
          sound.playBubble();
          triggerExplosion(entity.x + entity.width/2, entity.y + entity.height/2, "#00c6ff");
          arenaRef.current?.removeChild(entity.element);
          state.entities.splice(i, 1);
        } else if (entity.type === 'fish') {
          setShrimps(prev => prev + 1);
          sound.playFish();
          triggerExplosion(entity.x + entity.width/2, entity.y + entity.height/2, "#ffd700");
          arenaRef.current?.removeChild(entity.element);
          state.entities.splice(i, 1);
        } else if (entity.type === 'shield') {
          state.shieldTimer = 8.0;
          sound.playShield();
          triggerExplosion(entity.x + entity.width/2, entity.y + entity.height/2, "#ff007f");
          arenaRef.current?.removeChild(entity.element);
          state.entities.splice(i, 1);
        } else {
          // Obstacle hit
          if (state.shieldTimer > 0) {
            state.shieldTimer = 0;
            if (shieldEl) shieldEl.style.display = "none";
            sound.playShield();
            triggerExplosion(entity.x + entity.width/2, entity.y + entity.height/2, "white");
            arenaRef.current?.removeChild(entity.element);
            state.entities.splice(i, 1);
          } else if (state.invulnerableTimer <= 0) {
            state.health -= 1;
            sound.playHit();
            triggerExplosion(130, state.y + 45, "red");
            const hpBar = document.getElementById("health-bar");
            if (hpBar) hpBar.style.width = `${(state.health / 3) * 100}%`;

            if (state.health <= 0) {
              handleGameOver(`Defeated by a wild ${entity.type}!`);
              return;
            } else {
              state.invulnerableTimer = 1.5;
              playerEl?.classList.add("invulnerable");
              if (entity.type === 'mine') {
                arenaRef.current?.removeChild(entity.element);
                state.entities.splice(i, 1);
              }
            }
          }
        }
        continue;
      }

      if (entity.x + entity.width < -100) {
        arenaRef.current?.removeChild(entity.element);
        state.entities.splice(i, 1);
      }
    }

    // Process particles
    for (let i = state.particles.length - 1; i >= 0; i--) {
      const p = state.particles[i];
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.life -= p.decay;
      p.element.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`;
      p.element.style.opacity = p.life.toString();

      if (p.life <= 0) {
        arenaRef.current?.removeChild(p.element);
        state.particles.splice(i, 1);
      }
    }

    setScore(prev => {
      const next = prev + dt * 12;
      return Math.floor(next);
    });

    requestAnimationFrame(updateGame);
  };

  const handleGameOver = (reason: string) => {
    setIsPlaying(false);
    setIsGameOver(true);
    setGameOverReason(reason);
    sound.playGameOver();

    // Persist scores
    const finalDist = Math.floor(score);
    const prevBest = parseInt(localStorage.getItem('best_distance') || '0');
    if (finalDist > prevBest) {
      localStorage.setItem('best_distance', finalDist.toString());
      setHighScore(finalDist);
    }

    const prevShrimps = parseInt(localStorage.getItem('total_shrimps') || '0');
    const newTotalShrimps = prevShrimps + shrimps;
    localStorage.setItem('total_shrimps', newTotalShrimps.toString());
    setTotalShrimpsOwned(newTotalShrimps);
  };

  const handlePause = () => {
    setIsPaused(true);
  };

  const handleResume = () => {
    setIsPaused(false);
    gameStateRef.current.lastTime = performance.now();
    requestAnimationFrame(updateGame);
  };

  const handleExit = () => {
    setIsPlaying(false);
    setIsPaused(false);
    setIsGameOver(false);
  };

  return (
    <div className="overlay-screen active" ref={containerRef} style={{ background: "linear-gradient(to bottom, #0a192f, #020c1b)" }}>
      <style>{`
        .ostrich-flipper {
          transform-origin: 38px 75px;
          animation: swim-kick 0.6s infinite ease-in-out alternate;
        }
        .ostrich-bubble-stream {
          position: absolute;
          top: 40px;
          left: -10px;
          width: 6px;
          height: 6px;
          background: rgba(255, 255, 255, 0.5);
          border-radius: 50%;
          animation: drift-away 0.8s infinite linear;
        }
        @keyframes swim-kick {
          0% { transform: rotate(-20deg); }
          100% { transform: rotate(40deg); }
        }
        @keyframes drift-away {
          0% { transform: translate(0, 0) scale(0.6); opacity: 0.8; }
          100% { transform: translate(-30px, -20px) scale(1.5); opacity: 0; }
        }
        .invulnerable {
          animation: flash 0.15s infinite alternate;
        }
        @keyframes flash {
          0% { opacity: 0.3; }
          100% { opacity: 0.9; }
        }
        .jellyfish {
          animation: jelly-pulse 1.2s infinite ease-in-out alternate;
        }
        @keyframes jelly-pulse {
          0% { transform: scaleY(1) translateY(0); }
          100% { transform: scaleY(0.85) translateY(-5px); }
        }
        .mine {
          animation: spin 6s infinite linear;
        }
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        .bubble-collectible {
          border-radius: 50%;
          background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.7) 0%, rgba(0,210,255,0.3) 50%, rgba(0,114,255,0.1) 100%);
          box-shadow: 0 0 10px rgba(0,198,255,0.3), inset -2px -2px 5px rgba(0,114,255,0.5);
          animation: float-wobble 2s infinite ease-in-out alternate;
        }
        .shield-collectible {
          border-radius: 50%;
          background: radial-gradient(circle at 30% 30%, rgba(255,255,255,0.8) 0%, rgba(255,0,127,0.3) 60%, rgba(255,0,127,0.1) 100%);
          box-shadow: 0 0 15px rgba(255, 0, 127, 0.4), inset -3px -3px 7px rgba(255,0,127,0.5);
          animation: float-wobble 2.5s infinite ease-in-out alternate;
        }
        @keyframes float-wobble {
          0% { transform: translate(0, 0) scale(1); }
          100% { transform: translate(3px, -8px) scale(1.05); }
        }
        .shield-bubble {
          position: absolute;
          top: -15px;
          left: -15px;
          width: 120px;
          height: 120px;
          border-radius: 50%;
          border: 2px solid #ff007f;
          background: rgba(255, 0, 127, 0.15);
          box-shadow: 0 0 20px rgba(255, 0, 127, 0.4), inset 0 0 15px rgba(255, 0, 127, 0.4);
          animation: pulse-shield 1.5s infinite ease-in-out alternate;
          pointer-events: none;
        }
        @keyframes pulse-shield {
          0% { transform: scale(0.95); opacity: 0.6; }
          100% { transform: scale(1.05); opacity: 0.9; }
        }
      `}</style>

      {/* Background decoration */}
      <div id="bg-sunrays" className="bg-layer" style={{ background: "linear-gradient(135deg, rgba(0, 242, 254, 0.07) 0%, rgba(2, 12, 27, 0) 70%)", width: "100%", height: "100%", mixBlendMode: "overlay" }} />
      <div id="bg-back" className="bg-layer" style={{ backgroundImage: "url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"800\" height=\"600\" viewBox=\"0 0 800 600\"><path d=\"M0 500 Q 200 450, 400 500 T 800 500 L 800 600 L 0 600 Z\" fill=\"%23061327\"/><path d=\"M0 520 Q 250 480, 500 520 T 800 520 L 800 600 L 0 600 Z\" fill=\"%23040c1a\"/></svg>')", backgroundSize: "800px 100%", opacity: 0.5 }} />
      <div id="bg-mid" className="bg-layer" style={{ backgroundImage: "url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"600\" height=\"600\" viewBox=\"0 0 600 600\"><path d=\"M0 540 Q 150 510, 300 540 T 600 540 L 600 600 L 0 600 Z\" fill=\"%230a1c35\"/><g fill=\"%230c2443\"><path d=\"M50 540 Q 60 480, 55 450 Q 50 420, 60 450 T 70 540 Z\"/><path d=\"M250 540 Q 240 470, 250 440 T 260 540 Z\"/><path d=\"M450 540 Q 470 490, 460 430 T 480 540 Z\"/></g></svg>')", backgroundSize: "600px 100%", opacity: 0.75 }} />
      <div id="bg-front" className="bg-layer" style={{ backgroundImage: "url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"400\" height=\"600\" viewBox=\"0 0 400 600\"><path d=\"M0 560 Q 100 540, 200 560 T 400 560 L 400 600 L 0 600 Z\" fill=\"%230f2b4f\"/><g fill=\"%23133663\"><path d=\"M120 560 Q 110 500, 115 450 T 130 560 Z\"/><path d=\"M300 560 Q 315 480, 305 430 T 320 560 Z\"/></g></svg>')", backgroundSize: "400px 100%" }} />

      {/* Main Menu overlay */}
      {!isPlaying && !isGameOver && (
        <div className="panel-modal" style={{ zIndex: 110, padding: "40px", maxWidth: "90%", width: "480px", textAlign: "center", position: "relative" }}>
          <h1 style={{ fontSize: "2.5rem", marginBottom: "5px", color: "var(--color-primary)", textShadow: "0 0 10px var(--color-primary-glow)", fontFamily: "'Fredoka', sans-serif" }}>SCUBA OSTRICH</h1>
          <p style={{ color: "#94a3b8", fontSize: "0.9rem", marginBottom: "20px" }}>Dodge sea hazards, collect bubbles for oxygen, gather shrimp to unlock skins!</p>
          
          <div className="skin-selector-container" style={{ margin: "20px 0" }}>
            <h3 style={{ fontSize: "1rem", marginBottom: "8px" }}>Choose Your Scuba Suit</h3>
            <div className="skin-list" style={{ display: "flex", gap: "12px", justifyContent: "center", overflowX: "auto", padding: "10px 0" }}>
              {availableSkins.map(skin => {
                const isOwned = ownedSkinsList.includes(skin.id);
                const isSelected = activeSkin === skin.id;
                return (
                  <div
                    key={skin.id}
                    className={`skin-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => handleSelectSkin(skin)}
                    style={{
                      background: isSelected ? "rgba(0, 242, 254, 0.08)" : "rgba(255, 255, 255, 0.03)",
                      border: isSelected ? "2px solid var(--color-primary)" : "2px solid transparent",
                      borderRadius: "12px",
                      padding: "10px",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      width: "90px",
                      flexShrink: 0
                    }}
                  >
                    <div className="skin-icon-wrapper" style={{ width: "50px", height: "50px", display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <svg width="45" height="45" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="35" fill={skin.color} opacity="0.8"/>
                        <circle cx="45" cy="40" r="8" fill="white"/>
                        <circle cx="45" cy="40" r="3" fill="black"/>
                        <path d="M 50 45 L 70 50 L 50 55 Z" fill="orange"/>
                        <rect x="35" y="45" width="20" height="15" rx="5" fill="#334155"/>
                      </svg>
                    </div>
                    <div className="skin-name" style={{ fontSize: "0.75rem", marginTop: "8px", fontWeight: 600, color: "#e2e8f0" }}>{skin.name}</div>
                    <div className="skin-cost" style={{ fontSize: "0.7rem", color: isOwned ? '#34d399' : '#ffd700', marginTop: "3px" }}>
                      {isSelected ? 'Active' : isOwned ? 'Owned' : `🦐 ${skin.cost}`}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="highscore-display" style={{ display: "flex", justifyContent: "center", gap: "20px", fontSize: "0.95rem", color: "#94a3b8", marginTop: "15px" }}>
            <span>🏆 Best Distance: <strong style={{ color: "#fff" }}>{highScore}m</strong></span>
            <span>🦐 Total Shrimps: <strong style={{ color: "#ffd700" }}>{totalShrimpsOwned}</strong></span>
          </div>

          <div style={{ marginTop: "20px" }}>
            <button className="chat-send-btn play-btn-glow" style={{ padding: "12px 30px", fontSize: "1.1rem", fontWeight: "bold", borderRadius: "30px", cursor: "pointer", border: "none" }} onClick={handleStartDive}>Start Dive</button>
            <button className="role-btn" style={{ padding: "12px 30px", fontSize: "1.1rem", borderRadius: "30px", border: "1px solid var(--border-color)", background: "transparent", color: "#fff", cursor: "pointer", marginLeft: "10px" }} onClick={onClose}>Exit Game</button>
          </div>
        </div>
      )}

      {/* Game Over Screen */}
      {isGameOver && (
        <div className="panel-modal" style={{ zIndex: 110, padding: "40px", maxWidth: "90%", width: "480px", textAlign: "center", position: "relative" }}>
          <h2 style={{ color: "var(--color-secondary)", fontSize: "2.2rem", marginBottom: "5px", textShadow: "0 0 10px rgba(255, 0, 127, 0.4)" }}>DIVE OVER</h2>
          <p style={{ color: "#cbd5e1", fontStyle: "italic", marginBottom: "20px" }}>{gameOverReason}</p>
          
          <div className="gameover-score-row" style={{ display: "flex", justifyContent: "space-around", margin: "20px 0", background: "rgba(255, 255, 255, 0.03)", padding: "15px", borderRadius: "12px", border: "1px solid rgba(255, 255, 255, 0.05)" }}>
            <div className="score-box" style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase" }}>Distance</span>
              <span className="score-val" style={{ fontFamily: "var(--font-mono)", fontSize: "2.2rem", fontWeight: "bold", color: "#fff" }}>{score}m</span>
            </div>
            <div className="score-box" style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.8rem", color: "#94a3b8", textTransform: "uppercase" }}>Shrimps Gathered</span>
              <span className="score-val" style={{ fontFamily: "var(--font-mono)", fontSize: "2.2rem", fontWeight: "bold", color: "#ffd700" }}>{shrimps}</span>
            </div>
          </div>

          <div>
            <button className="chat-send-btn" style={{ padding: "12px 30px", borderRadius: "30px", border: "none", color: "#fff", cursor: "pointer", fontWeight: "bold" }} onClick={handleStartDive}>Dive Again</button>
            <button className="role-btn" style={{ padding: "12px 30px", borderRadius: "30px", border: "1px solid var(--border-color)", background: "transparent", color: "#fff", cursor: "pointer", marginLeft: "10px" }} onClick={handleExit}>Main Menu</button>
          </div>
        </div>
      )}

      {/* Pause Menu */}
      {isPaused && (
        <div className="panel-modal" style={{ zIndex: 110, padding: "40px", maxWidth: "90%", width: "480px", textAlign: "center", position: "relative" }}>
          <h2 style={{ fontSize: "2rem", marginBottom: "20px" }}>Game Paused</h2>
          <div>
            <button className="chat-send-btn" style={{ padding: "12px 30px", borderRadius: "30px", border: "none", color: "#fff", cursor: "pointer", fontWeight: "bold" }} onClick={handleResume}>Resume</button>
            <button className="role-btn" style={{ padding: "12px 30px", borderRadius: "30px", border: "1px solid var(--border-color)", background: "transparent", color: "#fff", cursor: "pointer", marginLeft: "10px" }} onClick={handleExit}>Quit to Menu</button>
          </div>
        </div>
      )}

      {/* Gameplay HUD & Arena */}
      {isPlaying && !isGameOver && !isPaused && (
        <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", zIndex: 5 }}>
          {/* HUD */}
          <div id="hud" style={{ position: "absolute", top: "20px", left: "20px", right: "20px", display: "flex", justifyContent: "space-between", alignItems: "center", zIndex: 10, pointerEvents: "none" }}>
            <div className="hud-group" style={{ display: "flex", gap: "15px", alignItems: "center" }}>
              <div className="hud-panel" style={{ background: "rgba(10, 25, 47, 0.7)", backdropFilter: "blur(8px)", border: "1px solid rgba(0, 242, 254, 0.2)", borderRadius: "12px", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px", pointerEvents: "auto" }}>
                <span className="hud-label" style={{ fontSize: "0.8rem", textTransform: "uppercase", color: "#94a3b8", fontWeight: 700 }}>Score</span>
                <span className="hud-value" style={{ fontFamily: "var(--font-mono)", fontSize: "1.5rem", fontWeight: "bold", color: "#00f2fe" }}>{score}m</span>
              </div>
              <div className="hud-panel" style={{ background: "rgba(10, 25, 47, 0.7)", backdropFilter: "blur(8px)", border: "1px solid rgba(0, 242, 254, 0.2)", borderRadius: "12px", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px", pointerEvents: "auto" }}>
                <span className="hud-label" style={{ fontSize: "0.8rem", textTransform: "uppercase", color: "#94a3b8", fontWeight: 700 }}>Shrimps</span>
                <span className="hud-value" style={{ fontFamily: "var(--font-mono)", fontSize: "1.5rem", fontWeight: "bold", color: "#ffd700" }}>{shrimps}</span>
              </div>
            </div>
            <div className="hud-group" style={{ display: "flex", gap: "15px", alignItems: "center" }}>
              <div className="hud-panel" style={{ background: "rgba(10, 25, 47, 0.7)", backdropFilter: "blur(8px)", border: "1px solid rgba(0, 242, 254, 0.2)", borderRadius: "12px", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px", pointerEvents: "auto" }}>
                <span className="hud-label" style={{ fontSize: "0.8rem", textTransform: "uppercase", color: "#94a3b8", fontWeight: 700 }}>O₂</span>
                <div className="bar-container" style={{ width: "120px", height: "12px", background: "rgba(255, 255, 255, 0.1)", borderRadius: "6px", overflow: "hidden", border: "1px solid rgba(255, 255, 255, 0.15)" }}>
                  <div id="oxygen-bar" className="bar-fill" style={{ height: "100%", background: "linear-gradient(90deg, #00c6ff, #0072ff)", width: "100%" }}></div>
                </div>
              </div>
              <div className="hud-panel" style={{ background: "rgba(10, 25, 47, 0.7)", backdropFilter: "blur(8px)", border: "1px solid rgba(0, 242, 254, 0.2)", borderRadius: "12px", padding: "10px 16px", display: "flex", alignItems: "center", gap: "10px", pointerEvents: "auto" }}>
                <span className="hud-label" style={{ fontSize: "0.8rem", textTransform: "uppercase", color: "#94a3b8", fontWeight: 700 }}>HP</span>
                <div className="bar-container" style={{ width: "120px", height: "12px", background: "rgba(255, 255, 255, 0.1)", borderRadius: "6px", overflow: "hidden", border: "1px solid rgba(255, 255, 255, 0.15)" }}>
                  <div id="health-bar" className="bar-fill" style={{ height: "100%", background: "linear-gradient(90deg, #ff416c, #ff4b2b)", width: "100%" }}></div>
                </div>
              </div>
              <button className="role-btn" style={{ height: "36px", padding: "0 12px", pointerEvents: "auto" }} onClick={handlePause}>
                Pause
              </button>
            </div>
          </div>

          {/* Game Arena container */}
          <div ref={arenaRef} id="game-arena" style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%" }} />
        </div>
      )}
    </div>
  );
}
