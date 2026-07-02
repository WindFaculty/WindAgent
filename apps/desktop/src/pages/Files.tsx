import { useState } from "react";

interface FileItem {
  id: string;
  name: string;
  type: string;
  owner: string;
  size: string;
  lastModified: string;
  status: "Synced" | "Active" | "Syncing" | "Shared" | "Archived";
  access: string;
  sparkPoints: string;
  description: string;
  fileId: string;
  location: string;
  tags: string[];
  previewLoadPct: number;
  syncStatusPct: number;
  sharingAccessPct: number;
  health: Array<{ name: string; status: "Good" | "In Progress" }>;
  activity: string[];
  steps: Array<{ name: string; desc: string; status: "Success" | "In Progress" }>;
}

export function Files() {
  const [selectedFileId, setSelectedFileId] = useState<string>("kronos_report");
  const [activeFilterTab, setActiveFilterTab] = useState<string>("all");
  const [searchText, setSearchText] = useState<string>("");

  const filesData: FileItem[] = [
    {
      id: "kronos_report",
      name: "kronos_training_report.pdf",
      type: "PDF",
      owner: "Researcher",
      size: "12.4 MB",
      lastModified: "4 min ago",
      status: "Synced",
      access: "93%",
      sparkPoints: "0,15 15,18 30,12 45,16 60,6 68,10",
      description: "Comprehensive training report containing Kronos model results, performance metrics, and validation summary.",
      fileId: "file_8f2c7a9d3b4e4c21",
      location: "/workspace/reports/kronos/",
      tags: ["Research", "Report", "Kronos", "High Priority"],
      previewLoadPct: 100,
      syncStatusPct: 100,
      sharingAccessPct: 91,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "Good" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "In Progress" },
      ],
      activity: [
        "File uploaded by Researcher (4 min ago)",
        "Preview generated (4 min ago)",
        "Shared with Planner (8 min ago)",
        "Synced to cloud storage (12 min ago)",
        "Indexed file metadata (15 min ago)",
      ],
      steps: [
        { name: "Upload", desc: "Completed", status: "Success" },
        { name: "Index", desc: "Indexed", status: "Success" },
        { name: "Analyze", desc: "Analyzed", status: "Success" },
        { name: "Share", desc: "Shared", status: "Success" },
        { name: "Archive", desc: "Archiving", status: "In Progress" },
      ],
    },
    {
      id: "routing_config",
      name: "agent_routing_config.json",
      type: "JSON",
      owner: "System",
      size: "240 KB",
      lastModified: "11 min ago",
      status: "Active",
      access: "94%",
      sparkPoints: "0,20 15,22 30,14 45,18 60,8 68,10",
      description: "Configuration files mapping active agent weights, latency endpoints, and fallback channels.",
      fileId: "file_3a12d8e4-b9ea-4f9c-8e4d-7a2b9c3e6d12",
      location: "/workspace/config/",
      tags: ["Config", "Routing", "Active"],
      previewLoadPct: 100,
      syncStatusPct: 100,
      sharingAccessPct: 50,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "Good" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "Good" },
      ],
      activity: [
        "Configuration checked by Dispatcher (11 min ago)",
        "Hot reload triggered successfully (10 min ago)",
      ],
      steps: [
        { name: "Upload", desc: "Completed", status: "Success" },
        { name: "Index", desc: "Indexed", status: "Success" },
      ],
    },
    {
      id: "dataset",
      name: "market_dataset_2025.csv",
      type: "CSV",
      owner: "Data Agent",
      size: "1.8 GB",
      lastModified: "23 min ago",
      status: "Syncing",
      access: "89%",
      sparkPoints: "0,18 15,12 30,14 45,10 60,8 68,6",
      description: "Raw CSV exchange records used for training baseline forecasting weights.",
      fileId: "file_9b4e2f1c-7c2a-4b8c-a8d0-6f2d9a3b8c4c",
      location: "/workspace/data/",
      tags: ["Datasets", "Finance", "Training"],
      previewLoadPct: 40,
      syncStatusPct: 75,
      sharingAccessPct: 0,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "In Progress" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "In Progress" },
      ],
      activity: [
        "Transfer sequence opened by Data Agent (23 min ago)",
        "Syncing chunk 41/80 (in progress) (2 min ago)",
      ],
      steps: [
        { name: "Upload", desc: "Syncing", status: "In Progress" },
      ],
    },
    {
      id: "mockup",
      name: "ui_mockup_v1.fig",
      type: "Design",
      owner: "GUI Agent",
      size: "32 MB",
      lastModified: "1 hour ago",
      status: "Shared",
      access: "91%",
      sparkPoints: "0,22 15,20 30,22 45,18 60,16 68,14",
      description: "Vibrant CSS styling mocks and page alignment structures generated by GUI agent loops.",
      fileId: "file_2c8f9d0e-5b12-4f6c-b7ea-9a8c1e2f3d4e",
      location: "/workspace/design/",
      tags: ["UI", "Design", "Shared"],
      previewLoadPct: 100,
      syncStatusPct: 100,
      sharingAccessPct: 100,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "Good" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "Good" },
      ],
      activity: [
        "Shared access given to wind faculty reviewers (1 hour ago)",
      ],
      steps: [
        { name: "Upload", desc: "Completed", status: "Success" },
        { name: "Index", desc: "Indexed", status: "Success" },
        { name: "Share", desc: "Shared", status: "Success" },
      ],
    },
    {
      id: "capture",
      name: "browser_capture_0511.png",
      type: "Image",
      owner: "Browser Agent",
      size: "4.1 MB",
      lastModified: "2 hours ago",
      status: "Archived",
      access: "82%",
      sparkPoints: "0,12 15,8 30,10 45,6 60,4 68,2",
      description: "Screenshot from verification loop testing visual alignment of dashboard charts.",
      fileId: "file_6f8b1a3d-2c90-4f6e-bd2a-9f8a7e6c5d4b",
      location: "/workspace/screenshots/",
      tags: ["Testing", "UI", "Visual-QA"],
      previewLoadPct: 100,
      syncStatusPct: 100,
      sharingAccessPct: 0,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "Good" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "Good" },
      ],
      activity: [
        "Captured by Browser Agent (2 hours ago)",
        "Moved to archives folder (1 hour ago)",
      ],
      steps: [
        { name: "Upload", desc: "Completed", status: "Success" },
        { name: "Archive", desc: "Archived", status: "Success" },
      ],
    },
    {
      id: "release_notes",
      name: "release_notes.md",
      type: "Markdown",
      owner: "Coder",
      size: "95 KB",
      lastModified: "Yesterday",
      status: "Active",
      access: "96%",
      sparkPoints: "0,15 15,15 30,15 45,15 60,15 68,15",
      description: "Text summary outlining new model route adjustments and performance diagnostics reports.",
      fileId: "file_7e9a8f2c-3b90-4f8d-bd2a-8c9d0a1b2c3d",
      location: "/workspace/docs/",
      tags: ["Logs", "Markdown", "Active"],
      previewLoadPct: 100,
      syncStatusPct: 100,
      sharingAccessPct: 20,
      health: [
        { name: "Local Disk", status: "Good" },
        { name: "Cloud Sync", status: "Good" },
        { name: "Indexing", status: "Good" },
        { name: "Permissions", status: "Good" },
        { name: "Backup", status: "Good" },
      ],
      activity: [
        "Draft completed by Coder (Yesterday)",
      ],
      steps: [
        { name: "Upload", desc: "Completed", status: "Success" },
        { name: "Index", desc: "Indexed", status: "Success" },
      ],
    },
  ];

  const totalFilesCount = 1284;
  const storageUsed = "221 GB / 500 GB";
  const syncedFiles = 842;
  const pendingUploads = 12;
  const avgAccessTime = "128 ms";
  const fileHealth = "97%";

  const filteredFiles = filesData.filter((f) => {
    if (activeFilterTab === "recent" && f.lastModified.includes("Yesterday")) return false;
    if (activeFilterTab === "shared" && f.status !== "Shared") return false;
    if (activeFilterTab === "synced" && f.status !== "Synced") return false;
    if (activeFilterTab === "archived" && f.status !== "Archived") return false;

    if (searchText.trim()) {
      const q = searchText.toLowerCase();
      return (
        f.name.toLowerCase().includes(q) ||
        f.type.toLowerCase().includes(q) ||
        f.owner.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const selectedFile = filesData.find((f) => f.id === selectedFileId) || filesData[0];

  return (
    <main className="models-view" style={{ overflow: 'hidden' }}>
      {/* Header controls row */}
      <div className="models-header-row">
        <div className="dashboard-title-box">
          <h1 className="dashboard-title-text">Files</h1>
          <p className="dashboard-subtitle-text">Organize, inspect, upload, and manage files across your agent workspace.</p>
        </div>
        <div className="models-header-right">
          <button className="chat-send-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Upload Files dialog.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 4v16m8-8H4" />
            </svg>
            Upload Files
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Create New Folder dialog.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            </svg>
            New Folder
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px', display: 'flex', alignItems: 'center', gap: '6px' }} onClick={() => alert("Import files.")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Import
          </button>
          <button className="role-btn" style={{ height: '36px', padding: '0 16px' }} onClick={() => alert("More Actions.")}>
            More Actions
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" style={{ marginLeft: '4px' }}>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Metric Cards Row */}
      <div className="metrics-row-grid">
        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
              <span>Total Files</span>
            </div>
            <div className="trend-indicator up">▲ 8.3%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{totalFilesCount.toLocaleString()}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg blue" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 7v10a2 2 0 002 2h12a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
              <span>Storage Used</span>
            </div>
            <div className="trend-indicator up">▲ 3.6%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{storageUsed.split(" ")[0]} GB</div>
              <div className="m-card-subtext">of 500 GB total</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,22 15,18 30,12 45,20 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-primary)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4" />
              </svg>
              <span>Synced Files</span>
            </div>
            <div className="trend-indicator up">▲ 5.2%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{syncedFiles}</div>
              <div className="m-card-subtext">vs yesterday</div>
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
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1" />
              </svg>
              <span>Pending Uploads</span>
            </div>
            <div className="trend-indicator up" style={{ color: 'var(--color-warning)' }}>▲ 20.0%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{pendingUploads}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg orange" viewBox="0 0 68 24">
              <polyline points="0,18 15,10 30,12 45,8 60,10 68,4" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-accent)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 8v4l3 3" />
              </svg>
              <span>Avg Access Time</span>
            </div>
            <div className="trend-indicator down" style={{ color: 'var(--color-success)' }}>▼ 6.1%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{avgAccessTime}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg purple" viewBox="0 0 68 24">
              <polyline points="0,22 15,14 30,18 45,8 60,12 68,6" />
            </svg>
          </div>
        </div>

        <div className="metric-card-box">
          <div className="m-card-header">
            <div className="m-card-header-left">
              <svg className="m-card-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--color-success)' }}>
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12l2 2 4-4" />
              </svg>
              <span>File Health</span>
            </div>
            <div className="trend-indicator up">▲ 1.4%</div>
          </div>
          <div className="m-card-body">
            <div className="m-card-value-container">
              <div className="m-card-value">{fileHealth}</div>
              <div className="m-card-subtext">vs yesterday</div>
            </div>
            <svg className="m-card-sparkline-svg green" viewBox="0 0 68 24">
              <polyline points="0,20 15,18 30,22 45,12 60,6 68,14" />
            </svg>
          </div>
        </div>
      </div>

      {/* Files Console 3 Column Grid layout */}
      <div className="files-console-layout">
        {/* Column 1: File Library & File Activity Flow */}
        <div className="files-col">
          <div className="dashboard-panel" style={{ flex: 1.3 }}>
            <header className="panel-header" style={{ height: 'auto', padding: '10px 12px', flexDirection: 'column', alignItems: 'stretch', gap: '8px' }}>
              <div className="agent-directory-header">
                <span className="panel-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                  </svg>
                  File Library
                </span>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button className="browser-nav-btn" style={{ padding: '4px' }}>⟳</button>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <div className="search-box-container" style={{ flex: 1 }}>
                  <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <input
                    type="text"
                    placeholder="Search files..."
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                  />
                </div>
                <button className="toggle-icon-btn" style={{ padding: '6px' }}>
                  <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                  </svg>
                </button>
              </div>

              {/* Status filtering tabs */}
              <div className="chart-header-tabs" style={{ alignSelf: 'flex-start', padding: '2px' }}>
                <button className={`tab-btn ${activeFilterTab === "all" ? "active" : ""}`} onClick={() => setActiveFilterTab("all")}>All</button>
                <button className={`tab-btn ${activeFilterTab === "recent" ? "active" : ""}`} onClick={() => setActiveFilterTab("recent")}>Recent</button>
                <button className={`tab-btn ${activeFilterTab === "shared" ? "active" : ""}`} onClick={() => setActiveFilterTab("shared")}>Shared</button>
                <button className={`tab-btn ${activeFilterTab === "synced" ? "active" : ""}`} onClick={() => setActiveFilterTab("synced")}>Synced</button>
                <button className={`tab-btn ${activeFilterTab === "archived" ? "active" : ""}`} onClick={() => setActiveFilterTab("archived")}>Archived</button>
              </div>
            </header>

            <div className="panel-body" style={{ padding: '0' }}>
              <table className="custom-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Owner</th>
                    <th>Size</th>
                    <th>Last Modified</th>
                    <th>Status</th>
                    <th>Access</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredFiles.map((file) => (
                    <tr
                      key={file.id}
                      className={selectedFileId === file.id ? "selected-row" : ""}
                      onClick={() => setSelectedFileId(file.id)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        <div className="agent-name-cell">
                          {file.type === "PDF" ? (
                            <span style={{ color: '#ef4444', fontWeight: 'bold', fontSize: '0.8rem' }}>PDF</span>
                          ) : file.type === "JSON" ? (
                            <span style={{ color: '#60a5fa', fontWeight: 'bold', fontSize: '0.85rem' }}>{`{}`}</span>
                          ) : (
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                          )}
                          <span style={{ fontWeight: '700' }}>{file.name}</span>
                        </div>
                      </td>
                      <td style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>{file.type}</td>
                      <td>{file.owner}</td>
                      <td>{file.size}</td>
                      <td>{file.lastModified}</td>
                      <td>
                        <span className={`agent-status-badge ${file.status === "Synced" || file.status === "Active" ? "running" : file.status === "Syncing" ? "busy" : "offline"}`}>
                          ● {file.status}
                        </span>
                      </td>
                      <td>
                        <div className="perf-cell-wrapper">
                          <span style={{ fontWeight: 'bold' }}>{file.access}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 12px', borderTop: '1px solid var(--border-color)', fontSize: '0.74rem', color: 'var(--text-dim)' }}>
                <span>Showing 1 to {filteredFiles.length} of 1,284 files</span>
                <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&lt;</button>
                  <span style={{ padding: '0 6px', color: 'var(--text-main)', fontWeight: 'bold' }}>1</span>
                  <span style={{ padding: '0 4px' }}>2</span>
                  <span style={{ padding: '0 4px' }}>3</span>
                  <span style={{ padding: '0 2px' }}>...</span>
                  <span style={{ padding: '0 4px' }}>214</span>
                  <button className="browser-nav-btn" style={{ width: '20px', height: '20px' }}>&gt;</button>
                </div>
              </div>
            </div>
          </div>

          {/* File Activity Flow steps flowchart */}
          <div className="dashboard-panel" style={{ flex: 0.8 }}>
            <header className="panel-header">
              <span className="panel-title">File Activity Flow: {selectedFile.name}</span>
            </header>
            <div className="panel-body" style={{ padding: '8px' }}>
              <div className="files-flowchart-row">
                {selectedFile.steps.map((step, idx) => (
                  <div key={idx} className={`files-flow-step-card ${step.status === "Success" ? "success" : "progress"}`}>
                    <span className="files-flow-step-num">{idx + 1} {step.name}</span>
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.64rem' }}>{step.desc}</span>
                    <span className={`files-flow-step-status-chip ${step.status === "Success" ? "success" : "progress"}`}>
                      {step.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Column 2: File Preview canvas simulated sheet */}
        <div className="files-col" style={{ flex: 1.3 }}>
          <div className="file-preview-canvas-frame">
            {/* Toolbar options */}
            <div className="file-preview-top-toolbar">
              <span>File Preview: <span style={{ color: '#fff' }}>{selectedFile.name}</span></span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button className="browser-nav-btn" style={{ padding: '2px 6px' }}>-</button>
                <span>100%</span>
                <button className="browser-nav-btn" style={{ padding: '2px 6px' }}>+</button>
                <span style={{ margin: '0 4px', fontSize: '0.74rem' }}>&lt; 1 / 8 &gt;</span>
                <button className="browser-nav-btn" style={{ padding: '3px' }}>🖥️</button>
                <button className="browser-nav-btn" style={{ padding: '3px' }}>🔗</button>
                <button className="browser-nav-btn" style={{ padding: '3px' }} onClick={() => alert(`Downloading ${selectedFile.name}...`)}>⬇</button>
              </div>
            </div>

            {/* Document PDF simulation viewport */}
            <div className="pdf-preview-scroller">
              <div className="pdf-white-sheet">
                <div className="pdf-header-row">
                  <div className="pdf-header-title-box">
                    <span className="pdf-header-main-title">Kronos Training Report</span>
                    <span className="pdf-header-subtitle">Training Results & Validation Summary | Generated on May 11, 2025</span>
                  </div>
                  <span className="pdf-logo">▲ KRONOS</span>
                </div>

                {/* Section 1: Performance Summary */}
                <div>
                  <h3 className="pdf-section-title">1. Performance Summary</h3>
                  <div className="pdf-metrics-flex">
                    <div className="pdf-metric-block">
                      <span className="pdf-metric-title">Accuracy</span>
                      <span className="pdf-metric-value">94.2%</span>
                      <span className="pdf-metric-trend">▲ 2.1%</span>
                    </div>
                    <div className="pdf-metric-block">
                      <span className="pdf-metric-title">Loss</span>
                      <span className="pdf-metric-value">0.082</span>
                      <span className="pdf-metric-trend" style={{ color: '#10b981' }}>▼ 8.6%</span>
                    </div>
                    <div className="pdf-metric-block">
                      <span className="pdf-metric-title">F1 Score</span>
                      <span className="pdf-metric-value">0.932</span>
                      <span className="pdf-metric-trend">▲ 1.8%</span>
                    </div>
                    <div className="pdf-metric-block">
                      <span className="pdf-metric-title">Duration</span>
                      <span className="pdf-metric-value">3h 24m</span>
                      <span className="pdf-metric-trend">▲ 7.3%</span>
                    </div>
                  </div>
                </div>

                {/* Section 2: Progress Plot and Dataset Splits Donut */}
                <div className="pdf-progress-plots-grid">
                  <div className="pdf-graph-box">
                    <span style={{ fontSize: '0.64rem', fontWeight: 'bold', color: '#64748b' }}>Training Progress (Accuracy vs Epochs)</span>
                    <svg style={{ width: '100%', height: '65px' }}>
                      {/* Grid lines */}
                      <line x1="0" y1="50" x2="200" y2="50" stroke="#f1f5f9" strokeWidth="1" />
                      <line x1="0" y1="25" x2="200" y2="25" stroke="#f1f5f9" strokeWidth="1" />
                      {/* Curves */}
                      <path d="M 0,60 Q 40,55 80,32 T 160,12 T 200,8" stroke="#3b82f6" strokeWidth="1.5" fill="none" />
                    </svg>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.52rem', color: '#94a3b8' }}>
                      <span>0</span>
                      <span>25</span>
                      <span>50</span>
                      <span>75</span>
                      <span>100 Epochs</span>
                    </div>
                  </div>

                  <div className="pdf-graph-box" style={{ flexDirection: 'row', alignItems: 'center', gap: '8px' }}>
                    <div style={{ position: 'relative', width: '48px', height: '48px' }}>
                      <svg width="48" height="48" viewBox="0 0 36 36">
                        <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f1f5f9" strokeWidth="3" />
                        <circle cx="18" cy="18" r="15.915" fill="none" stroke="#3b82f6" strokeWidth="3" strokeDasharray="70 30" strokeDashoffset="25" />
                        <circle cx="18" cy="18" r="15.915" fill="none" stroke="#10b981" strokeWidth="3" strokeDasharray="15 85" strokeDashoffset="95" />
                        <circle cx="18" cy="18" r="15.915" fill="none" stroke="#f59e0b" strokeWidth="3" strokeDasharray="15 85" strokeDashoffset="110" />
                      </svg>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '0.56rem', color: '#475569' }}>
                      <span style={{ fontWeight: 'bold', color: '#0f172a' }}>Dataset Split</span>
                      <span style={{ color: '#3b82f6' }}>● Train: 70%</span>
                      <span style={{ color: '#10b981' }}>● Val: 15%</span>
                      <span style={{ color: '#f59e0b' }}>● Test: 15%</span>
                    </div>
                  </div>
                </div>

                {/* Section 3: Model Metrics table */}
                <div>
                  <h3 className="pdf-section-title">3. Model Metrics</h3>
                  <table className="pdf-table">
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th>Train</th>
                        <th>Validation</th>
                        <th>Test</th>
                        <th>Delta</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td style={{ fontWeight: 'bold' }}>Precision</td>
                        <td>0.948</td>
                        <td>0.941</td>
                        <td>0.936</td>
                        <td style={{ color: '#ef4444' }}>▼ 0.012</td>
                      </tr>
                      <tr>
                        <td style={{ fontWeight: 'bold' }}>Recall</td>
                        <td>0.923</td>
                        <td>0.920</td>
                        <td>0.921</td>
                        <td style={{ color: '#10b981' }}>▲ 0.002</td>
                      </tr>
                      <tr>
                        <td style={{ fontWeight: 'bold' }}>F1 Score</td>
                        <td>0.940</td>
                        <td>0.934</td>
                        <td>0.932</td>
                        <td style={{ color: '#ef4444' }}>▼ 0.008</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Column 3: File Details Card */}
        <aside className="agent-details-pane">
          <div className="agent-details-card">
            <header className="agent-details-header">
              <div className="details-header-top">
                <div className="details-title-box">
                  <div className="details-title-icon-box" style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 'bold' }}>PDF</span>
                  </div>
                  <div>
                    <h2 className="details-title-name" style={{ maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={selectedFile.name}>
                      {selectedFile.name}
                    </h2>
                  </div>
                </div>
                <span className="details-status-badge running" style={{ color: 'var(--color-success)' }}>
                  Synced
                </span>
              </div>

              <div className="details-id-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>File ID: {selectedFile.fileId}</span>
                  <svg className="details-id-copy" width="12" height="12" fill="none" stroke="currentColor" viewBox="0 0 24 24" onClick={() => alert("Copied File ID!")}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1" />
                  </svg>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '12px', fontSize: '0.78rem', marginTop: '10px' }}>
                <div>
                  <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Owner</span>
                  <span style={{ fontWeight: '600' }}>{selectedFile.owner}</span>
                </div>
                <div>
                  <span className="details-section-title" style={{ display: 'block', marginBottom: '2px' }}>Location</span>
                  <span style={{ fontWeight: '600', fontFamily: 'var(--font-mono)', fontSize: '0.72rem' }}>{selectedFile.location}</span>
                </div>
              </div>

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
                {selectedFile.tags.map((tag, idx) => (
                  <span key={idx} className="mem-type-badge working" style={{ backgroundColor: 'rgba(59, 130, 246, 0.05)', color: '#93c5fd', borderColor: 'rgba(59, 130, 246, 0.15)' }}>{tag}</span>
                ))}
              </div>
            </header>

            <div className="agent-details-body">
              <div className="details-section-box">
                <p className="details-section-desc">{selectedFile.description}</p>
              </div>

              {/* Progress Resource usage details */}
              <div className="details-section-box">
                <span className="details-section-title">File Status Metrics</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Preview Load</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedFile.previewLoadPct}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedFile.previewLoadPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Sync Status</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedFile.syncStatusPct}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedFile.syncStatusPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                  <div className="memory-bar-item">
                    <div className="mem-bar-header" style={{ fontSize: '0.74rem' }}>
                      <span>Sharing Access</span>
                      <span style={{ color: 'var(--text-main)', fontWeight: '600' }}>{selectedFile.sharingAccessPct}%</span>
                    </div>
                    <div className="progress-bar-bg" style={{ height: '4px' }}>
                      <div className="progress-bar-fill" style={{ width: `${selectedFile.sharingAccessPct}%`, background: 'linear-gradient(90deg, var(--color-primary), #60a5fa)' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Buttons row */}
              <footer className="agent-details-footer" style={{ borderTop: 'none', padding: '0px', gridTemplateColumns: 'repeat(4, 1fr)' }}>
                <button className="details-footer-btn restart" onClick={() => alert(`Opening ${selectedFile.name}...`)}>
                  <span>Open</span>
                </button>
                <button className="details-footer-btn" onClick={() => alert(`Downloading ${selectedFile.name}...`)}>
                  <span>Download</span>
                </button>
                <button className="details-footer-btn" onClick={() => alert(`Sharing link copied for ${selectedFile.name}.`)}>
                  <span>Share</span>
                </button>
                <button className="details-footer-btn" onClick={() => alert(`Move ${selectedFile.name} triggered.`)}>
                  <span>Move</span>
                </button>
              </footer>

              {/* Storage Health Checklist */}
              <div className="details-section-box">
                <span className="details-section-title">Storage Health</span>
                <div className="health-metrics-list">
                  {selectedFile.health.map((item, idx) => (
                    <div key={idx} className="health-metric-row">
                      <div className="health-metric-left">
                        <span style={{
                          width: '6px',
                          height: '6px',
                          borderRadius: '50%',
                          backgroundColor: item.status === "Good" ? 'var(--color-success)' : 'var(--color-warning)',
                          boxShadow: item.status === "Good" ? '0 0 6px var(--color-success)' : '0 0 6px var(--color-warning)',
                        }} />
                        {item.name}
                      </div>
                      <span className={`health-metric-right ${item.status === "Good" ? "good" : "progress"}`}>
                        {item.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Recent Browser Activity logs */}
              <div className="details-section-box">
                <span className="details-section-title">Recent File Activity</span>
                <div className="recent-actions-list">
                  {selectedFile.activity.map((act, idx) => (
                    <div key={idx} className="action-row" style={{ alignItems: 'flex-start' }}>
                      <span className="action-dot" style={{ backgroundColor: 'var(--color-primary)', width: '5px', height: '5px', marginTop: '6px' }} />
                      <span className="action-text" style={{ fontSize: '0.78rem' }}>
                        {act}
                      </span>
                    </div>
                  ))}
                </div>
                <a href="#logs" className="view-timeline-link" style={{ fontSize: '0.74rem' }} onClick={(e) => { e.preventDefault(); alert("Show full files activity logs."); }}>
                  View all activity logs →
                </a>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </main>
  );
}
