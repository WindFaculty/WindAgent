import React, { useState, useEffect } from "react";
import { Dashboard, type MetricState } from "./pages/Dashboard";
import { AgentWorkspace } from "./pages/AgentWorkspace";
import { Agents } from "./pages/Agents";
import { Models } from "./pages/Models";
import { Memory } from "./pages/Memory";
import { Workflows } from "./pages/Workflows";
import { Browser } from "./pages/Browser";
import { Files } from "./pages/Files";
import { Router } from "./pages/Router";

interface ChecklistState {
  repoDiscovered: "success" | "pending" | "running";
  scanningStructure: "success" | "pending" | "running";
  runningTests: "success" | "pending" | "running";
  summarizingResults: "success" | "pending" | "running";
  summarizingProgress: number;
}

interface CurrentTaskStep {
  name: string;
  status: "success" | "pending" | "running";
  duration: string;
}

export function App() {
  // Page routing
  const [activeTab, setActiveTab] = useState<string>("dashboard");
  const [refreshInterval, setRefreshInterval] = useState<string>("10s");

  // Synchronized system CPU/RAM/GPU metrics
  const [metrics, setMetrics] = useState<MetricState>({
    cpu: 18,
    ram: 61,
    ramGb: 9.7,
    gpu: 28,
    vram: 42,
    vramGb: 6.7,
    cpuHistory: [15, 18, 16, 21, 19, 18],
    ramHistory: [60, 61, 61, 61, 61, 61],
    gpuHistory: [25, 30, 26, 29, 27, 28],
    vramHistory: [42, 42, 42, 42, 42, 42],
  });

  // Workspace simulation flow variables
  const [simulationStatus, setSimulationStatus] = useState<
    "idle" | "running" | "paused" | "completed"
  >("running");
  const [simStep, setSimStep] = useState<number>(4);

  // Chat stream list
  const [chatMessages, setChatMessages] = useState<Array<{
    sender: "user" | "assistant";
    time: string;
    text: string;
    checklist?: ChecklistState;
  }>>([
    {
      sender: "user",
      time: "10:21 AM",
      text: "Please analyze this project and give me a summary of its structure, tests, and code quality.",
    },
    {
      sender: "assistant",
      time: "10:21 AM",
      text: "Analyzing repository...",
      checklist: {
        repoDiscovered: "success",
        scanningStructure: "success",
        runningTests: "success",
        summarizingResults: "running",
        summarizingProgress: 72,
      },
    },
  ]);

  // Current task panels sub-task list
  const [currentTaskSteps, setCurrentTaskSteps] = useState<CurrentTaskStep[]>([
    { name: "Clone / Open Repository", status: "success", duration: "00:01" },
    { name: "Scan Codebase", status: "success", duration: "00:03" },
    { name: "Run Tests", status: "success", duration: "00:08" },
    { name: "Analyze & Summarize", status: "running", duration: "--:--" },
    { name: "Generate Report", status: "pending", duration: "--:--" },
  ]);

  // Command-line logs
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "git clone https://github.com/example/awesome-app.git",
    "Cloning into 'awesome-app'...",
    "remote: Enumerating objects: 1247, done.",
    "remote: Counting objects: 100% (1247/1247), done.",
    "remote: Compressing objects: 100% (812/812), done.",
    "remote: Total 1247 (delta 523), reused 1123 (delta 435), pack-reused 0",
    "Receiving objects: 100% (1247/1247), 2.34 MiB | 3.21 MiB/s, done.",
    "Resolving deltas: 100% (523/523), done.",
    "",
    "cd awesome-app",
    "npm install",
    "added 612 packages, and audited 613 packages in 2s",
    "120 packages are looking for funding",
    "run `npm fund` for details",
    "found 0 vulnerabilities",
    "",
    "npm test",
    "awesome-app@1.0.0 test",
    "jest --coverage",
    "",
    "PASS  src/utils/date.test.ts",
    "PASS  src/services/api.test.ts",
  ]);

  // Browser url & tab
  const [browserUrl, setBrowserUrl] = useState<string>("http://localhost:3000");
  const [browserTab, setBrowserTab] = useState<string>("overview");
  const [chatInput, setChatInput] = useState<string>("");

  // Sync metrics changes on interval
  useEffect(() => {
    const interval = setInterval(() => {
      setMetrics((prev) => {
        const nextCpu = Math.max(10, Math.min(90, Math.round(prev.cpu + (Math.random() * 6 - 3))));
        const nextRam = Math.max(50, Math.min(85, Math.round(prev.ram + (Math.random() * 2 - 1))));
        const nextRamGb = parseFloat(((nextRam / 100) * 16).toFixed(1));
        const nextGpu = Math.max(15, Math.min(95, Math.round(prev.gpu + (Math.random() * 8 - 4))));
        const nextVram = Math.max(35, Math.min(75, Math.round(prev.vram + (Math.random() * 2 - 1))));
        const nextVramGb = parseFloat(((nextVram / 100) * 16).toFixed(1));

        const updateHistory = (history: number[], nextVal: number) => {
          return [...history.slice(1), nextVal];
        };

        return {
          cpu: nextCpu,
          ram: nextRam,
          ramGb: nextRamGb,
          gpu: nextGpu,
          vram: nextVram,
          vramGb: nextVramGb,
          cpuHistory: updateHistory(prev.cpuHistory, nextCpu),
          ramHistory: updateHistory(prev.ramHistory, nextRam),
          gpuHistory: updateHistory(prev.gpuHistory, nextGpu),
          vramHistory: updateHistory(prev.vramHistory, nextVram),
        };
      });
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  // Workspace simulation flow management
  useEffect(() => {
    if (simulationStatus !== "running") return;

    if (simStep === 4) {
      const interval = setInterval(() => {
        setChatMessages((prev) => {
          const updated = [...prev];
          const assistantMsg = updated[1];
          if (assistantMsg && assistantMsg.checklist) {
            const nextProgress = Math.min(100, assistantMsg.checklist.summarizingProgress + 2);
            assistantMsg.checklist.summarizingProgress = nextProgress;

            if (nextProgress === 100) {
              assistantMsg.checklist.summarizingResults = "success";
              setSimStep(5);
              clearInterval(interval);
            }
          }
          return updated;
        });
      }, 500);
      return () => clearInterval(interval);
    }

    if (simStep === 5) {
      setSimulationStatus("completed");
      setCurrentTaskSteps((prev) =>
        prev.map((step) => {
          if (step.name === "Analyze & Summarize") {
            return { ...step, status: "success", duration: "00:15" };
          }
          if (step.name === "Generate Report") {
            return { ...step, status: "success", duration: "00:02" };
          }
          return step;
        })
      );
      setChatMessages((prev) => [
        ...prev,
        {
          sender: "assistant",
          time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          text: `Analysis complete! 🚀\n\nI have successfully scanned the codebase and run tests. Here's a brief summary:\n\n1. **Structure**: Standard React + Vite structure in \`apps/desktop\`.\n2. **Tests**: All tests passed (PASS \`date.test.ts\`, \`api.test.ts\`).\n3. **Code Quality**: High adherence to local styling and hooks conventions. No major errors.`,
        },
      ]);
      setTerminalLines((prev) => [
        ...prev,
        "",
        "Done! Analysis results saved to artifacts/report.json",
        "Vite server running at http://localhost:3000",
      ]);
    }
  }, [simStep, simulationStatus]);

  // Setup dynamic analysis flow
  const startNewAnalysis = (userQuery: string) => {
    setSimulationStatus("running");
    setSimStep(1);
    setChatMessages([
      {
        sender: "user",
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: userQuery,
      },
      {
        sender: "assistant",
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: "Initiating analysis flow for your request...",
        checklist: {
          repoDiscovered: "running",
          scanningStructure: "pending",
          runningTests: "pending",
          summarizingResults: "pending",
          summarizingProgress: 0,
        },
      },
    ]);

    setCurrentTaskSteps([
      { name: "Clone / Open Repository", status: "running", duration: "--:--" },
      { name: "Scan Codebase", status: "pending", duration: "--:--" },
      { name: "Run Tests", status: "pending", duration: "--:--" },
      { name: "Analyze & Summarize", status: "pending", duration: "--:--" },
      { name: "Generate Report", status: "pending", duration: "--:--" },
    ]);

    setTerminalLines([
      `Initialising request: "${userQuery}"`,
      "Loading local workspaces...",
    ]);

    setTimeout(() => {
      setChatMessages((prev) => {
        const next = [...prev];
        if (next[1] && next[1].checklist) {
          next[1].checklist.repoDiscovered = "success";
          next[1].checklist.scanningStructure = "running";
        }
        return next;
      });
      setCurrentTaskSteps((prev) => {
        const next = [...prev];
        next[0] = { name: "Clone / Open Repository", status: "success", duration: "00:02" };
        next[1] = { name: "Scan Codebase", status: "running", duration: "--:--" };
        return next;
      });
      setTerminalLines((prev) => [
        ...prev,
        "Workspace matched: d:\\antigaravity_code\\WindAgent",
        "Loading project files configurations...",
        "Resolving codebase structure...",
      ]);
    }, 2000);

    setTimeout(() => {
      setChatMessages((prev) => {
        const next = [...prev];
        if (next[1] && next[1].checklist) {
          next[1].checklist.scanningStructure = "success";
          next[1].checklist.runningTests = "running";
        }
        return next;
      });
      setCurrentTaskSteps((prev) => {
        const next = [...prev];
        next[1] = { name: "Scan Codebase", status: "success", duration: "00:03" };
        next[2] = { name: "Run Tests", status: "running", duration: "--:--" };
        return next;
      });
      setTerminalLines((prev) => [
        ...prev,
        "Found vite.config.ts, package.json, src/",
        "Total files analyzed: 42 files inside apps/desktop",
        "Starting Vitest Runner...",
      ]);
    }, 4500);

    setTimeout(() => {
      setChatMessages((prev) => {
        const next = [...prev];
        if (next[1] && next[1].checklist) {
          next[1].checklist.runningTests = "success";
          next[1].checklist.summarizingResults = "running";
          next[1].checklist.summarizingProgress = 20;
        }
        return next;
      });
      setCurrentTaskSteps((prev) => {
        const next = [...prev];
        next[2] = { name: "Run Tests", status: "success", duration: "00:05" };
        next[3] = { name: "Analyze & Summarize", status: "running", duration: "--:--" };
        return next;
      });
      setTerminalLines((prev) => [
        ...prev,
        "PASS  src/state/sessionStore.test.ts (1.2s)",
        "PASS  src/components/ControlBar.test.ts (2.1s)",
        "PASS  src/components/WorkflowPanel.test.ts (0.8s)",
        "All test files passed. 3 test suites, 12 tests passed.",
      ]);
      setSimStep(4);
    }, 7500);
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    startNewAnalysis(chatInput);
    setChatInput("");
  };

  // Sparkline coordinates calculator
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
            <span className="badge-connected">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
              </svg>
              Connected
            </span>
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
            <span className="metric-label">{metrics.gpu}%</span>
            <svg className="metric-sparkline gpu">
              <polyline points={renderSparkline(metrics.gpuHistory, 100)} />
            </svg>
          </div>
          <div className="metric-item">
            <span>VRAM</span>
            <span className="metric-label">{metrics.vram}% {metrics.vramGb} / 16 GB</span>
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
            startNewAnalysis={startNewAnalysis}
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
        ) : activeTab === "workspace" ? (
          <AgentWorkspace
            chatMessages={chatMessages}
            currentTaskSteps={currentTaskSteps}
            terminalLines={terminalLines}
            setTerminalLines={setTerminalLines}
            browserUrl={browserUrl}
            setBrowserUrl={setBrowserUrl}
            browserTab={browserTab}
            setBrowserTab={setBrowserTab}
            chatInput={chatInput}
            setChatInput={setChatInput}
            handleSend={handleSend}
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

        {/* Far Right Sidebar: Metadata Panels (only shown on Workspace view) */}
        {activeTab === "workspace" && (
          <aside className="right-sidebar">
            {/* Agent State */}
            <div className="agent-state-box">
              <div className="agent-state-circle">
                <svg>
                  <circle className="state-ring-bg" cx="16" cy="16" r="13" />
                  {simulationStatus === "running" && (
                    <circle className="state-ring-fill" cx="16" cy="16" r="13" />
                  )}
                </svg>
              </div>
              <div className="agent-state-right">
                <span className="state-title">Agent State</span>
                <span className="state-desc" style={{ color: simulationStatus === "running" ? "#60a5fa" : "var(--color-success)" }}>
                  {simulationStatus === "running" ? "Working on current objective" : "Task fully completed"}
                </span>
              </div>
            </div>

            {/* Current Goal */}
            <div className="goal-box">
              <div className="section-label">Current Goal</div>
              <div className="goal-content">
                {simStep < 5
                  ? "Analyze the project repository to understand its structure, test coverage, and code quality."
                  : "Deliver repository review summaries and ensure continuous integration health status."}
              </div>
              <div className="chat-progress-container" style={{ marginTop: '4px' }}>
                <div className="chat-progress-header" style={{ fontSize: '0.72rem' }}>
                  <span>Progress</span>
                  <span>{simStep === 4 ? "72%" : simStep === 5 ? "100%" : "35%"}</span>
                </div>
                <div className="progress-bar-bg" style={{ height: '4px' }}>
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: simStep === 4 ? "72%" : simStep === 5 ? "100%" : "35%",
                      transition: 'width 0.5s ease'
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Tools in Use */}
            <div className="goal-box">
              <div className="section-label">
                Tools in Use
                <span style={{ fontSize: '0.72rem', background: '#1e293b', padding: '2px 6px', borderRadius: '4px' }}>
                  {simulationStatus === "running" ? "4 active" : "0 active"}
                </span>
              </div>
              <div className="tools-in-use-list">
                <div className="tool-in-use-item">
                  <div className="tool-in-use-left">
                    <span className={`tool-use-dot ${simulationStatus === "running" && simStep < 5 ? "active" : ""}`} />
                    <span className="tool-use-label">File System</span>
                  </div>
                  <span className={`tool-use-state ${simulationStatus === "running" && simStep < 5 ? "active" : "inactive"}`}>
                    {simulationStatus === "running" && simStep < 5 ? "Reading" : "Idle"}
                  </span>
                </div>
                <div className="tool-in-use-item">
                  <div className="tool-in-use-left">
                    <span className={`tool-use-dot ${simulationStatus === "running" && simStep < 4 ? "active" : ""}`} />
                    <span className="tool-use-label">Terminal</span>
                  </div>
                  <span className={`tool-use-state ${simulationStatus === "running" && simStep < 4 ? "active" : "inactive"}`}>
                    {simulationStatus === "running" && simStep < 4 ? "Running" : "Idle"}
                  </span>
                </div>
                <div className="tool-in-use-item">
                  <div className="tool-in-use-left">
                    <span className={`tool-use-dot ${simulationStatus === "completed" ? "active" : ""}`} />
                    <span className="tool-use-label">Browser</span>
                  </div>
                  <span className={`tool-use-state ${simulationStatus === "completed" ? "active" : "inactive"}`}>
                    {simulationStatus === "completed" ? "Inspecting" : "Idle"}
                  </span>
                </div>
                <div className="tool-in-use-item">
                  <div className="tool-in-use-left">
                    <span className={`tool-use-dot ${simulationStatus === "running" && simStep === 4 ? "active" : ""}`} />
                    <span className="tool-use-label">Code Analyzer</span>
                  </div>
                  <span className={`tool-use-state ${simulationStatus === "running" && simStep === 4 ? "active" : "inactive"}`}>
                    {simulationStatus === "running" && simStep === 4 ? "Processing" : "Idle"}
                  </span>
                </div>
              </div>
            </div>

            {/* Permissions */}
            <div className="goal-box">
              <div className="section-label">Permissions</div>
              <div className="permissions-summary-box">
                <span>No permissions blocked</span>
                <span className="perms-badge">All Allowed ›</span>
              </div>
            </div>

            {/* Memory Summary */}
            <div className="goal-box">
              <div className="section-label">
                Memory Summary
                <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>8,192 tokens ›</span>
              </div>
              <div className="memory-bars-container">
                <div className="memory-bar-item">
                  <div className="mem-bar-header">
                    <span>Working Memory</span>
                    <span>72%</span>
                  </div>
                  <div className="mem-bar-bg">
                    <div className="mem-bar-fill working" />
                  </div>
                </div>
                <div className="memory-bar-item">
                  <div className="mem-bar-header">
                    <span>Long-term Memory</span>
                    <span>24%</span>
                  </div>
                  <div className="mem-bar-bg">
                    <div className="mem-bar-fill longterm" />
                  </div>
                </div>
                <div className="memory-bar-item">
                  <div className="mem-bar-header">
                    <span>Context Window</span>
                    <span>68%</span>
                  </div>
                  <div className="mem-bar-bg">
                    <div className="mem-bar-fill context" />
                  </div>
                </div>
              </div>
            </div>

            {/* Recent Actions */}
            <div className="goal-box">
              <div className="section-label">Recent Actions</div>
              <div className="recent-actions-list">
                <div className="action-row active">
                  <span className="action-time">10:21</span>
                  <span className="action-dot active" />
                  <span className="action-text">Analyzing code quality</span>
                </div>
                <div className="action-row">
                  <span className="action-time">10:21</span>
                  <span className="action-dot" />
                  <span className="action-text">Running tests</span>
                </div>
                <div className="action-row">
                  <span className="action-time">10:21</span>
                  <span className="action-dot" />
                  <span className="action-text">Installed dependencies</span>
                </div>
                <div className="action-row">
                  <span className="action-time">10:21</span>
                  <span className="action-dot" />
                  <span className="action-text">Cloned repository</span>
                </div>
                <div className="action-row">
                  <span className="action-time">10:21</span>
                  <span className="action-dot" />
                  <span className="action-text">Started project analysis</span>
                </div>
              </div>
              <a href="#timeline" className="view-timeline-link" onClick={(e) => { e.preventDefault(); alert("Timeline details panel."); }}>
                View full timeline
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                </svg>
              </a>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}