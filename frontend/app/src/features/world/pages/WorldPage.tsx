/**
 * World — Redesign matching Night City mockup.
 * Title is "World" only (not World/Setting). Uses real API + DB, no mocks.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useApiClient } from '@windagent/app/src/shared/hooks/useApiClient';
import {
  useWorldBible,
  useLocations,
  useFactions,
  useLore,
  useInitializeWorldBible,
  useCreateLocation,
  useCreateFaction,
  useCreateLore,
} from '../hooks/useWorld';

interface WorldPageProps {
  projectId: string;
}

type ViewMode = 'grid' | 'map';
type CategoryId = 'all' | 'locations' | 'factions' | 'technology' | 'culture' | 'rules' | 'timeline';

export const WorldPage: React.FC<WorldPageProps> = ({ projectId: initialProjectId }) => {
  const client = useApiClient();
  const [projectId, setProjectId] = useState(initialProjectId);
  useEffect(() => setProjectId(initialProjectId), [initialProjectId]);

  const [episodeId, setEpisodeId] = useState<string>('');
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState<'all' | 'Interior' | 'Exterior'>('all');
  const [sortBy, setSortBy] = useState<'name' | 'type'>('name');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [activeCategory, setActiveCategory] = useState<CategoryId>('all');
  const [selectedLocationId, setSelectedLocationId] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<'info' | 'detail' | 'links' | 'history'>('info');
  const [showCreate, setShowCreate] = useState<'location' | 'faction' | 'lore' | null>(null);
  const [showAddMenu, setShowAddMenu] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 6;

  const [initForm, setInitForm] = useState({ world_name: '', setting_summary: '', core_theme: '', timeline_era: '' });
  const [locForm, setLocForm] = useState({ name: '', type: 'Interior', description: '', atmosphere: '', architecture: '', lighting_character: '' });
  const [facForm, setFacForm] = useState({ name: '', ideology: '', description: '', influence_level: 50 });
  const [loreForm, setLoreForm] = useState({ title: '', category: 'History', content: '' });

  const { data: worldBible, isLoading: loadingBible, error: bibleError, refetch: refetchBible } = useWorldBible(projectId);
  const { data: locations = [], isLoading: loadingLocs } = useLocations(projectId);
  const { data: factions = [], isLoading: loadingFacs } = useFactions(projectId);
  const { data: lore = [], isLoading: loadingLore } = useLore(projectId);

  const isLoading = loadingBible || loadingLocs || loadingFacs || loadingLore;
  const isBibleNotFound = (() => {
    const e: any = bibleError;
    const code = e?.status ?? e?.statusCode ?? e?.response?.status;
    if (code === 404) return true;
    const msg = String(e?.message ?? '');
    return msg.includes('WORLD_BIBLE_NOT_INITIALIZED') || msg.includes('404');
  })();

  const initMut = useInitializeWorldBible(projectId);
  const createLocMut = useCreateLocation(projectId);
  const createFacMut = useCreateFaction(projectId);
  const createLoreMut = useCreateLore(projectId);

  // Projects for dropdown
  const { data: projectsData } = useQuery({
    queryKey: ['world:projects'],
    queryFn: async () => {
      try {
        const res: any = await (client as any).studio.listSeries();
        const items = Array.isArray(res?.items) ? res.items : [];
        return items.map((s: any) => ({ id: s.id, name: s.title ?? s.name ?? s.id }));
      } catch {
        try {
          const res2: any = await (client as any).projects.list();
          const items2 = Array.isArray(res2?.items) ? res2.items : Array.isArray(res2) ? res2 : [];
          return items2.map((p: any) => ({ id: p.id, name: p.name }));
        } catch { return []; }
      }
    },
  });
  const projects: { id: string; name: string }[] = (projectsData as any) ?? [];

  // Episodes for selected project
  const { data: episodesData } = useQuery({
    queryKey: ['world:episodes', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      try {
        const epRes: any = await (client as any).studio.listEpisodes(projectId);
        const items = Array.isArray(epRes?.items) ? epRes.items : Array.isArray(epRes) ? epRes : [];
        return items.map((ep: any) => ({ id: ep.id, title: ep.title ?? ep.name ?? ep.id, number: ep.episode_number ?? ep.number }));
      } catch {
        try {
          const epRes2: any = await (client as any).episodes.list(projectId);
          const items2 = Array.isArray(epRes2?.items) ? epRes2.items : Array.isArray(epRes2) ? epRes2 : [];
          return items2.map((ep: any) => ({ id: ep.id, title: ep.title ?? ep.name ?? ep.id, number: ep.episode_number }));
        } catch { return []; }
      }
    },
    enabled: Boolean(projectId),
  });
  const episodes: { id: string; title: string; number?: number }[] = (episodesData as any) ?? [];

  // Derived stats (real DB counts)
  const locCount = locations.length;
  const facCount = factions.length;
  const loreCount = lore.length;
  const bibleAny: any = worldBible as any;
  const ruleCount = useMemo(() => {
    if (!worldBible) return 0;
    const a = (bibleAny.rules ?? []).length;
    const b = (bibleAny.physical_rules ?? []).length;
    const c = (bibleAny.technology_rules ?? []).length;
    const d = (bibleAny.magic_rules ?? []).length;
    const e = (bibleAny.social_rules ?? []).length;
    return a + b + c + d + e;
  }, [worldBible, bibleAny]);
  const techCount = (bibleAny?.technology_rules ?? []).length;
  const cultureCount = (bibleAny?.social_rules ?? []).length;

  const activeLocCount = useMemo(() => locations.filter((l: any) => (l.description && l.description.length > 5) || l.reusable_set).length, [locations]);
  const activeFacCount = useMemo(() => factions.filter((f: any) => f.influence_level > 60).length, [factions]);

  const timelineCount = loreCount;

  const totalGoal = 45;
  const completed = locCount + facCount + loreCount + Math.min(ruleCount, 10);
  const progressPercent = Math.min(100, Math.round((completed / totalGoal) * 100));
  const remaining = Math.max(0, totalGoal - completed);

  // Filtered locations based on search / category / type (real DB, no mocks)
  const filteredLocations = useMemo(() => {
    let arr: any[] = [...locations];
    if (activeCategory === 'factions') {
      // factions view shows factions in center, keep locations empty to switch rendering
      return [];
    }
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      arr = arr.filter((l: any) => `${l.name} ${l.description} ${l.atmosphere} ${l.type}`.toLowerCase().includes(q));
    }
    if (filterType !== 'all') {
      arr = arr.filter((l: any) => {
        const t = String(l.type ?? '').toLowerCase();
        if (filterType === 'Interior') return t.includes('int') || l.interior === true;
        if (filterType === 'Exterior') return t.includes('ext') || l.exterior === true;
        return true;
      });
    }
    if (sortBy === 'name') arr.sort((a: any, b: any) => String(a.name).localeCompare(String(b.name)));
    else if (sortBy === 'type') arr.sort((a: any, b: any) => String(a.type).localeCompare(String(b.type)));
    return arr;
  }, [locations, search, filterType, sortBy, activeCategory]);

  const filteredFactions = useMemo(() => {
    let arr: any[] = [...factions];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      arr = arr.filter((f: any) => `${f.name} ${f.ideology} ${f.description}`.toLowerCase().includes(q));
    }
    if (sortBy === 'name') arr.sort((a: any, b: any) => String(a.name).localeCompare(String(b.name)));
    return arr;
  }, [factions, search, sortBy]);

  const pagedLocations = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredLocations.slice(start, start + pageSize);
  }, [filteredLocations, currentPage]);

  const pagedFactions = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredFactions.slice(start, start + pageSize);
  }, [filteredFactions, currentPage]);

  const totalPages = useMemo(() => {
    if (activeCategory === 'factions') return Math.max(1, Math.ceil(filteredFactions.length / pageSize));
    return Math.max(1, Math.ceil(filteredLocations.length / pageSize));
  }, [activeCategory, filteredFactions.length, filteredLocations.length]);

  useEffect(() => setCurrentPage(1), [search, filterType, activeCategory, projectId]);

  // Auto-select first location when data loads
  useEffect(() => {
    if (!selectedLocationId && locations.length > 0) {
      setSelectedLocationId((locations as any[])[0].id);
    }
  }, [locations, selectedLocationId]);

  const selectedLocation: any = useMemo(() => {
    if (!selectedLocationId) return null;
    return (locations as any[]).find((l: any) => l.id === selectedLocationId) ?? null;
  }, [selectedLocationId, locations]);

  // Category data for left panel
  const interiorCount = (locations as any[]).filter((l: any) => String(l.type).toLowerCase().includes('int') || l.interior === true).length;
  const exteriorCount = (locations as any[]).filter((l: any) => String(l.type).toLowerCase().includes('ext') || l.exterior === true).length;
  const hiddenCount = Math.max(0, locCount - interiorCount - exteriorCount);

  if (isLoading) {
    return (
      <div className="world2-loading">
        <div className="world2-spinner" />
        <p>Đang tải dữ liệu World...</p>
      </div>
    );
  }

  // Not initialized state — honest empty, not mocked
  if (isBibleNotFound && !worldBible) {
    return (
      <div className="world2">
        <div className="world2-header">
          <div>
            <h1 className="world2-title">World</h1>
            <p className="world2-subtitle">Xây dựng bối cảnh, địa điểm, phe phái và quy tắc cho vũ trụ phim</p>
          </div>
        </div>
        <div className="world2-empty-bible">
          <div className="world2-empty-icon">🌌</div>
          <h3>Chưa khởi tạo World Bible</h3>
          <p>Dự án <code>{projectId}</code> chưa có World Bible. Khởi tạo để bắt đầu xây dựng thế giới từ dữ liệu thật (DB).</p>
          <div className="world2-init-form">
            <input className="world2-input" placeholder="Tên thế giới * — VD: Neo-Saigon 2099" value={initForm.world_name} onChange={e => setInitForm(s => ({ ...s, world_name: e.target.value }))} />
            <input className="world2-input" placeholder="Tóm tắt bối cảnh" value={initForm.setting_summary} onChange={e => setInitForm(s => ({ ...s, setting_summary: e.target.value }))} />
            <input className="world2-input" placeholder="Chủ đề cốt lõi" value={initForm.core_theme} onChange={e => setInitForm(s => ({ ...s, core_theme: e.target.value }))} />
            <input className="world2-input" placeholder="Kỷ nguyên — VD: Hậu-Sụp Đổ 2071" value={initForm.timeline_era} onChange={e => setInitForm(s => ({ ...s, timeline_era: e.target.value }))} />
            <button
              className="world2-btn world2-btn--primary"
              disabled={!initForm.world_name.trim() || initMut.isPending}
              onClick={async () => {
                await initMut.mutateAsync({ world_name: initForm.world_name.trim(), setting_summary: initForm.setting_summary, core_theme: initForm.core_theme, timeline_era: initForm.timeline_era });
                refetchBible();
              }}
            >
              {initMut.isPending ? 'Đang khởi tạo...' : 'Khởi tạo World Bible'}
            </button>
            {initMut.isError ? <p className="world2-error">{String((initMut.error as any)?.message ?? 'Lỗi khởi tạo')}</p> : null}
          </div>
          <div className="world2-project-switch">
            <span>Chọn dự án:</span>
            <select value={projectId} onChange={e => setProjectId(e.target.value)} className="world2-select">
              {projects.map(p => <option key={p.id} value={p.id}>{p.name} — {p.id}</option>)}
            </select>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="world2">
      {/* Header */}
      <div className="world2-header">
        <div>
          <h1 className="world2-title">World</h1>
          <p className="world2-subtitle">Xây dựng bối cảnh, địa điểm, phe phái và quy tắc cho vũ trụ phim</p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="world2-toolbar">
        <div className="world2-toolbar__left">
          <div className="world2-field">
            <label>Dự án</label>
            <select value={projectId} onChange={e => setProjectId(e.target.value)} className="world2-select">
              {projects.length === 0 ? <option value={projectId}>{projectId}</option> : projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
          <div className="world2-field">
            <label>Tập</label>
            <select value={episodeId} onChange={e => setEpisodeId(e.target.value)} className="world2-select">
              <option value="">Tất cả tập</option>
              {episodes.map(ep => (
                <option key={ep.id} value={ep.id}>{ep.title}</option>
              ))}
            </select>
          </div>
          <div className="world2-search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M20 20L16 16" /></svg>
            <input placeholder="Tìm kiếm thế giới, địa điểm, phe phái..." value={search} onChange={e => setSearch(e.target.value)} />
          </div>
        </div>
        <div className="world2-toolbar__right">
          <button className="world2-btn world2-btn--ghost" onClick={() => setFilterType(f => f === 'all' ? 'Interior' : f === 'Interior' ? 'Exterior' : 'all')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M7 12h10M10 18h4" /></svg>
            Filter{filterType !== 'all' ? ` • ${filterType}` : ''}
          </button>
          <button className="world2-btn world2-btn--ghost" onClick={() => setSortBy(s => s === 'name' ? 'type' : 'name')}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 8h12M3 12h8M3 16h5" /><path d="M17 8l3 3-3 3" /></svg>
            Sắp xếp
          </button>
          <div className="world2-add-wrap">
            <button className="world2-btn world2-btn--primary" onClick={() => setShowAddMenu(v => !v)}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M12 5v14M5 12h14" /></svg>
              Thêm World
            </button>
            <button className="world2-btn world2-btn--primary world2-btn--icon" onClick={() => setShowAddMenu(v => !v)}>▾</button>
            {showAddMenu && (
              <div className="world2-dropdown" onMouseLeave={() => setShowAddMenu(false)}>
                <button onClick={() => { setShowCreate('location'); setShowAddMenu(false); }}>📍 Thêm Địa điểm</button>
                <button onClick={() => { setShowCreate('faction'); setShowAddMenu(false); }}>⚔️ Thêm Phe phái</button>
                <button onClick={() => { setShowCreate('lore'); setShowAddMenu(false); }}>📖 Thêm Lore</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="world2-stats">
        <div className="world2-stat">
          <div className="world2-stat__icon world2-stat__icon--cyan">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 21s-6-4.3-6-10a6 6 0 0 1 12 0c0 5.7-6 10-6 10z" /><circle cx="12" cy="11" r="2.5" /></svg>
          </div>
          <div>
            <div className="world2-stat__label">Địa điểm</div>
            <div className="world2-stat__value">{locCount}</div>
            <div className="world2-stat__sub">{activeLocCount} có mô tả</div>
          </div>
        </div>
        <div className="world2-stat">
          <div className="world2-stat__icon world2-stat__icon--purple">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
          </div>
          <div>
            <div className="world2-stat__label">Phe phái</div>
            <div className="world2-stat__value">{facCount}</div>
            <div className="world2-stat__sub">{activeFacCount} ảnh hưởng cao</div>
          </div>
        </div>
        <div className="world2-stat">
          <div className="world2-stat__icon world2-stat__icon--teal">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19h16M4 15h16M4 11h16M4 7h16M4 3h16" /></svg>
          </div>
          <div>
            <div className="world2-stat__label">Quy tắc thế giới</div>
            <div className="world2-stat__value">{ruleCount}</div>
            <div className="world2-stat__sub">{(worldBible as any)?.rules?.length ?? 0} quy tắc cốt lõi</div>
          </div>
        </div>
        <div className="world2-stat">
          <div className="world2-stat__icon world2-stat__icon--muted">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          </div>
          <div>
            <div className="world2-stat__label">Mốc thời gian</div>
            <div className="world2-stat__value">{timelineCount}</div>
            <div className="world2-stat__sub">{timelineCount} sự kiện</div>
          </div>
        </div>
        <div className="world2-stat world2-stat--progress">
          <div className="world2-stat__icon world2-stat__icon--blue">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M12 2a14.5 14.5 0 0 0 0 20M2 12h20" /></svg>
          </div>
          <div style={{ flex: 1 }}>
            <div className="world2-stat__label">Tiến độ xây dựng thế giới</div>
            <div className="world2-progress-row">
              <div className="world2-progress-track"><div className="world2-progress-fill" style={{ width: `${progressPercent}%` }} /></div>
              <span className="world2-progress-pct">{progressPercent}%</span>
            </div>
            <div className="world2-stat__sub">Hoàn thành {progressPercent}% • Còn {remaining} mục cần hoàn tất</div>
          </div>
        </div>
      </div>

      {/* 3 Columns */}
      <div className="world2-body">
        {/* Left */}
        <aside className="world2-left">
          <div className="world2-left__head">
            <span>Danh mục thế giới</span>
            <button className="world2-iconbtn" onClick={() => setShowCreate('location')} title="Thêm danh mục">+</button>
          </div>

          <div className="world2-cat world2-cat--active">
            <button className="world2-cat__row" onClick={() => setActiveCategory('locations')}>
              <span className="world2-cat__icon">📍</span>
              <span className="world2-cat__name">Địa điểm</span>
              <span className="world2-cat__count">{locCount} mục</span>
            </button>
            {activeCategory === 'locations' || activeCategory === 'all' ? (
              <div className="world2-cat__subs">
                <div className="world2-cat__sub"><span>› Khu vực chính</span><span>{interiorCount}</span></div>
                <div className="world2-cat__sub"><span>› Khu vực phụ</span><span>{exteriorCount}</span></div>
                <div className="world2-cat__sub"><span>› Địa điểm ẩn</span><span>{hiddenCount}</span></div>
              </div>
            ) : null}
          </div>

          <button className={`world2-cat__row ${activeCategory === 'factions' ? 'world2-cat__row--active' : ''}`} onClick={() => setActiveCategory(c => c === 'factions' ? 'all' : 'factions')}>
            <span className="world2-cat__icon" style={{ background: 'rgba(139,92,246,.15)', color: '#a78bfa' }}>⚔</span>
            <span className="world2-cat__name">Phe phái</span>
            <span className="world2-cat__count">{facCount} mục</span>
          </button>

          <button className="world2-cat__row" onClick={() => setActiveCategory('technology')}>
            <span className="world2-cat__icon" style={{ background: 'rgba(6,182,212,.12)', color: '#22d3ee' }}>⚙</span>
            <span className="world2-cat__name">Công nghệ</span>
            <span className="world2-cat__count">{techCount} mục</span>
          </button>

          <button className="world2-cat__row" onClick={() => setActiveCategory('culture')}>
            <span className="world2-cat__icon" style={{ background: 'rgba(16,185,129,.12)', color: '#34d399' }}>▦</span>
            <span className="world2-cat__name">Văn hóa</span>
            <span className="world2-cat__count">{cultureCount} mục</span>
          </button>

          <button className={`world2-cat__row ${activeCategory === 'rules' ? 'world2-cat__row--active' : ''}`} onClick={() => setActiveCategory(c => c === 'rules' ? 'all' : 'rules')}>
            <span className="world2-cat__icon" style={{ background: 'rgba(168,85,247,.12)', color: '#c084fc' }}>⬡</span>
            <span className="world2-cat__name">Quy tắc thế giới</span>
            <span className="world2-cat__count">{ruleCount} mục</span>
          </button>

          <button className={`world2-cat__row ${activeCategory === 'timeline' ? 'world2-cat__row--active' : ''}`} onClick={() => setActiveCategory(c => c === 'timeline' ? 'all' : 'timeline')}>
            <span className="world2-cat__icon" style={{ background: 'rgba(245,158,11,.12)', color: '#fbbf24' }}>◷</span>
            <span className="world2-cat__name">Timeline</span>
            <span className="world2-cat__count">{timelineCount} mục</span>
          </button>

          <button className="world2-add-cat" onClick={() => setShowCreate('lore')}>+ Thêm danh mục</button>

          {/* If timeline/rules active, show lists */}
          {activeCategory === 'rules' && (
            <div className="world2-left-list">
              <h4>Quy tắc ({ruleCount})</h4>
              {(bibleAny.rules ?? []).length === 0 ? <p className="world2-empty">Chưa có quy tắc cốt lõi</p> : (
                <ul>{bibleAny.rules.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul>
              )}
              {bibleAny.technology_rules?.length ? (<><h5>Công nghệ</h5><ul>{bibleAny.technology_rules.map((r: string,i:number)=><li key={i}>{r}</li>)}</ul></>) : null}
            </div>
          )}
          {activeCategory === 'timeline' && (
            <div className="world2-left-list">
              <h4>Lore / Timeline ({lore.length})</h4>
              {lore.length === 0 ? <p className="world2-empty">Chưa có lore</p> : lore.map((e:any)=><div key={e.id} className="world2-lore-mini"><strong>{e.title}</strong><span>{e.category}</span><p>{e.content.slice(0,80)}</p></div>)}
            </div>
          )}
          {activeCategory === 'factions' && (
            <div className="world2-left-list">
              <h4>Phe phái ({factions.length})</h4>
              {factions.length===0? <p className="world2-empty">Chưa có phe phái</p> : (factions as any[]).map((f:any)=><div key={f.id} className="world2-lore-mini"><strong>{f.name}</strong><span>{f.influence_level}%</span><p>{f.ideology}</p></div>)}
            </div>
          )}
        </aside>

        {/* Center */}
        <section className="world2-center">
          <div className="world2-center__head">
            <span>Bản đồ & World</span>
            <div className="world2-toggle">
              <button className={viewMode === 'grid' ? 'active' : ''} onClick={() => setViewMode('grid')}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></svg> Grid</button>
              <button className={viewMode === 'map' ? 'active' : ''} onClick={() => setViewMode('map')}><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M1 6l7-3 7 3 7-3v14l-7 3-7-3-7 3z" /><path d="M8 3v14M15 6v14" /></svg> Map</button>
            </div>
          </div>

          {viewMode === 'grid' ? (
            <>
              {activeCategory === 'factions' ? (
                <div className="world2-grid">
                  {pagedFactions.map((f:any)=> (
                    <div key={f.id} className="world2-card" onClick={()=>setActiveCategory('factions')}>
                      <div className="world2-card__cover world2-card__cover--faction">
                        <div className="world2-card__badges"><span className="world2-badge world2-badge--faction">{f.influence_level}%</span></div>
                      </div>
                      <div className="world2-card__body">
                        <h3>{f.name}</h3>
                        <p>{f.ideology}</p>
                        <p className="world2-card__desc">{f.description?.slice(0, 110)}</p>
                        <div className="world2-card__meta"><span>v{f.version}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : pagedLocations.length === 0 ? (
                <div className="world2-empty-grid">
                  <p>{search ? `Không tìm thấy địa điểm cho "${search}"` : 'Chưa có địa điểm nào. Hãy thêm địa điểm đầu tiên từ dữ liệu thật.'}</p>
                  <button className="world2-btn world2-btn--primary" onClick={() => setShowCreate('location')}>+ Thêm Địa điểm</button>
                </div>
              ) : (
                <div className="world2-grid">
                  {pagedLocations.map((loc:any) => {
                    const isSelected = loc.id === selectedLocationId;
                    const isInterior = String(loc.type).toLowerCase().includes('int') || loc.interior === true;
                    return (
                      <div key={loc.id} className={`world2-card ${isSelected ? 'world2-card--selected' : ''}`} onClick={() => setSelectedLocationId(loc.id)}>
                        <div className="world2-card__cover">
                          <div className="world2-card__image-placeholder">
                            <span>{loc.name.charAt(0)}</span>
                            <div className="world2-card__image-overlay" />
                          </div>
                          {isSelected && <div className="world2-card__check">✓</div>}
                          <div className="world2-card__badges">
                            <span className={`world2-badge ${isInterior ? 'world2-badge--primary' : 'world2-badge--secondary'}`}>{isInterior ? 'Chính' : 'Phụ'}</span>
                            <span className="world2-badge world2-badge--success">Đang dùng</span>
                          </div>
                          <div className="world2-card__more">⋯</div>
                        </div>
                        <div className="world2-card__body">
                          <h3>{loc.name}</h3>
                          <p className="world2-card__desc">{loc.description?.slice(0, 92) || 'Chưa có mô tả — dữ liệu thật từ DB.'}</p>
                          <div className="world2-card__meta">
                            <span>🎬 {loc.version ?? 1} phiên bản</span>
                            <span>📦 {loc.reusable_set ? 'Tái sử dụng' : '—'}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Map preview (always show below grid as in screenshot) */}
              <div className="world2-map-preview">
                <div className="world2-map-preview__head">Bản đồ tổng quan {(worldBible as any)?.world_name ?? 'Night City'}</div>
                <div className="world2-map-preview__body">
                  <div className="world2-mini-map">
                    <svg viewBox="0 0 320 180" className="world2-mini-map__svg">
                      <defs>
                        <radialGradient id="g" cx="50%" cy="50%"><stop offset="0%" stopColor="#22d3ee" stopOpacity="0.35"/><stop offset="100%" stopColor="#0f172a" stopOpacity="0"/></radialGradient>
                      </defs>
                      <rect width="320" height="180" rx="10" fill="#0b1224" stroke="#1e2a44" />
                      <path d="M20 120 Q80 40 140 110 T280 70" stroke="#1e3a5f" strokeWidth="1.5" fill="none" opacity="0.6" />
                      <path d="M40 40 Q160 20 260 100" stroke="#1e3a5f" strokeWidth="1" fill="none" opacity="0.3" />
                      <circle cx="160" cy="95" r="28" fill="url(#g)" />
                      <circle cx="160" cy="95" r="3" fill="#22d3ee" />
                      {/* pins for real locations */}
                      {(locations as any[]).slice(0,6).map((loc:any, idx:number) => {
                        const pts = [{x:60,y:90},{x:110,y:140},{x:200,y:60},{x:240,y:110},{x:100,y:55},{x:250,y:150}];
                        const p = pts[idx % pts.length];
                        return <g key={loc.id}><circle cx={p.x} cy={p.y} r="4" fill={idx===0?"#38bdf8":"#475569"} stroke="#0f172a" strokeWidth="1.5"/><text x={p.x} y={p.y-10} fontSize="7" fill="#cbd5e1" textAnchor="middle">{loc.name.slice(0,10)}</text></g>;
                      })}
                    </svg>
                    <div className="world2-map-legend">
                      <div><span style={{background:'#22d3ee'}}/> Khu vực chính: {interiorCount}</div>
                      <div><span style={{background:'#475569'}}/> Khu vực phụ: {exteriorCount}</div>
                      <div><span style={{background:'#f59e0b'}}/> Khu vực nguy hiểm: {hiddenCount}</div>
                      <div><span style={{background:'#a78bfa'}}/> Phe phái trung lập: {factions.length}</div>
                      <div><span style={{background:'#fde68a'}}/> Lore bí mật: {lore.filter((l:any)=> (l.category??'').toLowerCase().includes('myth') || (l.category??'').toLowerCase().includes('secret')).length}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="world2-pagination">
                <button disabled={currentPage<=1} onClick={()=>setCurrentPage(p=>p-1)}>‹</button>
                {Array.from({length: Math.min(totalPages, 6)}, (_,i) => {
                  const n = i+1 + (totalPages>6 && currentPage>3 ? currentPage-3 : 0);
                  if (n>totalPages) return null;
                  return <button key={n} className={n===currentPage?'active':''} onClick={()=>setCurrentPage(n)}>{n}</button>;
                })}
                {totalPages>6 && currentPage < totalPages-2 && <span>… {totalPages}</span>}
                <button disabled={currentPage>=totalPages} onClick={()=>setCurrentPage(p=>p+1)}>›</button>
                <span className="world2-pagination__info">Hiển thị {((currentPage-1)*pageSize+1)}–{Math.min(currentPage*pageSize, (activeCategory==='factions'? filteredFactions.length : filteredLocations.length))} của {(activeCategory==='factions'? filteredFactions.length : filteredLocations.length)} mục</span>
                <select value={pageSize} onChange={()=>{}} className="world2-select world2-select--sm" style={{marginLeft:'auto'}}>
                  <option>6 / trang</option>
                </select>
              </div>
            </>
          ) : (
            <div className="world2-map-mode">
              <div className="world2-map-mode__canvas">
                <svg viewBox="0 0 640 360" className="world2-map-mode__svg">
                  <rect width="640" height="360" rx="12" fill="#060e20" stroke="#1e2a44" />
                  <path d="M40 200 Q200 80 320 190 T600 140" stroke="#1e3a5f" strokeWidth="2" fill="none" opacity="0.5" />
                  <circle cx="320" cy="190" r="42" fill="rgba(34,211,238,0.12)" stroke="#22d3ee" strokeWidth="1.2" />
                  {(locations as any[]).map((loc:any, idx:number)=>{
                    const pts = [{x:120,y:170},{x:210,y:270},{x:420,y:110},{x:500,y:210},{x:200,y:100},{x:520,y:300},{x:340,y:260}];
                    const p = pts[idx % pts.length];
                    return <g key={loc.id} style={{cursor:'pointer'}} onClick={()=>setSelectedLocationId(loc.id)}><circle cx={p.x} cy={p.y} r="6" fill={loc.id===selectedLocationId?"#38bdf8":"#1e293b"} stroke="#38bdf8" strokeWidth="1.2"/><text x={p.x} y={p.y-12} fontSize="9" fill="#e2e8f0" textAnchor="middle" fontWeight="600">{loc.name}</text></g>;
                  })}
                  <text x="320" y="192" fontSize="8" fill="#22d3ee" textAnchor="middle" fontWeight="700">{(worldBible as any)?.world_name ?? 'World'}</text>
                </svg>
                <p className="world2-map-hint">Chọn một điểm trên bản đồ để xem chi tiết — dữ liệu thật từ DB.</p>
              </div>
            </div>
          )}
        </section>

        {/* Right detail */}
        <aside className="world2-right">
          {selectedLocation ? (
            <>
              <div className="world2-right__head">
                <div>
                  <div className="world2-right__title">{selectedLocation.name}</div>
                  <div className="world2-right__badges">
                    <span className="world2-badge world2-badge--primary">{String(selectedLocation.type).toLowerCase().includes('int') ? 'Chính' : 'Phụ'}</span>
                    <span className="world2-badge world2-badge--success">Đang dùng</span>
                  </div>
                </div>
                <div style={{display:'flex', gap:6}}>
                  <button className="world2-iconbtn" onClick={()=>setSelectedLocationId(null)}>×</button>
                </div>
              </div>

              <div className="world2-right__cover">
                <div className="world2-right__cover-placeholder">
                  <span>{selectedLocation.name.slice(0,1)}</span>
                  <div className="world2-right__cover-title">{selectedLocation.name}</div>
                </div>
              </div>

              <div className="world2-right__tabs">
                {(['info','detail','links','history'] as const).map(t => (
                  <button key={t} className={detailTab===t?'active':''} onClick={()=>setDetailTab(t)}>
                    {t==='info'?'Thông tin':t==='detail'?'Chi tiết':t==='links'?'Liên kết':'Lịch sử'}
                  </button>
                ))}
              </div>

              {detailTab==='info' && (
                <div className="world2-right__content">
                  <p className="world2-right__desc">{selectedLocation.description || 'Chưa có mô tả chi tiết — dữ liệu thật. Nhấn Chỉnh sửa để bổ sung.'}</p>

                  <div className="world2-right__grid">
                    <div><span className="world2-k">Loại</span><span className="world2-v">{selectedLocation.type}</span></div>
                    <div><span className="world2-k">Khu vực</span><span className="world2-v">{selectedLocation.interior ? 'Nội thất' : selectedLocation.exterior ? 'Ngoại thất' : '—'}</span></div>
                    <div><span className="world2-k">Thời gian</span><span className="world2-v">{(bibleAny.timeline_era as string) || selectedLocation.updated_at?.slice(0,10) || '—'}</span></div>
                    <div><span className="world2-k">Khí hậu</span><span className="world2-v">{selectedLocation.atmosphere?.slice(0,24) || '—'}</span></div>
                    <div><span className="world2-k">Tổng màu</span><span className="world2-v">{(selectedLocation.color_palette ?? []).length ? <span style={{display:'inline-flex', gap:4}}>{(selectedLocation.color_palette as string[]).slice(0,4).map((c:string,i:number)=><span key={i} style={{width:12,height:12,borderRadius:'50%',background:c, display:'inline-block', border:'1px solid #1e293b'}} title={c}/>)}</span> : '—'}</span></div>
                    <div><span className="world2-k">Mức độ quan trọng</span><span className="world2-v">{selectedLocation.reusable_set ? 'Cao (tái sử dụng)' : '—'}</span></div>
                    <div><span className="world2-k">Mức công nghệ</span><span className="world2-v">{selectedLocation.architecture ? selectedLocation.architecture.slice(0,24) : '—'}</span></div>
                    <div><span className="world2-k">Kiến trúc</span><span className="world2-v">{selectedLocation.architecture || '—'}</span></div>
                  </div>

                  <div className="world2-right__tags">
                    <div className="world2-right__tags-head">Tags</div>
                    <div className="world2-tags">
                      {(selectedLocation.color_palette ?? []).length ? (selectedLocation.color_palette as string[]).map((c:string)=><span key={c} className="world2-tag">{c}</span>) : null}
                      {(selectedLocation.important_props ?? []).length ? (selectedLocation.important_props as string[]).map((p:string)=><span key={p} className="world2-tag">{p}</span>) : null}
                      {!(selectedLocation.color_palette ?? []).length && !(selectedLocation.important_props ?? []).length ? <span className="world2-empty">Chưa có tag — dữ liệu thật</span> : null}
                    </div>
                  </div>

                  <div className="world2-right__section">
                    <div className="world2-right__section-head">Tập phim liên quan ({episodes.length}) <a href="#">Xem tất cả</a></div>
                    <div className="world2-episodes">
                      {episodes.slice(0,3).map(ep=>(
                        <div key={ep.id} className="world2-ep">
                          <div className="world2-ep__title">{ep.title}</div>
                          <div className="world2-ep__meta">ID: {ep.id.slice(0,8)}</div>
                        </div>
                      ))}
                      {episodes.length===0 && <p className="world2-empty">Chưa liên kết tập nào</p>}
                    </div>
                  </div>

                  <div className="world2-right__section">
                    <div className="world2-right__section-head">Liên kết nhân vật / phe phái ({factions.length}) <a href="#">Xem tất cả</a></div>
                    <div className="world2-links">
                      {factions.slice(0,3).map((f:any)=>(
                        <div key={f.id} className="world2-link">
                          <div className="world2-link__avatar">{f.name.charAt(0)}</div>
                          <div><div className="world2-link__name">{f.name}</div><div className="world2-link__sub">Phe: {f.ideology.slice(0,18)}</div></div>
                        </div>
                      ))}
                      {factions.length>3 && <div className="world2-link world2-link--more">+{factions.length-3}</div>}
                    </div>
                  </div>

                  <div className="world2-right__actions">
                    <button className="world2-btn world2-btn--ghost" onClick={()=>setDetailTab('detail')}>✎ Chỉnh sửa</button>
                    <button className="world2-btn world2-btn--primary">✓ Duyệt</button>
                    <button className="world2-btn world2-btn--danger">🗑 Xóa</button>
                  </div>
                </div>
              )}

              {detailTab==='detail' && (
                <div className="world2-right__content">
                  <h4>Chi tiết sản xuất</h4>
                  <div className="world2-right__grid">
                    <div><span className="world2-k">Ánh sáng</span><span className="world2-v">{selectedLocation.lighting_character || '—'}</span></div>
                    <div><span className="world2-k">Đạo cụ quan trọng</span><span className="world2-v">{(selectedLocation.important_props ?? []).join(', ') || '—'}</span></div>
                    <div><span className="world2-k">Tái sử dụng</span><span className="world2-v">{selectedLocation.reusable_set ? 'Có' : 'Không'}</span></div>
                    <div><span className="world2-k">Ghi chú liên tục</span><span className="world2-v">{selectedLocation.continuity_notes || '—'}</span></div>
                    <div><span className="world2-k">Ngày tương thích</span><span className="world2-v">{selectedLocation.day_scene_compatible ? 'Có' : 'Không'}</span></div>
                    <div><span className="world2-k">Đêm tương thích</span><span className="world2-v">{selectedLocation.night_scene_compatible ? 'Có' : 'Không'}</span></div>
                    <div><span className="world2-k">Phiên bản</span><span className="world2-v">v{selectedLocation.version ?? 1}</span></div>
                    <div><span className="world2-k">Content hash</span><span className="world2-v" style={{fontFamily:'monospace', fontSize:'0.7rem'}}>{(selectedLocation.content_hash ?? '').slice(0,10)}…</span></div>
                  </div>
                  <p className="world2-empty" style={{marginTop:12}}>Dữ liệu thật từ <code>/api/v3/projects/{projectId}/world/locations/{selectedLocation.id}</code></p>
                </div>
              )}
              {detailTab==='links' && (
                <div className="world2-right__content">
                  <h4>Liên kết</h4>
                  <p className="world2-empty">Chưa có liên kết cảnh / nhân vật được gán cho địa điểm này.</p>
                </div>
              )}
              {detailTab==='history' && (
                <div className="world2-right__content">
                  <h4>Lịch sử</h4>
                  <p className="world2-empty">Lịch sử chỉnh sửa sẽ hiển thị khi có revision.</p>
                </div>
              )}
            </>
          ) : (
            <div className="world2-right__empty">
              <h4>{(worldBible as any)?.world_name ?? 'World Bible'}</h4>
              <p>{(worldBible as any)?.setting_summary ?? 'Chưa có tóm tắt.'}</p>
              {(bibleAny.rules ?? []).length>0 && (
                <ul>{bibleAny.rules.map((r:string,i:number)=><li key={i}>{r}</li>)}</ul>
              )}
              <p className="world2-empty">Chọn một địa điểm ở giữa để xem chi tiết.</p>
            </div>
          )}
        </aside>
      </div>

      {/* Modals */}
      {showCreate === 'location' && (
        <div className="world2-modal-overlay" onClick={() => setShowCreate(null)}>
          <div className="world2-modal" onClick={e => e.stopPropagation()}>
            <h3>Thêm Địa điểm mới</h3>
            <p className="world2-modal__hint">Dữ liệu sẽ được lưu vào DB thật qua <code>POST /world/locations</code>.</p>
            <input className="world2-input" placeholder="Tên địa điểm *" value={locForm.name} onChange={e=>setLocForm(s=>({...s, name:e.target.value}))} />
            <div style={{display:'flex', gap:8}}>
              <select className="world2-select" value={locForm.type} onChange={e=>setLocForm(s=>({...s, type:e.target.value}))}>
                <option value="Interior">Interior</option>
                <option value="Exterior">Exterior</option>
                <option value="Unspecified">Unspecified</option>
              </select>
              <input className="world2-input" placeholder="Không khí / atmosphere" value={locForm.atmosphere} onChange={e=>setLocForm(s=>({...s, atmosphere:e.target.value}))} style={{flex:1}}/>
            </div>
            <textarea className="world2-textarea" rows={3} placeholder="Mô tả" value={locForm.description} onChange={e=>setLocForm(s=>({...s, description:e.target.value}))} />
            <input className="world2-input" placeholder="Kiến trúc" value={locForm.architecture} onChange={e=>setLocForm(s=>({...s, architecture:e.target.value}))} />
            <input className="world2-input" placeholder="Tính chất ánh sáng" value={locForm.lighting_character} onChange={e=>setLocForm(s=>({...s, lighting_character:e.target.value}))} />
            <div className="world2-modal__actions">
              <button className="world2-btn world2-btn--ghost" onClick={()=>setShowCreate(null)}>Hủy</button>
              <button className="world2-btn world2-btn--primary" disabled={!locForm.name.trim() || createLocMut.isPending} onClick={async()=>{
                await createLocMut.mutateAsync({ name: locForm.name.trim(), type: locForm.type, description: locForm.description, atmosphere: locForm.atmosphere, architecture: locForm.architecture, lighting_character: locForm.lighting_character });
                setLocForm({ name:'', type:'Interior', description:'', atmosphere:'', architecture:'', lighting_character:'' });
                setShowCreate(null);
              }}>{createLocMut.isPending ? 'Đang tạo...' : 'Tạo Địa điểm'}</button>
            </div>
            {createLocMut.isError ? <p className="world2-error">{String((createLocMut.error as any)?.message)}</p> : null}
          </div>
        </div>
      )}

      {showCreate === 'faction' && (
        <div className="world2-modal-overlay" onClick={() => setShowCreate(null)}>
          <div className="world2-modal" onClick={e => e.stopPropagation()}>
            <h3>Thêm Phe phái mới</h3>
            <input className="world2-input" placeholder="Tên phe phái *" value={facForm.name} onChange={e=>setFacForm(s=>({...s, name:e.target.value}))} />
            <input className="world2-input" placeholder="Hệ tư tưởng" value={facForm.ideology} onChange={e=>setFacForm(s=>({...s, ideology:e.target.value}))} />
            <textarea className="world2-textarea" rows={2} placeholder="Mô tả" value={facForm.description} onChange={e=>setFacForm(s=>({...s, description:e.target.value}))} />
            <label style={{fontSize:'0.8rem', color:'#94a3b8'}}>Ảnh hưởng: {facForm.influence_level}%</label>
            <input type="range" min={0} max={100} value={facForm.influence_level} onChange={e=>setFacForm(s=>({...s, influence_level: Number(e.target.value)}))} />
            <div className="world2-modal__actions">
              <button className="world2-btn world2-btn--ghost" onClick={()=>setShowCreate(null)}>Hủy</button>
              <button className="world2-btn world2-btn--primary" disabled={!facForm.name.trim() || createFacMut.isPending} onClick={async()=>{
                await createFacMut.mutateAsync({ name: facForm.name.trim(), ideology: facForm.ideology, description: facForm.description, influence_level: facForm.influence_level });
                setFacForm({ name:'', ideology:'', description:'', influence_level:50 });
                setShowCreate(null);
              }}>{createFacMut.isPending ? 'Đang tạo...' : 'Tạo Phe phái'}</button>
            </div>
          </div>
        </div>
      )}

      {showCreate === 'lore' && (
        <div className="world2-modal-overlay" onClick={() => setShowCreate(null)}>
          <div className="world2-modal" onClick={e => e.stopPropagation()}>
            <h3>Thêm Lore / Sự kiện mới</h3>
            <input className="world2-input" placeholder="Tiêu đề *" value={loreForm.title} onChange={e=>setLoreForm(s=>({...s, title:e.target.value}))} />
            <select className="world2-select" value={loreForm.category} onChange={e=>setLoreForm(s=>({...s, category:e.target.value}))}>
              <option value="History">History</option>
              <option value="Culture">Culture</option>
              <option value="Technology">Technology</option>
              <option value="Myth">Myth</option>
            </select>
            <textarea className="world2-textarea" rows={4} placeholder="Nội dung" value={loreForm.content} onChange={e=>setLoreForm(s=>({...s, content:e.target.value}))} />
            <div className="world2-modal__actions">
              <button className="world2-btn world2-btn--ghost" onClick={()=>setShowCreate(null)}>Hủy</button>
              <button className="world2-btn world2-btn--primary" disabled={!loreForm.title.trim() || createLoreMut.isPending} onClick={async()=>{
                await createLoreMut.mutateAsync({ title: loreForm.title.trim(), category: loreForm.category, content: loreForm.content });
                setLoreForm({ title:'', category:'History', content:'' });
                setShowCreate(null);
              }}>{createLoreMut.isPending ? 'Đang tạo...' : 'Tạo Lore'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
