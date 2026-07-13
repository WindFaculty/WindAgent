import { useState, useEffect, useRef } from "react";
import { Dashboard, type MetricState } from "./pages/Dashboard";
import { MultiAgentWorkspace } from "./pages/MultiAgentWorkspace";
import { MultiAgentProvider } from "./state/multiAgentStore";
import { Agents } from "./pages/Agents";
import { Models } from "./pages/Models";
import { Memory } from "./pages/Memory";
import { Workflows } from "./pages/Workflows";
import { Browser } from "./pages/Browser";
import { Files } from "./pages/Files";
import { Router } from "./pages/Router";
import { AgentWorkspace } from "./pages/AgentWorkspace";
import { Settings } from "./pages/Settings";
import { fetchHermesHealth, fetchHealth } from "./api/client";

export function App() {
  // Page routing
  const [activeTab, setActiveTab] = useState<string>("dashboard");
  const [refreshInterval, setRefreshInterval] = useState<string>("10s");
  const [conversationId] = useState<string>(() => {
    const key = "wa_conversation_id";
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;
    const id = (crypto as any).randomUUID();
    sessionStorage.setItem(key, id);
    return id;
  });

  const [hermesOnline, setHermesOnline] = useState<boolean | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [browserUrl, setBrowserUrl] = useState<string>("");
  const [browserTab, setBrowserTab] = useState<string>("url");

  // Poll health status of backend and Hermes
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const backendHealth = await fetchHealth();
        setBackendOnline(backendHealth.status === "ok" || backendHealth.status === "healthy");
      } catch (err) {
        setBackendOnline(false);
      }

      try {
        const hermesHealth = await fetchHermesHealth();
        setHermesOnline(hermesHealth.reachable);
      } catch (err) {
        setHermesOnline(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  // Synchronized system CPU/RAM/GPU metrics
  const [metrics, setMetrics] = useState<MetricState>({
    cpu: 18,
    ram: 61,
    ramGb: 9.7,
    ramTotalGb: 16,
    gpu: 28,
    gpuName: "NVIDIA GPU",
    vram: 42,
    vramGb: 6.7,
    vramTotalGb: 16,
    cpuHistory: [15, 18, 16, 21, 19, 18],
    ramHistory: [60, 61, 61, 61, 61, 61],
    gpuHistory: [25, 30, 26, 29, 27, 28],
    vramHistory: [42, 42, 42, 42, 42, 42],
  });

  // Whether we are running inside Tauri (true) or plain browser (false)
  const isTauri = useRef<boolean>(
    typeof (window as any).__TAURI__ !== "undefined" ||
    typeof (window as any).__TAURI_INTERNALS__ !== "undefined" ||
    (window as any).navigator?.userAgent?.includes("Tauri")
  );
  
  // Debug: log Tauri detection
  useEffect(() => {
    console.log('[App] Tauri detection:', {
      hasTauri: typeof (window as any).__TAURI__ !== "undefined",
      hasTauriInternals: typeof (window as any).__TAURI_INTERNALS__ !== "undefined",
      tauriObj: (window as any).__TAURI__,
      tauriInternals: (window as any).__TAURI_INTERNALS__,
      isTauriRef: isTauri.current,
      userAgent: navigator.userAgent,
      href: window.location.href
    });
  }, []);

  // Sync metrics changes on interval
  useEffect(() => {
    const updateHistory = (history: number[], nextVal: number) => {
      return [...history.slice(1), nextVal];
    };

    const fetchMetrics = async () => {
      if (isTauri.current) {
        // ── Real metrics from Tauri / Rust backend ────────────────────────
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          const m = await invoke<{
            cpu: number;
            ram: number;
            ram_gb: number;
            ram_total_gb: number;
            gpu: number;
            gpu_name: string;
            vram: number;
            vram_gb: number;
            vram_total_gb: number;
          }>("get_system_metrics");

          setMetrics((prev) => ({
            cpu: Math.round(m.cpu),
            ram: Math.round(m.ram),
            ramGb: m.ram_gb,
            ramTotalGb: m.ram_total_gb,
            gpu: Math.round(m.gpu),
            gpuName: m.gpu_name,
            vram: Math.round(m.vram),
            vramGb: m.vram_gb,
            vramTotalGb: m.vram_total_gb,
            cpuHistory: updateHistory(prev.cpuHistory, Math.round(m.cpu)),
            ramHistory: updateHistory(prev.ramHistory, Math.round(m.ram)),
            gpuHistory: updateHistory(prev.gpuHistory, Math.round(m.gpu)),
            vramHistory: updateHistory(prev.vramHistory, Math.round(m.vram)),
          }));
        } catch (err) {
          console.warn("[metrics] Tauri invoke failed:", err);
        }
      } else {
        // ── Fallback: random mock (plain browser / Vite dev) ──────────────
        setMetrics((prev) => {
          const nextCpu = Math.max(10, Math.min(90, Math.round(prev.cpu + (Math.random() * 6 - 3))));
          const nextRam = Math.max(50, Math.min(85, Math.round(prev.ram + (Math.random() * 2 - 1))));
          const nextRamGb = parseFloat(((nextRam / 100) * 16).toFixed(1));
          const nextGpu = Math.max(15, Math.min(95, Math.round(prev.gpu + (Math.random() * 8 - 4))));
          const nextVram = Math.max(35, Math.min(75, Math.round(prev.vram + (Math.random() * 2 - 1))));
          const nextVramGb = parseFloat(((nextVram / 100) * 16).toFixed(1));

          return {
            cpu: nextCpu,
            ram: nextRam,
            ramGb: nextRamGb,
            ramTotalGb: prev.ramTotalGb,
            gpu: nextGpu,
            gpuName: prev.gpuName,
            vram: nextVram,
            vramGb: nextVramGb,
            vramTotalGb: prev.vramTotalGb,
            cpuHistory: updateHistory(prev.cpuHistory, nextCpu),
            ramHistory: updateHistory(prev.ramHistory, nextRam),
            gpuHistory: updateHistory(prev.gpuHistory, nextGpu),
            vramHistory: updateHistory(prev.vramHistory, nextVram),
          };
        });
      }
    };

    // Initial fetch immediately, then every 2 s
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, []);

  // Workspace streaming now handled inside AgentWorkspace via useAgentSession.

  const renderSparkline = (points: number[], maxVal: number) => {
    const width = 50;
    const height = 14;
    const len = points.length;
    const xStep = width / (len - 1);
    const coords = points.map((p, i) => {
      const x = i * xStep;
      const y = height - (p / maxVal) * height;
      return `${x},${y}`;
    });
    return coords.join(" ");
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="top-header">
        <div className="header-left">
          <div className="brand">
            <svg
              className="brand-icon"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2.5}
                d="M4.5 12a7.5 7.5 0 0015 0m-15 0a7.5 7.5 0 1115 0m-15 0H3m16.5 0H21m-1.5 0H12m-8.457 3.077l1.41-.513m14.095-5.128l1.41-.513M5.106 17.785l1.15-.827m11.488-8.226l1.15-.827M8.14 21.27l.707-1.03m10.15-6.83l.707-1.03"
              />
            </svg>
            WindAgent
          </div>
          <div className="status-badges">
            <span className="badge-localhost">Localhost</span>
            {backendOnline === false ? (
              <span className="badge-localhost" style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)', color: '#ef4444' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#ef4444', borderRadius: '50%', boxShadow: '0 0 8px #ef4444', marginRight: '6px' }} />
                Backend: Offline
              </span>
            ) : (
              <span className="badge-connected">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
                Connected
              </span>
            )}
            
            {hermesOnline === null ? (
              <span className="badge-local-first" style={{ opacity: 0.6 }}>
                Hermes: Checking...
              </span>
            ) : hermesOnline ? (
              <span className="badge-localhost" style={{ background: 'rgba(59, 130, 246, 0.08)', border: '1px solid rgba(59, 130, 246, 0.2)', color: '#3b82f6' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#3b82f6', borderRadius: '50%', boxShadow: '0 0 8px #3b82f6', marginRight: '6px' }} />
                Hermes: Connected
              </span>
            ) : (
              <span className="badge-localhost" style={{ background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.2)', color: '#ef4444' }}>
                <span style={{ display: 'inline-block', width: '6px', height: '6px', backgroundColor: '#ef4444', borderRadius: '50%', boxShadow: '0 0 8px #ef4444', marginRight: '6px' }} />
                Hermes: Offline
              </span>
            )}

            <span className="badge-local-first">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ marginRight: '2px' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Local First
            </span>
          </div>
        </div>

        <div className="header-metrics">
          <div className="metric-item">
            <span>CPU</span>
            <span className="metric-label">{metrics.cpu}%</span>
            <svg className="metric-sparkline">
              <polyline points={renderSparkline(metrics.cpuHistory, 100)} />
            </svg>
          </div>
          <div className="metric-item">
            <span>RAM</span>
            <span className="metric-label">{metrics.ram}% {metrics.ramGb} / 16 GB</span>
            <svg className="metric-sparkline ram">
              <polyline points={renderSparkline(metrics.ramHistory, 100)} />
            </svg>
          </div>
          <div className="metric-item">
            <span>GPU</span>
            <span className="metric-label" title={metrics.gpuName}>{metrics.gpu}%</span>
            <svg className="metric-sparkline gpu">
              <polyline points={renderSparkline(metrics.gpuHistory, 100)} />
            </svg>
          </div>
          <div className="metric-item">
            <span>VRAM</span>
            <span className="metric-label">{metrics.vram}% {metrics.vramGb} / {metrics.vramTotalGb} GB</span>
            <svg className="metric-sparkline vram">
              <polyline points={renderSparkline(metrics.vramHistory, 100)} />
            </svg>
          </div>
        </div>

        <div className="header-right">
          <div className="window-controls">
            <span className="win-btn close" />
            <span className="win-btn minimize" />
            <span className="win-btn maximize" />
          </div>
        </div>
      </header>

      {/* Main Workspace Frame */}
      <div className="workspace-wrapper">
        {/* Left Sidebar */}
        <aside className="left-sidebar">
          <div className="sidebar-nav">
            <div
              className={`nav-item ${activeTab === "dashboard" ? "active" : ""}`}
              onClick={() => setActiveTab("dashboard")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2H6a2 2 0 01-2-2v-4zM14 16a2 2 0 012-2h2a2 2 0 012 2v4a2 2 0 01-2 2h-2a2 2 0 01-2-2v-4z" />
              </svg>
              Dashboard
            </div>
            <div
              className={`nav-item ${activeTab === "agents" ? "active" : ""}`}
              onClick={() => setActiveTab("agents")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
              Agents
            </div>
            <div
              className={`nav-item ${activeTab === "workspace" ? "active" : ""}`}
              onClick={() => setActiveTab("workspace")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
              Agent Workspace
            </div>

            <div
              className={`nav-item ${activeTab === "workflows" ? "active" : ""}`}
              onClick={() => setActiveTab("workflows")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              Workflows
            </div>
            <div
              className={`nav-item ${activeTab === "browser" ? "active" : ""}`}
              onClick={() => setActiveTab("browser")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              Browser
            </div>
            <div
              className={`nav-item ${activeTab === "files" ? "active" : ""}`}
              onClick={() => setActiveTab("files")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              Files
            </div>
            <div
              className={`nav-item ${activeTab === "memory" ? "active" : ""}`}
              onClick={() => setActiveTab("memory")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              Memory
            </div>
            <div
              className={`nav-item ${activeTab === "models" ? "active" : ""}`}
              onClick={() => setActiveTab("models")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
              </svg>
              Models
            </div>
            <div
              className={`nav-item ${activeTab === "router" ? "active" : ""}`}
              onClick={() => setActiveTab("router")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A2 2 0 013 15.483V7.517a2 2 0 011.553-1.957L9 4m0 16v-8" />
              </svg>
              Router
            </div>
            <div
              className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => setActiveTab("settings")}
            >
              <svg className="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Settings
            </div>
          </div>

          <div className="sidebar-bottom">
            <div className="version-box">
              <div className="version-title">WindAgent v1.2.0</div>
              <div className="version-desc">Your local AI agent platform</div>
              <svg className="version-sparkline">
                <polyline points="0,20 20,12 40,22 60,8 80,18 100,10 120,24 140,6 160,20 180,12 200,18" />
              </svg>
            </div>

            <div className="user-profile">
              <div className="user-info">
                <div className="user-avatar">W</div>
                <div>
                  <div className="user-name">WindUser</div>
                  <div className="user-role">Administrator</div>
                </div>
              </div>
              <svg className="user-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </aside>

        {/* Dynamic page content router */}
        {activeTab === "dashboard" ? (
          <Dashboard
            metrics={metrics}
            setMetrics={setMetrics}
            setActiveTab={setActiveTab}
            refreshInterval={refreshInterval}
            setRefreshInterval={setRefreshInterval}
          />
        ) : activeTab === "agents" ? (
          <Agents
            setActiveTab={setActiveTab}
          />
        ) : activeTab === "models" ? (
          <Models
            setActiveTab={setActiveTab}
          />
        ) : activeTab === "memory" ? (
          <Memory
            setActiveTab={setActiveTab}
          />
        ) : activeTab === "workflows" ? (
          <Workflows />
        ) : activeTab === "browser" ? (
          <Browser />
        ) : activeTab === "files" ? (
          <Files />
        ) : activeTab === "router" ? (
          <Router />
        ) : activeTab === "settings" ? (
          <Settings />
        ) : activeTab === "workspace" ? (
                  <AgentWorkspace
                    selectedAgentId={selectedAgentId}
                    setSelectedAgentId={setSelectedAgentId}
                    browserUrl={browserUrl}
                    setBrowserUrl={setBrowserUrl}
                    browserTab={browserTab}
                    setBrowserTab={setBrowserTab}
                    hermesOnline={hermesOnline}
                    backendOnline={backendOnline}
                  />
                ) : (
                  /* Placeholder views for settings and other navigation tabs */
                  <main className="central-workspace" style={{ justifyContent: 'center', alignItems: 'center' }}>
                    <div className="dashboard-panel" style={{ width: '400px', padding: '24px', textAlign: 'center', gap: '16px' }}>
                      <div className="brand-icon" style={{ width: '48px', height: '48px', margin: '0 auto' }}>
                        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                      </div>
                      <h2 style={{ fontSize: '1.25rem' }}>{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Pane</h2>
                      <p style={{ color: 'var(--text-muted)' }}>
                        This is a visual preview node. Return to <strong>Dashboard</strong> to inspect the system health.
                      </p>
                      <button className="chat-send-btn" onClick={() => setActiveTab("dashboard")} style={{ margin: '0 auto' }}>
                        Back to Dashboard
                      </button>
                    </div>
                  </main>
                )}
              </div>
            </div>
          );
        }