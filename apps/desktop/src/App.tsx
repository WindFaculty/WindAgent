import { useState, useEffect, useRef, lazy, Suspense } from "react";
import {
  AppShell,
  TopBar,
  Sidebar,
  MainWorkspace,
  BackendStatus,
  NavigationGroup,
  DESKTOP_NAVIGATION_GROUPS,
  type MetricState,
} from "@windagent/studio-shell";
import { MultiAgentProvider } from "./state/multiAgentStore";
import { fetchHermesHealth, fetchHealth } from "./api/client";

function lazyNamed<T extends React.ComponentType<any>>(
  factory: () => Promise<any>,
  name: string
) {
  return lazy(() => factory().then((module) => ({ default: module[name] as T })));
}

const Dashboard = lazyNamed(() => import("./pages/Dashboard"), "Dashboard");
const Agents = lazyNamed(() => import("./pages/Agents"), "Agents");
const Models = lazyNamed(() => import("./pages/Models"), "Models");
const Endpoints = lazyNamed(() => import("./pages/Endpoints"), "Endpoints");
const Memory = lazyNamed(() => import("./pages/Memory"), "Memory");
const Workflows = lazyNamed(() => import("./pages/Workflows"), "Workflows");
const Browser = lazyNamed(() => import("./pages/Browser"), "Browser");
const Files = lazyNamed(() => import("./pages/Files"), "Files");
const Router = lazyNamed(() => import("./pages/Router"), "Router");
const Settings = lazyNamed(() => import("./pages/Settings"), "Settings");
const MultiAgentWorkspace = lazyNamed(() => import("./pages/MultiAgentWorkspace"), "MultiAgentWorkspace");
const AssetWorkspace = lazyNamed(() => import("./components/assets/AssetWorkspace"), "AssetWorkspace");
const ProductionWorkspacePage = lazyNamed(() => import("./pages/ProductionWorkspacePage"), "ProductionWorkspacePage");
const StudioPage = lazyNamed(() => import("./pages/StudioPage"), "StudioPage");
const CharactersPage = lazyNamed(() => import("./pages/CharactersPage"), "CharactersPage");
const EpisodesPage = lazyNamed(() => import("./pages/EpisodesPage"), "EpisodesPage");
const StoryBoardPage = lazyNamed(() => import("./pages/StoryBoardPage"), "StoryBoardPage");
const ProjectsPage = lazyNamed(() => import("./pages/ProjectsPage"), "ProjectsPage");
const ReviewsPage = lazyNamed(() => import("./pages/ReviewsPage"), "ReviewsPage");

const PageSkeleton: React.FC<{ tabId?: string }> = ({ tabId }) => (
  <div
    style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      height: "100%",
      minHeight: "400px",
      color: "var(--text-muted, #c2c6d6)",
      gap: "16px",
      fontFamily: "var(--font-sans, sans-serif)",
    }}
  >
    <div
      style={{
        width: "36px",
        height: "36px",
        border: "3px solid var(--bg-panel-light, #171f33)",
        borderTop: "3px solid var(--color-primary, #4d8eff)",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }}
    />
    <span style={{ fontSize: "14px", letterSpacing: "0.5px", opacity: 0.8 }}>
      {tabId ? `Loading ${tabId}...` : "Loading page..."}
    </span>
  </div>
);

