import { useState } from "react";

export interface ReviewComment {
  id: string;
  author: string;
  role: "Director Agent" | "You" | "Producer Agent";
  timestamp: string;
  text: string;
  avatarUrl?: string;
}

export interface ReviewVersion {
  version: string;
  label: string;
  status: "Pending" | "Approved" | "Revision Needed";
  description: string;
  timestamp: string;
}

const DEFAULT_VERSIONS: ReviewVersion[] = [
  {
    version: "v3.0",
    label: "v3.0 - Hiện tại",
    status: "Pending",
    description: "Director Agent đã cập nhật hiệu ứng ánh sáng neon trong phân cảnh 4.",
    timestamp: "10:42 AM",
  },
  {
    version: "v2.1",
    label: "v2.1 - Chỉnh sửa",
    status: "Revision Needed",
    description: "Người dùng yêu cầu tăng độ tương phản và giảm độ chói của biển hiệu.",
    timestamp: "Hôm qua",
  },
  {
    version: "v1.0",
    label: "v1.0 - Khởi tạo",
    status: "Approved",
    description: "Bản dựng kịch bản gốc từ ý tưởng ban đầu.",
    timestamp: "10/08/2025",
  },
];

const DEFAULT_COMMENTS: ReviewComment[] = [
  {
    id: "c1",
    author: "Director Agent",
    role: "Director Agent",
    timestamp: "10:42 AM",
    text: "Tôi đã điều chỉnh lại tone màu hẻm phố theo đúng phong cách 'neo-noir' bạn yêu cầu. Ánh đèn neon phản chiếu trên mặt đường ướt rõ nét hơn.",
    avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuB_nqZH2fvi4pDA5m61GV4-goP1yeWlGxso8tdO6Lkuc9lVr8uDiIP4OSd8DO85_PC5nMnW5SCAC3Ih63KWCIEx7HEe3KI1t9MqwuBpov6QQefRaBekcChyAO3ZsV_aUyjLp1_fbMz61gg0GsHCDFy-TytcszA_CNpCmV0eVaWqVhLmL5DVd4QmmZol6Bd_A9s9UnD7397otCi8hl0D32M7vZQMh-7LeYn2CfQRvqTjScmYG-SmUCfE7Q",
  },
  {
    id: "c2",
    author: "Bạn",
    role: "You",
    timestamp: "10:45 AM",
    text: "Trông tốt hơn nhiều đấy! Hãy giảm bớt một chút độ chói (bloom) của biển hiệu holographic trung tâm để không làm phân tán sự chú ý vào nhân vật.",
    avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuBgUs-0k8UL8P8R9SJctaRINGmND-8G0_va6zMRkWs0To8uFvpJwyaWMxx-5mY66gsMXrJzQLwaXQv9lsufdyQXIOpcJUrqg2q9gHYLJFWuxg83k2zowEN_JpBvxyJTWtfbxGFv38uh7h2RRM3w_U_z8iXp6CAvnMSVMimJXY6PBILrraIQQbz-CG_9Xp-cWcvre1P-eA5PVz0NKQgB-IjyZvGT1AAfkzHOSg2ZUd8bTVu4yI0wdUskdQ",
  },
];

