import { useState } from "react";

export function Settings() {
  const [activeCategory, setActiveCategory] = useState("general");
  const [darkMode, setDarkMode] = useState(true);
  const [autoSave, setAutoSave] = useState(true);
  const [localFirstMode, setLocalFirstMode] = useState(true);
  const [enableTelemetry, setEnableTelemetry] = useState(false);
  const [smartSuggestions, setSmartSuggestions] = useState(true);
  const [retryFailedTasks, setRetryFailedTasks] = useState(true);
  const [safeMode, setSafeMode] = useState(false);
  const [allowBackground, setAllowBackground] = useState(true);
  const [workspaceName, setWorkspaceName] = useState("WindAgent Workspace");
  const [language, setLanguage] = useState("English");
  const [timezone, setTimezone] = useState("UTC+7");
  const [autoSaveInterval, setAutoSaveInterval] = useState("30 sec");
  const [theme, setTheme] = useState("Dark");
  const [accentColor, setAccentColor] = useState("Blue");
  const [maxParallelAgents, setMaxParallelAgents] = useState(5);
  const [approvalMode, setApprovalMode] = useState("On Critical Actions");
  const [timeout, setTimeout] = useState(120);

  const categories = [
    { id: "general", label: "General", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )},
    { id: "appearance", label: "Appearance", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
      </svg>
    )},
    { id: "agents", label: "Agents", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
      </svg>
    )},
    { id: "models", label: "Models", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
    )},
    { id: "routing", label: "Routing", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 20l-5.447-2.724A2 2 0 013 15.483V7.517a2 2 0 011.553-1.957L9 4m0 16v-8" />
      </svg>
    )},
    { id: "browser", label: "Browser", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
      </svg>
    )},
    { id: "files", label: "Files", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
      </svg>
    )},
    { id: "memory", label: "Memory", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
      </svg>
    )},
    { id: "notifications", label: "Notifications", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
    )},
    { id: "security", label: "Security", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    )},
    { id: "integrations", label: "Integrations", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z" />
      </svg>
    )},
    { id: "advanced", label: "Advanced", icon: (
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
      </svg>
    )},
  ];

  const integrations = [
    { name: "Ollama Local", status: "Connected", latency: "18ms", color: "#10b981" },
    { name: "OpenAI API", status: "Connected", latency: "142ms", color: "#10b981" },
    { name: "Anthropic API", status: "Connected", latency: "161ms", color: "#10b981" },
    { name: "GitHub", status: "Connected", latency: "92ms", color: "#10b981" },
    { name: "Local Cache", status: "Healthy", latency: "6ms", color: "#10b981" },
    { name: "Vector DB", status: "Connected", latency: "24ms", color: "#10b981" },
  ];

  const permissions = [
    { name: "File System", status: "Allowed", color: "#10b981" },
    { name: "Terminal", status: "Allowed", color: "#10b981" },
    { name: "Browser Automation", status: "Allowed", color: "#10b981" },
    { name: "Network Access", status: "Restricted", color: "#f59e0b" },
    { name: "Model Downloads", status: "Allowed", color: "#10b981" },
    { name: "Cloud Sync", status: "Allowed", color: "#10b981" },
  ];

  const recentActivity = [
    { time: "10:20 AM", text: "Updated Default Coder Model", user: "WindUser" },
    { time: "10:18 AM", text: "Changed Auto Save Interval", user: "WindUser" },
    { time: "10:16 AM", text: "Enabled Safe Mode", user: "WindUser" },
    { time: "10:12 AM", text: "Updated Permission: Network Access", user: "WindUser" },
    { time: "10:10 AM", text: "Created Backup", user: "System" },
  ];

  const notificationRules = [
    { name: "Email Notifications", count: 18, enabled: true, color: "#3b82f6" },
    { name: "Desktop Notifications", count: 18, enabled: true, color: "#a855f7" },
    { name: "Sound Alerts", count: 6, enabled: false, color: "#f59e0b" },
    { name: "Critical Alerts", count: 12, enabled: true, color: "#ef4444" },
  ];

  const Toggle = ({ value, onChange }: { value: boolean; onChange: () => void }) => (
    <button
      onClick={onChange}
      style={{
        width: '36px', height: '20px', borderRadius: '10px', border: 'none', cursor: 'pointer',
        background: value ? 'var(--color-primary)' : 'rgba(255,255,255,0.1)',
        position: 'relative', transition: 'background 0.2s', flexShrink: 0,
        boxShadow: value ? '0 0 8px rgba(59,130,246,0.4)' : 'none',
      }}
    >
      <span style={{
        position: 'absolute', top: '3px', width: '14px', height: '14px',
        borderRadius: '50%', background: '#fff',
        left: value ? '19px' : '3px', transition: 'left 0.2s',
      }} />
    </button>
  );

  return (
    <main className="models-view" style={{ overflow: 'hidden' }}>
      {/* Header */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Settings</h1>
          <p className="dashboard-subtitle-text">Configure application preferences, models, agents, permissions, and system behavior.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Settings saved!")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
            </svg>
            Save Changes
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Settings reset to defaults.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
            </svg>
            Reset
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Exporting config...")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Export Config
          </button>
          <button className="toggle-icon-btn">
            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Metric Cards Row */}
      <div className="metrics-row-grid">
        {[
          { label: "Active Profiles", value: "3", trend: "▲ 50%", trendUp: true, color: "blue", points: "0,20 15,18 30,22 45,12 60,6 68,14" },
          { label: "Connected Providers", value: "6", trend: "▲ 20%", trendUp: true, color: "purple", points: "0,22 15,18 30,12 45,20 60,10 68,4" },
          { label: "Enabled Automations", value: "12", trend: "▲ 33%", trendUp: true, color: "orange", points: "0,20 15,22 30,14 45,18 60,8 68,10" },
          { label: "Security Score", value: "94%", trend: "▲ 5%", trendUp: true, color: "green", points: "0,18 15,10 30,12 45,8 60,10 68,4" },
          { label: "Notifications Enabled", value: "18", trend: "▲ 12%", trendUp: true, color: "blue", points: "0,22 15,14 30,18 45,8 60,12 68,6" },
          { label: "Config Health", value: "98%", trend: "▲ 3%", trendUp: true, color: "purple", points: "0,20 15,18 30,22 45,12 60,6 68,14" },
        ].map((card, i) => (
          <div key={i} className="metric-card-box">
            <div className="m-card-header">
              <div className="m-card-header-left">
                <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: `var(--color-${card.color === 'blue' ? 'primary' : card.color === 'purple' ? 'accent' : card.color === 'orange' ? 'warning' : 'success'})` }}>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                </svg>
                <span>{card.label}</span>
              </div>
              <div className="trend-indicator up">{card.trend}</div>
            </div>
            <div className="m-card-body">
              <div className="m-card-value-container">
                <div className="m-card-value">{card.value}</div>
                <div className="m-card-subtext">vs yesterday</div>
              </div>
              <svg className={`m-card-sparkline-svg ${card.color}`} viewBox="0 0 68 24">
                <polyline points={card.points} />
              </svg>
            </div>
          </div>
        ))}
      </div>

      {/* Settings 3-column layout */}
      <div className="settings-console-layout">

        {/* Left Column: Categories + Quick Preferences */}
        <div className="settings-left-col">
          <div className="dashboard-panel" style={{ flex: 1 }}>
            <header className="panel-header">
              <span className="panel-title">Settings Categories</span>
            </header>
            <div className="panel-body" style={{ padding: '6px' }}>
              {categories.map((cat) => (
                <button
                  key={cat.id}
                  className={`settings-category-btn ${activeCategory === cat.id ? "active" : ""}`}
                  onClick={() => setActiveCategory(cat.id)}
                >
                  <span className="settings-cat-icon">{cat.icon}</span>
                  {cat.label}
                  {activeCategory === cat.id && (
                    <svg style={{ marginLeft: 'auto', width: '12px', height: '12px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="dashboard-panel" style={{ flex: 0, minHeight: 0 }}>
            <header className="panel-header">
              <span className="panel-title">Quick Preferences</span>
            </header>
            <div className="panel-body" style={{ padding: '10px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[
                { label: "Dark Mode", value: darkMode, onChange: () => setDarkMode(v => !v) },
                { label: "Auto Save", value: autoSave, onChange: () => setAutoSave(v => !v) },
                { label: "Local First Mode", value: localFirstMode, onChange: () => setLocalFirstMode(v => !v) },
                { label: "Enable Telemetry", value: enableTelemetry, onChange: () => setEnableTelemetry(v => !v) },
                { label: "Smart Suggestions", value: smartSuggestions, onChange: () => setSmartSuggestions(v => !v) },
              ].map((pref, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{pref.label}</span>
                  <Toggle value={pref.value} onChange={pref.onChange} />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Center Column: Main Configuration */}
        <div className="settings-center-col">

          {/* General Settings */}
          <div className="dashboard-panel">
            <header className="panel-header">
              <span className="panel-title">Configuration</span>
              <span style={{ fontSize: '0.72rem', color: 'var(--color-primary)', fontWeight: '600' }}>
                {categories.find(c => c.id === activeCategory)?.label || "General"} Settings
              </span>
            </header>
            <div className="panel-body" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

              {/* General Settings row */}
              <div>
                <span className="details-section-title" style={{ display: 'block', marginBottom: '10px' }}>General Settings</span>
                <div className="settings-form-grid">
                  <div className="settings-form-field">
                    <label>Workspace Name</label>
                    <input
                      type="text"
                      value={workspaceName}
                      onChange={e => setWorkspaceName(e.target.value)}
                      className="settings-input"
                    />
                  </div>
                  <div className="settings-form-field">
                    <label>Language</label>
                    <select value={language} onChange={e => setLanguage(e.target.value)} className="settings-select">
                      <option>English</option>
                      <option>Vietnamese</option>
                      <option>Japanese</option>
                    </select>
                  </div>
                  <div className="settings-form-field">
                    <label>Timezone</label>
                    <select value={timezone} onChange={e => setTimezone(e.target.value)} className="settings-select">
                      <option>UTC+7</option>
                      <option>UTC+0</option>
                      <option>UTC-5</option>
                    </select>
                  </div>
                  <div className="settings-form-field">
                    <label>Auto Save Interval</label>
                    <select value={autoSaveInterval} onChange={e => setAutoSaveInterval(e.target.value)} className="settings-select">
                      <option>10 sec</option>
                      <option>30 sec</option>
                      <option>1 min</option>
                      <option>5 min</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Appearance */}
              <div>
                <span className="details-section-title" style={{ display: 'block', marginBottom: '10px' }}>Appearance</span>
                <div className="settings-form-grid">
                  <div className="settings-form-field">
                    <label>Theme</label>
                    <select value={theme} onChange={e => setTheme(e.target.value)} className="settings-select">
                      <option>Dark</option>
                      <option>Light</option>
                      <option>System</option>
                    </select>
                  </div>
                  <div className="settings-form-field">
                    <label>Accent Color</label>
                    <select value={accentColor} onChange={e => setAccentColor(e.target.value)} className="settings-select">
                      <option>Blue</option>
                      <option>Purple</option>
                      <option>Green</option>
                      <option>Amber</option>
                    </select>
                  </div>
                  <div className="settings-form-field" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label>Compact Density</label>
                    <Toggle value={false} onChange={() => {}} />
                  </div>
                  <div className="settings-form-field">
                    <label>UI Scale</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
                      <input type="range" min="80" max="120" defaultValue="100" style={{ flex: 1, accentColor: 'var(--color-primary)' }} />
                      <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', width: '32px' }}>100%</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Agent Behavior */}
              <div>
                <span className="details-section-title" style={{ display: 'block', marginBottom: '10px' }}>Agent Behavior</span>
                <div className="settings-form-grid">
                  <div className="settings-form-field">
                    <label>Default Planner Model</label>
                    <select className="settings-select">
                      <option>Qwen 3.5 4B (Q4)</option>
                      <option>GPT-4o</option>
                      <option>Claude Sonnet 4.6</option>
                    </select>
                  </div>
                  <div className="settings-form-field">
                    <label>Default Coder Model</label>
                    <select className="settings-select">
                      <option>Claude Sonnet 4.6</option>
                      <option>Codestral 22B</option>
                      <option>GPT-4.1</option>
                    </select>
                  </div>
                  <div className="settings-form-field" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label>Allow Background Tasks</label>
                    <Toggle value={allowBackground} onChange={() => setAllowBackground(v => !v)} />
                  </div>
                  <div className="settings-form-field">
                    <label>Max Parallel Agents</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
                      <button className="browser-nav-btn" onClick={() => setMaxParallelAgents(v => Math.max(1, v - 1))} style={{ width: '24px', height: '24px' }}>−</button>
                      <span style={{ fontWeight: 'bold', fontSize: '0.9rem', minWidth: '16px', textAlign: 'center' }}>{maxParallelAgents}</span>
                      <button className="browser-nav-btn" onClick={() => setMaxParallelAgents(v => Math.min(20, v + 1))} style={{ width: '24px', height: '24px' }}>+</button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Automation Preferences */}
              <div>
                <span className="details-section-title" style={{ display: 'block', marginBottom: '10px' }}>Automation Preferences</span>
                <div className="settings-form-grid">
                  <div className="settings-form-field" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label>Retry Failed Tasks</label>
                    <Toggle value={retryFailedTasks} onChange={() => setRetryFailedTasks(v => !v)} />
                  </div>
                  <div className="settings-form-field" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label>Safe Mode</label>
                    <Toggle value={safeMode} onChange={() => setSafeMode(v => !v)} />
                  </div>
                  <div className="settings-form-field">
                    <label>Approval Mode</label>
                    <select value={approvalMode} onChange={e => setApprovalMode(e.target.value)} className="settings-select">
                      <option>On Critical Actions</option>
                      <option>Always Ask</option>
                      <option>Auto Approve</option>
                      <option>Never</option>
                    </select>
                  </div>
                  <div className="settings-form-field">
                    <label>Timeout (Seconds)</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
                      <input type="range" min="30" max="600" value={timeout} onChange={e => setTimeout(Number(e.target.value))} style={{ flex: 1, accentColor: 'var(--color-primary)' }} />
                      <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', width: '28px' }}>{timeout}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Bottom two panels */}
          <div className="bottom-tables-grid" style={{ minHeight: '200px' }}>
            {/* Notification Rules */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Notification Rules</span>
                <a href="#manage" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={e => { e.preventDefault(); alert("Manage notification rules."); }}>
                  Manage Rules →
                </a>
              </header>
              <div className="panel-body" style={{ padding: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {notificationRules.map((rule, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.8rem' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: rule.color, boxShadow: `0 0 6px ${rule.color}`, flexShrink: 0 }} />
                    <span style={{ flex: 1, color: 'var(--text-muted)' }}>{rule.name}</span>
                    <span style={{ color: 'var(--text-dim)', fontWeight: '600', width: '20px', textAlign: 'right' }}>{rule.count}</span>
                    <Toggle value={rule.enabled} onChange={() => {}} />
                  </div>
                ))}
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-dim)', borderTop: '1px solid var(--border-color)', paddingTop: '6px', marginTop: '4px' }}>
                  <span>Total Rules</span>
                  <span style={{ fontWeight: '600', color: 'var(--text-muted)' }}>54</span>
                </div>
              </div>
            </div>

            {/* Integration Status */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Integration Status</span>
                <a href="#manage" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={e => { e.preventDefault(); alert("Manage integrations."); }}>
                  Manage Integrations →
                </a>
              </header>
              <div className="panel-body" style={{ padding: '10px', display: 'flex', flexDirection: 'column', gap: '7px' }}>
                {integrations.map((integ, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.78rem' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: integ.color, boxShadow: `0 0 5px ${integ.color}`, flexShrink: 0 }} />
                    <span style={{ flex: 1, color: 'var(--text-muted)' }}>{integ.name}</span>
                    <span style={{ color: integ.color, fontWeight: '600', fontSize: '0.72rem' }}>{integ.status}</span>
                    <span style={{ color: 'var(--text-dim)', fontSize: '0.72rem', width: '36px', textAlign: 'right' }}>{integ.latency}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Backup & Restore */}
            <div className="dashboard-panel">
              <header className="panel-header">
                <span className="panel-title">Backup &amp; Restore</span>
              </header>
              <div className="panel-body" style={{ padding: '10px', display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.78rem' }}>
                {[
                  { label: "Latest Backup", value: "Today, 10:15 AM" },
                  { label: "Storage Location", value: "Local Storage (SSD)" },
                  { label: "Backup Size", value: "2.48 GB" },
                  { label: "Retention Policy", value: "14 Days" },
                  { label: "Next Scheduled", value: "Tomorrow, 02:00 AM" },
                ].map((item, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>{item.label}</span>
                    <span style={{ color: 'var(--text-muted)', fontWeight: '600' }}>{item.value}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                  <button className="details-footer-btn restart" style={{ flex: 1, padding: '6px', fontSize: '0.74rem' }} onClick={() => alert("Creating backup...")}>
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 7v10a2 2 0 002 2h12a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H6a2 2 0 00-2 2z" />
                    </svg>
                    Create Backup
                  </button>
                  <button className="details-footer-btn" style={{ flex: 1, padding: '6px', fontSize: '0.74rem' }} onClick={() => alert("Restore from backup...")}>
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3-3-3" />
                    </svg>
                    Restore
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Settings Details */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--color-primary)' }}>
                    <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <div>
                    <h2 className="details-title-name">Settings Details</h2>
                  </div>
                </div>
                <span className="agent-status-badge running" style={{ fontSize: '0.68rem' }}>● Active</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '10px', fontSize: '0.78rem' }}>
                {[
                  { label: "Current Profile", value: "Default Workspace ∨" },
                  { label: "Sync Status", value: "Synced", valueColor: '#10b981' },
                  { label: "Last Updated", value: "2 min ago" },
                  { label: "Config Version", value: "v1.2.0" },
                ].map((row, i) => (
                  <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-dim)' }}>{row.label}</span>
                    <span style={{ fontWeight: '600', color: row.valueColor || 'var(--text-muted)' }}>{row.value}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                  {['Production', 'Local First', 'Secure', 'High Priority'].map((tag, i) => (
                    <span key={i} className="mem-type-badge" style={{
                      fontSize: '0.64rem',
                      backgroundColor: i === 3 ? 'rgba(239,68,68,0.1)' : 'rgba(59,130,246,0.05)',
                      color: i === 3 ? '#f87171' : '#93c5fd',
                      borderColor: i === 3 ? 'rgba(239,68,68,0.2)' : 'rgba(59,130,246,0.15)',
                    }}>
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </header>

            <div className="agent-details-body">
              {/* Config health bars */}
              <div className="details-section-box">
                <span className="details-section-title">Config Health Metrics</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px' }}>
                  {[
                    { label: "Sync Coverage", pct: 98, color: 'var(--color-primary)' },
                    { label: "Security Compliance", pct: 72, color: '#f59e0b' },
                    { label: "Performance Mode", pct: 85, color: '#10b981' },
                    { label: "Backup Health", pct: 95, color: '#10b981' },
                  ].map((bar, i) => (
                    <div key={i} className="memory-bar-item">
                      <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                        <span>{bar.label}</span>
                        <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{bar.pct}%</span>
                      </div>
                      <div className="progress-bar-bg" style={{ height: '4px' }}>
                        <div className="progress-bar-fill" style={{ width: `${bar.pct}%`, background: bar.color }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="details-section-box">
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button className="details-footer-btn logs" onClick={() => alert(`Switched to workspace logs.`)} style={{ flex: 1, padding: '8px', fontSize: '0.74rem', flexDirection: 'row', gap: '6px' }}>
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                    </svg>
                    Apply
                  </button>
                  <button className="details-footer-btn" style={{ flex: 1, padding: '8px', fontSize: '0.74rem', flexDirection: 'row', gap: '6px' }} onClick={() => alert("Duplicating profile...")}>
                    Duplicate Profile
                  </button>
                  <button className="details-footer-btn" style={{ flex: 1, padding: '8px', fontSize: '0.74rem', flexDirection: 'row', gap: '6px' }} onClick={() => alert("Restoring backup...")}>
                    Restore Backup
                  </button>
                </div>
              </div>

              {/* Permission Controls */}
              <div className="details-section-box">
                <span className="details-section-title">Permission Controls</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '6px' }}>
                  {permissions.map((perm, i) => (
                    <div key={i} className="health-metric-row">
                      <div className="health-metric-left" style={{ fontSize: '0.76rem' }}>
                        <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: perm.color, boxShadow: `0 0 5px ${perm.color}` }} />
                        {perm.name}
                      </div>
                      <span className={`health-metric-right ${perm.status === "Allowed" || perm.status === "Healthy" ? "good" : "progress"}`} style={{ fontSize: '0.7rem' }}>
                        {perm.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent Settings Activity */}
              <div className="details-section-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className="details-section-title">Recent Settings Activity</span>
                  <a href="#all" className="view-timeline-link" style={{ fontSize: '0.7rem' }} onClick={e => { e.preventDefault(); alert("View all activity."); }}>View All</a>
                </div>
                <div className="recent-actions-list">
                  {recentActivity.map((act, i) => (
                    <div key={i} className="action-row" style={{ alignItems: 'flex-start' }}>
                      <span className="action-dot" style={{ backgroundColor: 'var(--color-primary)', width: '5px', height: '5px', marginTop: '5px' }} />
                      <div style={{ flex: 1 }}>
                        <div className="action-text" style={{ fontSize: '0.76rem' }}>
                          <span style={{ color: 'var(--text-dim)', marginRight: '4px' }}>{act.time}</span>
                          {act.text}
                        </div>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>{act.user}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
