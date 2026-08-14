import { useState } from "react";

export interface StoryBoardScene {
  id: string;
  sceneNumber: number;
  title: string;
  status: "Drafted" | "Generating" | "Outline Only" | "Locked";
  scriptText: string;
  duration: string;
  location: string;
  characters: string[];
  imageUrl?: string;
}

const DEFAULT_SCENES: StoryBoardScene[] = [
  {
    id: "scene_01",
    sceneNumber: 1,
    title: "Phát hiện bí mật (The Discovery)",
    status: "Drafted",
    scriptText: "Elara tình cờ tìm thấy khu rừng cổ đại. Không khí dày đặc sương mù và những cái cây phát ra năng lượng tần số thấp. Cô chạm vào biểu tượng ánh sáng trên thân cây sồi trung tâm.",
    duration: "2m 30s",
    location: "Ext. Woods",
    characters: ["EL", "KV"],
    imageUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuBr5Uh-38OHiIL7GgVuxLvvDVZaDFZ27Xus-xnSN6XsArnpW_s749smSwUtGhu0LYcLXUDPRFgx7N9Ft_Xjp0G_hFVqphb_Y4Yw3HPo0g1IGZKxtqSoi2cPMogT5B5tTvy__WO7PbWqTir6bPD3phjSKEvRGCADa1UhskgE7xr7PoFTgcPdhrQrqbznusC0gQFN6jjHUCdwXW9naS3UnR4S4nZ7tHkI8DOeAnDciohbZyTzgX-Tmu4xmw",
  },
  {
    id: "scene_02",
    sceneNumber: 2,
    title: "Vệ binh thức giấc (The Guardian Awakens)",
    status: "Generating",
    scriptText: "Mặt đất rung chuyển khi rễ cây xé toạc lòng đất. Một sinh vật khổng lồ làm từ đất và những cành cây đan xen vươn dậy trước mặt Elara.",
    duration: "1m 45s",
    location: "Ext. Woods",
    characters: ["EL", "GR"],
  },
  {
    id: "scene_03",
    sceneNumber: 3,
    title: "Giao ước cổ đại (The Bargain)",
    status: "Outline Only",
    scriptText: "Elara cố gắng giao tiếp với Vệ binh. Cô phải đánh đổi một vật có giá trị để được phép tiến vào vùng thánh địa bên trong.",
    duration: "3m 10s",
    location: "Int. Ancient Sanctum",
    characters: ["EL"],
  },
];

