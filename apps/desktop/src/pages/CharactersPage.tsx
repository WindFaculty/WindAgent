import { useState } from "react";

export interface CharacterItem {
  id: string;
  name: string;
  role: "Protagonist" | "Antagonist" | "Supporting" | "Draft";
  dominantTrait: string;
  flaw: string;
  alignment: number; // 0 to 100
  bio: string;
  avatarUrl: string;
  bannerUrl: string;
  voiceModel: string;
  voiceStyle: string;
  traits: string[];
  connections: Array<{ name: string; type: "Ally" | "Rival" | "Mentor"; avatar: string }>;
}

const DEFAULT_CHARACTERS: CharacterItem[] = [
  {
    id: "char_kaelen",
    name: "Kaelen Vance",
    role: "Protagonist",
    dominantTrait: "Stoic",
    flaw: "Distrustful",
    alignment: 75,
    bio: "Một cựu đặc nhiệm bị bỏ lại tại các phân khu Outer Rim. Kaelen dựa vào sự chính xác trong chiến thuật và sự nghi ngờ chính quyền để sinh tồn. Mặc dù vẻ ngoài lạnh lùng, anh sở hữu một la bàn đạo đức kiên định.",
    avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuAgd7m-oW9qyLC5a5bN6PEkQPvlWxr9w3H3EWe_0HjIp5JQFQjB6vs18Bv78naoQwRLeS9Pt0yyvpjJ9SdPkeqW7SVJT1ud9XrPklJRGTl_ADpjiOwn_AFudC9gtAOuLI5_1NPgy4gHE2SieuARxed3GOE_pXydmJigzPvg7XpMasDsAPS2atdM0lL8Xz3ui2hPzu2FWEWSC7pHYpTt2PDdMsheSXc_7l12TIdTUg2CPtjz2rRZNoYs-g",
    bannerUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuALMt6gcEyDUU3ozmzONqnv-092PvpWyTnyKy2pz0VU_Wn-7pgTibgT1uSeS_aATbLUPNGBbXPnVrx_l4Q0N3WQYWF6yvfFkK4Ydr2m9gzv2H9zyeLS1JaUzDqOJ0VEkTfxDIux19LvJtMNcTUdKH4rVT1RHYJz5GiriaVrGGXoZfoEjm-UMOxCzMbfdwA3ADM99X24a2wZSku_aDE6DIGPMUCPyLC7TNhmbOyHhMPNDGqj8Se7nIexOg",
    voiceModel: "ELEVEN_GRIT_02",
    voiceStyle: "Trầm ấm, đanh thép, quyết đoán",
    traits: ["Stoic", "Tactical", "Ex-Operative"],
    connections: [
      { name: "Nova Tink", type: "Ally", avatar: "https://lh3.googleusercontent.com/aida-public/AB6AXuDPuuYLlSJxyPIPXIcLNYjpeUDIxje1V45ASKSC0qsaJs2P5XIKvY3UnBK5NVowErutYXTBcXyz98pRxFTlMSp7R3VvH6DhtFmSUiDb1-PUXk9en3mj6vQE9GAEVlsVySO3IRwy6WS6YgNyjavqfqVqVkeweYb4N0hYxNA9XbFIDHEBiZBduI4q9Bra-WvsSCMcS_GImga7uV8L9hjFq0_BH3Vc6xfV7PhhqzxQwcNMLfiqUpBL8f8kiQ" },
      { name: "Sylas Thorne", type: "Rival", avatar: "https://lh3.googleusercontent.com/aida-public/AB6AXuCZPETH2Zw2pFtVjzjV2CGr8jHIJpe9aRXrxH96hy7STEED1wRVAK5qbf_cHe_8sXcjJ9P3DKvrN0uvG3t70U9yGEYOAWuddclxQD_J3K8IK1qYZop96v3Zz8dfBy5E2zFyKWxmUkxwEhQldPf1fzOEhwpkM7m6QqSbeKAzj9v1q3zhfDCK0-a3fN1pSZs2iUChUKuMfhXxJJAGBL4bkJC_SZTnKo8jrEWM0RYjeHNo8Cpl9YEP8nadpQ" },
    ],
  },
  {
    id: "char_nova",
    name: "Nova Tink",
    role: "Supporting",
    dominantTrait: "Chaotic Good",
    flaw: "Impulsive",
    alignment: 60,
    bio: "Kỹ sư cơ khí thiên tài với tính cách lập dị. Nova có khả năng biến những phế liệu công nghệ thành vũ khí và thiết bị thông minh trong thời gian kỷ lục.",
    avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuDPuuYLlSJxyPIPXIcLNYjpeUDIxje1V45ASKSC0qsaJs2P5XIKvY3UnBK5NVowErutYXTBcXyz98pRxFTlMSp7R3VvH6DhtFmSUiDb1-PUXk9en3mj6vQE9GAEVlsVySO3IRwy6WS6YgNyjavqfqVqVkeweYb4N0hYxNA9XbFIDHEBiZBduI4q9Bra-WvsSCMcS_GImga7uV8L9hjFq0_BH3Vc6xfV7PhhqzxQwcNMLfiqUpBL8f8kiQ",
    bannerUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuALMt6gcEyDUU3ozmzONqnv-092PvpWyTnyKy2pz0VU_Wn-7pgTibgT1uSeS_aATbLUPNGBbXPnVrx_l4Q0N3WQYWF6yvfFkK4Ydr2m9gzv2H9zyeLS1JaUzDqOJ0VEkTfxDIux19LvJtMNcTUdKH4rVT1RHYJz5GiriaVrGGXoZfoEjm-UMOxCzMbfdwA3ADM99X24a2wZSku_aDE6DIGPMUCPyLC7TNhmbOyHhMPNDGqj8Se7nIexOg",
    voiceModel: "ELEVEN_ENERGETIC_01",
    voiceStyle: "Nhanh, hào hứng, tự nhiên",
    traits: ["Inventive", "Chaotic Good", "Engineer"],
    connections: [
      { name: "Kaelen Vance", type: "Ally", avatar: "https://lh3.googleusercontent.com/aida-public/AB6AXuAgd7m-oW9qyLC5a5bN6PEkQPvlWxr9w3H3EWe_0HjIp5JQFQjB6vs18Bv78naoQwRLeS9Pt0yyvpjJ9SdPkeqW7SVJT1ud9XrPklJRGTl_ADpjiOwn_AFudC9gtAOuLI5_1NPgy4gHE2SieuARxed3GOE_pXydmJigzPvg7XpMasDsAPS2atdM0lL8Xz3ui2hPzu2FWEWSC7pHYpTt2PDdMsheSXc_7l12TIdTUg2CPtjz2rRZNoYs-g" },
    ],
  },
  {
    id: "char_sylas",
    name: "Sylas Thorne",
    role: "Antagonist",
    dominantTrait: "Manipulative",
    flaw: "Arrogant",
    alignment: 20,
    bio: "Lãnh đạo ẩn danh của tổ chức bóng tối Syndicate. Sylas sử dụng trí tuệ cùng mạng lưới tình báo để kiểm soát nền kinh tế ngầm.",
    avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuCZPETH2Zw2pFtVjzjV2CGr8jHIJpe9aRXrxH96hy7STEED1wRVAK5qbf_cHe_8sXcjJ9P3DKvrN0uvG3t70U9yGEYOAWuddclxQD_J3K8IK1qYZop96v3Zz8dfBy5E2zFyKWxmUkxwEhQldPf1fzOEhwpkM7m6QqSbeKAzj9v1q3zhfDCK0-a3fN1pSZs2iUChUKuMfhXxJJAGBL4bkJC_SZTnKo8jrEWM0RYjeHNo8Cpl9YEP8nadpQ",
    bannerUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuALMt6gcEyDUU3ozmzONqnv-092PvpWyTnyKy2pz0VU_Wn-7pgTibgT1uSeS_aATbLUPNGBbXPnVrx_l4Q0N3WQYWF6yvfFkK4Ydr2m9gzv2H9zyeLS1JaUzDqOJ0VEkTfxDIux19LvJtMNcTUdKH4rVT1RHYJz5GiriaVrGGXoZfoEjm-UMOxCzMbfdwA3ADM99X24a2wZSku_aDE6DIGPMUCPyLC7TNhmbOyHhMPNDGqj8Se7nIexOg",
    voiceModel: "ELEVEN_SILK_05",
    voiceStyle: "Lạnh lùng, quý phái, súc tích",
    traits: ["Strategic", "Manipulative", "Mastermind"],
    connections: [
      { name: "Kaelen Vance", type: "Rival", avatar: "https://lh3.googleusercontent.com/aida-public/AB6AXuAgd7m-oW9qyLC5a5bN6PEkQPvlWxr9w3H3EWe_0HjIp5JQFQjB6vs18Bv78naoQwRLeS9Pt0yyvpjJ9SdPkeqW7SVJT1ud9XrPklJRGTl_ADpjiOwn_AFudC9gtAOuLI5_1NPgy4gHE2SieuARxed3GOE_pXydmJigzPvg7XpMasDsAPS2atdM0lL8Xz3ui2hPzu2FWEWSC7pHYpTt2PDdMsheSXc_7l12TIdTUg2CPtjz2rRZNoYs-g" },
    ],
  },
];

