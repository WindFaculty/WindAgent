import { useState } from "react";

export interface EpisodeItem {
  id: string;
  title: string;
  seriesName: string;
  status: "COMPLETED" | "IN_PROGRESS" | "DRAFT" | "READY";
  progress: number;
  updatedAt: string;
  thumbnailUrl?: string;
  description: string;
  currentCheckpoint: string;
}

const DEFAULT_EPISODES: EpisodeItem[] = [
  {
    id: "ep_01",
    title: "Tập 01: Khởi đầu mới",
    seriesName: "Chú thỏ và cánh diều",
    status: "COMPLETED",
    progress: 100,
    updatedAt: "2 giờ trước",
    thumbnailUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuDcTFM4oPy2bNuiGZ6VtddmiE_doc5m1r8jug016IQU3bkNsbuQrP7knXFTbAxOQkVLPpeA0oDoz6FX9T87sRvogDFePuZuBpF-D4RtsFyiaIj82UxumiGF71VIqYf7jM50zy7Ck7OYfpWXRriB6a8wVX2UsSU-ow0Euxb4TO4V5rnMa--xnJuHJhRR6Vwgl2FoEt6fhPv_BaOmRqrfXlP5UYbQ5QHPElJQTtJV1tIkOK-n-EwLttC_Ig",
    description: "Câu chuyện bắt đầu tại vùng đồng cỏ rực rỡ nơi Kaelen phát hiện ra những bí mật đầu tiên.",
    currentCheckpoint: "LOCKED / READY_FOR_PRODUCTION",
  },
  {
    id: "ep_02",
    title: "Tập 02: Bóng tối trỗi dậy",
    seriesName: "Chú thỏ và cánh diều",
    status: "IN_PROGRESS",
    progress: 65,
    updatedAt: "10 phút trước",
    thumbnailUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuAIgaaKzBjOF3Eh_oV9kMSRplOGw7epnL6s10BJ4cBDZ0fbDzzaHAHkyd1pCCXws-pOV7qPdGfsNs3wnUwywpaMv2loX0sIkTBORYVC4I4qyr1tX9ujFo_wNkmNsNfmDqOOZhlsW80yJA92Icvpdjkaa4EJBdVJ7JB0q-Q1QMQ5jFnGDYnnSxfuqkcCDzeCV43-gxerFMf_KYJIXzixEnFN7SG3iI3aEeI-8LBDGQ9jI9kbQNmeMQ4uKw",
    description: "Nhóm bạn phải đối mặt với chướng ngại vật lớn nhất khi cơn bão đêm tràn qua thung lũng.",
    currentCheckpoint: "SCREENPLAY_REVIEW",
  },
  {
    id: "ep_03",
    title: "Tập 03: Bản ngã & Hy vọng",
    seriesName: "Chú thỏ và cánh diều",
    status: "DRAFT",
    progress: 25,
    updatedAt: "Hôm qua",
    description: "Phát triển dàn ý chi tiết về cuộc đối đầu giữa Kaelen và Sylas tại thành phố neon.",
    currentCheckpoint: "STORY_BIBLE_GEN",
  },
];

