import React, { useState } from "react";

export const AssetAcquisitionWizard: React.FC<{ onClose: () => void; onSuccess: () => void }> = ({ onClose, onSuccess }) => {
  const [sourceType, setSourceType] = useState<"UPLOAD" | "URL" | "GENERATION">("UPLOAD");
  const [assetName, setAssetName] = useState("");
  const [kind, setKind] = useState("CHARACTER");
  const [urlInput, setUrlInput] = useState("");
  const [promptInput, setPromptInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      let cmdType = "UPLOAD_ASSET";
      if (sourceType === "URL") cmdType = "IMPORT_ASSET";
      if (sourceType === "GENERATION") cmdType = "REQUEST_ASSET_GENERATION";

      const res = await fetch("/api/v2/video-production/assets/commands", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command_type: cmdType,
          project_id: "prj_default",
          target_revision_id: "rev_0",
          entity_id: `ast_${Date.now()}`,
          reason: "Acquisition wizard submit",
          payload: {
            name: assetName || "New Acquired Asset",
            kind,
            source_url: urlInput,
            prompt: promptInput,
            license_state: "UNKNOWN",
          },
        }),
      });

      if (res.ok) {
        onSuccess();
        onClose();
      }
    } catch (err) {
      console.error("Failed asset acquisition:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: "8px", width: "480px", padding: "24px", color: "#e2e8f0" }}>
        <h2 style={{ margin: "0 0 16px 0", fontSize: "1.1rem", color: "#38bdf8" }}>Acquire / Import Production Asset</h2>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <label style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700 }}>Acquisition Method</label>
            <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
              <button
                type="button"
                onClick={() => setSourceType("UPLOAD")}
                style={{ flex: 1, padding: "8px", background: sourceType === "UPLOAD" ? "#0284c7" : "#0f172a", color: "#fff", border: "1px solid #334155", borderRadius: "4px", cursor: "pointer" }}
              >
                Local Upload
              </button>
              <button
                type="button"
                onClick={() => setSourceType("URL")}
                style={{ flex: 1, padding: "8px", background: sourceType === "URL" ? "#0284c7" : "#0f172a", color: "#fff", border: "1px solid #334155", borderRadius: "4px", cursor: "pointer" }}
              >
                URL Import
              </button>
              <button
                type="button"
                onClick={() => setSourceType("GENERATION")}
                style={{ flex: 1, padding: "8px", background: sourceType === "GENERATION" ? "#0284c7" : "#0f172a", color: "#fff", border: "1px solid #334155", borderRadius: "4px", cursor: "pointer" }}
              >
                AI Generation
              </button>
            </div>
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700 }}>Asset Name</label>
            <input
              type="text"
              required
              value={assetName}
              onChange={(e) => setAssetName(e.target.value)}
              placeholder="e.g. Cyberpunk Speeder Model"
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            />
          </div>

          <div>
            <label style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700 }}>Production Asset Kind Taxonomy</label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
            >
              <option value="CHARACTER">Character</option>
              <option value="ENVIRONMENT">Environment</option>
              <option value="PROP">Prop</option>
              <option value="MODEL_3D">3D Model</option>
              <option value="MATERIAL">Material</option>
              <option value="MUSIC">Music</option>
              <option value="SFX">SFX</option>
            </select>
          </div>

          {sourceType === "URL" && (
            <div>
              <label style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700 }}>External Source URL</label>
              <input
                type="url"
                required
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="https://example.com/asset.glb"
                style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
              />
            </div>
          )}

          {sourceType === "GENERATION" && (
            <div>
              <label style={{ fontSize: "0.75rem", color: "#94a3b8", fontWeight: 700 }}>Generation Prompt & Style Target</label>
              <textarea
                rows={3}
                required
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                placeholder="Describe desired 3D asset mesh style, proportions, and lighting budget..."
                style={{ width: "100%", padding: "8px", marginTop: "4px", background: "#0f172a", border: "1px solid #334155", borderRadius: "4px", color: "#fff" }}
              />
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "8px" }}>
            <button
              type="button"
              onClick={onClose}
              style={{ padding: "8px 16px", background: "#334155", color: "#e2e8f0", border: "none", borderRadius: "4px", cursor: "pointer" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              style={{ padding: "8px 16px", background: "#0284c7", color: "#fff", border: "none", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}
            >
              {isSubmitting ? "Submitting..." : "Acquire Asset"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
