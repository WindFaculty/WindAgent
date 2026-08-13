import { useState, useEffect, useRef } from "react";
import {
  AppShell,
  TopBar,
  Sidebar,
  MainWorkspace,
  BackendStatus,
  RuntimeMetrics,
  NavigationGroup,
  DESKTOP_NAVIGATION_GROUPS,
  type MetricState,
} from "@windagent/studio-shell";
import { Dashboard } from "./pages/Dashboard";
import { Agents } from "./pages/Agents";
import { Models } from "./pages/Models";
import { Memory } from "./pages/Memory";
import { Workflows } from "./pages/Workflows";
import { Browser } from "./pages/Browser";
import { Files } from "./pages/Files";
import { Router } from "./pages/Router";
import { Settings } from "./pages/Settings";
import { MultiAgentWorkspace } from "./pages/MultiAgentWorkspace";
import { MultiAgentProvider } from "./state/multiAgentStore";
import { fetchHermesHealth, fetchHealth } from "./api/client";
import { Endpoints } from "./pages/Endpoints";
import { AssetWorkspace } from "./components/assets/AssetWorkspace";
import { ProductionWorkspacePage } from "./pages/ProductionWorkspacePage";
import { StudioPage } from "./pages/StudioPage";

function useConversationId(): string {
  const [conversationId] = useState<string>(() => {
    const existing = sessionStorage.getItem("windagent.conversationId");
    if (existing) return existing;
    const fresh =
      typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
        ? crypto.randomUUID()
        : `conv-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem("windagent.conversationId", fresh);
    return fresh;
  });
  return conversationId;
}

export function App() {
  const certificationEpisodeId =
    (typeof import.meta !== "undefined" &&
      (import.meta as any).env?.VITE_STUDIO_CERTIFICATION_EPISODE_ID) ||
    "";
  const [activeTab, setActiveTab] = useState<string>(
    certificationEpisodeId ? "studio" : "dashboard",
  );
  const conversationId = useConversationId();
  const [refreshInterval, setRefreshInterval] = useState<string>("10s");

  // Synchronize top-level routing hash with activeTab
  useEffect(() => {
    if (certificationEpisodeId) {
      const route = `#/studio/episodes/${encodeURIComponent(certificationEpisodeId)}`;
      if (window.location.hash !== route) window.location.hash = route;
    }
  }, [certificationEpisodeId]);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.toLowerCase();
      if (hash.startsWith("#/studio")) {
        setActiveTab("studio");
      } else if (hash.startsWith("#/production/assets")) {
        setActiveTab("production-assets");
      } else if (hash.startsWith("#/production/video")) {
        setActiveTab("production-video");
      } else if (hash.startsWith("#/production")) {
        setActiveTab("production-script");
      } else if (hash.startsWith("#/system/workspace")) {
        setActiveTab("workspace");
      } else if (hash.startsWith("#/system/agents")) {
        setActiveTab("agents");
      } else if (hash.startsWith("#/system/settings")) {
        setActiveTab("settings");
      }
    };

    handleHashChange();
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  const [hermesOnline, setHermesOnline] = useState<boolean | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const backendHealth = await fetchHealth();
        setBackendOnline(backendHealth.status === "ok" || backendHealth.status === "healthy");
      } catch {
        setBackendOnline(false);
      }

      try {
        const hermesHealth = await fetchHermesHealth();
        setHermesOnline(hermesHealth.reachable);
      } catch {
        setHermesOnline(false);
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

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

  const isTauri = useRef<boolean>(
    typeof (window as any).__TAURI__ !== "undefined" ||
    typeof (window as any).__TAURI_INTERNALS__ !== "undefined" ||
    (window as any).navigator?.userAgent?.includes("Tauri")
  );

  useEffect(() => {
    const updateHistory = (history: number[], nextVal: number) => {
      return [...history.slice(1), nextVal];
    };

    const fetchMetrics = async () => {
      if (isTauri.current) {
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

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectTab = (tabId: string) => {
    setActiveTab(tabId);
    if (tabId === "studio" && !window.location.hash.startsWith("#/studio")) {
      window.location.hash = "#/studio";
    }
  };

  return (
    <AppShell
      header={
        <TopBar
          statusSlot={<BackendStatus backendOnline={backendOnline} hermesOnline={hermesOnline} />}
          metricsSlot={<RuntimeMetrics metrics={metrics} />}
        />
      }
    >
      <MainWorkspace
        sidebar={
          <Sidebar>
            {DESKTOP_NAVIGATION_GROUPS.map((group) => (
              <NavigationGroup
                key={group.id}
                group={group}
                activeTab={activeTab}
                onSelectTab={handleSelectTab}
              />
            ))}
          </Sidebar>
        }
      >
        {activeTab === "dashboard" && (
          <Dashboard
            metrics={metrics}
            setMetrics={setMetrics}
            setActiveTab={setActiveTab}
            refreshInterval={refreshInterval}
            setRefreshInterval={setRefreshInterval}
          />
        )}
        {activeTab === "agents" && <Agents setActiveTab={setActiveTab} />}
        {activeTab === "models-library" && <Models setActiveTab={setActiveTab} />}
        {activeTab === "models-endpoints" && <Endpoints />}
        {activeTab === "memory" && <Memory setActiveTab={setActiveTab} />}
        {activeTab === "workflows" && <Workflows />}
        {activeTab === "browser" && <Browser />}
        {activeTab === "files" && <Files />}
        {activeTab === "workspace" && (
          <MultiAgentProvider conversationId={conversationId}>
            <MultiAgentWorkspace conversationId={conversationId} />
          </MultiAgentProvider>
        )}
        {activeTab === "router" && <Router />}
        {activeTab === "studio" && <StudioPage />}
        {activeTab === "asset-library" && <AssetWorkspace />}
        {activeTab === "production-script" && <ProductionWorkspacePage initialPage="script" />}
        {activeTab === "production-assets" && <ProductionWorkspacePage initialPage="assets" />}
        {activeTab === "production-video" && <ProductionWorkspacePage initialPage="video" />}
        {activeTab === "settings" && <Settings />}
      </MainWorkspace>
    </AppShell>
  );
}
