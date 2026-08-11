import React, { useState, useEffect } from "react";
import { ThreeDPreviewViewer } from "./ThreeDPreviewViewer";
import { NonThreeDPreviewViewer } from "./NonThreeDPreviewViewer";

export const AssetInspector: React.FC<{ assetId: string; onRefresh: () => void }> = ({ assetId, onRefresh }) => {
  const [activeTab, setActiveTab] = useState<"overview" | "preview" | "versions" | "provenance" | "license" | "dependencies">("overview");
  const [detail, setDetail] = useState<any>(null);
  const [revisions, setRevisions] = useState<any[]>([]);
  const [provenance, setProvenance] = useState<any>(null);
  const [dependencies, setDependencies] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const loadDetail = async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`/api/v2/video-production/assets/${assetId}`);
        if (res.ok) {
          const data = await res.json();
          setDetail(data);
        }

        const revRes = await fetch(`/api/v2/video-production/assets/${assetId}/revisions`);
        if (revRes.ok) {
          const revData = await revRes.json();
          setRevisions(revData.revisions || []);
        }

        const provRes = await fetch(`/api/v2/video-production/assets/${assetId}/provenance`);
        if (provRes.ok) {
          const provData = await provRes.json();
          setProvenance(provData);
        }

        const depRes = await fetch(`/api/v2/video-production/assets/${assetId}/dependencies`);
        if (depRes.ok) {
          const depData = await depRes.json();
          setDependencies(depData);
        }
      } catch (err) {
        console.error("Failed to load asset inspector details:", err);
      } finally {
        setIsLoading(false);
      }
    };

    if (assetId) {
      loadDetail();
    }
  }, [assetId]);

  if (isLoading) return <div style={{ padding: "20px", color: "#94a3b8" }}>Loading asset inspector...</div>;
  if (!detail) return <div style={{ padding: "20px", color: "#f87171" }}>Asset details not available</div>;

  const asset = detail.asset;
  const activeRevision = detail.active_revision;

  const handleApprove = async () => {
    try {
      await fetch("/api/v2/video-production/assets/commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_type: "APPROVE_ASSET",
          project_id: "prj_default",
          target_revision_id: "rev_0",
          entity_id: assetId,
          reason: "Human approval via Inspector",
        }),
      });
      onRefresh();
    } catch (err) {
      console.error("Failed to approve asset:", err);
    }
  };

  const handleReject = async () => {
    try {
      await fetch("/api/v2/video-production/assets/commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_type: "REJECT_ASSET",
          project_id: "prj_default",
          target_revision_id: "rev_0",
          entity_id: assetId,
          reason: "Human rejection via Inspector",
        }),
      });
      onRefresh();
    } catch (err) {
      console.error("Failed to reject asset:", err);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", color: "#e2e8f0", fontSize: "0.85rem" }}>
      {/* Header */}
      <div style={{ padding: "16px", borderBottom: "1px solid #334155", background: "#0f172a" }}>
        <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "#f8fafc" }}>{asset.name}</div>
        <div style={{ fontSize: "0.75rem", color: "#38bdf8", marginTop: "2px" }}>{asset.kind} • ID: {asset.asset_id}</div>
        
        {/* Action Toolbar */}
        <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
          <button
            onClick={handleApprove}
            disabled={asset.lifecycle_state === "APPROVED" || asset.lifecycle_state === "BOUND_TO_PROJECT"}
            style={{ flex: 1, padding: "6px", background: "#16a34a", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", opacity: asset.lifecycle_state === "APPROVED" ? 0.5 : 1 }}
          >
            Approve
          </button>
          <button
            onClick={handleReject}
            disabled={asset.lifecycle_state === "REJECTED"}
            style={{ flex: 1, padding: "6px", background: "#dc2626", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer", opacity: asset.lifecycle_state === "REJECTED" ? 0.5 : 1 }}
          >
            Reject
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid #334155", background: "#1e293b", overflowX: "auto" }}>
        {(["overview", "preview", "versions", "provenance", "license", "dependencies"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: "8px 12px",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === tab ? "2px solid #38bdf8" : "2px solid transparent",
              color: activeTab === tab ? "#38bdf8" : "#94a3b8",
              cursor: "pointer",
              textTransform: "capitalize",
              fontSize: "0.75rem",
              fontWeight: 600,
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={{ flex: 1, padding: "16px", overflowY: "auto", background: "#0f172a" }}>
        {activeTab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Description</label>
              <div>{asset.description || "No description provided."}</div>
            </div>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Lifecycle State</label>
              <div style={{ fontWeight: 600, color: "#38bdf8" }}>{asset.lifecycle_state}</div>
            </div>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>License State</label>
              <div style={{ fontWeight: 600, color: asset.license_state === "UNKNOWN" ? "#f87171" : "#4ade80" }}>
                {asset.license_state} {!detail.is_eligible_for_production && " (Production Render Blocked)"}
              </div>
            </div>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Active Revision ID</label>
              <div style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>{asset.active_revision_id || "None"}</div>
            </div>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Content Hash (SHA-256)</label>
              <div style={{ fontFamily: "monospace", fontSize: "0.7rem", wordBreak: "break-all", background: "#1e293b", padding: "6px", borderRadius: "4px" }}>
                {activeRevision?.content_hash || "N/A"}
              </div>
            </div>
          </div>
        )}

        {activeTab === "preview" && (
          <div>
            {activeRevision?.media_type === "model_3d" ? (
              <ThreeDPreviewViewer glbUri={activeRevision?.preview_artifacts?.glb_uri} />
            ) : (
              <NonThreeDPreviewViewer mediaType={activeRevision?.media_type || "image"} />
            )}
          </div>
        )}

        {activeTab === "versions" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <div style={{ fontWeight: 600, color: "#94a3b8", fontSize: "0.75rem" }}>Lineage Revisions ({revisions.length})</div>
            {revisions.map((rev) => (
              <div key={rev.revision_id} style={{ background: "#1e293b", padding: "10px", borderRadius: "6px", border: rev.revision_id === asset.active_revision_id ? "1px solid #38bdf8" : "1px solid #334155" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 600 }}>
                  <span>{rev.revision_id}</span>
                  {rev.revision_id === asset.active_revision_id && <span style={{ color: "#38bdf8", fontSize: "0.7rem" }}>ACTIVE</span>}
                </div>
                <div style={{ fontSize: "0.7rem", color: "#94a3b8", marginTop: "4px" }}>
                  Size: {(rev.size_bytes / 1024 / 1024).toFixed(2)} MB • {new Date(rev.created_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "provenance" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Source Type</label>
              <div>{provenance?.source_type || asset.source_type}</div>
            </div>
            <div>
              <label style={{ color: "#94a3b8", fontSize: "0.75rem" }}>Provenance Evidence</label>
              <pre style={{ background: "#1e293b", padding: "10px", borderRadius: "4px", fontSize: "0.7rem", overflowX: "auto" }}>
                {JSON.stringify(provenance?.provenance || {}, null, 2)}
              </pre>
            </div>
          </div>
        )}

        {activeTab === "license" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            <div style={{ padding: "10px", background: asset.license_state === "UNKNOWN" ? "#7f1d1d" : "#14532d", borderRadius: "6px" }}>
              <div style={{ fontWeight: 700 }}>License Status: {asset.license_state}</div>
              <div style={{ fontSize: "0.75rem", marginTop: "4px" }}>
                {asset.license_state === "UNKNOWN" ? "Server-side governance gate active: This asset cannot be rendered in final production." : "Asset is approved for commercial video rendering."}
              </div>
            </div>
          </div>
        )}

        {activeTab === "dependencies" && (
          <div>
            <div style={{ fontWeight: 600, color: "#94a3b8", fontSize: "0.75rem", marginBottom: "8px" }}>Dependency Graph</div>
            <pre style={{ background: "#1e293b", padding: "10px", borderRadius: "4px", fontSize: "0.7rem", overflowX: "auto" }}>
              {JSON.stringify(dependencies || {}, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