export function ReviewsPage() {
  const [reviewStatus, setReviewStatus] = useState<"Pending" | "Approved" | "Revision Needed">("Pending");
  const [comments, setComments] = useState<ReviewComment[]>(DEFAULT_COMMENTS);
  const [newCommentText, setNewCommentText] = useState<string>("");
  const [isPlaying, setIsPlaying] = useState<boolean>(false);

  const handleSendComment = () => {
    if (!newCommentText.trim()) return;
    const fresh: ReviewComment = {
      id: `c_${Date.now()}`,
      author: "Bạn",
      role: "You",
      timestamp: "Vừa xong",
      text: newCommentText.trim(),
      avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuBgUs-0k8UL8P8R9SJctaRINGmND-8G0_va6zMRkWs0To8uFvpJwyaWMxx-5mY66gsMXrJzQLwaXQv9lsufdyQXIOpcJUrqg2q9gHYLJFWuxg83k2zowEN_JpBvxyJTWtfbxGFv38uh7h2RRM3w_U_z8iXp6CAvnMSVMimJXY6PBILrraIQQbz-CG_9Xp-cWcvre1P-eA5PVz0NKQgB-IjyZvGT1AAfkzHOSg2ZUd8bTVu4yI0wdUskdQ",
    };
    setComments((prev) => [...prev, fresh]);
    setNewCommentText("");
  };

  return (
    <main className="flex-1 bg-background text-on-surface p-6 h-screen flex flex-col space-y-4 overflow-hidden">
      {/* Context Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl bg-surface-container-low border border-outline-variant/15 shrink-0">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="px-2.5 py-0.5 rounded-full bg-surface-container-high border border-outline-variant/20 text-[10px] font-mono font-bold text-on-surface-variant">
              TẬP 04 (EPISODE 04)
            </span>
            <h2 className="text-xl font-extrabold text-on-surface">The Neon Ascendancy</h2>
          </div>
          <p className="text-xs text-on-surface-variant">
            Đánh giá phân cảnh storyboard tự động sinh và độ đồng bộ kịch bản.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className={`px-3 py-1 rounded-full text-xs font-mono font-bold uppercase flex items-center gap-1.5 border ${
              reviewStatus === "Approved"
                ? "bg-secondary/10 text-secondary border-secondary/30"
                : reviewStatus === "Revision Needed"
                ? "bg-error/10 text-error border-error/30"
                : "bg-primary/10 text-primary border-primary/30"
            }`}
          >
            <span className="material-symbols-outlined text-xs">
              {reviewStatus === "Approved" ? "check_circle" : reviewStatus === "Revision Needed" ? "warning" : "pending"}
            </span>
            {reviewStatus === "Approved" ? "Đã duyệt" : reviewStatus === "Revision Needed" ? "Cần sửa" : "Chờ duyệt"}
          </span>

          <button
            onClick={() => setReviewStatus("Revision Needed")}
            className="px-3.5 py-1.5 rounded-lg border border-outline-variant/30 text-on-surface hover:bg-surface-container-high transition-colors text-xs font-semibold"
          >
            Yêu cầu sửa (Revision)
          </button>

          <button
            onClick={() => setReviewStatus("Approved")}
            className="px-4 py-1.5 rounded-lg bg-primary text-on-primary hover:bg-primary-container transition-colors text-xs font-semibold shadow-[0_0_15px_rgba(77,142,255,0.25)]"
          >
            Duyệt Nội dung (Approve)
          </button>
        </div>
      </div>

      {/* Split Screen Workspace */}
      <div className="flex-1 flex gap-6 overflow-hidden min-h-0">
        {/* Left: Simulated Media Viewer */}
        <div className="flex-1 bg-surface-container-low border border-outline-variant/15 rounded-xl overflow-hidden flex flex-col relative group">
          <div className="flex-1 relative bg-black flex items-center justify-center overflow-hidden">
            <img
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuD_cgIIhWTV7vwSP3e-YHSRf2VUQVuw6O8JzfU-nEN7kwC4qUC56KKitvV_m4FOFQ0Cy-9AxvZN3TKzjO4Cpm5UOaSuzvUOXh5STpEE5UnsUTOMvLWM-6O_F8QT-QGVDDZNV22BaT7uszt9MQa0CGfpgSe8mnpkegIkOMbTbu_ibI4V9kMi6hwLPmKaOF7iX7sWi1VgSDJorOeI6hp2eKTkAxqd9XDBEDm2749rqw3Q2IBxVLQI2dHbzQ"
              alt="Review Storyboard Preview"
              className="w-full h-full object-cover opacity-85"
            />

            {/* Video Controls Overlay */}
            <div className="absolute inset-x-0 bottom-0 p-4 bg-gradient-to-t from-black/90 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300">
              <div className="flex items-center gap-4 text-on-surface">
                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="p-1.5 hover:text-primary transition-colors cursor-pointer"
                >
                  <span className="material-symbols-outlined text-2xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                    {isPlaying ? "pause" : "play_arrow"}
                  </span>
                </button>

                <div className="flex-1 h-1.5 bg-surface-variant/40 rounded-full overflow-hidden relative cursor-pointer">
                  <div className="absolute left-0 top-0 bottom-0 w-1/3 bg-primary" />
                </div>

                <span className="text-xs font-mono">01:24 / 04:10</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Feedback & Info Panel */}
        <div className="w-96 shrink-0 flex flex-col gap-4 overflow-y-auto">
          {/* Version History Bento */}
          <div className="bg-surface-container-low border border-outline-variant/15 rounded-xl p-4">
            <h3 className="text-xs font-mono uppercase text-on-surface-variant font-bold mb-3 flex items-center gap-2">
              <span className="material-symbols-outlined text-sm">history</span> Lịch sử Phiên bản
            </h3>
            <div className="space-y-3">
              {DEFAULT_VERSIONS.map((v, idx) => (
                <div key={idx} className="flex gap-3 text-xs">
                  <div className="mt-0.5 w-4 h-4 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                  </div>
                  <div>
                    <div className="font-bold text-on-surface flex items-center gap-2">
                      <span>{v.label}</span>
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-surface-container-high text-on-surface-variant">
                        {v.timestamp}
                      </span>
                    </div>
                    <p className="text-[11px] text-on-surface-variant mt-0.5">{v.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Conversation Thread */}
          <div className="bg-surface-container-low border border-outline-variant/15 rounded-xl flex-1 flex flex-col overflow-hidden min-h-[350px]">
            <div className="p-3.5 border-b border-outline-variant/10 shrink-0">
              <h3 className="text-xs font-mono uppercase text-on-surface-variant font-bold flex items-center gap-2">
                <span className="material-symbols-outlined text-sm">forum</span> Ghi chú & Đóng góp ý kiến
              </h3>
            </div>

            <div className="flex-1 p-4 space-y-3 overflow-y-auto">
              {comments.map((c) => (
                <div key={c.id} className={`flex gap-3 ${c.role === "You" ? "flex-row-reverse" : ""}`}>
                  <div className="w-7 h-7 rounded-full bg-surface-container-highest shrink-0 overflow-hidden border border-outline-variant/20">
                    <img src={c.avatarUrl} alt={c.author} className="w-full h-full object-cover" />
                  </div>
                  <div
                    className={`flex-1 rounded-xl p-3 text-xs space-y-1 ${
                      c.role === "You"
                        ? "bg-primary-container/20 border border-primary/20 text-right"
                        : "bg-surface-container border border-outline-variant/10"
                    }`}
                  >
                    <div className={`flex items-center justify-between ${c.role === "You" ? "flex-row-reverse" : ""}`}>
                      <span className="font-bold text-primary">{c.author}</span>
                      <span className="text-[10px] font-mono text-on-surface-variant">{c.timestamp}</span>
                    </div>
                    <p className="text-on-surface leading-relaxed">{c.text}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Input Box */}
            <div className="p-3 border-t border-outline-variant/10 bg-surface-container-low shrink-0">
              <div className="relative">
                <textarea
                  rows={2}
                  placeholder="Gửi phản hồi hoặc yêu cầu chỉnh sửa..."
                  value={newCommentText}
                  onChange={(e) => setNewCommentText(e.target.value)}
                  className="w-full bg-surface-container border border-outline-variant/20 rounded-lg p-2.5 pr-10 text-xs text-on-surface focus:outline-none focus:border-primary resize-none"
                />
                <button
                  onClick={handleSendComment}
                  className="absolute right-2 bottom-2 p-1.5 rounded-md text-primary hover:bg-primary/10 transition-colors"
                >
                  <span className="material-symbols-outlined text-base">send</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