export function StoryBoardPage() {
  const [scenes, setScenes] = useState<StoryBoardScene[]>(DEFAULT_SCENES);
  const [activeProject] = useState<string>("The Whispering Woods - Ep 01");
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>("");
  const [newLocation, setNewLocation] = useState<string>("Ext. Woods");
  const [newScript, setNewScript] = useState<string>("");

  const handleAddScene = () => {
    if (!newTitle.trim()) return;
    const fresh: StoryBoardScene = {
      id: `scene_${Date.now()}`,
      sceneNumber: scenes.length + 1,
      title: newTitle.trim(),
      status: "Outline Only",
      scriptText: newScript.trim() || "Nội dung phân cảnh mới vừa được khởi tạo.",
      duration: "2m 00s",
      location: newLocation.trim() || "Ext. Stage",
      characters: ["EL"],
    };
    setScenes((prev) => [...prev, fresh]);
    setNewTitle("");
    setNewScript("");
    setShowAddModal(false);
  };

  const handleGenerateArt = (sceneId: string) => {
    setScenes((prev) =>
      prev.map((s) => (s.id === sceneId ? { ...s, status: "Generating" } : s))
    );

    setTimeout(() => {
      setScenes((prev) =>
        prev.map((s) =>
          s.id === sceneId
            ? {
                ...s,
                status: "Drafted",
                imageUrl:
                  "https://lh3.googleusercontent.com/aida-public/AB6AXuBr5Uh-38OHiIL7GgVuxLvvDVZaDFZ27Xus-xnSN6XsArnpW_s749smSwUtGhu0LYcLXUDPRFgx7N9Ft_Xjp0G_hFVqphb_Y4Yw3HPo0g1IGZKxtqSoi2cPMogT5B5tTvy__WO7PbWqTir6bPD3phjSKEvRGCADa1UhskgE7xr7PoFTgcPdhrQrqbznusC0gQFN6jjHUCdwXW9naS3UnR4S4nZ7tHkI8DOeAnDciohbZyTzgX-Tmu4xmw",
              }
            : s
        )
      );
    }, 2000);
  };

  return (
    <main className="flex-1 bg-background text-on-surface p-6 h-screen flex flex-col space-y-6 overflow-hidden">
      {/* Header & Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-outline-variant/10 shrink-0">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
            <span className="material-symbols-outlined text-primary text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
              grid_view
            </span>
            Bảng Phân cảnh (Story Board)
          </h1>
          <p className="text-xs text-on-surface-variant mt-1">
            Dự án: <span className="text-primary font-semibold cursor-pointer hover:underline">{activeProject}</span>
          </p>
        </div>

        {/* Toolbar Controls */}
        <div className="flex items-center gap-2 bg-surface-container-low p-1.5 rounded-xl border border-outline-variant/20">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary font-semibold text-xs shadow-[0_0_15px_rgba(77,142,255,0.25)] hover:bg-primary-container transition-all"
          >
            <span className="material-symbols-outlined text-sm">add_box</span>
            Thêm Phân cảnh
          </button>

          <button
            onClick={() => {
              const outlineScene = scenes.find((s) => s.status === "Outline Only");
              if (outlineScene) handleGenerateArt(outlineScene.id);
            }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high text-xs font-semibold transition-all"
          >
            <span className="material-symbols-outlined text-sm">brush</span>
            Tự động Sinh Concept Art
          </button>

          <button className="flex items-center gap-2 px-3 py-2 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high text-xs font-semibold transition-all">
            <span className="material-symbols-outlined text-sm">sync</span>
            Đồng bộ từ Kịch bản
          </button>
        </div>
      </div>

      {/* Story Board Sequence Canvas (Horizontal Flow) */}
      <div className="flex-1 overflow-x-auto overflow-y-hidden pb-4 flex gap-6 snap-x snap-mandatory relative items-stretch">
        {scenes.map((scene) => (
          <div
            key={scene.id}
            className="bg-surface-container-low border border-outline-variant/15 hover:border-primary/50 rounded-2xl p-5 flex flex-col justify-between min-w-[380px] max-w-[440px] shrink-0 snap-center transition-all duration-300 group"
          >
            {/* Header metadata */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="bg-surface-container-high text-on-surface font-mono font-bold text-xs px-2.5 py-1 rounded-md">
                  SCENE {scene.sceneNumber}
                </span>
                <span
                  className={`text-[10px] font-mono font-bold uppercase px-2.5 py-1 rounded-full border ${
                    scene.status === "Drafted"
                      ? "bg-secondary/10 text-secondary border-secondary/30"
                      : scene.status === "Generating"
                      ? "bg-primary/10 text-primary border-primary/30 animate-pulse"
                      : "bg-surface-container-highest text-on-surface-variant border-outline-variant/20"
                  }`}
                >
                  {scene.status === "Drafted"
                    ? "Hoàn tất Concept"
                    : scene.status === "Generating"
                    ? "Đang vẽ Concept..."
                    : "Chưa có hình ảnh"}
                </span>
              </div>
              <span className="material-symbols-outlined text-on-surface-variant text-sm cursor-pointer hover:text-primary">
                more_horiz
              </span>
            </div>

            {/* Concept Image / Render Frame */}
            <div className="relative w-full aspect-video rounded-xl overflow-hidden bg-surface-container-lowest border border-outline-variant/20 my-2 flex items-center justify-center">
              {scene.status === "Generating" ? (
                <div className="flex flex-col items-center gap-2 text-primary">
                  <span className="material-symbols-outlined text-3xl animate-spin">refresh</span>
                  <span className="text-xs font-mono">Rendering Concept Art...</span>
                </div>
              ) : scene.imageUrl ? (
                <div className="relative w-full h-full">
                  <img
                    src={scene.imageUrl}
                    alt={scene.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                  />
                  <div className="absolute bottom-2 right-2 bg-background/80 backdrop-blur px-2.5 py-1 rounded text-[10px] text-on-surface font-mono border border-outline-variant/20 flex items-center gap-1">
                    <span className="material-symbols-outlined text-xs text-primary">auto_awesome</span> AI Gen
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => handleGenerateArt(scene.id)}
                  className="flex flex-col items-center gap-1.5 text-on-surface-variant/60 hover:text-primary transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-4xl">image_search</span>
                  <span className="text-xs font-medium">Bấm để tạo Concept Art</span>
                </button>
              )}
            </div>

            {/* Script Text */}
            <div className="my-3 space-y-1.5 flex-1">
              <h3 className="font-bold text-on-surface text-base group-hover:text-primary transition-colors">
                {scene.title}
              </h3>
              <p className="text-xs text-on-surface-variant line-clamp-3 leading-relaxed">
                {scene.scriptText}
              </p>
            </div>

            {/* Footer Scene Info */}
            <div className="pt-3 border-t border-outline-variant/10 flex items-center justify-between text-xs text-on-surface-variant font-mono">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-xs">schedule</span> {scene.duration}
                </span>
                <span className="flex items-center gap-1">
                  <span className="material-symbols-outlined text-xs">location_on</span> {scene.location}
                </span>
              </div>

              <div className="flex -space-x-2">
                {scene.characters.map((c, idx) => (
                  <div
                    key={idx}
                    className="w-7 h-7 rounded-full bg-primary-container text-on-primary-container text-[10px] font-bold flex items-center justify-center border-2 border-surface-container-low"
                  >
                    {c}
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}

        {/* Add Scene Card Button */}
        <div className="min-w-[200px] flex items-center justify-center shrink-0">
          <button
            onClick={() => setShowAddModal(true)}
            className="w-20 h-20 rounded-full bg-surface-container-low border-2 border-dashed border-outline-variant/30 flex items-center justify-center text-on-surface-variant hover:text-primary hover:border-primary transition-all cursor-pointer shadow-lg hover:scale-105"
          >
            <span className="material-symbols-outlined text-3xl">add</span>
          </button>
        </div>
      </div>

      {/* Modal Thêm Scene Mới */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface-container-low border border-outline-variant/20 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h3 className="text-xl font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">add_box</span>
              Thêm Phân cảnh Phim Mới
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Tên phân cảnh</label>
                <input
                  type="text"
                  placeholder="Ví dụ: Phân cảnh 4: Thoát khỏi căn hầm..."
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Địa điểm (Location)</label>
                <input
                  type="text"
                  placeholder="Ví dụ: Ext. Woods / Int. Bunker..."
                  value={newLocation}
                  onChange={(e) => setNewLocation(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Mô tả hành động & thoại</label>
                <textarea
                  rows={3}
                  placeholder="Mô tả bối cảnh và diễn biến trong phân cảnh này..."
                  value={newScript}
                  onChange={(e) => setNewScript(e.target.value)}
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
                onClick={handleAddScene}
                disabled={!newTitle.trim()}
                className="px-4 py-2 bg-primary text-on-primary font-semibold text-xs rounded-lg hover:bg-primary-container disabled:opacity-50"
              >
                Tạo phân cảnh
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
