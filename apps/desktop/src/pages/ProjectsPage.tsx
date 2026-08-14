import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Folder,
  FolderPlus,
  Film,
  Sparkles,
  Search,
  Grid,
  List,
  ArrowRight,
  Clock,
  Copy,
  Check,
  RefreshCw,
  AlertCircle,
  SlidersHorizontal,
  PlusCircle,
  Tv,
  CheckCircle2,
  ShieldCheck,
} from 'lucide-react';
import { HttpStudioApiClient } from '@windagent/studio-client';
import { StudioStore } from '@windagent/studio-state';
import type { StudioSeries } from '@windagent/studio-contracts';
import { API_BASE } from '../lib/apiBase';
import './ProjectsPage.css';

export interface ProjectItem {
  id: string;
  title: string;
  description: string;
  episodeCount: number;
  createdAt?: string;
  updatedAt?: string;
}

const COVER_GRADIENTS = [
  {
    from: '#1e3a8a',
    via: '#2563eb',
    to: '#06b6d4',
    accent: '#38bdf8',
    genre: 'Sci-Fi / High-Tech',
    badgeBg: 'rgba(56, 189, 248, 0.15)',
    badgeBorder: 'rgba(56, 189, 248, 0.35)',
  },
  {
    from: '#4c1d95',
    via: '#7c3aed',
    to: '#ec4899',
    accent: '#f472b6',
    genre: 'Cyberpunk / Fantasy',
    badgeBg: 'rgba(244, 114, 182, 0.15)',
    badgeBorder: 'rgba(244, 114, 182, 0.35)',
  },
  {
    from: '#064e3b',
    via: '#059669',
    to: '#10b981',
    accent: '#34d399',
    genre: 'Adventure / World Lore',
    badgeBg: 'rgba(52, 211, 153, 0.15)',
    badgeBorder: 'rgba(52, 211, 153, 0.35)',
  },
  {
    from: '#78350f',
    via: '#d97706',
    to: '#f59e0b',
    accent: '#fbbf24',
    genre: 'Drama / Mystery Noir',
    badgeBg: 'rgba(251, 191, 36, 0.15)',
    badgeBorder: 'rgba(251, 191, 36, 0.35)',
  },
  {
    from: '#831843',
    via: '#db2777',
    to: '#f43f5e',
    accent: '#fb7185',
    genre: 'Thriller / Psychological',
    badgeBg: 'rgba(251, 113, 133, 0.15)',
    badgeBorder: 'rgba(251, 113, 133, 0.35)',
  },
  {
    from: '#1e1b4b',
    via: '#4338ca',
    to: '#6366f1',
    accent: '#818cf8',
    genre: 'Animation / Epic Saga',
    badgeBg: 'rgba(129, 140, 248, 0.15)',
    badgeBorder: 'rgba(129, 140, 248, 0.35)',
  },
];

