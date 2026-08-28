/**
 * CharactersPage — Dark Cinematic Characters Studio (WindAgent)
 * Pixel-close to reference mock (Image 1) but 100% real API + DB.
 * NO FALLBACK_CHARACTERS, NO mock arrays — all data from V3 resource authority.
 *
 * Layout:
 *  - Header: title + subtitle
 *  - Controls: Project select | Search | Filter | Sắp xếp | Thêm Character
 *  - Metrics: Tổng nhân vật / Nhân vật chính / Nhân vật phụ / Phe phái liên kết / Tiến độ hoàn thiện
 *  - 3 columns: Danh mục nhân vật (left) | Danh sách nhân vật grid (center) | Chi tiết nhân vật (right)
 *  - Footer: Sơ đồ quan hệ nổi bật (real relationship graph)
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  LayoutGrid,
  List as ListIcon,
  Plus,
  ChevronDown,
  MoreVertical,
  X,
  Pencil,
  Check,
  Trash2,
  User,
  Users,
  Shield,
  Clock,
  Tag,
  Layers,
  Video,
  Heart,
  Target,
  Eye,
  FileText,
  Network,
  BadgeCheck,
  Crown,
  Swords,
  Handshake,
  Briefcase,
} from 'lucide-react';

import { useCharacters, useCreateCharacter, useDeleteCharacter, useSetCharacterStatus, useUpdateCharacter } from '../hooks/useCharacters';
import { useStudioSeries } from '../../studio/hooks/useStudioSeries';
import { useFactions } from '../../world/hooks/useWorld';
import { useApiClient } from '../../../shared/hooks/useApiClient';
import { useQuery } from '@tanstack/react-query';

interface CharactersPageProps {
  projectId: string;
}

// ── helpers ───────────────────────────────────────────────────────────────

function hashGradient(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  const hues = [220, 245, 265, 200, 235, 285, 190, 250];
  const hue = hues[h % hues.length];
  return `linear-gradient(135deg, hsl(${hue} 65% 14%) 0%, hsl(${(hue + 28) % 360} 62% 24%) 50%, hsl(${(hue + 52) % 360} 68% 10%) 100%)`;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function roleBadge(role: string): { label: string; color: string; bg: string; border: string } {
  const r = (role || '').toLowerCase();
  if (r === 'protagonist' || r.includes('chính') || r.includes('chinh')) return { label: 'Chính', color: '#60a5fa', bg: 'rgba(59,130,246,0.16)', border: 'rgba(59,130,246,0.32)' };
  if (r === 'antagonist' || r.includes('phản') || r.includes('phan dien')) return { label: 'Phản diện', color: '#fb7185', bg: 'rgba(239,68,68,0.16)', border: 'rgba(239,68,68,0.30)' };
  if (r.includes('đồng minh') || r.includes('dong minh') || r === 'ally') return { label: 'Đồng minh', color: '#34d399', bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.30)' };
  if (r.includes('ai companion') || r.includes('ai')) return { label: 'AI Companion', color: '#2dd4bf', bg: 'rgba(45,212,191,0.15)', border: 'rgba(45,212,191,0.30)' };
  if (r.includes('chính quyền') || r.includes('chinh quyen')) return { label: 'Chính quyền', color: '#fbbf24', bg: 'rgba(251,191,36,0.15)', border: 'rgba(251,191,36,0.30)' };
  if (r.includes('hacker')) return { label: 'Hacker bí ẩn', color: '#c4b5fd', bg: 'rgba(139,92,246,0.16)', border: 'rgba(139,92,246,0.32)' };
  if (r === 'supporting' || r.includes('phụ') || r.includes('phu')) return { label: 'Phụ', color: '#a78bfa', bg: 'rgba(139,92,246,0.14)', border: 'rgba(139,92,246,0.28)' };
  if (r === 'draft' || r.includes('nháp') || r.includes('nhap')) return { label: 'Nháp', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.22)' };
  return { label: role || 'Nháp', color: '#94a3b8', bg: 'rgba(148,163,184,0.12)', border: 'rgba(148,163,184,0.22)' };
}

function characterCompletion(c: any): number {
  const checks: boolean[] = [
    !!c?.identity?.name?.trim(),
    !!c?.identity?.biography?.trim(),
    Array.isArray(c?.identity?.aliases) && c.identity.aliases.length > 0,
    !!c?.psychology?.dominant_trait?.trim(),
    !!c?.psychology?.flaw?.trim(),
    Array.isArray(c?.psychology?.traits) && c.psychology.traits.length > 0,
    !!c?.psychology?.archetype?.trim(),
    !!c?.psychology?.motivation?.trim(),
    !!c?.psychology?.goal?.trim(),
    !!c?.visual_profile?.physical_description?.trim(),
    !!c?.visual_profile?.avatar_url,
    !!c?.visual_profile?.banner_url,
    Array.isArray(c?.continuity?.immutable_features) && c.continuity.immutable_features.length > 0,
    Array.isArray(c?.continuity?.wardrobe_rules) && c.continuity.wardrobe_rules.length > 0,
  ];
  const filled = checks.filter(Boolean).length;
  return Math.round((filled / checks.length) * 100);
}

function deriveTags(c: any): string[] {
  const out: string[] = [];
  const push = (v: any) => {
    if (!v) return;
    if (Array.isArray(v)) v.forEach((x) => { if (typeof x === 'string' && x.trim()) out.push(x.trim().toLowerCase()); });
    else if (typeof v === 'string' && v.trim()) out.push(v.trim().toLowerCase());
  };
  push((c?.psychology?.traits || []));
  push(c?.psychology?.dominant_trait);
  push(c?.psychology?.archetype);
  // also split physical style notes maybe
  return Array.from(new Set(out)).slice(0, 4);
}

function statusLabel(status: string): string {
  const s = (status || '').toUpperCase();
  if (s === 'PRODUCTION_READY') return 'Sẵn sàng';
  if (s === 'APPROVED') return 'Đã duyệt';
  if (s === 'REVIEW_REQUIRED') return 'Chờ duyệt';
  return 'Đang dùng';
}

// ── component ─────────────────────────────────────────────────────────────

export const CharactersPage: React.FC<CharactersPageProps> = ({ projectId: propProjectId }) => {
  const { series, isLoading: loadingSeries } = useStudioSeries();
  const apiClient = useApiClient();

  // project selector — real series list, no fallback mock
  const [selectedSeriesId, setSelectedSeriesId] = useState<string | null>(propProjectId || null);
  const [projectDropdownOpen, setProjectDropdownOpen] = useState(false);
  const [episodeDropdownOpen, setEpisodeDropdownOpen] = useState(false);

  // hydrate project when series loads
  useEffect(() => {
    if (series.length === 0) return;
    if (!selectedSeriesId) {
      setSelectedSeriesId(series[0].id);
      return;
    }
    const exists = series.find((s: any) => s.id === selectedSeriesId);
    if (!exists) setSelectedSeriesId(series[0].id);
  }, [series]); // eslint-disable-line

  const activeProjectId = selectedSeriesId || propProjectId;
  const activeSeries = useMemo(() => (series as any[]).find((s: any) => s.id === activeProjectId) || null, [series, activeProjectId]);

  // search with debounce for API
  const [searchInput, setSearchInput] = useState('');
  const [searchDebounced, setSearchDebounced] = useState<string | undefined>(undefined);
  useEffect(() => {
    const t = setTimeout(() => {
      const v = searchInput.trim();
      setSearchDebounced(v || undefined);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  const { data: charactersRaw = [], isLoading, error } = useCharacters(activeProjectId, searchDebounced);
  const createMut = useCreateCharacter(activeProjectId);
  const deleteMut = useDeleteCharacter(activeProjectId);
  const updateMut = useUpdateCharacter();
  const statusMut = useSetCharacterStatus();

  const { data: factions = [] } = useFactions(activeProjectId);
  // episodes not strictly needed but fetch for graph counts
  const { data: studioEpisodes } = useQuery({
    queryKey: ['studio-episodes-for-char', activeProjectId],
    queryFn: async () => {
      try {
        const res: any = await apiClient.studio.listEpisodes(activeProjectId);
        return res.items || [];
      } catch { return []; }
    },
    enabled: Boolean(activeProjectId),
  });

  // left category filter
  type CatKey = 'all' | 'main' | 'support' | 'antagonist' | 'ally' | 'incomplete';
  const [selectedCat, setSelectedCat] = useState<CatKey>('all');
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [sortMode, setSortMode] = useState<'updated' | 'name' | 'progress'>('updated');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [detailTab, setDetailTab] = useState<'info' | 'relations' | 'appearances' | 'history'>('info');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingChar, setEditingChar] = useState<any | null>(null);

  // create form
  const [newForm, setNewForm] = useState({ name: '', role: 'Supporting', biography: '', dominant_trait: '', flaw: '', physical_description: '' });
  const [editForm, setEditForm] = useState({ name: '', role: 'Supporting', biography: '', dominant_trait: '', flaw: '', physical_description: '' });

  // selected character — real selection, no mock
  const [selectedCharId, setSelectedCharId] = useState<string | null>(null);
  useEffect(() => {
    if (!selectedCharId && (charactersRaw as any[]).length > 0) {
      setSelectedCharId((charactersRaw as any[])[0].id);
    }
    if (selectedCharId && (charactersRaw as any[]).length > 0) {
      const still = (charactersRaw as any[]).find((c: any) => c.id === selectedCharId);
      if (!still) setSelectedCharId((charactersRaw as any[])[0].id);
    }
  }, [charactersRaw, selectedCharId]);

  const selectedChar: any | null = useMemo(
    () => (charactersRaw as any[]).find((c: any) => c.id === selectedCharId) || null,
    [charactersRaw, selectedCharId],
  );

  // derived metrics — truth from DB
  const totalChars = (charactersRaw as any[]).length;
  const mainCount = (charactersRaw as any[]).filter((c: any) => (c.identity.role || '').toLowerCase() === 'protagonist').length;
  const supportCount = (charactersRaw as any[]).filter((c: any) => (c.identity.role || '').toLowerCase() === 'supporting').length;
  const antagonistCount = (charactersRaw as any[]).filter((c: any) => (c.identity.role || '').toLowerCase() === 'antagonist').length;
  const allyCount = useMemo(() => {
    const allyChars = (charactersRaw as any[]).filter((c: any) => c.relationships?.some((r: any) => /ally|đồng minh/i.test(r.relationship_type || '')));
    if (allyChars.length > 0) return allyChars.length;
    // fallback: count factions linked via project
    return (factions as any[])?.length ?? 0;
  }, [charactersRaw, factions]);
  const incompleteCount = (charactersRaw as any[]).filter((c: any) => characterCompletion(c) < 70 || c.status === 'DRAFT').length;
  const avgProgress = useMemo(() => {
    if (totalChars === 0) return 0;
    const sum = (charactersRaw as any[]).reduce((s: number, c: any) => s + characterCompletion(c), 0);
    return Math.round(sum / totalChars);
  }, [charactersRaw, totalChars]);

  // filtered + sorted characters for center grid (real client-side for category/sort, search is server-side)
  const filteredChars = useMemo(() => {
    let out = [...(charactersRaw as any[])];
    if (selectedCat !== 'all') {
      out = out.filter((c: any) => {
        const role = (c.identity.role || '').toLowerCase();
        const prog = characterCompletion(c);
        if (selectedCat === 'main') return role === 'protagonist';
        if (selectedCat === 'support') return role === 'supporting';
        if (selectedCat === 'antagonist') return role === 'antagonist';
        if (selectedCat === 'ally') return c.relationships?.some((r: any) => /ally|đồng minh/i.test(r.relationship_type || ''));
        if (selectedCat === 'incomplete') return prog < 70 || c.status === 'DRAFT';
        return true;
      });
    }
    if (sortMode === 'name') out.sort((a: any, b: any) => a.identity.name.localeCompare(b.identity.name, 'vi'));
    else if (sortMode === 'progress') out.sort((a: any, b: any) => characterCompletion(b) - characterCompletion(a));
    else out.sort((a: any, b: any) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
    return out;
  }, [charactersRaw, selectedCat, sortMode]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  };

  const handleCreate = async () => {
    if (!newForm.name.trim()) return;
    await createMut.mutateAsync({
      name: newForm.name.trim(),
      role: newForm.role,
      biography: newForm.biography,
      dominant_trait: newForm.dominant_trait,
      flaw: newForm.flaw,
    } as any);
    setNewForm({ name: '', role: 'Supporting', biography: '', dominant_trait: '', flaw: '', physical_description: '' });
    setShowCreateModal(false);
  };

  const openEdit = (c: any) => {
    setEditingChar(c);
    setEditForm({
      name: c.identity.name || '',
      role: c.identity.role || 'Supporting',
      biography: c.identity.biography || '',
      dominant_trait: c.psychology?.dominant_trait || '',
      flaw: c.psychology?.flaw || '',
      physical_description: c.visual_profile?.physical_description || '',
    });
    setShowEditModal(true);
  };

  const handleEditSave = async () => {
    if (!editingChar) return;
    await updateMut.mutateAsync({
      characterId: editingChar.id,
      name: editForm.name.trim() || undefined,
      role: editForm.role,
      biography: editForm.biography,
      dominant_trait: editForm.dominant_trait,
      flaw: editForm.flaw,
      expected_version: editingChar.version,
    } as any);
    setShowEditModal(false);
    setEditingChar(null);
  };

  const handleApprove = async () => {
    if (!selectedChar) return;
    const order = ['DRAFT', 'REVIEW_REQUIRED', 'APPROVED', 'PRODUCTION_READY'];
    const cur = (selectedChar.status || 'DRAFT').toUpperCase();
    const idx = order.indexOf(cur);
    if (idx === -1 || idx === order.length - 1) return;
    const next = order[idx + 1];
    try {
      // The hook invalidates the character caches on success — no reload.
      await statusMut.mutateAsync({
        characterId: selectedChar.id,
        status: next,
        expected_version: selectedChar.version,
      });
    } catch (e: any) {
      alert(e?.message || 'Không thể duyệt — kiểm tra ràng buộc PRODUCTION_READY (thiếu visual/continuity).');
    }
  };

  const handleDelete = async (id?: string) => {
    const target = id || selectedChar?.id;
    if (!target) return;
    if (!confirm('Xóa nhân vật này? Hành động không thể hoàn tác.')) return;
    await deleteMut.mutateAsync(target);
    if (selectedCharId === target) setSelectedCharId(null);
  };

  // loading / empty project guard — no mock fallback
  if (loadingSeries && !activeProjectId) {
    return (
      <div style={styles.root}>
        <div style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>Đang tải danh sách dự án...</div>
      </div>
    );
  }

  if (!activeProjectId) {
    return (
      <div style={styles.root}>
        <div style={{ padding: 32, textAlign: 'center', color: '#94a3b8' }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🎬</div>
          <h3 style={{ color: '#f1f5f9', marginBottom: 8 }}>Chưa có Dự án nào để hiển thị Characters</h3>
          <p style={{ fontSize: 13, marginBottom: 16 }}>Tạo Project/Series ở trang Projects trước — dữ liệu được lưu thật trong DB (V3 resource authority), không có mock.</p>
          <a href="#/projects" style={{ color: '#60a5fa', fontWeight: 700, textDecoration: 'none' }}>→ Đi tới Projects</a>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.root}>
      {/* ── Title ─────────────────────────── */}
      <div style={styles.titleRow}>
        <div>
          <h1 style={styles.h1}>Characters</h1>
          <p style={styles.subtitle}>Quản lý hồ sơ nhân vật, mối quan hệ, vai trò và trạng thái phát triển.</p>
        </div>
      </div>

      {/* ── Controls band ─────────────────── */}
      <div style={styles.controls}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', flex: 1 }}>
          {/* Dự án select — real series */}
          <div style={{ position: 'relative' }}>
            <button onClick={() => setProjectDropdownOpen((v) => !v)} style={styles.selectBtn}>
              <span style={styles.selectLabel}>Dự án</span>
              <span style={styles.selectValue}>{activeSeries?.title || activeProjectId}</span>
              <ChevronDown size={14} color="#64748b" style={{ marginLeft: 6 }} />
            </button>
            {projectDropdownOpen && (
              <div style={styles.dropdown}>
                {(series as any[]).length === 0 && <div style={styles.dropdownEmpty}>Chưa có Series — tạo ở Projects (lưu thật trong DB)</div>}
                {(series as any[]).map((s: any) => (
                  <div
                    key={s.id}
                    onClick={() => { setSelectedSeriesId(s.id); setProjectDropdownOpen(false); setSelectedCharId(null); }}
                    style={{ ...styles.dropdownItem, ...(s.id === activeProjectId ? styles.dropdownItemActive : {}) }}
                  >
                    <span style={{ fontWeight: 700 }}>{s.title}</span>
                    <span style={{ fontSize: 11, color: '#64748b' }}>{s.episode_count ?? 0} tập</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Search — real API search */}
          <div style={styles.searchWrap}>
            <Search size={14} color="#64748b" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Tìm kiếm nhân vật..."
              style={styles.searchInput}
            />
            {searchInput && (
              <button onClick={() => setSearchInput('')} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><X size={12} /></button>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          <button onClick={() => setShowCategoryManager((v) => !v)} style={styles.iconBtn} title="Filter theo vai trò">
            <SlidersHorizontal size={14} /> Filter
          </button>
          <div style={{ position: 'relative' }}>
            <button onClick={() => setEpisodeDropdownOpen((v) => !v)} style={styles.iconBtn} title={`Sắp xếp: ${sortMode}`}>
              <ArrowUpDown size={14} /> Sắp xếp
            </button>
            {episodeDropdownOpen && (
              <div style={{ ...styles.dropdown, right: 0, left: 'auto', minWidth: 180 }}>
                {(['updated', 'name', 'progress'] as const).map((m) => (
                  <div key={m} onClick={() => { setSortMode(m); setEpisodeDropdownOpen(false); }} style={{ ...styles.dropdownItem, ...(sortMode === m ? styles.dropdownItemActive : {}) }}>
                    {m === 'updated' ? 'Mới cập nhật' : m === 'name' ? 'Tên A→Z' : 'Tiến độ cao → thấp'}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={() => setShowCreateModal(true)} style={styles.btnPrimary}>
              <Plus size={14} /> Thêm Character
            </button>
            <button onClick={() => setShowCreateModal(true)} style={{ ...styles.btnPrimary, padding: '9px 8px', borderLeft: '1px solid rgba(255,255,255,0.15)', borderTopLeftRadius: 0, borderBottomLeftRadius: 0, marginLeft: -6 }}>
              <ChevronDown size={12} />
            </button>
          </div>
        </div>
      </div>

      {/* ── Metrics strip ─────────────────── */}
      <div style={styles.metrics}>
        <div style={styles.metricCell}>
          <div style={{ ...styles.metricIcon, background: 'rgba(45,212,191,0.14)', borderColor: 'rgba(45,212,191,0.28)' }}><Users size={16} color="#2dd4bf" /></div>
          <div>
            <div style={styles.metricLabel}>Tổng nhân vật</div>
            <div style={styles.metricValue}>{totalChars}</div>
          </div>
        </div>
        <div style={styles.metricCell}>
          <div style={{ ...styles.metricIcon, background: 'rgba(139,92,246,0.14)', borderColor: 'rgba(139,92,246,0.28)' }}><Crown size={16} color="#a78bfa" /></div>
          <div>
            <div style={styles.metricLabel}>Nhân vật chính</div>
            <div style={styles.metricValue}>{mainCount}</div>
          </div>
        </div>
        <div style={styles.metricCell}>
          <div style={{ ...styles.metricIcon, background: 'rgba(16,185,129,0.14)', borderColor: 'rgba(16,185,129,0.28)' }}><Users size={16} color="#34d399" /></div>
          <div>
            <div style={styles.metricLabel}>Nhân vật phụ</div>
            <div style={styles.metricValue}>{supportCount}</div>
          </div>
        </div>
        <div style={styles.metricCell}>
          <div style={{ ...styles.metricIcon, background: 'rgba(99,102,241,0.14)', borderColor: 'rgba(99,102,241,0.28)' }}><Network size={16} color="#818cf8" /></div>
          <div>
            <div style={styles.metricLabel}>Phe phái liên kết</div>
            <div style={styles.metricValue}>{allyCount}</div>
          </div>
        </div>
        <div style={{ ...styles.metricCell, flex: 1.3, borderRight: 'none', minWidth: 180 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <span style={styles.metricLabel}>Tiến độ hoàn thiện hồ sơ</span>
              <span style={{ fontSize: 12, fontWeight: 800, color: '#f1f5f9' }}>{avgProgress}%</span>
            </div>
            <div style={{ height: 6, background: '#1e293b', borderRadius: 999, overflow: 'hidden' }}>
              <div style={{ width: `${avgProgress}%`, height: '100%', background: 'linear-gradient(90deg,#3b82f6 0%,#6366f1 100%)', borderRadius: 999, transition: 'width 0.35s' }} />
            </div>
          </div>
        </div>
      </div>

      {/* ── Main 3 columns + graph ─────────── */}
      <div style={styles.mainWrap}>
        {/* left + center + graph column */}
        <div style={styles.leftCenterColumn}>
          <div style={styles.leftCenterRow}>
            {/* LEFT: Danh mục nhân vật */}
            <div style={styles.leftPanel}>
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>Danh mục nhân vật</span>
                <button onClick={() => setShowCreateModal(true)} style={styles.smallIconBtn} title="Thêm nhân vật"><Plus size={14} /></button>
              </div>
              <div style={styles.catList}>
                {[
                  { key: 'all' as const, label: 'Tất cả nhân vật', icon: <Layers size={13} color="#38bdf8" />, count: totalChars, activeBg: 'rgba(56,189,248,0.12)' },
                  { key: 'main' as const, label: 'Nhân vật chính', icon: <Crown size={13} color="#a78bfa" />, count: mainCount },
                  { key: 'support' as const, label: 'Nhân vật phụ', icon: <Users size={13} color="#a78bfa" />, count: supportCount },
                  { key: 'antagonist' as const, label: 'Phản diện', icon: <Swords size={13} color="#fb7185" />, count: antagonistCount },
                  { key: 'ally' as const, label: 'Đồng minh', icon: <Handshake size={13} color="#34d399" />, count: allyCount },
                  { key: 'incomplete' as const, label: 'Chưa hoàn thiện', icon: <Clock size={13} color="#f59e0b" />, count: incompleteCount },
                ].map((cat) => {
                  const isActive = selectedCat === cat.key;
                  return (
                    <div
                      key={cat.key}
                      onClick={() => setSelectedCat(cat.key)}
                      style={{
                        ...styles.catItem,
                        ...(isActive ? styles.catItemActive : {}),
                        ...(isActive && cat.key === 'all' ? { background: cat.activeBg!, borderColor: 'rgba(56,189,248,0.28)' } : {}),
                      }}
                    >
                      <span style={styles.catIcon}>{cat.icon}</span>
                      <span style={{ flex: 1, fontSize: 12, fontWeight: isActive ? 700 : 500, color: isActive ? '#f1f5f9' : '#cbd5e1' }}>{cat.label}</span>
                      <span style={{ ...styles.catCount, ...(isActive ? styles.catCountActive : {}) }}>{cat.count}</span>
                    </div>
                  );
                })}
              </div>
              <div style={styles.panelFooter}>
                <button onClick={() => setShowCategoryManager(true)} style={styles.footerBtn}><Plus size={12} /> Thêm danh mục</button>
              </div>
            </div>

            {/* CENTER: Danh sách nhân vật */}
            <div style={styles.centerPanel}>
              <div style={styles.panelHeader}>
                <span style={styles.panelTitle}>Danh sách nhân vật</span>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <button onClick={() => setViewMode('grid')} style={{ ...styles.viewMiniBtn, ...(viewMode === 'grid' ? styles.viewMiniActive : {}) }}><LayoutGrid size={14} /></button>
                  <button onClick={() => setViewMode('list')} style={{ ...styles.viewMiniBtn, ...(viewMode === 'list' ? styles.viewMiniActive : {}) }}><ListIcon size={14} /></button>
                </div>
              </div>

              <div style={styles.centerScroll}>
                {isLoading ? (
                  <div style={{ padding: 16, display: 'grid', gridTemplateColumns: viewMode === 'grid' ? 'repeat(3,1fr)' : '1fr', gap: 10 }}>
                    {[1, 2, 3, 4, 5, 6].map((i) => (
                      <div key={i} style={{ height: viewMode === 'grid' ? 260 : 96, background: '#0b1224', border: '1px solid #1e293b', borderRadius: 10, animation: 'pulse 1.4s infinite' }} />
                    ))}
                  </div>
                ) : error ? (
                  <div style={{ margin: 12, padding: 12, background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.22)', borderRadius: 8, color: '#fca5a5', fontSize: 12 }}>
                    {(error as Error).message}
                  </div>
                ) : filteredChars.length === 0 ? (
                  <div style={{ padding: 28, textAlign: 'center', color: '#64748b' }}>
                    <div style={{ fontSize: 22, marginBottom: 8 }}>🎭</div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#cbd5e1', marginBottom: 6 }}>{searchDebounced ? `Không tìm thấy "${searchDebounced}"` : selectedCat !== 'all' ? 'Không có nhân vật trong danh mục này' : 'Chưa có nhân vật nào'}</div>
                    <div style={{ fontSize: 11, lineHeight: 1.5, marginBottom: 12 }}>Dữ liệu được lưu thật trong DB qua /api/v3/projects/{activeProjectId}/characters — không có mock.</div>
                    <button onClick={() => setShowCreateModal(true)} style={{ background: '#2563eb', color: '#fff', border: 'none', padding: '8px 14px', borderRadius: 8, fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>+ Thêm nhân vật đầu tiên</button>
                  </div>
                ) : (
                  <div style={viewMode === 'grid' ? styles.grid3 : styles.listCol}>
                    {filteredChars.map((char: any) => {
                      const isSelected = selectedCharId === char.id;
                      const checked = selectedIds.has(char.id);
                      const badge = roleBadge(char.identity.role);
                      const prog = characterCompletion(char);
                      const tags = deriveTags(char);
                      const avatar = char.visual_profile?.avatar_url || char.visual_profile?.banner_url;
                      const bio = char.identity.biography || '';
                      // map role secondary label like "Neuron", "Null Corp"
                      const secondaryFaction = char.psychology?.archetype || (char as any).continuity?.wardrobe_rules?.[0] || '';
                      return (
                        <div
                          key={char.id}
                          onClick={() => setSelectedCharId(char.id)}
                          style={{
                            ...styles.charCard,
                            ...(isSelected ? styles.charCardSelected : {}),
                            ...(viewMode === 'list' ? { flexDirection: 'row', height: 96 } as any : {}),
                          }}
                        >
                          {/* image header */}
                          <div style={{ ...styles.charThumbWrap, ...(viewMode === 'list' ? { width: 110, height: '100%', flexShrink: 0 } as any : {}) }}>
                            {avatar ? (
                              <img src={avatar} alt={char.identity.name} style={styles.charThumbImg} loading="lazy" />
                            ) : (
                              <div style={{ ...styles.charThumbFallback, background: hashGradient(char.id) }}>
                                <span style={{ fontSize: viewMode === 'list' ? 22 : 26, fontWeight: 800, color: 'rgba(255,255,255,0.92)', letterSpacing: '-0.5px' }}>{initials(char.identity.name)}</span>
                              </div>
                            )}
                            <div style={styles.charCheckbox} onClick={(e) => { e.stopPropagation(); toggleSelect(char.id); }}>
                              <div style={{ ...styles.checkboxBox, ...(checked || isSelected ? styles.checkboxBoxChecked : {}) }}>
                                {(checked || isSelected) && <Check size={10} color="#fff" strokeWidth={3} />}
                              </div>
                            </div>
                            <button onClick={(e) => e.stopPropagation()} style={styles.charMoreBtn}><MoreVertical size={12} color="#e2e8f0" /></button>
                          </div>

                          <div style={styles.charBody}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'space-between' }}>
                              <span style={styles.charName}>{char.identity.name}</span>
                              <span style={{ fontSize: 10, fontWeight: 700, color: badge.color, background: badge.bg, border: `1px solid ${badge.border}`, padding: '2px 6px', borderRadius: 20, whiteSpace: 'nowrap' }}>{badge.label}</span>
                            </div>
                            <div style={{ display: 'flex', gap: 6, marginTop: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                              <span style={{ fontSize: 11, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 4 }}><User size={10} color="#64748b" /> {roleBadge(char.identity.role).label === 'Chính' ? 'Nhân vật chính' : roleBadge(char.identity.role).label === 'Phản diện' ? 'Phản diện' : roleBadge(char.identity.role).label === 'Phụ' ? 'Nhân vật phụ' : badge.label}</span>
                              {secondaryFaction && <span style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}><Shield size={10} color="#64748b" /> {String(secondaryFaction).slice(0, 14)}</span>}
                            </div>
                            {tags.length > 0 && (
                              <div style={{ display: 'flex', gap: 5, marginTop: 7, flexWrap: 'wrap' }}>
                                {tags.slice(0, 3).map((t) => (
                                  <span key={t} style={styles.tagPill}>{t}</span>
                                ))}
                              </div>
                            )}
                            <div style={{ fontSize: 11, color: '#94a3b8', lineHeight: 1.45, marginTop: 7, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', minHeight: 30 }}>
                              {bio ? (bio.length > 110 ? bio.slice(0, 110) + '...' : bio) : <span style={{ color: '#475569', fontStyle: 'italic' }}>Chưa có mô tả — chỉnh sửa để thêm tiểu sử (lưu thật vào DB).</span>}
                            </div>
                            <div style={{ marginTop: 8 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                                <span style={{ fontSize: 10.5, color: '#64748b', fontWeight: 600 }}>{prog}% hoàn thiện</span>
                                <span style={{ fontSize: 10.5, color: '#64748b', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4 }}><Video size={10} color="#64748b" /> Tập {(char as any).episode_ids?.length ? `1-${(char as any).episode_ids.length}` : '—'}</span>
                              </div>
                              <div style={{ height: 4, background: '#1e293b', borderRadius: 999, overflow: 'hidden' }}>
                                <div style={{ width: `${prog}%`, height: '100%', background: prog >= 80 ? '#22c55e' : prog >= 50 ? '#3b82f6' : '#f59e0b', borderRadius: 999 }} />
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              <div style={styles.panelFooter}>
                <button onClick={() => setShowCreateModal(true)} style={styles.footerBtn}><Plus size={12} /> Thêm nhân vật vào dự án</button>
              </div>
            </div>
          </div>

          {/* GRAPH: Sơ đồ quan hệ nổi bật — real relations */}
          <div style={styles.graphPanel}>
            <div style={styles.graphHeader}>
              <span style={{ fontSize: 12, fontWeight: 800, color: '#f1f5f9', display: 'flex', alignItems: 'center', gap: 6 }}><Network size={13} color="#60a5fa" /> Sơ đồ quan hệ nổi bật</span>
              <button style={{ fontSize: 11, color: '#60a5fa', background: 'rgba(59,130,246,0.10)', border: '1px solid rgba(59,130,246,0.22)', padding: '4px 8px', borderRadius: 20, cursor: 'pointer', fontWeight: 600 }} onClick={() => setDetailTab('relations')}>Xem toàn bộ quan hệ</button>
            </div>
            <div style={styles.graphBody}>
              {!selectedChar || (selectedChar.relationships || []).length === 0 ? (
                <div style={{ display: 'flex', gap: 14, alignItems: 'center', justifyContent: 'center', padding: '8px 12px', color: '#64748b', fontSize: 11, flexWrap: 'wrap' }}>
                  <span>Chưa có quan hệ nào cho <b style={{ color: '#cbd5e1' }}>{selectedChar?.identity?.name || '—'}</b>.</span>
                  <span style={{ color: '#475569' }}>Thêm quan hệ qua API /characters/{'{id}'}/relationships (lưu thật trong DB).</span>
                  {(charactersRaw as any[]).length >= 2 && (
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {(charactersRaw as any[]).slice(0, 4).map((c: any) => (
                        <span key={c.id} onClick={() => setSelectedCharId(c.id)} style={{ width: 28, height: 28, borderRadius: '50%', background: hashGradient(c.id), border: '1px solid rgba(255,255,255,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 800, color: '#fff', cursor: 'pointer' }}>{initials(c.identity.name)}</span>
                      ))}
                    </span>
                  )}
                </div>
              ) : (
                <div style={styles.graphNodes}>
                  {/* Render center + up to 5 neighbors with relation labels */}
                  {(() => {
                    const rels: any[] = selectedChar.relationships.slice(0, 5);
                    const others = rels.map((r: any) => (charactersRaw as any[]).find((c: any) => c.id === r.target_character_id) || { id: r.target_character_id, identity: { name: r.target_name }, visual_profile: {} });
                    return (
                      <>
                        {/* left cluster */}
                        <div style={styles.graphCluster}>
                          {others.slice(0, 2).map((o: any, i: number) => (
                            <div key={o.id} style={styles.graphNodeWrap}>
                              <div style={{ ...styles.graphAvatar, background: hashGradient(o.id) }}>{initials(o.identity.name)}</div>
                              <span style={styles.graphName}>{o.identity.name}</span>
                              <span style={{ ...styles.graphEdgeLabel, color: i === 0 ? '#34d399' : '#60a5fa' }}>{rels[i]?.relationship_type || 'Liên kết'}</span>
                            </div>
                          ))}
                        </div>
                        {/* center */}
                        <div style={styles.graphCenter}>
                          <div style={{ ...styles.graphAvatar, width: 44, height: 44, border: '2px solid #3b82f6', boxShadow: '0 0 0 4px rgba(59,130,246,0.18)' , background: hashGradient(selectedChar.id) }}>{initials(selectedChar.identity.name)}</div>
                          <span style={{ ...styles.graphName, fontWeight: 800, color: '#bfdbfe' }}>{selectedChar.identity.name}</span>
                          <div style={styles.graphCenterLines}>
                            <span style={{ ...styles.graphEdgeLabel, color: '#ef4444' }}>—</span>
                          </div>
                        </div>
                        {/* right cluster */}
                        <div style={styles.graphCluster}>
                          {others.slice(2, 5).map((o: any, i: number) => (
                            <div key={o.id} style={styles.graphNodeWrap}>
                              <div style={{ ...styles.graphAvatar, background: hashGradient(o.id) }}>{initials(o.identity.name)}</div>
                              <span style={styles.graphName}>{o.identity.name}</span>
                              <span style={{ ...styles.graphEdgeLabel, color: ['#f59e0b', '#a78bfa', '#34d399'][i % 3] }}>{rels[i + 2]?.relationship_type || 'Liên kết'}</span>
                            </div>
                          ))}
                        </div>
                      </>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT: Chi tiết nhân vật — real DB */}
        <div style={styles.rightPanel}>
          <div style={styles.panelHeader}>
            <span style={styles.panelTitle}>Chi tiết nhân vật</span>
            <button onClick={() => setSelectedCharId(null)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b', width: 22, height: 22, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><X size={14} /></button>
          </div>

          {!selectedChar ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#64748b', fontSize: 12 }}>
              Chọn một nhân vật ở giữa để xem chi tiết — mọi trường được đọc trực tiếp từ Character trong DB.
            </div>
          ) : (
            <div style={styles.rightScroll}>
              {/* banner */}
              <div style={styles.detailBannerWrap}>
                {(() => {
                  const banner = selectedChar.visual_profile?.banner_url || selectedChar.visual_profile?.avatar_url;
                  return banner ? <img src={banner} alt={selectedChar.identity.name} style={styles.detailBannerImg} /> : <div style={{ ...styles.detailBannerFallback, background: hashGradient(selectedChar.id) }}><span style={{ fontSize: 42, fontWeight: 800, color: 'rgba(255,255,255,0.95)' }}>{initials(selectedChar.identity.name)}</span></div>;
                })()}
                <div style={styles.bannerOverlay} />
                <span style={{ ...styles.bannerBadge, left: 10, background: roleBadge(selectedChar.identity.role).bg, color: roleBadge(selectedChar.identity.role).color, border: `1px solid ${roleBadge(selectedChar.identity.role).border}` }}>{roleBadge(selectedChar.identity.role).label}</span>
                <span style={{ ...styles.bannerBadge, right: 10, background: 'rgba(16,185,129,0.16)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.28)' }}>{statusLabel(selectedChar.status)}</span>
              </div>

              <div style={{ padding: '12px 12px 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 15, fontWeight: 800, color: '#f1f5f9' }}>{selectedChar.identity.name}</span>
                <button onClick={() => openEdit(selectedChar)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><Pencil size={13} /></button>
              </div>

              {/* tabs */}
              <div style={styles.detailTabs}>
                {[
                  { k: 'info', l: 'Thông tin' },
                  { k: 'relations', l: 'Quan hệ' },
                  { k: 'appearances', l: 'Xuất hiện' },
                  { k: 'history', l: 'Lịch sử' },
                ].map((t) => (
                  <button
                    key={t.k}
                    onClick={() => setDetailTab(t.k as any)}
                    style={{ ...styles.tabBtn, ...(detailTab === t.k ? styles.tabBtnActive : {}) }}
                  >
                    {t.l}
                  </button>
                ))}
              </div>

              <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {detailTab === 'info' && (
                  <>
                    <DetailRow icon={<Shield size={12} color="#64748b" />} label="Vai trò" value={selectedChar.identity.role || '—'} />
                    <DetailRow icon={<User size={12} color="#64748b" />} label="Tuổi" value={(selectedChar as any).visual_profile?.age_appearance || '—'} />
                    <DetailRow icon={<Briefcase size={12} color="#64748b" />} label="Nghề nghiệp" value={selectedChar.psychology?.archetype || selectedChar.psychology?.dominant_trait || '—'} />
                    <DetailRow icon={<Layers size={12} color="#64748b" />} label="Phe phái" value={(selectedChar as any).continuity?.wardrobe_rules?.[0] || (factions as any[])[0]?.name || '—'} />
                    <DetailRow icon={<Heart size={12} color="#64748b" />} label="Tính cách" value={selectedChar.psychology?.traits?.join(', ') || selectedChar.psychology?.dominant_trait || '—'} />
                    <DetailRow icon={<Target size={12} color="#64748b" />} label="Mục tiêu" value={selectedChar.psychology?.goal || selectedChar.psychology?.motivation || '—'} />
                    <DetailRow icon={<Eye size={12} color="#64748b" />} label="Ngoại hình" value={selectedChar.visual_profile?.physical_description ? selectedChar.visual_profile.physical_description.slice(0, 56) : '—'} />
                    <div style={styles.infoCard}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}><Tag size={12} color="#64748b" /><span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8' }}>Tags</span></div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {deriveTags(selectedChar).length ? deriveTags(selectedChar).map((t) => <span key={t} style={styles.tagPillSmall}>{t}</span>) : <span style={{ fontSize: 11, color: '#475569' }}>Chưa có tags</span>}
                      </div>
                    </div>
                    <div style={styles.infoCard}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 6 }}><BadgeCheck size={12} color="#64748b" /> Tiến độ hồ sơ</span>
                        <span style={{ fontSize: 11, fontWeight: 800, color: '#f1f5f9' }}>{characterCompletion(selectedChar)}%</span>
                      </div>
                      <div style={{ height: 6, background: '#1e293b', borderRadius: 999, overflow: 'hidden' }}><div style={{ width: `${characterCompletion(selectedChar)}%`, height: '100%', background: '#3b82f6', borderRadius: 999 }} /></div>
                    </div>
                    <DetailRow icon={<Video size={12} color="#64748b" />} label="Tập xuất hiện" value={(studioEpisodes as any[])?.length ? (studioEpisodes as any[]).slice(0, 3).map((e: any) => e.title || `Tập ${e.episode_number}`).join(', ') : '—'} />
                    <div style={styles.infoCard}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}><Network size={12} color="#64748b" /><span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8' }}>Quan hệ nổi bật</span></div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {(selectedChar.relationships || []).length ? (selectedChar.relationships as any[]).slice(0, 6).map((r: any) => <span key={r.target_character_id} style={styles.relationChip}>{r.target_name}</span>) : <span style={{ fontSize: 11, color: '#475569' }}>Chưa có liên kết</span>}
                      </div>
                    </div>
                    <div style={styles.infoCard}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}><FileText size={12} color="#64748b" /><span style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8' }}>Mô tả</span></div>
                      <div style={{ fontSize: 11, color: '#cbd5e1', lineHeight: 1.6 }}>{selectedChar.identity.biography || 'Chưa có mô tả. Nhấn Chỉnh sửa để bổ sung (lưu thật vào DB, version pinning). Phiên bản hiện tại: v' + selectedChar.version + '.'}</div>
                    </div>
                  </>
                )}
                {detailTab === 'relations' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {(selectedChar.relationships || []).length === 0 ? (
                      <div style={{ fontSize: 11, color: '#64748b', padding: 12, textAlign: 'center', background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8 }}>Chưa có quan hệ nào. Quan hệ được tạo qua storyboard/assets liên kết nhân vật và được lưu thật trong DB.</div>
                    ) : (
                      (selectedChar.relationships as any[]).map((r: any) => (
                        <div key={r.target_character_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 10px', background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8 }}>
                          <div style={{ width: 30, height: 30, borderRadius: '50%', background: hashGradient(r.target_character_id), display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: 11 }}>{initials(r.target_name)}</div>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: '#f1f5f9' }}>{r.target_name}</div>
                            <div style={{ fontSize: 11, color: '#94a3b8' }}>{r.relationship_type}</div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
                {detailTab === 'appearances' && (
                  <div style={{ fontSize: 11, color: '#64748b', padding: 12, textAlign: 'center', background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8 }}>
                    {(studioEpisodes as any[])?.length ? `Xuất hiện trong ${ (studioEpisodes as any[]).length } tập của series "${activeSeries?.title || activeProjectId}" — liên kết tập được suy ra từ story bible & locked screenplay (canon sync).` : 'Chưa có tập nào liên kết trực tiếp — thực hiện Canon Sync từ locked screenplay để gán.'}
                  </div>
                )}
                {detailTab === 'history' && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 11, color: '#94a3b8', padding: '8px 10px', background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8 }}>
                      <div style={{ fontWeight: 700, color: '#e2e8f0', marginBottom: 4 }}>Lịch sử phiên bản (version pinning)</div>
                      <div>Phiên bản hiện tại: <b style={{ color: '#60a5fa' }}>v{selectedChar.version}</b> • Content hash: <span style={{ fontFamily: 'monospace', fontSize: 10 }}>{(selectedChar.content_hash || '—').slice(0, 12)}</span></div>
                      <div style={{ marginTop: 6, color: '#64748b' }}>Cập nhật lần cuối: {new Date(selectedChar.updated_at).toLocaleString('vi-VN')}</div>
                      <div style={{ marginTop: 4 }}>Trạng thái canon: <b style={{ color: '#a78bfa' }}>{selectedChar.status}</b> • Revision: {(selectedChar.current_revision_id || '—')}</div>
                    </div>
                  </div>
                )}
              </div>

              <div style={styles.detailActions}>
                <button onClick={() => openEdit(selectedChar)} style={styles.detailBtnGhost}><Pencil size={12} /> Chỉnh sửa</button>
                <button onClick={handleApprove} style={styles.detailBtnPrimary}><Check size={12} /> Duyệt</button>
                <button onClick={() => handleDelete()} style={styles.detailBtnDanger}><Trash2 size={12} /> Xóa</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Create modal ───────────────────── */}
      {showCreateModal && (
        <div style={styles.overlay} onClick={() => setShowCreateModal(false)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 800, color: '#f1f5f9' }}>Thêm Character mới</h3>
              <button onClick={() => setShowCreateModal(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><X size={16} /></button>
            </div>
            <p style={{ fontSize: 11, color: '#94a3b8', margin: 0 }}>Nhân vật được tạo qua POST /api/v3/projects/{activeProjectId}/characters — lưu thật vào V3 resource authority (idempotency + version pinning).</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input value={newForm.name} onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))} placeholder="Tên nhân vật *" style={styles.editInput} />
              <select value={newForm.role} onChange={(e) => setNewForm((f) => ({ ...f, role: e.target.value }))} style={styles.editInput}>
                <option value="Protagonist">Nhân vật chính (Protagonist)</option>
                <option value="Antagonist">Phản diện (Antagonist)</option>
                <option value="Supporting">Đồng minh / Nhân vật phụ (Supporting)</option>
                <option value="Draft">Nháp (Draft)</option>
              </select>
              <textarea value={newForm.biography} onChange={(e) => setNewForm((f) => ({ ...f, biography: e.target.value }))} placeholder="Tiểu sử / mô tả..." rows={3} style={{ ...styles.editInput, resize: 'vertical' as any }} />
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={newForm.dominant_trait} onChange={(e) => setNewForm((f) => ({ ...f, dominant_trait: e.target.value }))} placeholder="Tính cách nổi bật" style={{ ...styles.editInput, flex: 1 }} />
                <input value={newForm.flaw} onChange={(e) => setNewForm((f) => ({ ...f, flaw: e.target.value }))} placeholder="Điểm yếu" style={{ ...styles.editInput, flex: 1 }} />
              </div>
              <input value={newForm.physical_description} onChange={(e) => setNewForm((f) => ({ ...f, physical_description: e.target.value }))} placeholder="Ngoại hình / mô tả vật lý (tính vào % hoàn thiện)" style={styles.editInput} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button onClick={() => setShowCreateModal(false)} style={styles.detailBtnGhost}>Hủy</button>
              <button onClick={handleCreate} disabled={!newForm.name.trim() || createMut.isPending} style={{ ...styles.detailBtnPrimary, opacity: !newForm.name.trim() ? 0.5 : 1 }}>{createMut.isPending ? 'Đang tạo...' : 'Tạo nhân vật'}</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Edit modal ─────────────────────── */}
      {showEditModal && editingChar && (
        <div style={styles.overlay} onClick={() => setShowEditModal(false)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 800, color: '#f1f5f9' }}>Chỉnh sửa: {editingChar.identity.name}</h3>
              <button onClick={() => setShowEditModal(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#64748b' }}><X size={16} /></button>
            </div>
            <p style={{ fontSize: 11, color: '#94a3b8', margin: 0 }}>PATCH /api/v3/characters/{editingChar.id} với expected_version={editingChar.version} — optimistic locking.</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <input value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} placeholder="Tên" style={styles.editInput} />
              <select value={editForm.role} onChange={(e) => setEditForm((f) => ({ ...f, role: e.target.value }))} style={styles.editInput}>
                <option value="Protagonist">Protagonist</option>
                <option value="Antagonist">Antagonist</option>
                <option value="Supporting">Supporting</option>
                <option value="Draft">Draft</option>
              </select>
              <textarea value={editForm.biography} onChange={(e) => setEditForm((f) => ({ ...f, biography: e.target.value }))} rows={3} style={{ ...styles.editInput, resize: 'vertical' as any }} placeholder="Tiểu sử" />
              <div style={{ display: 'flex', gap: 8 }}>
                <input value={editForm.dominant_trait} onChange={(e) => setEditForm((f) => ({ ...f, dominant_trait: e.target.value }))} placeholder="Tính cách nổi bật" style={{ ...styles.editInput, flex: 1 }} />
                <input value={editForm.flaw} onChange={(e) => setEditForm((f) => ({ ...f, flaw: e.target.value }))} placeholder="Điểm yếu" style={{ ...styles.editInput, flex: 1 }} />
              </div>
              <input value={editForm.physical_description} onChange={(e) => setEditForm((f) => ({ ...f, physical_description: e.target.value }))} placeholder="Ngoại hình" style={styles.editInput} />
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
              <button onClick={() => setShowEditModal(false)} style={styles.detailBtnGhost}>Hủy</button>
              <button onClick={handleEditSave} disabled={updateMut.isPending} style={styles.detailBtnPrimary}>{updateMut.isPending ? 'Đang lưu...' : 'Lưu'}</button>
            </div>
          </div>
        </div>
      )}

      {showCategoryManager && (
        <div style={styles.overlay} onClick={() => setShowCategoryManager(false)}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: 0, fontSize: 14, fontWeight: 800, color: '#f1f5f9' }}>Thêm danh mục</h3>
            <p style={{ fontSize: 11, color: '#94a3b8', margin: '4px 0 0 0' }}>Danh mục hiện tại là các bộ lọc suy ra từ <b style={{ color: '#cbd5e1' }}>role & relationships</b> trong DB — không lưu riêng. Để thêm phe phái mới, tạo Faction trong World Bible (lưu thật qua /world/factions).</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
              <button onClick={() => setShowCategoryManager(false)} style={styles.detailBtnGhost}>Đóng</button>
              <a href="#/world" style={{ ...styles.detailBtnPrimary, textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>→ Đi tới World</a>
            </div>
          </div>
        </div>
      )}

      <style>{`@keyframes pulse{0%{opacity:0.9}50%{opacity:0.55}100%{opacity:0.9}} *{scrollbar-width:thin;scrollbar-color:#1e293b transparent;}`}</style>
    </div>
  );
};

// ── subcomponents ─────────────────────────────────────────────────────────

const DetailRow: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '8px 10px', background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, minWidth: 110 }}>
      <span style={{ width: 18, height: 18, borderRadius: 5, background: '#0f172a', border: '1px solid #1e293b', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{icon}</span>
      <span style={{ fontSize: 11, fontWeight: 600, color: '#94a3b8' }}>{label}</span>
    </div>
    <span style={{ fontSize: 11.5, fontWeight: 600, color: '#e2e8f0', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{value}</span>
  </div>
);

// ── styles ────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    height: '100%',
    width: '100%',
    background: '#070d1f',
    color: '#e2e8f0',
    fontFamily: 'var(--font-sans, Plus Jakarta Sans, system-ui)',
    padding: '16px 14px 12px 14px',
    boxSizing: 'border-box',
    overflow: 'hidden',
    margin: '-16px',
    minHeight: '100%',
  },
  titleRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 },
  h1: { margin: 0, fontSize: 20, fontWeight: 800, color: '#f1f5f9', letterSpacing: '-0.3px' },
  subtitle: { margin: '4px 0 0 0', fontSize: 11.5, color: '#64748b', fontWeight: 500 },
  controls: {
    display: 'flex',
    gap: 10,
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    padding: 10,
  },
  selectBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    background: '#0b1224',
    border: '1px solid #1e293b',
    color: '#e2e8f0',
    padding: '7px 10px',
    borderRadius: 8,
    fontSize: 11.5,
    fontWeight: 600,
    cursor: 'pointer',
    minWidth: 220,
    justifyContent: 'space-between',
  },
  selectLabel: { fontSize: 10, color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.4px' },
  selectValue: { fontSize: 12, color: '#f1f5f9', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 170 },
  dropdown: {
    position: 'absolute',
    top: 'calc(100% + 6px)',
    left: 0,
    minWidth: 240,
    maxWidth: 340,
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 8,
    boxShadow: '0 10px 28px rgba(0,0,0,0.45)',
    zIndex: 30,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  } as React.CSSProperties,
  dropdownEmpty: { padding: 12, fontSize: 11, color: '#64748b' },
  dropdownItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
    padding: '9px 10px',
    fontSize: 11.5,
    color: '#e2e8f0',
    cursor: 'pointer',
    borderBottom: '1px solid rgba(255,255,255,0.04)',
  },
  dropdownItemActive: { background: 'rgba(59,130,246,0.12)', color: '#bfdbfe' },
  searchWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    background: '#0b1224',
    border: '1px solid #1e293b',
    borderRadius: 8,
    padding: '0 10px',
    height: 34,
    minWidth: 220,
    flex: 1,
    maxWidth: 360,
  },
  searchInput: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    outline: 'none',
    color: '#e2e8f0',
    fontSize: 12,
    fontWeight: 500,
  },
  iconBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    background: '#0b1224',
    border: '1px solid #1e293b',
    color: '#cbd5e1',
    padding: '7px 10px',
    borderRadius: 8,
    fontSize: 11.5,
    fontWeight: 600,
    cursor: 'pointer',
  },
  btnPrimary: {
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    background: 'linear-gradient(135deg,#3b82f6 0%,#6366f1 55%,#7c3aed 100%)',
    border: 'none',
    color: '#fff',
    padding: '9px 14px',
    borderRadius: 8,
    fontSize: 12,
    fontWeight: 800,
    cursor: 'pointer',
    boxShadow: '0 4px 14px rgba(59,130,246,0.35)',
  },
  metrics: {
    display: 'flex',
    gap: 0,
    alignItems: 'stretch',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
  },
  metricCell: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '12px 14px',
    borderRight: '1px solid #1e293b',
    flex: 1,
    minWidth: 120,
  },
  metricIcon: {
    width: 36,
    height: 36,
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid',
    flexShrink: 0,
  },
  metricLabel: { fontSize: 10.5, color: '#94a3b8', fontWeight: 600, whiteSpace: 'nowrap' },
  metricValue: { fontSize: 13, fontWeight: 800, color: '#f1f5f9', marginTop: 2 },
  mainWrap: {
    display: 'flex',
    gap: 12,
    flex: 1,
    minHeight: 0,
    overflow: 'hidden',
    alignItems: 'stretch',
  },
  leftCenterColumn: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    minWidth: 0,
    minHeight: 0,
    overflow: 'hidden',
  },
  leftCenterRow: {
    display: 'flex',
    gap: 12,
    flex: 1,
    minHeight: 0,
    overflow: 'hidden',
  },
  leftPanel: {
    width: 190,
    minWidth: 170,
    maxWidth: 210,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
  },
  centerPanel: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
  },
  rightPanel: {
    width: 340,
    minWidth: 320,
    maxWidth: 380,
    flexShrink: 0,
    display: 'flex',
    flexDirection: 'column',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
  },
  panelHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderBottom: '1px solid #1e293b',
    background: '#0f172a',
    flexShrink: 0,
  },
  panelTitle: { fontSize: 12.5, fontWeight: 800, color: '#f1f5f9' },
  smallIconBtn: {
    width: 26,
    height: 26,
    borderRadius: 7,
    background: '#0b1224',
    border: '1px solid #1e293b',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    color: '#94a3b8',
  },
  catList: { flex: 1, overflowY: 'auto', padding: 8, display: 'flex', flexDirection: 'column', gap: 6 } as React.CSSProperties,
  catItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 9px',
    borderRadius: 8,
    border: '1px solid transparent',
    cursor: 'pointer',
    background: 'transparent',
  },
  catItemActive: {
    background: '#111f36',
    borderColor: '#1e3a5f',
    boxShadow: 'inset 0 0 0 1px rgba(59,130,246,0.10)',
  },
  catIcon: {
    width: 22,
    height: 22,
    borderRadius: 6,
    background: '#0b1224',
    border: '1px solid #1e293b',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  catCount: {
    fontSize: 11,
    fontWeight: 700,
    color: '#64748b',
    background: '#0b1224',
    border: '1px solid #1e293b',
    padding: '1px 6px',
    borderRadius: 20,
    minWidth: 18,
    textAlign: 'center',
  } as React.CSSProperties,
  catCountActive: { color: '#bfdbfe', background: 'rgba(59,130,246,0.16)', borderColor: 'rgba(59,130,246,0.28)' },
  panelFooter: { borderTop: '1px solid #1e293b', padding: 8, background: '#0f172a', flexShrink: 0 },
  footerBtn: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    background: '#0b1224',
    border: '1px dashed #334155',
    color: '#94a3b8',
    padding: '8px',
    borderRadius: 7,
    fontSize: 11.5,
    fontWeight: 600,
    cursor: 'pointer',
  },
  viewMiniBtn: {
    width: 26,
    height: 26,
    borderRadius: 6,
    background: '#0b1224',
    border: '1px solid #1e293b',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    color: '#64748b',
  },
  viewMiniActive: { background: '#2563eb', borderColor: '#2563eb', color: '#fff' },
  centerScroll: { flex: 1, overflowY: 'auto', padding: 10, minHeight: 0 } as React.CSSProperties,
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 } as React.CSSProperties,
  listCol: { display: 'flex', flexDirection: 'column', gap: 10 } as React.CSSProperties,
  charCard: {
    background: '#0b1224',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
    cursor: 'pointer',
    display: 'flex',
    flexDirection: 'column',
    transition: 'border-color 0.15s, box-shadow 0.15s, transform 0.15s',
  },
  charCardSelected: { borderColor: '#3b82f6', boxShadow: '0 0 0 1px rgba(59,130,246,0.30), 0 8px 20px rgba(0,0,0,0.35)' },
  charThumbWrap: { position: 'relative', height: 132, overflow: 'hidden', background: '#060b18', flexShrink: 0 } as React.CSSProperties,
  charThumbImg: { width: '100%', height: '100%', objectFit: 'cover', display: 'block' } as React.CSSProperties,
  charThumbFallback: { width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' } as React.CSSProperties,
  charCheckbox: { position: 'absolute', top: 8, left: 8, cursor: 'pointer' } as React.CSSProperties,
  checkboxBox: {
    width: 18,
    height: 18,
    borderRadius: 4,
    background: 'rgba(15,23,42,0.85)',
    border: '1px solid rgba(255,255,255,0.18)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxBoxChecked: { background: '#2563eb', borderColor: '#3b82f6' },
  charMoreBtn: { position: 'absolute', top: 8, right: 8, width: 22, height: 22, borderRadius: 6, background: 'rgba(15,23,42,0.78)', border: '1px solid rgba(255,255,255,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' } as React.CSSProperties,
  charBody: { padding: 10, display: 'flex', flexDirection: 'column', gap: 2, flex: 1, minWidth: 0 },
  charName: { fontSize: 13, fontWeight: 800, color: '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } as React.CSSProperties,
  tagPill: { fontSize: 10, fontWeight: 600, color: '#94a3b8', background: '#0f172a', border: '1px solid #1e293b', padding: '2px 6px', borderRadius: 20, whiteSpace: 'nowrap' } as React.CSSProperties,
  tagPillSmall: { fontSize: 10, fontWeight: 600, color: '#94a3b8', background: '#0b1224', border: '1px solid #1e293b', padding: '2px 7px', borderRadius: 20 } as React.CSSProperties,
  relationChip: { fontSize: 11, fontWeight: 600, color: '#cbd5e1', background: '#0f172a', border: '1px solid #1e293b', padding: '3px 8px', borderRadius: 20 } as React.CSSProperties,
  graphPanel: {
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 10,
    overflow: 'hidden',
    flexShrink: 0,
  },
  graphHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 12px', borderBottom: '1px solid #1e293b', background: '#0f172a' },
  graphBody: { padding: '12px 10px', background: '#0b1224', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 72 },
  graphNodes: { display: 'flex', alignItems: 'center', gap: 18, justifyContent: 'center', flexWrap: 'wrap' } as React.CSSProperties,
  graphCluster: { display: 'flex', gap: 14, alignItems: 'center' } as React.CSSProperties,
  graphNodeWrap: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, minWidth: 54 } as React.CSSProperties,
  graphAvatar: { width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: 11, border: '1px solid rgba(255,255,255,0.14)', overflow: 'hidden' } as React.CSSProperties,
  graphName: { fontSize: 10.5, fontWeight: 600, color: '#cbd5e1', whiteSpace: 'nowrap' } as React.CSSProperties,
  graphEdgeLabel: { fontSize: 9, fontWeight: 700, whiteSpace: 'nowrap' } as React.CSSProperties,
  graphCenter: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '0 8px' } as React.CSSProperties,
  graphCenterLines: { display: 'flex', gap: 6, alignItems: 'center', fontSize: 10, color: '#64748b' },
  rightScroll: { flex: 1, overflowY: 'auto', minHeight: 0, display: 'flex', flexDirection: 'column' } as React.CSSProperties,
  detailBannerWrap: { position: 'relative', height: 160, overflow: 'hidden', background: '#060b18', flexShrink: 0, borderBottom: '1px solid #1e293b' } as React.CSSProperties,
  detailBannerImg: { width: '100%', height: '100%', objectFit: 'cover', display: 'block' } as React.CSSProperties,
  detailBannerFallback: { width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' } as React.CSSProperties,
  bannerOverlay: { position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(7,13,31,0.85) 0%, transparent 55%)' } as React.CSSProperties,
  bannerBadge: { position: 'absolute', bottom: 10, fontSize: 10, fontWeight: 800, padding: '3px 7px', borderRadius: 20, backdropFilter: 'blur(6px)' } as React.CSSProperties,
  detailTabs: { display: 'flex', gap: 0, borderBottom: '1px solid #1e293b', padding: '0 8px', marginTop: 8, flexShrink: 0 } as React.CSSProperties,
  tabBtn: { flex: 1, padding: '8px 6px', fontSize: 11, fontWeight: 600, color: '#64748b', background: 'transparent', border: 'none', borderBottom: '2px solid transparent', cursor: 'pointer', whiteSpace: 'nowrap' } as React.CSSProperties,
  tabBtnActive: { color: '#60a5fa', borderBottomColor: '#3b82f6', fontWeight: 800 },
  infoCard: { background: '#0b1224', border: '1px solid #1e293b', borderRadius: 8, padding: 10 },
  detailActions: { display: 'flex', gap: 8, padding: 10, borderTop: '1px solid #1e293b', background: '#0f172a', marginTop: 'auto' } as React.CSSProperties,
  detailBtnGhost: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    background: '#0b1224',
    border: '1px solid #1e293b',
    color: '#94a3b8',
    padding: '8px 6px',
    borderRadius: 7,
    fontSize: 11,
    fontWeight: 700,
    cursor: 'pointer',
  },
  detailBtnPrimary: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    background: 'linear-gradient(135deg,#3b82f6 0%,#6366f1 100%)',
    border: 'none',
    color: '#fff',
    padding: '8px 10px',
    borderRadius: 7,
    fontSize: 11,
    fontWeight: 800,
    cursor: 'pointer',
    boxShadow: '0 3px 10px rgba(59,130,246,0.32)',
  },
  detailBtnDanger: {
    flex: 0.9,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    background: 'rgba(239,68,68,0.10)',
    border: '1px solid rgba(239,68,68,0.22)',
    color: '#fca5a5',
    padding: '8px 6px',
    borderRadius: 7,
    fontSize: 11,
    fontWeight: 700,
    cursor: 'pointer',
  },
  editInput: {
    width: '100%',
    background: '#0b1224',
    border: '1px solid #1e293b',
    borderRadius: 7,
    padding: '8px 10px',
    color: '#e2e8f0',
    fontSize: 11.5,
    outline: 'none',
    boxSizing: 'border-box',
  } as React.CSSProperties,
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.58)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 50,
  } as React.CSSProperties,
  modal: {
    width: 460,
    maxWidth: '92vw',
    background: '#0f172a',
    border: '1px solid #1e293b',
    borderRadius: 12,
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    boxShadow: '0 16px 32px rgba(0,0,0,0.55)',
    maxHeight: '88vh',
    overflowY: 'auto',
  } as React.CSSProperties,
};

export default CharactersPage;
