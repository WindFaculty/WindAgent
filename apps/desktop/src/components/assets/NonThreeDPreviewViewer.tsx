import React, { useState } from "react";

export const NonThreeDPreviewViewer: React.FC<{ mediaType: string }> = ({ mediaType }) => {
  const [isPlaying, setIsPlaying] = useState(false);

  if (mediaType === "audio") {
    return (
      <div style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: "8px", padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ fontWeight: 600, color: "#38bdf8", fontSize: "0.85rem" }}>Audio Waveform Preview</div>
        <div style={{ height: "60px", background: "#1e293b", borderRadius: "6px", display: "flex", alignItems: "center", justifyContent: "center", color: "#38bdf8" }}>
          📊 [Waveform Audio Visualization Data]
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            style={{ padding: "6px 12px", background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
          >
            {isPlaying ? "Pause ⏸️" : "Play ▶️"}
          </button>
          <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>0:00 / 3:45 • 44.1 kHz • Stereo</span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ background: "#020617", border: "1px solid #1e293b", borderRadius: "8px", padding: "16px", textAlign: "center" }}>
      <div style={{ fontSize: "3rem" }}>🖼️</div>
      <div style={{ fontWeight: 600, color: "#e2e8f0", marginTop: "8px" }}>2D Image Reference Preview</div>
      <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>PNG / JPG Derivative Artifact</div>
    </div>
  );
};