function getCoverDesign(id: string, title: string) {
  let hash = 0;
  const str = `${id}:${title}`;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % COVER_GRADIENTS.length;
  return COVER_GRADIENTS[idx];
}

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return 'Vừa xong';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return 'Vừa xong';
    if (diffMin < 60) return `${diffMin} phút trước`;
    if (diffHour < 24) return `${diffHour} giờ trước`;
    if (diffDay < 7) return `${diffDay} ngày trước`;
    return d.toLocaleDateString('vi-VN', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

const AI_STARTER_TEMPLATES = [
  {
    id: 'tmpl_cyberpunk',
    title: 'Cyberpunk Odyssey 2099',
    description: 'Vũ trụ siêu đô thị ngầm tương lai nơi các hacker và người máy cyborg tìm kiếm ký ức đã mất.',
    genre: 'Cyberpunk / Sci-Fi',
    initialEpisode: 'Tập 01: Mã Nguồn Thức Tỉnh',
    episodeBrief: 'Khởi đầu với một tin tặc phát hiện đoạn mã bất thường trong hệ thống AI trung tâm.',
    accentColor: '#38bdf8',
  },
  {
    id: 'tmpl_fantasy',
    title: 'Biên Niên Sử Vùng Đất Rồng',
    description: 'Cuộc phiêu lưu huyền ảo qua các vương quốc cổ đại nhằm khôi phục viên ngọc nguyên tố bóng đêm.',
    genre: 'High Fantasy / Adventure',
    initialEpisode: 'Tập 01: Tiếng Gọi Rừng Thiêng',
    episodeBrief: 'Người giám hộ trẻ phát hiện dấu vết sinh vật thần thoại thức giấc sau một ngàn năm.',
    accentColor: '#34d399',
  },
  {
    id: 'tmpl_mystery',
    title: 'Hồ Sơ Vụ Án Màn Đêm',
    description: 'Series trinh thám hình sự giật gân theo chân thám tử giải mã chuỗi sự kiện bí ẩn tại cảng biển.',
    genre: 'Detective / Thriller',
    initialEpisode: 'Tập 01: Vết Dấu Lúc Hoàng Hôn',
    episodeBrief: 'Hiện trường một vụ mất tích kỳ lạ không để lại bất kỳ dấu vết vật lý nào.',
    accentColor: '#fbbf24',
  },
  {
    id: 'tmpl_space_sitcom',
    title: 'Trạm Vũ Trụ Số 9',
    description: 'Hài kịch tình huống về nhóm phi hành gia bất đắc dĩ làm việc tại trạm trung chuyển ngoài quỹ đạo.',
    genre: 'Sci-Fi / Sitcom Comedy',
    initialEpisode: 'Tập 01: Sự Cố Trọng Lực Không Mong Muốn',
    episodeBrief: 'Máy phát trọng lực bị đảo ngược khiến bữa tiệc chào đón thành viên mới trở nên hỗn loạn.',
    accentColor: '#f472b6',
  },
];

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [capabilities, setCapabilities] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Search, Filter & Sort
  const [search, setSearch] = useState<string>('');
  const [filterType, setFilterType] = useState<'ALL' | 'WITH_EPISODES' | 'DRAFT'>('ALL');
  const [sortBy, setSortBy] = useState<'NEWEST' | 'OLDEST' | 'TITLE' | 'EPISODES'>('NEWEST');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

  // Creation Modal
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>('');
  const [newDesc, setNewDesc] = useState<string>('');
  const [newInitialEpTitle, setNewInitialEpTitle] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Quick Add Episode Modal
  const [selectedSeriesForEp, setSelectedSeriesForEp] = useState<ProjectItem | null>(null);
  const [newEpTitle, setNewEpTitle] = useState<string>('');
  const [newEpBrief, setNewEpBrief] = useState<string>('');
  const [isAddingEp, setIsAddingEp] = useState<boolean>(false);

  // Toast Feedback
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'info' | 'error' } | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const showToast = (text: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  // Studio Store Singleton
  const storeRef = useRef<StudioStore | null>(null);
  if (storeRef.current === null) {
    const fetchImpl = typeof window !== 'undefined' ? window.fetch.bind(window) : undefined;
    const client = new HttpStudioApiClient({ baseUrl: API_BASE, fetchImpl });
    storeRef.current = new StudioStore(client);
  }
  const store = storeRef.current;

  // Load Real Data from Backend
  const loadData = async (isManualRefresh = false) => {
    if (isManualRefresh) setRefreshing(true);
    setError(null);

    try {
      const [seriesData, capsData] = await Promise.all([
        store.loadSeriesList(),
        store.loadCapabilities().catch(() => null),
      ]);

      const mapped: ProjectItem[] = seriesData.map((s: StudioSeries) => ({
        id: s.id,
        title: s.title,
        description: s.description || 'Chưa có mô tả dự án.',
        episodeCount: s.episode_count ?? 0,
        createdAt: s.created_at,
        updatedAt: s.updated_at,
      }));

      setProjects(mapped);

      const storeErr = store.getLastError();
      if (storeErr) {
        setError(storeErr.message || 'Không thể kết nối đến máy chủ Studio. Vui lòng kiểm tra lại dịch vụ.');
      }

      if (capsData?.capabilities) {
        const capsMap: Record<string, string> = {};
        capsData.capabilities.forEach((c) => {
          capsMap[c.name] = c.status;
        });
        setCapabilities(capsMap);
      }
    } catch (err: any) {
      console.error('[ProjectsPage] Failed to fetch data from API:', err);
      setError(err?.message || 'Không thể kết nối đến máy chủ Studio. Vui lòng kiểm tra lại dịch vụ.');
    } finally {
      setLoading(false);
      if (isManualRefresh) setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  // Handle Project Creation in Real DB
  const handleCreateProject = async () => {
    if (!newTitle.trim()) return;
    setIsSubmitting(true);
    try {
      const key = `series_key_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const result = await store.createSeries(key, newTitle.trim(), newDesc.trim() || undefined);

      if (result) {
        if (newInitialEpTitle.trim()) {
          const epKey = `ep_init_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
          await store.createEpisode(
            epKey,
            result.series_id,
            newInitialEpTitle.trim(),
            'Tập mở đầu của dự án kịch bản.'
          );
        }

        showToast(`Đã tạo dự án "${newTitle.trim()}" thành công!`, 'success');
        setNewTitle('');
        setNewDesc('');
        setNewInitialEpTitle('');
        setShowAddModal(false);
        await loadData();
      } else {
        const lastErr = store.getLastError();
        showToast(lastErr?.message || 'Lỗi khi khởi tạo dự án.', 'error');
      }
    } catch (err: any) {
      console.error('[ProjectsPage] Create project failed:', err);
      showToast(err?.message || 'Tạo dự án thất bại.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle Quick Add Episode
  const handleCreateEpisode = async () => {
    if (!selectedSeriesForEp || !newEpTitle.trim()) return;
    setIsAddingEp(true);
    try {
      const epKey = `ep_create_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const result = await store.createEpisode(
        epKey,
        selectedSeriesForEp.id,
        newEpTitle.trim(),
        newEpBrief.trim() || undefined
      );

      if (result) {
        showToast(`Đã thêm tập "${newEpTitle.trim()}" vào ${selectedSeriesForEp.title}!`, 'success');
        setNewEpTitle('');
        setNewEpBrief('');
        setSelectedSeriesForEp(null);
        await loadData();
      } else {
        const lastErr = store.getLastError();
        showToast(lastErr?.message || 'Lỗi khi thêm tập phim.', 'error');
      }
    } catch (err: any) {
      console.error('[ProjectsPage] Add episode failed:', err);
      showToast(err?.message || 'Thêm tập phim thất bại.', 'error');
    } finally {
      setIsAddingEp(false);
    }
  };

  // Handle Applying an AI Template
  const handleApplyTemplate = async (template: typeof AI_STARTER_TEMPLATES[0]) => {
    setIsSubmitting(true);
    try {
      const key = `series_tmpl_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      const result = await store.createSeries(key, template.title, template.description);

      if (result) {
        const epKey = `ep_tmpl_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        await store.createEpisode(
          epKey,
          result.series_id,
          template.initialEpisode,
          template.episodeBrief
        );

        showToast(`Đã tạo dự án mẫu "${template.title}" cùng Tập 1 thành công!`, 'success');
        await loadData();
      }
    } catch (err: any) {
      console.error('[ProjectsPage] Template apply failed:', err);
      showToast(err?.message || 'Không thể tạo từ template.', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Copy Project ID
  const handleCopyId = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(id);
      setCopiedId(id);
      showToast(`Đã sao chép ID: ${id}`, 'info');
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  // Filter & Sort Logic
  const filteredAndSortedProjects = useMemo(() => {
    let list = projects.filter((p) => {
      const matchesSearch =
        p.title.toLowerCase().includes(search.toLowerCase()) ||
        p.description.toLowerCase().includes(search.toLowerCase()) ||
        p.id.toLowerCase().includes(search.toLowerCase());

      if (!matchesSearch) return false;

      if (filterType === 'WITH_EPISODES') return p.episodeCount > 0;
      if (filterType === 'DRAFT') return p.episodeCount === 0;
      return true;
    });

    list.sort((a, b) => {
      if (sortBy === 'NEWEST') {
        return new Date(b.createdAt || 0).getTime() - new Date(a.createdAt || 0).getTime();
      }
      if (sortBy === 'OLDEST') {
        return new Date(a.createdAt || 0).getTime() - new Date(b.createdAt || 0).getTime();
      }
      if (sortBy === 'TITLE') {
        return a.title.localeCompare(b.title);
      }
      if (sortBy === 'EPISODES') {
        return b.episodeCount - a.episodeCount;
      }
      return 0;
    });

    return list;
  }, [projects, search, filterType, sortBy]);

  // Overall Statistics
  const totalEpisodes = useMemo(() => {
    return projects.reduce((acc, p) => acc + p.episodeCount, 0);
  }, [projects]);

  const activeProjectsCount = useMemo(() => {
    return projects.filter((p) => p.episodeCount > 0).length;
  }, [projects]);

  return (
    <main className="projects-page-container">
      {/* Main Workspace Stage */}
      <div className="projects-main-stage">
        {/* Top Header & Overview Bar */}
        <div className="projects-top-header">
          <div className="projects-header-main-row">
            <div className="projects-title-box">
              <div className="projects-header-icon">
                <Folder size={22} />
              </div>
              <div>
                <h1 className="projects-main-heading">
                  Quản lý Dự án & Vũ trụ Kịch bản
                  <span className="projects-v3-tag">Studio V3</span>
                </h1>
                <p className="projects-subtext">
                  Quản lý các chuỗi tác phẩm điện ảnh, universe nhân vật và pipeline sáng tạo AI trực tiếp trên cơ sở dữ liệu thực.
                </p>
              </div>
            </div>

            <div className="projects-top-actions">
              <button
                onClick={() => void loadData(true)}
                disabled={refreshing}
                title="Đồng bộ dữ liệu mới nhất từ máy chủ"
                className="btn-header-refresh"
              >
                <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
                <span>Làm mới</span>
              </button>

              <button
                onClick={() => setShowAddModal(true)}
                className="btn-header-create"
              >
                <FolderPlus size={16} />
                <span>Tạo Dự Án Mới</span>
              </button>
            </div>
          </div>

          {/* Real-time KPI Stats Ribbon */}
          <div className="projects-kpi-ribbon">
            <div className="kpi-card">
              <div className="kpi-icon-box kpi-icon-blue">
                <Folder size={18} />
              </div>
              <div className="kpi-info-col">
                <span className="kpi-title">Tổng Số Dự Án</span>
                <span className="kpi-value">{loading ? '...' : projects.length}</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-box kpi-icon-green">
                <Film size={18} />
              </div>
              <div className="kpi-info-col">
                <span className="kpi-title">Tổng Số Tập Phim</span>
                <span className="kpi-value">{loading ? '...' : totalEpisodes}</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-box kpi-icon-purple">
                <Tv size={18} />
              </div>
              <div className="kpi-info-col">
                <span className="kpi-title">Dự Án Đang Sản Xuất</span>
                <span className="kpi-value">{loading ? '...' : activeProjectsCount}</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-icon-box kpi-icon-amber">
                <ShieldCheck size={18} />
              </div>
              <div className="kpi-info-col">
                <span className="kpi-title">Studio Engine</span>
                <span className="kpi-status-live">
                  <span className="pulse-dot"></span>
                  {capabilities['durable_db'] === 'AVAILABLE' ? 'Online / DB Sẵn Sàng' : 'Đang Kiểm Tra'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Filter, Search & View Controls */}
        <div className="projects-controls-bar">
          {/* Filter Pills */}
          <div className="filter-pills-row">
            <button
              onClick={() => setFilterType('ALL')}
              className={`filter-pill ${filterType === 'ALL' ? 'active' : ''}`}
            >
              Tất cả ({projects.length})
            </button>
            <button
              onClick={() => setFilterType('WITH_EPISODES')}
              className={`filter-pill ${filterType === 'WITH_EPISODES' ? 'active' : ''}`}
            >
              Có tập phim ({activeProjectsCount})
            </button>
            <button
              onClick={() => setFilterType('DRAFT')}
              className={`filter-pill ${filterType === 'DRAFT' ? 'active' : ''}`}
            >
              Bản thảo ({projects.length - activeProjectsCount})
            </button>
          </div>

          {/* Search, Sort & View Mode */}
          <div className="controls-right-side">
            {/* Search Input */}
            <div className="search-input-wrap">
              <Search size={14} className="search-icon-pos" />
              <input
                type="text"
                placeholder="Tìm kiếm theo tên, ID, mô tả..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="projects-search-field"
              />
            </div>

            {/* Sort Dropdown */}
            <div className="sort-select-wrap">
              <SlidersHorizontal size={13} style={{ opacity: 0.7 }} />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="sort-native-select"
              >
                <option value="NEWEST">Mới nhất</option>
                <option value="OLDEST">Cũ nhất</option>
                <option value="TITLE">Tên A-Z</option>
                <option value="EPISODES">Nhiều tập nhất</option>
              </select>
            </div>

            {/* View Mode Toggle */}
            <div className="view-switcher-box">
              <button
                onClick={() => setViewMode('grid')}
                title="Chế độ thẻ lưới (Grid)"
                className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`}
              >
                <Grid size={14} />
              </button>
              <button
                onClick={() => setViewMode('list')}
                title="Chế độ danh sách (List)"
                className={`view-btn ${viewMode === 'list' ? 'active' : ''}`}
              >
                <List size={14} />
              </button>
            </div>
          </div>
        </div>

        {/* Error Banner if API fails */}
        {error && (
          <div className="projects-error-banner">
            <div className="error-left">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
            <button
              onClick={() => void loadData(true)}
              className="btn-retry-err"
            >
              Thử Lại
            </button>
          </div>
        )}

        {/* Main Content Area */}
        <div className="projects-content-scroll">
          {/* Loading State */}
          {loading ? (
            <div className="projects-cards-grid">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="project-card" style={{ height: '240px', opacity: 0.6, background: '#131b2e' }}>
                  <div style={{ height: '110px', background: 'rgba(255,255,255,0.04)' }} />
                  <div style={{ padding: '16px' }}>
                    <div style={{ height: '16px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', width: '60%' }} />
                    <div style={{ height: '12px', background: 'rgba(255,255,255,0.04)', borderRadius: '4px', width: '90%', marginTop: '8px' }} />
                  </div>
                </div>
              ))}
            </div>
          ) : filteredAndSortedProjects.length === 0 ? (
            /* Empty State */
            <div className="projects-empty-state">
              <div className="empty-icon-circle">
                <FolderPlus size={32} />
              </div>
              <h3 className="empty-title">
                {search ? 'Không tìm thấy dự án phù hợp' : 'Chưa có dự án nào trong hệ thống'}
              </h3>
              <p className="empty-desc">
                {search
                  ? `Không có kết quả nào khớp với từ khóa "${search}". Hãy thử tìm kiếm với tên hoặc ID khác.`
                  : 'Hãy bắt đầu bằng cách khởi tạo một dự án mới hoặc chọn một bộ template kịch bản mẫu ở khung bên phải.'}
              </p>
              <div style={{ display: 'flex', gap: '10px' }}>
                {search && (
                  <button
                    onClick={() => setSearch('')}
                    className="btn-modal-cancel"
                    style={{ border: '1px solid #1e293b' }}
                  >
                    Xóa tìm kiếm
                  </button>
                )}
                <button
                  onClick={() => setShowAddModal(true)}
                  className="btn-modal-submit"
                >
                  <PlusCircle size={16} />
                  <span>Tạo Dự Án Đầu Tiên</span>
                </button>
              </div>
            </div>
          ) : viewMode === 'grid' ? (
            /* Grid View */
            <div className="projects-cards-grid">
              {filteredAndSortedProjects.map((proj) => {
                const cover = getCoverDesign(proj.id, proj.title);
                return (
                  <div key={proj.id} className="project-card">
                    {/* Dynamic Procedural Cover Art */}
                    <div
                      className="card-cover"
                      style={{
                        background: `linear-gradient(135deg, ${cover.from}, ${cover.via}, ${cover.to})`,
                      }}
                    >
                      <div className="card-cover-top">
                        <span
                          className="card-genre-pill"
                          style={{
                            backgroundColor: cover.badgeBg,
                            borderColor: cover.badgeBorder,
                          }}
                        >
                          {cover.genre}
                        </span>

                        <span
                          className="card-ep-count-pill"
                          style={{
                            backgroundColor: proj.episodeCount > 0 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                            borderColor: proj.episodeCount > 0 ? 'rgba(16, 185, 129, 0.4)' : 'rgba(245, 158, 11, 0.4)',
                            color: proj.episodeCount > 0 ? '#34d399' : '#fbbf24',
                          }}
                        >
                          {proj.episodeCount > 0 ? `${proj.episodeCount} Tập` : 'Bản Thảo'}
                        </span>
                      </div>

                      <div className="card-cover-bottom">
                        <div className="card-emblem-icon">
                          <Film size={14} />
                        </div>
                        <span
                          className="card-id-copy-chip"
                          onClick={(e) => handleCopyId(proj.id, e)}
                          title="Click để sao chép Project ID"
                        >
                          {copiedId === proj.id ? (
                            <>
                              <Check size={12} color="#34d399" />
                              <span style={{ color: '#34d399', fontWeight: 700 }}>Đã chép!</span>
                            </>
                          ) : (
                            <>
                              <Copy size={12} style={{ opacity: 0.6 }} />
                              <span>{proj.id.slice(0, 12)}...</span>
                            </>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Card Body */}
                    <div className="card-body">
                      <div>
                        <h3
                          className="card-title"
                          onClick={() => {
                            window.location.hash = `#/studio/series/${proj.id}`;
                          }}
                          title={proj.title}
                        >
                          {proj.title}
                        </h3>
                        <p className="card-desc">
                          {proj.description}
                        </p>
                      </div>

                      {/* Card Footer */}
                      <div className="card-footer">
                        <div className="card-date">
                          <Clock size={12} />
                          <span>{formatRelativeTime(proj.updatedAt || proj.createdAt)}</span>
                        </div>

                        <div className="card-actions-row">
                          <button
                            onClick={() => {
                              setSelectedSeriesForEp(proj);
                              setNewEpTitle(`Tập ${proj.episodeCount + 1}: `);
                            }}
                            title="Thêm tập phim mới vào dự án này"
                            className="btn-card-add-ep"
                          >
                            <PlusCircle size={14} />
                          </button>

                          <a
                            href={`#/studio/series/${proj.id}`}
                            className="btn-card-open"
                          >
                            <span>Mở Studio</span>
                            <ArrowRight size={12} />
                          </a>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* List View / Table Mode */
            <div className="projects-table-wrap">
              <table className="projects-table">
                <thead>
                  <tr>
                    <th>Tên Dự Án</th>
                    <th>Thể Loại</th>
                    <th>Số Tập</th>
                    <th>Cập Nhật</th>
                    <th style={{ textAlign: 'right' }}>Thao Tác</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAndSortedProjects.map((proj) => {
                    const cover = getCoverDesign(proj.id, proj.title);
                    return (
                      <tr
                        key={proj.id}
                        onClick={() => {
                          window.location.hash = `#/studio/series/${proj.id}`;
                        }}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            <div
                              style={{
                                width: '32px',
                                height: '32px',
                                borderRadius: '8px',
                                background: `linear-gradient(135deg, ${cover.from}, ${cover.to})`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: '#ffffff',
                                flexShrink: 0,
                              }}
                            >
                              <Film size={14} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 800, color: '#ffffff' }}>
                                {proj.title}
                              </div>
                              <div style={{ fontSize: '0.68rem', color: '#94a3b8', maxWidth: '350px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {proj.description}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td>
                          <span
                            className="card-genre-pill"
                            style={{
                              backgroundColor: cover.badgeBg,
                              borderColor: cover.badgeBorder,
                              color: cover.accent,
                            }}
                          >
                            {cover.genre}
                          </span>
                        </td>

                        <td style={{ fontFamily: 'var(--font-mono)' }}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontWeight: 700,
                              background: proj.episodeCount > 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                              color: proj.episodeCount > 0 ? '#34d399' : '#fbbf24',
                            }}
                          >
                            {proj.episodeCount} Tập
                          </span>
                        </td>

                        <td style={{ color: '#94a3b8' }}>
                          {formatRelativeTime(proj.updatedAt || proj.createdAt)}
                        </td>

                        <td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'center' }}>
                            <button
                              onClick={() => {
                                setSelectedSeriesForEp(proj);
                                setNewEpTitle(`Tập ${proj.episodeCount + 1}: `);
                              }}
                              className="btn-card-add-ep"
                              style={{ fontSize: '0.72rem', padding: '4px 8px' }}
                            >
                              + Thêm Tập
                            </button>
                            <a
                              href={`#/studio/series/${proj.id}`}
                              className="btn-card-open"
                              style={{ padding: '4px 10px' }}
                            >
                              <span>Vào Studio</span>
                              <ArrowRight size={12} />
                            </a>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Right AI Template & Starters Panel */}
      <aside className="projects-ai-sidebar">
        <div className="sidebar-header-box">
          <div className="sidebar-title-row">
            <Sparkles size={16} color="#60a5fa" />
            <span>Mẫu Kịch Bản AI</span>
          </div>
          <p className="sidebar-subdesc">
            Khởi tạo tức thì các dự án mẫu hoàn chỉnh với tập mở đầu vào cơ sở dữ liệu.
          </p>
        </div>

        <div className="sidebar-templates-list">
          {AI_STARTER_TEMPLATES.map((tmpl) => (
            <div
              key={tmpl.id}
              onClick={() => void handleApplyTemplate(tmpl)}
              className="template-card-box"
            >
              <div className="template-top-badge">
                <span
                  className="template-pill"
                  style={{
                    backgroundColor: `${tmpl.accentColor}20`,
                    color: tmpl.accentColor,
                    border: `1px solid ${tmpl.accentColor}40`,
                  }}
                >
                  {tmpl.genre}
                </span>
                <PlusCircle size={14} color="#94a3b8" />
              </div>

              <h4 className="template-name">
                {tmpl.title}
              </h4>
              <p className="template-desc">
                {tmpl.description}
              </p>

              <div className="template-footer">
                <span style={{ fontFamily: 'var(--font-mono)', color: '#94a3b8' }}>{tmpl.initialEpisode}</span>
                <span style={{ color: '#60a5fa', fontWeight: 700 }}>Áp dụng →</span>
              </div>
            </div>
          ))}
        </div>

        {/* System Status Footer */}
        <div className="sidebar-system-footer">
          <div className="system-status-title">
            <span>Kết nối Studio Engine</span>
            <span className="pulse-dot" />
          </div>
          <div className="system-status-rows">
            <div className="status-row-item">
              <span>DB Persistence:</span>
              <span style={{ color: '#34d399', fontWeight: 700 }}>ACTIVE (SQLite)</span>
            </div>
            <div className="status-row-item">
              <span>Series Aggregate:</span>
              <span style={{ color: '#34d399', fontWeight: 700 }}>V3 CANONICAL</span>
            </div>
            <div className="status-row-item">
              <span>Creative Pipeline:</span>
              <span style={{ color: '#60a5fa', fontWeight: 700 }}>14-STEP AUTONOMOUS</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Modal: Tạo Dự Án Mới */}
      {showAddModal && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header-row">
              <div className="modal-title-wrap">
                <div className="kpi-icon-box kpi-icon-blue">
                  <FolderPlus size={18} />
                </div>
                <div>
                  <h3 className="modal-heading">Khởi Tạo Dự Án Mới</h3>
                  <p className="modal-subdesc">Tạo chuỗi series kịch bản trong cơ sở dữ liệu Studio</p>
                </div>
              </div>
              <button
                onClick={() => setShowAddModal(false)}
                className="btn-close-modal"
              >
                ✕
              </button>
            </div>

            <div className="modal-form-fields">
              <div className="field-group">
                <label className="field-label">
                  Tên Dự Án (Series Title) <span style={{ color: '#60a5fa' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: Rừng Xanh Kỳ Diệu, Cyberpunk Odyssey..."
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  autoFocus
                  className="text-input-styled"
                />
              </div>

              <div className="field-group">
                <label className="field-label">Mô Tả / Cốt Truyện Tổng Quan</label>
                <textarea
                  rows={3}
                  placeholder="Tóm tắt bối cảnh, chủ đề kịch bản và thế giới nhân vật..."
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="textarea-styled"
                />
              </div>

              <div className="field-group">
                <label className="field-label">
                  Khởi Tạo Ngay Tập Mở Đầu (Tùy chọn)
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: Tập 01: Khởi Đầu Mới"
                  value={newInitialEpTitle}
                  onChange={(e) => setNewInitialEpTitle(e.target.value)}
                  className="text-input-styled"
                />
              </div>
            </div>

            <div className="modal-footer-btns">
              <button
                onClick={() => setShowAddModal(false)}
                disabled={isSubmitting}
                className="btn-modal-cancel"
              >
                Hủy
              </button>
              <button
                onClick={() => void handleCreateProject()}
                disabled={!newTitle.trim() || isSubmitting}
                className="btn-modal-submit"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Đang khởi tạo...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} />
                    <span>Tạo Dự Án</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Thêm Tập Phim Nhanh */}
      {selectedSeriesForEp && (
        <div className="modal-overlay">
          <div className="modal-dialog">
            <div className="modal-header-row">
              <div className="modal-title-wrap">
                <div className="kpi-icon-box kpi-icon-green">
                  <Film size={18} />
                </div>
                <div>
                  <h3 className="modal-heading">Thêm Tập Phim Mới</h3>
                  <p className="modal-subdesc">
                    Vào dự án: <span style={{ color: '#ffffff', fontWeight: 700 }}>{selectedSeriesForEp.title}</span>
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedSeriesForEp(null)}
                className="btn-close-modal"
              >
                ✕
              </button>
            </div>

            <div className="modal-form-fields">
              <div className="field-group">
                <label className="field-label">
                  Tên Tập Phim <span style={{ color: '#60a5fa' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="Ví dụ: Tập 02: Cuộc Đào Tẩu"
                  value={newEpTitle}
                  onChange={(e) => setNewEpTitle(e.target.value)}
                  autoFocus
                  className="text-input-styled"
                />
              </div>

              <div className="field-group">
                <label className="field-label">Tóm Tắt Ý Tưởng Tập (Brief)</label>
                <textarea
                  rows={3}
                  placeholder="Mô tả xung đột chính, bối cảnh và diễn biến trong tập này..."
                  value={newEpBrief}
                  onChange={(e) => setNewEpBrief(e.target.value)}
                  className="textarea-styled"
                />
              </div>
            </div>

            <div className="modal-footer-btns">
              <button
                onClick={() => setSelectedSeriesForEp(null)}
                disabled={isAddingEp}
                className="btn-modal-cancel"
              >
                Hủy
              </button>
              <button
                onClick={() => void handleCreateEpisode()}
                disabled={!newEpTitle.trim() || isAddingEp}
                className="btn-modal-submit"
                style={{ background: '#059669' }}
              >
                {isAddingEp ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    <span>Đang thêm...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} />
                    <span>Thêm Tập Phim</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toast Notification */}
      {toastMessage && (
        <div className="floating-toast-alert">
          <div
            className={`toast-box ${
              toastMessage.type === 'error'
                ? 'toast-error'
                : toastMessage.type === 'info'
                ? 'toast-info'
                : 'toast-success'
            }`}
          >
            {toastMessage.type === 'error' ? (
              <AlertCircle size={16} />
            ) : toastMessage.type === 'info' ? (
              <Check size={16} />
            ) : (
              <CheckCircle2 size={16} />
            )}
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </main>
  );
}

export default ProjectsPage;
