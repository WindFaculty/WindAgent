import React from "react";

export const AssetJobMonitor: React.FC = () => {
  return (
    <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: "6px", padding: "12px", marginTop: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
        <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Job Monitor (UI31)</span>
        <span style={{ fontSize: "0.65rem", background: "#1e293b", padding: "2px 6px", borderRadius: "4px", color: "#4ade80" }}>Active</span>
      </div>

      <div style={{ fontSize: "0.75rem", color: "#e2e8f0", marginBottom: "4px" }}>
        Job #job_norm_88: Normalizing GLB derivative
      </div>

      {/* Progress Bar */}
      <div style={{ height: "6px", background: "#1e293b", borderRadius: "3px", overflow: "hidden", marginBottom: "6px" }}>
        <div style={{ width: "65%", height: "100%", background: "#38bdf8" }} />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.65rem", color: "#94a3b8" }}>
        <span>Stage 2/3: Generating Preview</span>
        <span>65%</span>
      </div>
    </div>
  );
};
