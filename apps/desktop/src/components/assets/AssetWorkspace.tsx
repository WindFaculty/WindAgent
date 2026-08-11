import React, { useState, useEffect } from "react";
import { AssetInspector } from "./AssetInspector";
import { AssetAcquisitionWizard } from "./AssetAcquisitionWizard";
import { AssetJobMonitor } from "./AssetJobMonitor";
import { AssetVersionImpactModal } from "./AssetVersionImpactModal";

export interface AssetSummaryItem {
  asset_id: string;
  kind: string;
  name: string;
  description: string;
  lifecycle_state: string;
  processing_state: string;
  license_state: string;
  source_type: string;
  active_revision_id: string | null;
  content_hash: string | null;
  media_type: string;
  preview_artifacts: Record<string, any>;
  project_bindings: string[];
  tags: string[];
  created_at: string;
  updated_at: string;
}

export const AssetWorkspace: React.FC<{ projectId?: string }> = ({ projectId = "prj_default" }) => {
  const [assets, setAssets] = useState<AssetSummaryItem[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>("ast_hero_01");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedKind, setSelectedKind] = useState<string>("ALL");
  const [selectedLicense, setSelectedLicense] = useState<string>("ALL");
  const [selectedLifecycle, setSelectedLifecycle] = useState<string>("ALL");
  const [isAcquisitionOpen, setIsAcquisitionOpen] = useState(false);
  const [isImpactModalOpen, setIsImpactModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const fetchAssets = async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (projectId) params.append("project_id", projectId);
      if (selectedKind !== "ALL") params.append("kind", selectedKind);
      if (selectedLicense !== "ALL") params.append("license_state", selectedLicense);
      if (selectedLifecycle !== "ALL") params.append("lifecycle_state", selectedLifecycle);
      if (searchQuery) params.append("q", searchQuery);

      const res = await fetch(`/api/v2/video-production/assets?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setAssets(data.items || []);
      }
    } catch (err) {
      console.error("Failed to fetch assets:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAssets();
  }, [projectId, selectedKind, selectedLicense, selectedLifecycle, searchQuery]);

  const selectedAsset = assets.find((a) => a.asset_id === selectedAssetId) || assets[0] || null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "#0f172a", color: "#f8fafc", fontFamily: "sans-serif" }}>
      {/* Top Header */}
      <div style={{ padding: "16px 24px", borderBottom: "1px solid #334155", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#1e293b" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "#38bdf8" }}>Universal Production Asset Library</h1>
          <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "#94a3b8" }}>Stage D Resource Management & Governance</p>
        </div>

        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <button
            onClick={() => setIsAcquisitionOpen(true)}
            style={{ padding: "8px 16px", background: "#0284c7", color: "#fff", border: "none", borderRadius: "6px", fontWeight: 600, cursor: "pointer" }}
          >
            + Acquire / Import Asset
          </button>
          {selectedAsset && (
            <button
              onClick={() => setIsImpactModalOpen(true)}
              style={{ padding: "8px 16px", background: "#334155", color: "#e2e8f0", border: "1px solid #475569", borderRadius: "6px", cursor: "pointer" }}
            >
              Replace Version Impact
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left Filter Sidebar */}
        <div style={{ width: "240px", borderRight: "1px solid #334155", background: "#1e293b", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>Search</label>
            <input
              type="text"
              placeholder="Search assets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            />
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>Asset Kind Taxonomy</label>
            <select
              value={selectedKind}
              onChange={(e) => setSelectedKind(e.target.value)}
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            >
              <option value="ALL">All Taxonomy Kinds</option>
              <option value="CHARACTER">Character</option>
              <option value="ENVIRONMENT">Environment</option>
              <option value="PROP">Prop</option>
              <option value="MODEL_3D">3D Model</option>
              <option value="MATERIAL">Material</option>
              <option value="TEXTURE">Texture</option>
              <option value="MUSIC">Music</option>
              <option value="SFX">SFX</option>
              <option value="DIALOGUE_AUDIO">Dialogue Audio</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>License Governance</label>
            <select
              value={selectedLicense}
              onChange={(e) => setSelectedLicense(e.target.value)}
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            >
              <option value="ALL">All License States</option>
              <option value="UNKNOWN">UNKNOWN (Blocked)</option>
              <option value="LICENSED">LICENSED</option>
              <option value="CREATIVE_COMMONS">Creative Commons</option>
              <option value="PUBLIC_DOMAIN">Public Domain</option>
            </select>
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase" }}>Business Lifecycle</label>
            <select
              value={selectedLifecycle}
              onChange={(e) => setSelectedLifecycle(e.target.value)}
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            >
              <option value="ALL">All Lifecycle States</option>
              <option value="DISCOVERED">Discovered</option>
              <option value="DOWNLOADED">Downloaded</option>
              <option value="VALIDATED">Validated</option>
              <option value="APPROVED">Approved</option>
              <option value="BOUND_TO_PROJECT">Bound to Project</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          <AssetJobMonitor />
        </div>

        {/* Center Grid/List View */}
        <div style={{ flex: 1, padding: "20px", overflowY: "auto", background: "#0f172a" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
            <span style={{ fontSize: "0.85rem", color: "#94a3b8" }}>Showing {assets.length} assets</span>
            <div style={{ display: "flex", gap: "4px" }}>
              <button
                onClick={() => setViewMode("grid")}
                style={{ padding: "4px 8px", background: viewMode === "grid" ? "#0284c7" : "#334155", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
              >
                Grid
              </button>
              <button
                onClick={() => setViewMode("list")}
                style={{ padding: "4px 8px", background: viewMode === "list" ? "#0284c7" : "#334155", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
              >
                List
              </button>
            </div>
          </div>

          {isLoading ? (
            <div style={{ color: "#94a3b8", textAlign: "center", padding: "40px" }}>Loading assets...</div>
          ) : viewMode === "grid" ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "16px" }}>
              {assets.map((asset) => {
                const isSelected = selectedAssetId === asset.asset_id;
                return (
                  <div
                    key={asset.asset_id}
                    onClick={() => setSelectedAssetId(asset.asset_id)}
                    style={{
                      background: "#1e293b",
                      border: isSelected ? "2px solid #38bdf8" : "1px solid #334155",
                      borderRadius: "8px",
                      padding: "12px",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                    }}
                  >
                    <div style={{ height: "100px", background: "#0f172a", borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", color: "#64748b" }}>
                      {asset.media_type === "model_3d" ? "📦 3D Model" : asset.media_type === "audio" ? "🎵 Audio" : "🖼️ Image"}
                    </div>
                    <div style={{ marginTop: "8px" }}>
                      <div style={{ fontWeight: 600, fontSize: "0.9rem", color: "#f8fafc" }}>{asset.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "#38bdf8", marginTop: "2px" }}>{asset.kind}</div>
                      <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px", fontSize: "0.7rem" }}>
                        <span style={{ color: asset.license_state === "UNKNOWN" ? "#f87171" : "#4ade80" }}>{asset.license_state}</span>
                        <span style={{ color: "#94a3b8" }}>{asset.lifecycle_state}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", color: "#e2e8f0", fontSize: "0.85rem" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155", textAlign: "left", color: "#94a3b8" }}>
                  <th style={{ padding: "8px" }}>Name</th>
                  <th style={{ padding: "8px" }}>Kind</th>
                  <th style={{ padding: "8px" }}>Media</th>
                  <th style={{ padding: "8px" }}>License</th>
                  <th style={{ padding: "8px" }}>Lifecycle</th>
                  <th style={{ padding: "8px" }}>Active Revision</th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr
                    key={asset.asset_id}
                    onClick={() => setSelectedAssetId(asset.asset_id)}
                    style={{
                      borderBottom: "1px solid #1e293b",
                      background: selectedAssetId === asset.asset_id ? "#1e293b" : "transparent",
                      cursor: "pointer",
                    }}
                  >
                    <td style={{ padding: "8px", fontWeight: 600 }}>{asset.name}</td>
                    <td style={{ padding: "8px", color: "#38bdf8" }}>{asset.kind}</td>
                    <td style={{ padding: "8px" }}>{asset.media_type}</td>
                    <td style={{ padding: "8px", color: asset.license_state === "UNKNOWN" ? "#f87171" : "#4ade80" }}>{asset.license_state}</td>
                    <td style={{ padding: "8px" }}>{asset.lifecycle_state}</td>
                    <td style={{ padding: "8px", fontFamily: "monospace", fontSize: "0.75rem" }}>{asset.active_revision_id || "None"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Right Inspector Panel */}
        <div style={{ width: "360px", borderLeft: "1px solid #334155", background: "#1e293b" }}>
          {selectedAsset ? (
            <AssetInspector assetId={selectedAsset.asset_id} onRefresh={fetchAssets} />
          ) : (
            <div style={{ padding: "20px", color: "#94a3b8" }}>Select an asset to inspect</div>
          )}
        </div>
      </div>

      {/* Modals */}
      {isAcquisitionOpen && <AssetAcquisitionWizard onClose={() => setIsAcquisitionOpen(false)} onSuccess={fetchAssets} />}
      {isImpactModalOpen && selectedAsset && (
        <AssetVersionImpactModal
          assetId={selectedAsset.asset_id}
          oldRevisionId={selectedAsset.active_revision_id || "rev_old"}
          newRevisionId="rev_candidate_v2"
          onClose={() => setIsImpactModalOpen(false)}
        />
      )}
    </div>
  );
};