export function EpisodesPage() {
  const [episodes, setEpisodes] = useState<EpisodeItem[]>(DEFAULT_EPISODES);
  const [search, setSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>("");
  const [newDesc, setNewDesc] = useState<string>("");

  const filtered = episodes.filter((ep) => {
    const matchesSearch =
      ep.title.toLowerCase().includes(search.toLowerCase()) ||
      ep.seriesName.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === "ALL" || ep.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const handleAddEpisode = () => {
    if (!newTitle.trim()) return;
    const fresh: EpisodeItem = {
      id: `ep_${Date.now()}`,
      title: newTitle.trim(),
      seriesName: "Chú thỏ và cánh diều",
      status: "DRAFT",
      progress: 5,
      updatedAt: "Vừa xong",
      description: newDesc.trim() || "Tập phim mới vừa được khởi tạo.",
      currentCheckpoint: "IDEA_SELECTION",
    };
    setEpisodes((prev) => [fresh, ...prev]);
    setNewTitle("");
    setNewDesc("");
    setShowAddModal(false);
  };

  return (
    <main className="flex-1 bg-background text-on-surface p-6 min-h-screen space-y-6 overflow-y-auto">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-outline-variant/10">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
            <span className="material-symbols-outlined text-primary text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
              movie
            </span>
            Danh sách Tập phim (Episodes)
          </h1>
          <p className="text-xs text-on-surface-variant mt-1">
            Quản lý tiến độ sản xuất, kịch bản phân cảnh và pipeline kiểm duyệt từng tập phim.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <span className="material-symbols-outlined absolute left-3 top-2.5 text-on-surface-variant text-sm">
              search
            </span>
            <input
              type="text"
              placeholder="Tìm tập phim..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-surface-container border border-outline-variant/20 rounded-lg py-1.5 pl-9 pr-4 text-xs text-on-surface focus:outline-none focus:border-primary w-56 transition-all"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-surface-container border border-outline-variant/20 rounded-lg py-1.5 px-3 text-xs text-on-surface focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="ALL" className="bg-surface-container-high">Tất cả trạng thái</option>
            <option value="COMPLETED" className="bg-surface-container-high">Đã hoàn thành</option>
            <option value="IN_PROGRESS" className="bg-surface-container-high">Đang sản xuất</option>
            <option value="DRAFT" className="bg-surface-container-high">Đang soạn thảo</option>
          </select>

          <button
            onClick={() => setShowAddModal(true)}
            className="bg-primary hover:bg-primary-container text-on-primary font-semibold text-xs py-2 px-4 rounded-lg flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(77,142,255,0.25)] whitespace-nowrap"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Thêm Tập Mới
          </button>
        </div>
      </div>

      {/* Episodes Grid Layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filtered.map((ep) => (
          <div
            key={ep.id}
            className={`group bg-surface-container-low rounded-xl border transition-all duration-300 overflow-hidden flex flex-col justify-between ${
              ep.status === "IN_PROGRESS"
                ? "border-primary/40 shadow-[0_0_20px_rgba(77,142,255,0.15)] hover:border-primary"
                : "border-outline-variant/15 hover:border-primary/40"
            }`}
          >
            {/* Thumbnail Header */}
            <div className="relative h-44 bg-surface-container-highest overflow-hidden">
              {ep.thumbnailUrl ? (
                <img
                  src={ep.thumbnailUrl}
                  alt={ep.title}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-on-surface-variant/40">
                  <span className="material-symbols-outlined text-5xl">movie</span>
                </div>
              )}
              <div className="absolute top-3 left-3">
                <span
                  className={`px-2.5 py-1 rounded-md text-[10px] font-mono font-bold uppercase tracking-wider backdrop-blur-md border flex items-center gap-1.5 shadow-sm ${
                    ep.status === "COMPLETED"
                      ? "bg-secondary-container/80 text-on-secondary-container border-secondary/30"
                      : ep.status === "IN_PROGRESS"
                      ? "bg-primary-container/80 text-on-primary-container border-primary/30 animate-pulse"
                      : "bg-surface-container-high/80 text-on-surface-variant border-outline-variant/20"
                  }`}
                >
                  <span className="material-symbols-outlined text-xs">
                    {ep.status === "COMPLETED"
                      ? "check_circle"
                      : ep.status === "IN_PROGRESS"
                      ? "sync"
                      : "edit_note"}
                  </span>
                  {ep.status === "COMPLETED"
                    ? "Đã hoàn thành"
                    : ep.status === "IN_PROGRESS"
                    ? "Đang sản xuất"
                    : "Đang soạn thảo"}
                </span>
              </div>
            </div>

            {/* Body Info */}
            <div className="p-5 space-y-4 flex-1 flex flex-col justify-between">
              <div>
                <div className="text-[11px] font-mono text-primary font-semibold">{ep.seriesName}</div>
                <h3 className="text-lg font-bold text-on-surface mt-0.5 group-hover:text-primary transition-colors">
                  {ep.title}
                </h3>
                <p className="text-xs text-on-surface-variant line-clamp-2 mt-1.5 leading-relaxed">
                  {ep.description}
                </p>
              </div>

              {/* Progress Bar */}
              <div className="space-y-1.5 pt-2">
                <div className="flex justify-between text-xs font-mono">
                  <span className="text-on-surface-variant">Tiến độ kịch bản</span>
                  <span className={ep.status === "COMPLETED" ? "text-secondary font-bold" : "text-primary font-bold"}>
                    {ep.progress}%
                  </span>
                </div>
                <div className="w-full bg-surface-container-highest rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-1.5 rounded-full transition-all duration-500 ${
                      ep.status === "COMPLETED" ? "bg-secondary" : "bg-primary shadow-[0_0_8px_rgba(77,142,255,0.8)]"
                    }`}
                    style={{ width: `${ep.progress}%` }}
                  />
                </div>
              </div>

              {/* Footer Actions & Timestamp */}
              <div className="pt-3 border-t border-outline-variant/10 flex items-center justify-between text-xs">
                <span className="text-[11px] text-on-surface-variant flex items-center gap-1 font-mono">
                  <span className="material-symbols-outlined text-xs">schedule</span>
                  {ep.updatedAt}
                </span>

                <a
                  href={`#/studio/episodes/${ep.id}`}
                  className="px-3 py-1.5 rounded-lg border border-primary/30 text-primary hover:bg-primary/10 transition-colors font-semibold flex items-center gap-1"
                >
                  <span>Mở Workspace</span>
                  <span className="material-symbols-outlined text-xs">arrow_forward</span>
                </a>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modal Thêm Tập Mới */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface-container-low border border-outline-variant/20 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h3 className="text-xl font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">video_call</span>
              Thêm Tập phim Mới
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Tên tập phim</label>
                <input
                  type="text"
                  placeholder="Ví dụ: Tập 04: Ánh sáng cuối đường hầm..."
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Mô tả tóm tắt</label>
                <textarea
                  rows={3}
                  placeholder="Tóm tắt ý tưởng kịch bản cho tập phim này..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary resize-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-xs font-semibold text-on-surface-variant hover:text-on-surface"
              >
                Hủy
              </button>
              <button
                onClick={handleAddEpisode}
                disabled={!newTitle.trim()}
                className="px-4 py-2 bg-primary text-on-primary font-semibold text-xs rounded-lg hover:bg-primary-container disabled:opacity-50"
              >
                Khởi tạo tập phim
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