function TabKeeper({
  id,
  activeTab,
  visitedTabs,
  children,
}: {
  id: string;
  activeTab: string;
  visitedTabs: Set<string>;
  children: React.ReactNode;
}) {
  if (!visitedTabs.has(id)) {
    return null;
  }
  const isActive = activeTab === id;
  return (
    <div
      style={{ display: isActive ? "contents" : "none" }}
      data-tab-id={id}
      data-active={isActive}
    >
      <Suspense fallback={<PageSkeleton tabId={id} />}>
        {children}
      </Suspense>
    </div>
  );
}

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

  const [visitedTabs, setVisitedTabs] = useState<Set<string>>(
    () => new Set([certificationEpisodeId ? "studio" : "dashboard"])
  );

  useEffect(() => {
    setVisitedTabs((prev) => {
      if (prev.has(activeTab)) return prev;
      const next = new Set(prev);
      next.add(activeTab);
      return next;
    });
  }, [activeTab]);

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
      if (hash === "#/dashboard" || hash === "#/" || hash === "") {
        setActiveTab("dashboard");
      } else if (hash.startsWith("#/studio")) {
        setActiveTab("studio");
      } else if (hash.startsWith("#/production/assets")) {
        setActiveTab("production-assets");
      } else if (hash.startsWith("#/production/video")) {
        setActiveTab("production-video");
      } else if (hash.startsWith("#/production")) {
        setActiveTab("production-script");
      } else if (hash.startsWith("#/system/workspace") || hash === "#/workspace") {
        setActiveTab("workspace");
      } else if (hash.startsWith("#/system/agents") || hash === "#/agents") {
        setActiveTab("agents");
      } else if (hash.startsWith("#/system/settings") || hash === "#/settings") {
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
    } else if (tabId === "dashboard") {
      window.location.hash = "#/dashboard";
    }
  };

  return (
    <AppShell
      header={
        <TopBar
          statusSlot={<BackendStatus backendOnline={backendOnline} hermesOnline={hermesOnline} />}
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
        <TabKeeper id="dashboard" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Dashboard
            metrics={metrics}
            setMetrics={setMetrics}
            setActiveTab={setActiveTab}
            refreshInterval={refreshInterval}
            setRefreshInterval={setRefreshInterval}
          />
        </TabKeeper>
        <TabKeeper id="agents" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Agents setActiveTab={setActiveTab} />
        </TabKeeper>
        <TabKeeper id="models-library" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Models setActiveTab={setActiveTab} />
        </TabKeeper>
        <TabKeeper id="models-endpoints" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Endpoints />
        </TabKeeper>
        <TabKeeper id="memory" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Memory setActiveTab={setActiveTab} />
        </TabKeeper>
        <TabKeeper id="workflows" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Workflows />
        </TabKeeper>
        <TabKeeper id="browser" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Browser />
        </TabKeeper>
        <TabKeeper id="files" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Files />
        </TabKeeper>
        <TabKeeper id="workspace" activeTab={activeTab} visitedTabs={visitedTabs}>
          <MultiAgentProvider conversationId={conversationId}>
            <MultiAgentWorkspace conversationId={conversationId} />
          </MultiAgentProvider>
        </TabKeeper>
        <TabKeeper id="router" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Router />
        </TabKeeper>
        <TabKeeper id="studio" activeTab={activeTab} visitedTabs={visitedTabs}>
          <StudioPage />
        </TabKeeper>
        <TabKeeper id="projects" activeTab={activeTab} visitedTabs={visitedTabs}>
          <ProjectsPage />
        </TabKeeper>
        <TabKeeper id="episodes" activeTab={activeTab} visitedTabs={visitedTabs}>
          <EpisodesPage />
        </TabKeeper>
        <TabKeeper id="storyboard" activeTab={activeTab} visitedTabs={visitedTabs}>
          <StoryBoardPage />
        </TabKeeper>
        <TabKeeper id="characters" activeTab={activeTab} visitedTabs={visitedTabs}>
          <CharactersPage />
        </TabKeeper>
        <TabKeeper id="reviews" activeTab={activeTab} visitedTabs={visitedTabs}>
          <ReviewsPage />
        </TabKeeper>
        <TabKeeper id="asset-library" activeTab={activeTab} visitedTabs={visitedTabs}>
          <AssetWorkspace />
        </TabKeeper>
        <TabKeeper id="production-script" activeTab={activeTab} visitedTabs={visitedTabs}>
          <ProductionWorkspacePage initialPage="script" />
        </TabKeeper>
        <TabKeeper id="production-assets" activeTab={activeTab} visitedTabs={visitedTabs}>
          <ProductionWorkspacePage initialPage="assets" />
        </TabKeeper>
        <TabKeeper id="production-video" activeTab={activeTab} visitedTabs={visitedTabs}>
          <ProductionWorkspacePage initialPage="video" />
        </TabKeeper>
        <TabKeeper id="settings" activeTab={activeTab} visitedTabs={visitedTabs}>
          <Settings />
        </TabKeeper>
      </MainWorkspace>
    </AppShell>
  );
}

