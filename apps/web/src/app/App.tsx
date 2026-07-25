import React, { useState } from "react";
import { StateRecoveryEngine, AppStateSnapshot } from "../state/state_recovery";

const recoveryEngine = new StateRecoveryEngine();

export const App: React.FC = () => {
  const [snapshot, setSnapshot] = useState<AppStateSnapshot>(() => recoveryEngine.loadSnapshot());

  const handleTabChange = (tab: string) => {
    const updated = { ...snapshot, activeTab: tab, lastSyncTimestamp: Date.now() };
    setSnapshot(updated);
    recoveryEngine.saveSnapshot(updated);
  };

  return (
    <div style={{ fontFamily: "sans-serif", padding: "2rem", backgroundColor: "#0f172a", color: "#f8fafc", minHeight: "100vh" }}>
      <header style={{ borderBottom: "1px solid #334155", paddingBottom: "1rem", marginBottom: "1rem" }}>
        <h1>WindAgent V2 Architecture - Web Portal</h1>
        <p style={{ color: "#94a3b8" }}>Decoupled Web Frontend Package (<code>apps/web</code>)</p>
      </header>

      {snapshot.isWorkerDisconnected && (
        <div style={{ backgroundColor: "#ef4444", color: "#fff", padding: "0.75rem", borderRadius: "6px", marginBottom: "1rem" }}>
          ⚠️ Worker Disconnected! Attempting reconnect...
        </div>
      )}

      <nav style={{ display: "flex", gap: "1rem", marginBottom: "2rem" }}>
        {["overview", "tasks", "workflows", "providers", "evals"].map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              backgroundColor: snapshot.activeTab === tab ? "#3b82f6" : "#1e293b",
              color: "#fff",
            }}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </nav>

      <main style={{ backgroundColor: "#1e293b", padding: "1.5rem", borderRadius: "8px" }}>
        <h2>Current View: {snapshot.activeTab.toUpperCase()}</h2>
        <p>State Recovery: Active tab restored from snapshot ({new Date(snapshot.lastSyncTimestamp).toLocaleTimeString()}).</p>
      </main>
    </div>
  );
};