export function CharactersPage() {
  const [characters, setCharacters] = useState<CharacterItem[]>(DEFAULT_CHARACTERS);
  const [selectedId, setSelectedId] = useState<string>("char_kaelen");
  const [search, setSearch] = useState<string>("");
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [newCharName, setNewCharName] = useState<string>("");
  const [newCharRole, setNewCharRole] = useState<"Protagonist" | "Antagonist" | "Supporting">("Protagonist");

  const selectedChar = characters.find((c) => c.id === selectedId) || characters[0];

  const filteredCharacters = characters.filter(
    (c) =>
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.role.toLowerCase().includes(search.toLowerCase())
  );

  const handleCreateCharacter = () => {
    if (!newCharName.trim()) return;
    const fresh: CharacterItem = {
      id: `char_${Date.now()}`,
      name: newCharName.trim(),
      role: newCharRole,
      dominantTrait: "Flexible",
      flaw: "Unexplored",
      alignment: 50,
      bio: "Nhân vật mới vừa được phác thảo trong vũ trụ kịch bản.",
      avatarUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuAgd7m-oW9qyLC5a5bN6PEkQPvlWxr9w3H3EWe_0HjIp5JQFQjB6vs18Bv78naoQwRLeS9Pt0yyvpjJ9SdPkeqW7SVJT1ud9XrPklJRGTl_ADpjiOwn_AFudC9gtAOuLI5_1NPgy4gHE2SieuARxed3GOE_pXydmJigzPvg7XpMasDsAPS2atdM0lL8Xz3ui2hPzu2FWEWSC7pHYpTt2PDdMsheSXc_7l12TIdTUg2CPtjz2rRZNoYs-g",
      bannerUrl: "https://lh3.googleusercontent.com/aida-public/AB6AXuALMt6gcEyDUU3ozmzONqnv-092PvpWyTnyKy2pz0VU_Wn-7pgTibgT1uSeS_aATbLUPNGBbXPnVrx_l4Q0N3WQYWF6yvfFkK4Ydr2m9gzv2H9zyeLS1JaUzDqOJ0VEkTfxDIux19LvJtMNcTUdKH4rVT1RHYJz5GiriaVrGGXoZfoEjm-UMOxCzMbfdwA3ADM99X24a2wZSku_aDE6DIGPMUCPyLC7TNhmbOyHhMPNDGqj8Se7nIexOg",
      voiceModel: "ELEVEN_DEFAULT",
      voiceStyle: "Tự nhiên, dễ nghe",
      traits: ["New Character"],
      connections: [],
    };

    setCharacters((prev) => [...prev, fresh]);
    setSelectedId(fresh.id);
    setNewCharName("");
    setShowAddModal(false);
  };

  return (
    <main className="flex-1 bg-background text-on-surface p-6 h-screen flex gap-6 overflow-hidden">
      {/* Left Gallery Section */}
      <div className="flex-1 flex flex-col h-full bg-surface-container-low rounded-xl border border-outline-variant/15 overflow-hidden">
        {/* Gallery Header */}
        <div className="p-6 border-b border-outline-variant/10 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface-container-low/50">
          <div>
            <h2 className="text-2xl font-extrabold tracking-tight text-on-surface flex items-center gap-3">
              <span className="material-symbols-outlined text-primary text-3xl" style={{ fontVariationSettings: "'FILL' 1" }}>
                groups
              </span>
              Diễn viên & Nhân vật (Cast & Characters)
            </h2>
            <p className="text-xs text-on-surface-variant mt-1">
              Quản lý tính cách, hồ sơ tiểu sử, ma trận tâm lý và mẫu giọng nói AI của nhân vật.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-2.5 text-on-surface-variant text-sm">
                search
              </span>
              <input
                type="text"
                placeholder="Tìm nhân vật..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="bg-surface-container border border-outline-variant/20 rounded-full py-1.5 pl-9 pr-4 text-xs text-on-surface focus:outline-none focus:border-primary w-56 transition-all"
              />
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="bg-primary hover:bg-primary-container text-on-primary font-semibold text-xs py-2 px-4 rounded-full flex items-center gap-2 transition-all shadow-[0_0_15px_rgba(77,142,255,0.25)]"
            >
              <span className="material-symbols-outlined text-sm">add</span>
              Tạo Nhân vật Mới
            </button>
          </div>
        </div>

        {/* Gallery Grid */}
        <div className="p-6 overflow-y-auto flex-1 bg-surface-container-lowest/30">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
            {filteredCharacters.map((char) => {
              const isSelected = char.id === selectedId;
              return (
                <div
                  key={char.id}
                  onClick={() => setSelectedId(char.id)}
                  className={`group relative bg-surface-container rounded-xl p-4 flex flex-col items-center text-center cursor-pointer transition-all duration-300 ${
                    isSelected
                      ? "border-2 border-primary shadow-[0_0_20px_rgba(77,142,255,0.3)] bg-primary-container/10"
                      : "border border-outline-variant/15 hover:border-primary/40 hover:-translate-y-1 hover:bg-surface-container-high"
                  }`}
                >
                  <div
                    className={`w-20 h-20 rounded-full mb-3 overflow-hidden border-2 relative transition-all ${
                      isSelected ? "border-primary shadow-[0_0_12px_rgba(77,142,255,0.4)]" : "border-outline-variant/30"
                    }`}
                  >
                    <img
                      src={char.avatarUrl}
                      alt={char.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  </div>
                  <h3 className="font-bold text-on-surface text-base mb-0.5">{char.name}</h3>
                  <span
                    className={`text-[10px] font-mono tracking-wider uppercase mb-2 ${
                      char.role === "Protagonist"
                        ? "text-primary"
                        : char.role === "Antagonist"
                        ? "text-error"
                        : "text-secondary"
                    }`}
                  >
                    {char.role}
                  </span>
                  <div className="flex flex-wrap gap-1 justify-center w-full mt-auto">
                    {char.traits.map((t, idx) => (
                      <span
                        key={idx}
                        className="px-2 py-0.5 rounded-full bg-surface-variant text-on-surface-variant text-[10px] border border-outline-variant/20"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right Detail Panel (Active Character Inspector) */}
      <aside className="w-96 shrink-0 flex flex-col h-full bg-surface-container-low rounded-xl overflow-hidden border border-outline-variant/15">
        {selectedChar && (
          <>
            {/* Header Banner */}
            <div className="relative h-44 bg-surface-container-highest">
              <img src={selectedChar.bannerUrl} alt={selectedChar.name} className="w-full h-full object-cover opacity-50" />
              <div className="absolute inset-0 bg-gradient-to-t from-surface-container-low via-transparent to-transparent" />
              <div className="absolute bottom-3 left-4 right-4 flex items-end gap-3 z-10">
                <div className="w-16 h-16 rounded-full border-2 border-primary bg-surface-dim overflow-hidden shadow-lg shrink-0">
                  <img src={selectedChar.avatarUrl} alt={selectedChar.name} className="w-full h-full object-cover" />
                </div>
                <div>
                  <h2 className="text-xl font-bold text-on-surface">{selectedChar.name}</h2>
                  <span
                    className={`text-xs font-mono tracking-widest uppercase ${
                      selectedChar.role === "Protagonist"
                        ? "text-primary"
                        : selectedChar.role === "Antagonist"
                        ? "text-error"
                        : "text-secondary"
                    }`}
                  >
                    {selectedChar.role}
                  </span>
                </div>
              </div>
            </div>

            {/* Content Details */}
            <div className="flex-1 overflow-y-auto p-5 space-y-6">
              {/* Background Bio */}
              <div>
                <h4 className="text-xs font-mono uppercase text-on-surface-variant mb-2 flex items-center gap-2 font-bold">
                  <span className="material-symbols-outlined text-sm">menu_book</span> Hồ sơ Tiểu sử
                </h4>
                <p className="text-xs text-on-surface leading-relaxed opacity-90 bg-surface-container/40 p-3 rounded-lg border border-outline-variant/10">
                  {selectedChar.bio}
                </p>
              </div>

              {/* Persona Matrix */}
              <div>
                <h4 className="text-xs font-mono uppercase text-on-surface-variant mb-2 flex items-center gap-2 font-bold">
                  <span className="material-symbols-outlined text-sm">psychology</span> Ma trận Tâm lý (Persona)
                </h4>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-surface-container p-2.5 rounded-lg border border-outline-variant/10">
                    <div className="text-[10px] font-mono text-on-surface-variant uppercase">Tính cách chính</div>
                    <div className="text-xs font-bold text-primary mt-0.5">{selectedChar.dominantTrait}</div>
                  </div>
                  <div className="bg-surface-container p-2.5 rounded-lg border border-outline-variant/10">
                    <div className="text-[10px] font-mono text-on-surface-variant uppercase">Điểm yếu (Flaw)</div>
                    <div className="text-xs font-bold text-error mt-0.5">{selectedChar.flaw}</div>
                  </div>
                  <div className="bg-surface-container p-2.5 rounded-lg border border-outline-variant/10 col-span-2 space-y-1">
                    <div className="text-[10px] font-mono text-on-surface-variant uppercase">Thước đo Thiện / Ác</div>
                    <div className="w-full h-1.5 bg-surface-dim rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-secondary to-primary rounded-full"
                        style={{ width: `${selectedChar.alignment}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Voice Profile */}
              <div>
                <h4 className="text-xs font-mono uppercase text-on-surface-variant mb-2 flex items-center gap-2 font-bold">
                  <span className="material-symbols-outlined text-sm">mic</span> Giọng nói AI (Voice Profile)
                </h4>
                <div className="bg-surface-container-high border border-outline-variant/20 rounded-lg p-3 flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center shrink-0">
                    <span className="material-symbols-outlined text-sm">play_arrow</span>
                  </div>
                  <div>
                    <div className="text-xs font-bold text-on-surface">{selectedChar.voiceModel}</div>
                    <div className="text-[11px] text-on-surface-variant">{selectedChar.voiceStyle}</div>
                  </div>
                </div>
              </div>

              {/* Key Connections */}
              {selectedChar.connections.length > 0 && (
                <div>
                  <h4 className="text-xs font-mono uppercase text-on-surface-variant mb-2 flex items-center gap-2 font-bold">
                    <span className="material-symbols-outlined text-sm">hub</span> Mối quan hệ
                  </h4>
                  <div className="space-y-2">
                    {selectedChar.connections.map((conn, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-2 rounded-lg bg-surface-container border border-outline-variant/10"
                      >
                        <div className="flex items-center gap-2">
                          <img src={conn.avatar} alt={conn.name} className="w-6 h-6 rounded-full object-cover" />
                          <span className="text-xs font-medium text-on-surface">{conn.name}</span>
                        </div>
                        <span
                          className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded font-bold ${
                            conn.type === "Ally" ? "bg-secondary/10 text-secondary" : "bg-error/10 text-error"
                          }`}
                        >
                          {conn.type}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </aside>

      {/* Modal tạo nhân vật mới */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-surface-container-low border border-outline-variant/20 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <h3 className="text-xl font-bold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary">person_add</span>
              Tạo Nhân vật Mới
            </h3>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Tên nhân vật</label>
                <input
                  type="text"
                  placeholder="Ví dụ: Kaelen Vance..."
                  value={newCharName}
                  onChange={(e) => setNewCharName(e.target.value)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-on-surface-variant block mb-1">Vai trò trong tác phẩm</label>
                <select
                  value={newCharRole}
                  onChange={(e) => setNewCharRole(e.target.value as any)}
                  className="w-full px-3 py-2 text-sm bg-surface-container border border-outline-variant/20 rounded-lg text-on-surface focus:outline-none focus:border-primary"
                >
                  <option value="Protagonist">Nhân vật chính (Protagonist)</option>
                  <option value="Supporting">Nhân vật phụ (Supporting)</option>
                  <option value="Antagonist">Nhân vật phản diện (Antagonist)</option>
                </select>
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
                onClick={handleCreateCharacter}
                disabled={!newCharName.trim()}
                className="px-4 py-2 bg-primary text-on-primary font-semibold text-xs rounded-lg hover:bg-primary-container disabled:opacity-50"
              >
                Tạo nhân vật
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
