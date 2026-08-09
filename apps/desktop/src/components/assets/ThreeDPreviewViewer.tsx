import React, { useState } from "react";

export const ThreeDPreviewViewer: React.FC<{ glbUri?: string }> = ({ glbUri }) => {
  const [wireframe, setWireframe] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);

  return (
    <div style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: "8px", padding: "12px", display: "flex", flexDirection: "column", gap: "12px" }}>
      {/* 3D Canvas Mock Render Container */}
      <div
        style={{
          height: "220px",
          background: "radial-gradient(circle at center, #1e293b 0%, #020617 100%)",
          borderRadius: "6px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          border: "1px dashed #334155",
        }}
      >
        <div style={{ fontSize: "2.5rem" }}>📦</div>
        <div style={{ color: "#38bdf8", fontWeight: 600, marginTop: "8px", fontSize: "0.85rem" }}>glTF / GLB 3D Preview Engine</div>
        <div style={{ color: "#64748b", fontSize: "0.75rem" }}>{glbUri || "Default Derivative Mesh"}</div>

        {/* Overlay Stats */}
        <div style={{ position: "absolute", top: "8px", left: "8px", background: "rgba(15,23,42,0.8)", padding: "4px 8px", borderRadius: "4px", fontSize: "0.65rem", color: "#94a3b8" }}>
          <div>Polys: 14,280</div>
          <div>VRAM: 12.4 MB</div>
          <div>Bones: 48 (Semantic Rigged)</div>
        </div>
      </div>

      {/* Control Toolbar */}
      <div style={{ display: "flex", gap: "8px", justifyContent: "space-between" }}>
        <button
          onClick={() => setWireframe(!wireframe)}
          style={{ padding: "4px 8px", background: wireframe ? "#0284c7" : "#1e293b", color: "#fff", border: "1px solid #334155", borderRadius: "4px", fontSize: "0.75rem", cursor: "pointer" }}
        >
          Wireframe
        </button>
        <button
          onClick={() => setShowSkeleton(!showSkeleton)}
          style={{ padding: "4px 8px", background: showSkeleton ? "#0284c7" : "#1e293b", color: "#fff", border: "1px solid #334155", borderRadius: "4px", fontSize: "0.75rem", cursor: "pointer" }}
        >
          Skeleton
        </button>
        <button style={{ padding: "4px 8px", background: "#1e293b", color: "#fff", border: "1px solid #334155", borderRadius: "4px", fontSize: "0.75rem", cursor: "pointer" }}>
          Reset Orbit
        </button>
      </div>
    </div>
  );
};
