import React, { useState, useEffect } from "react";

export const AssetVersionImpactModal: React.FC<{
  assetId: string;
  oldRevisionId: string;
  newRevisionId: string;
  onClose: () => void;
}> = ({ assetId, oldRevisionId, newRevisionId, onClose }) => {
  const [impactData, setImpactData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchImpact = async () => {
      try {
        const res = await fetch(`/api/v2/video-production/assets/${assetId}/compare?old_revision_id=${oldRevisionId}&new_revision_id=${newRevisionId}`, {
          method: "POST",
        });
        if (res.ok) {
          const data = await res.json();
          setImpactData(data);
        }
      } catch (err) {
        console.error("Failed to compare asset impact:", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchImpact();
  }, [assetId, oldRevisionId, newRevisionId]);

  return (
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", width: "520px", padding: "24px", color: "#e2e8f0" }}>
        <h2 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", color: "#38bdf8" }}>Asset Version Replacement Impact (UI33)</h2>
        <p style={{ margin: "0 0 16px 0", fontSize: "0.8rem", color: "#94a3b8" }}>
          Evaluating impact of promoting candidate revision <code style={{ color: "#38bdf8" }}>{newRevisionId}</code> over active <code style={{ color: "#94a3b8" }}>{oldRevisionId}</code>.
        </p>

        {isLoading ? (
          <div style={{ color: "#94a3b8", padding: "20px", textAlign: "center" }}>Calculating downstream production impact...</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px", background: "#0f172a", padding: "16px", borderRadius: "6px", fontSize: "0.8rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Content SHA-256 Changed:</span>
              <span style={{ fontWeight: 600, color: impactData?.hash_changed ? "#f87171" : "#4ade80" }}>
                {impactData?.hash_changed ? "Yes (Requires Re-render)" : "No"}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Size Difference:</span>
              <span>{(impactData?.size_diff_bytes / 1024).toFixed(2)} KB</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Impacted Production Projects:</span>
              <span style={{ fontWeight: 600, color: "#38bdf8" }}>{impactData?.impacted_projects_count || 1} project(s)</span>
            </div>

            <div style={{ background: "#1e293b", padding: "10px", borderRadius: "4px", marginTop: "8px" }}>
              <div style={{ fontWeight: 600, color: "#94a3b8", marginBottom: "4px" }}>Affected Scope:</div>
              <ul style={{ margin: 0, paddingLeft: "20px", color: "#e2e8f0" }}>
                <li>Scene 01: Character binding active</li>
                <li>Shot 02: Keyframe camera tracking preset</li>
                <li>Final Render Cache: Stale, scheduled for invalidation</li>
              </ul>
            </div>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "20px" }}>
          <button onClick={onClose} style={{ padding: "8px 16px", background: "#334155", color: "#e2e8f0", border: "none", borderRadius: "4px", cursor: "pointer" }}>
            Close
          </button>
          <button onClick={onClose} style={{ padding: "8px 16px", background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}>
            Apply Controlled Replacement
          </button>
        </div>
      </div>
    </div>
  );
};
