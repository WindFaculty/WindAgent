import React, { useState, useEffect } from "react";
import {
  navigateBrowser,
  clickBrowser,
  controlBrowser,
  goBackBrowser,
  goForwardBrowser,
  reloadBrowser,
} from "../../../api/client";

interface Props {
  sessionId: string | null;
  browserState: {
    url: string;
    title: string;
    loading: boolean;
    screenshotUrl: string | null;
    controlledBy: "agent" | "user";
  };
  dispatch: React.Dispatch<any>;
}

export function AgentBrowserPanel({ sessionId, browserState, dispatch }: Props) {
  const [addressInput, setAddressInput] = useState<string>(browserState.url);

  // Sync addressInput with store state.browser.url
  useEffect(() => {
    setAddressInput(browserState.url);
  }, [browserState.url]);

  const handleNavigate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionId || !addressInput.trim()) return;
    await navigateBrowser(sessionId, addressInput);
  };

  const handleBack = async () => {
    if (!sessionId) return;
    await goBackBrowser(sessionId);
  };

  const handleForward = async () => {
    if (!sessionId) return;
    await goForwardBrowser(sessionId);
  };

  const handleReload = async () => {
    if (!sessionId) return;
    await reloadBrowser(sessionId);
  };

  const handleToggleControl = async () => {
    if (!sessionId) return;
    const newControl = browserState.controlledBy === "user" ? "agent" : "user";
    await controlBrowser(sessionId, newControl);
    dispatch({ type: "updateBrowserState", browser: { controlledBy: newControl } });
  };

  const handleScreenshotClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!sessionId || browserState.controlledBy !== "user") return;
    const rect = e.currentTarget.getBoundingClientRect();

    // Scale coordinates to 1280x800 viewport size
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 1280);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 800);

    await clickBrowser(sessionId, x, y);
  };

  return (
    <section className="dashboard-panel">
      <header className="panel-header">
        <div className="panel-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
          Browser / App Preview
        </div>
      </header>
      <div className="browser-header">
        <div className="browser-actions" style={{ gap: "2px" }}>
          <button className="browser-nav-btn" onClick={handleBack} disabled={!sessionId}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button className="browser-nav-btn" onClick={handleForward} disabled={!sessionId}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
            </svg>
          </button>
          <button className="browser-nav-btn" onClick={handleReload} disabled={!sessionId}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleNavigate} className="browser-address-bar" style={{ display: "flex", width: "100%" }}>
          <input
            type="text"
            value={addressInput}
            onChange={(e) => setAddressInput(e.target.value)}
            disabled={!sessionId}
            style={{
              background: "transparent",
              border: "none",
              outline: "none",
              color: "inherit",
              fontFamily: "inherit",
              fontSize: "inherit",
              width: "100%",
            }}
          />
          <button type="submit" disabled={!sessionId} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", display: "flex", alignItems: "center" }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
          </button>
        </form>

        <div className="browser-actions">
          <button
            className="browser-nav-btn"
            onClick={() => { if (browserState.url) window.open(browserState.url, "_blank"); }}
            title="Open Externally"
            disabled={!browserState.url || browserState.url === "about:blank"}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </button>
          <button
            className={`browser-nav-btn ${browserState.controlledBy === "user" ? "active-control" : ""}`}
            onClick={handleToggleControl}
            disabled={!sessionId}
            title={browserState.controlledBy === "user" ? "Controlled by You (Click to release)" : "Controlled by Agent (Click to take control)"}
            style={browserState.controlledBy === "user" ? { color: "#f59e0b", backgroundColor: "rgba(245, 158, 11, 0.15)" } : {}}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
            </svg>
            <span style={{ fontSize: "0.65rem", marginLeft: "4px", fontWeight: "600" }}>
              {browserState.controlledBy === "user" ? "USER" : "AGENT"}
            </span>
          </button>
        </div>
      </div>

      <div className="browser-viewport" style={{ position: "relative", overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center", height: "calc(100% - 40px)", background: "#0f172a" }}>
        {browserState.screenshotUrl ? (
          <img
            src={browserState.screenshotUrl.startsWith("/") ? `http://127.0.0.1:8765${browserState.screenshotUrl}` : browserState.screenshotUrl}
            alt="Browser Preview"
            style={{
              width: "100%",
              height: "100%",
              objectFit: "contain",
              cursor: browserState.controlledBy === "user" ? "crosshair" : "default",
            }}
            onClick={handleScreenshotClick}
          />
        ) : (
          <div className="empty-state" style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-muted)",
            gap: "8px",
          }}>
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ opacity: 0.4 }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9" />
            </svg>
            <p style={{ fontSize: "0.82rem" }}>No active browser session</p>
          </div>
        )}
        {browserState.loading && (
          <div style={{
            position: "absolute",
            top: "12px",
            right: "12px",
            backgroundColor: "rgba(15, 23, 42, 0.8)",
            padding: "6px 12px",
            borderRadius: "20px",
            border: "1px solid rgba(255,255,255,0.1)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "0.75rem",
            color: "var(--text-main)",
          }}>
            <div className="check-spinner" style={{ width: "12px", height: "12px" }} />
            Loading...
          </div>
        )}
      </div>
    </section>
  );
}
