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
    <div className="flex flex-col h-full w-full bg-background text-on-surface min-h-screen overflow-hidden">
      {/* Top Header */}
      <div className="px-6 py-4 border-b border-outline-variant/15 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface-container-low/80 backdrop-blur-md">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
            <span className="material-symbols-outlined text-primary text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
              inventory_2
            </span>
            Thư viện Tài sản & Media (Media Library)
          </h1>
          <p className="text-xs text-on-surface-variant mt-1">
            Quản lý, phân loại taxonomy và kiểm duyệt bản quyền cho các tài sản sáng tạo.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsAcquisitionOpen(true)}
            className="px-4 py-2 bg-primary text-on-primary font-semibold rounded-lg hover:bg-primary-container transition-all flex items-center gap-2 text-sm shadow-[0_0_15px_rgba(77,142,255,0.2)]"
          >
            <span className="material-symbols-outlined text-sm">cloud_upload</span>
            + Nhập / Tạo Tài sản Mới
          </button>
          {selectedAsset && (
            <button
              onClick={() => setIsImpactModalOpen(true)}
              className="px-3 py-2 bg-surface-container-high hover:bg-surface-container-highest border border-outline-variant/20 rounded-lg text-on-surface text-xs font-medium transition-all"
            >
              Xem Ảnh hưởng Phiên bản
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Filter Sidebar */}
        <aside className="w-64 border-r border-outline-variant/15 bg-surface-container-low p-4 flex flex-col gap-4 overflow-y-auto shrink-0">
          <div>
            <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1.5">
              Tìm kiếm
            </label>
            <div className="relative">
              <span className="material-symbols-outlined absolute left-2.5 top-2 text-on-surface-variant text-sm">
                search
              </span>
              <input
                type="text"
                placeholder="Tìm tên tài sản..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary transition-all"
              />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1.5">
              Loại Tài sản (Taxonomy)
            </label>
            <select
              value={selectedKind}
              onChange={(e) => setSelectedKind(e.target.value)}
              className="w-full py-1.5 px-3 text-xs bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary transition-all cursor-pointer"
            >
              <option value="ALL" className="bg-surface-container-high">Tất cả thể loại</option>
              <option value="CHARACTER" className="bg-surface-container-high">Nhân vật (Character)</option>
              <option value="ENVIRONMENT" className="bg-surface-container-high">Thế giới / Bối cảnh</option>
              <option value="PROP" className="bg-surface-container-high">Đạo cụ (Prop)</option>
              <option value="MODEL_3D" className="bg-surface-container-high">Mô hình 3D</option>
              <option value="MATERIAL" className="bg-surface-container-high">Material</option>
              <option value="TEXTURE" className="bg-surface-container-high">Texture / Mat</option>
              <option value="MUSIC" className="bg-surface-container-high">Âm nhạc (Music)</option>
              <option value="SFX" className="bg-surface-container-high">Hiệu ứng âm thanh (SFX)</option>
              <option value="DIALOGUE_AUDIO" className="bg-surface-container-high">Thoại (Dialogue Audio)</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1.5">
              Bản quyền (License)
            </label>
            <select
              value={selectedLicense}
              onChange={(e) => setSelectedLicense(e.target.value)}
              className="w-full py-1.5 px-3 text-xs bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary transition-all cursor-pointer"
            >
              <option value="ALL" className="bg-surface-container-high">Tất cả bản quyền</option>
              <option value="UNKNOWN" className="bg-surface-container-high">Chưa rõ (Blocked)</option>
              <option value="LICENSED" className="bg-surface-container-high">Đã cấp phép (Licensed)</option>
              <option value="CREATIVE_COMMONS" className="bg-surface-container-high">Creative Commons</option>
              <option value="PUBLIC_DOMAIN" className="bg-surface-container-high">Public Domain</option>
            </select>
          </div>

          <div>
            <label className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider block mb-1.5">
              Vòng đời (Lifecycle)
            </label>
            <select
              value={selectedLifecycle}
              onChange={(e) => setSelectedLifecycle(e.target.value)}
              className="w-full py-1.5 px-3 text-xs bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary transition-all cursor-pointer"
            >
              <option value="ALL" className="bg-surface-container-high">Tất cả vòng đời</option>
              <option value="DISCOVERED" className="bg-surface-container-high">Đã phát hiện (Discovered)</option>
              <option value="DOWNLOADED" className="bg-surface-container-high">Đã tải về (Downloaded)</option>
              <option value="VALIDATED" className="bg-surface-container-high">Đã xác minh (Validated)</option>
              <option value="APPROVED" className="bg-surface-container-high">Đã duyệt (Approved)</option>
              <option value="BOUND_TO_PROJECT" className="bg-surface-container-high">Gắn vào dự án</option>
              <option value="REJECTED" className="bg-surface-container-high">Từ chối (Rejected)</option>
            </select>
          </div>

          <AssetJobMonitor />
        </aside>

        {/* Center Grid/List View Stage */}
        <main className="flex-1 p-5 overflow-y-auto space-y-4">
          <div className="flex justify-between items-center text-xs text-on-surface-variant">
            <span>Hiển thị {assets.length} tài sản media</span>
            <div className="flex gap-1 bg-surface-container-high p-1 rounded-lg">
              <button
                onClick={() => setViewMode("grid")}
                className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
                  viewMode === "grid" ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                Grid
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`px-3 py-1 rounded text-xs font-semibold transition-all ${
                  viewMode === "list" ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface"
                }`}
              >
                List
              </button>
            </div>
          </div>

          {isLoading ? (
            <div className="text-on-surface-variant text-center py-16 text-sm">Đang tải danh sách tài sản...</div>
          ) : viewMode === "grid" ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {assets.map((asset) => {
                const isSelected = selectedAssetId === asset.asset_id;
                return (
                  <div
                    key={asset.asset_id}
                    onClick={() => setSelectedAssetId(asset.asset_id)}
                    className={`p-3 rounded-xl bg-surface-container-low border transition-all cursor-pointer flex flex-col justify-between group ${
                      isSelected
                        ? "border-primary shadow-[0_0_15px_rgba(77,142,255,0.25)]"
                        : "border-outline-variant/15 hover:border-primary/40 hover:-translate-y-0.5"
                    }`}
                  >
                    <div className="h-32 bg-surface-container-lowest rounded-lg flex flex-col items-center justify-center text-on-surface-variant group-hover:text-primary transition-colors relative overflow-hidden">
                      <span className="material-symbols-outlined text-4xl">
                        {asset.media_type === "model_3d"
                          ? "view_in_ar"
                          : asset.media_type === "audio"
                          ? "audio_file"
                          : "image"}
                      </span>
                      <span className="text-[10px] mt-1 font-mono uppercase tracking-wider">
                        {asset.media_type}
                      </span>
                    </div>

                    <div className="mt-3">
                      <div className="font-bold text-sm text-on-surface truncate">{asset.name}</div>
                      <div className="text-xs text-primary font-medium mt-0.5">{asset.kind}</div>
                      <div className="flex justify-between items-center mt-3 text-[11px]">
                        <span
                          className={`font-semibold px-1.5 py-0.5 rounded ${
                            asset.license_state === "UNKNOWN"
                              ? "bg-error-container/20 text-error"
                              : "bg-secondary/10 text-secondary"
                          }`}
                        >
                          {asset.license_state}
                        </span>
                        <span className="text-on-surface-variant">{asset.lifecycle_state}</span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-outline-variant/15 overflow-hidden bg-surface-container-low">
              <table className="w-full text-left text-xs text-on-surface">
                <thead className="bg-surface-container-high/60 text-on-surface-variant border-b border-outline-variant/10 font-bold uppercase tracking-wider">
                  <tr>
                    <th className="p-3">Tên tài sản</th>
                    <th className="p-3">Taxonomy Kind</th>
                    <th className="p-3">Media</th>
                    <th className="p-3">Bản quyền</th>
                    <th className="p-3">Vòng đời</th>
                    <th className="p-3">Active Revision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/10">
                  {assets.map((asset) => (
                    <tr
                      key={asset.asset_id}
                      onClick={() => setSelectedAssetId(asset.asset_id)}
                      className={`cursor-pointer transition-colors ${
                        selectedAssetId === asset.asset_id
                          ? "bg-primary-container/20 text-primary font-semibold"
                          : "hover:bg-surface-container-high/40"
                      }`}
                    >
                      <td className="p-3 font-bold">{asset.name}</td>
                      <td className="p-3 text-primary">{asset.kind}</td>
                      <td className="p-3 uppercase">{asset.media_type}</td>
                      <td className="p-3">
                        <span
                          className={`px-1.5 py-0.5 rounded font-semibold ${
                            asset.license_state === "UNKNOWN"
                              ? "bg-error-container/20 text-error"
                              : "bg-secondary/10 text-secondary"
                          }`}
                        >
                          {asset.license_state}
                        </span>
                      </td>
                      <td className="p-3">{asset.lifecycle_state}</td>
                      <td className="p-3 font-mono text-[11px]">{asset.active_revision_id || "None"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>

        {/* Right Inspector Panel */}
        <aside className="w-80 border-l border-outline-variant/15 bg-surface-container-low overflow-y-auto shrink-0">
          {selectedAsset ? (
            <AssetInspector assetId={selectedAsset.asset_id} onRefresh={fetchAssets} />
          ) : (
            <div className="p-6 text-center text-xs text-on-surface-variant">Chọn một tài sản để xem chi tiết inspector</div>
          )}
        </aside>
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
