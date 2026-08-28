/**
 * EpisodesPage — Cinematic Twin-Pane, 100% Real Data (No Mock).
 * Every row, badge, duration, progress and drawer section is derived from
 * /api/v3/studio (windagent.db: studio_series_projects + studio_episodes + studio_artifacts).
 * No synthetic durations, subtitles or beats are generated — missing data renders as "—" or empty state.
 */

import React, { useState, useMemo, useEffect } from 'react';
import {
  Film,
  Clapperboard,
  Search,
  Filter,
  ArrowUpDown,
  LayoutGrid,
  Table2,
  Eye,
  Pencil,
  MoreHorizontal,
  ChevronDown,
  Clock3,
  CalendarDays,
  Play,
  Trash2,
  BookOpen,
  FileText,
  Layers,
  Plus,
  AlertCircle,
  RefreshCw,
  ChevronRight,
} from 'lucide-react';
import { useRouter } from '../../../app/router';
import { useEpisodes } from '../hooks/useEpisodes';
import { useEpisodeArtifacts } from '../hooks/useEpisodeArtifacts';
import { useStudioSeries } from '../../studio/hooks/useStudioSeries';
import { useCreateEpisode } from '../../projects/hooks/useCreateEpisode';
import { CreateEpisodeDialog } from '../../projects/components/CreateEpisodeDialog';
import { getStageProgress, getEpisodeStateMeta, getProgressColor } from '../model/types';
import { useApiClient } from '../../../api/ApiProvider';
import { Button, Card } from '@windagent/ui';

// ── Filters (canonical EpisodeState values) ──────────────────────────────
const STATE_FILTERS = [
  { id: 'ALL', label: 'Tất cả trạng thái' },
  { id: 'DRAFT', label: 'Bản nháp' },
  { id: 'IDEA_REVIEW', label: 'Chờ duyệt ý tưởng' },
  { id: 'STORY_BIBLE_REVIEW', label: 'Story Bible' },
  { id: 'OUTLINE_REVIEW', label: 'Dàn ý' },
  { id: 'SCREENPLAY_REVIEW', label: 'Kịch bản' },
  { id: 'REVISING', label: 'Đang chỉnh sửa' },
  { id: 'LOCKED', label: 'Đã khóa' },
  { id: 'READY_FOR_PRODUCTION', label: 'Sẵn sàng SX' },
  { id: 'FAILED', label: 'Thất bại' },
] as const;

const SORT_OPTIONS = [
  { id: 'updated', label: 'Mới cập nhật' },
  { id: 'episode', label: 'Số tập' },
  { id: 'progress', label: 'Tiến độ' },
  { id: 'name', label: 'Tên A→Z' },
] as const;

// Visual fallback when episode/series has no cover image in DB
const EP_GRADIENTS = [
  'linear-gradient(135deg,#0ea5e9 0%,#1e40af 55%,#0f172a 100%)',
  'linear-gradient(135deg,#f43f5e 0%,#7c3aed 50%,#0f172a 100%)',
  'linear-gradient(135deg,#f59e0b 0%,#b45309 55%,#1a1200 100%)',
  'linear-gradient(135deg,#ec4899 0%,#4f46e5 50%,#0f172a 100%)',
  'linear-gradient(135deg,#dc2626 0%,#991b1b 55%,#1a0505 100%)',
  'linear-gradient(135deg,#06b6d4 0%,#0e7490 55%,#042f2e 100%)',
  'linear-gradient(135deg,#8b5cf6 0%,#4c1d95 55%,#0f172a 100%)',
  'linear-gradient(135deg,#10b981 0%,#065f46 55%,#022c22 100%)',
];

function thumbFor(id: string, idx: number): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return EP_GRADIENTS[(h + idx) % EP_GRADIENTS.length];
}

function formatUpdated(iso?: string): { date: string; time: string } {
  if (!iso) return { date: '—', time: '' };
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return { date: '—', time: '' };
    const date = d.toLocaleDateString('vi-VN');
    const time = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', hour12: false });
    return { date, time };
  } catch {
    return { date: '—', time: '' };
  }
}

function realDuration(ep: any): string | null {
  const meta: any = ep?.metadata || {};
  // Check common keys where duration might be stored in real DB
  const raw = meta.duration ?? meta.estimated_duration ?? meta.target_duration_seconds ?? ep.duration ?? null;
  if (raw == null || raw === '') return null;
  // If numeric seconds, format as mm:ss
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    const mins = Math.floor(raw / 60);
    const secs = Math.floor(raw % 60);
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }
  return String(raw);
}

function realDescription(ep: any): string | null {
  const meta: any = ep?.metadata || {};
  const raw = ep?.description ?? meta.description ?? meta.brief ?? meta.synopsis ?? meta.summary ?? null;
  if (raw == null || String(raw).trim() === '') return null;
  return String(raw).trim();
}

function realGenre(project: any): string | null {
  const g = (project?.metadata as any)?.genre;
  if (!g || String(g).trim() === '') return null;
  return String(g).trim();
}

export const EpisodesPage: React.FC = () => {
  const { navigate } = useRouter();
  const client = useApiClient();
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('ALL');
  const [projectFilter, setProjectFilter] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<string>('updated');
  const [viewMode, setViewMode] = useState<'list' | 'timeline'>('list');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailTab, setDetailTab] = useState<'overview' | 'script' | 'scenes' | 'assets' | 'notes' | 'history'>('overview');
  const [showFilters, setShowFilters] = useState(false);
  const [showSort, setShowSort] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [projDropdownOpen, setProjDropdownOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const { series } = useStudioSeries();
  const { createEpisode } = useCreateEpisode();

  const { episodes, isLoading, isError, error, refetch, invalidate } = useEpisodes({
    search: search.trim() || undefined,
    state: stateFilter !== 'ALL' ? stateFilter : undefined,
    projectId: projectFilter !== 'ALL' ? projectFilter : undefined,
  });

  const displayEpisodes = useMemo(() => {
    const list = [...episodes];
    if (sortBy === 'name') list.sort((a: any, b: any) => String(a.title).localeCompare(String(b.title), 'vi'));
    else if (sortBy === 'episode') list.sort((a: any, b: any) => (a.episode_number ?? 0) - (b.episode_number ?? 0));
    else if (sortBy === 'progress') list.sort((a: any, b: any) => (b.progress_percent ?? getStageProgress(b.state || 'DRAFT')) - (a.progress_percent ?? getStageProgress(a.state || 'DRAFT')));
    else list.sort((a: any, b: any) => {
      const aTime = new Date(a.updated_at || a.created_at || 0).getTime();
      const bTime = new Date(b.updated_at || b.created_at || 0).getTime();
      return bTime - aTime;
    });
    return list;
  }, [episodes, sortBy]);

  useEffect(() => {
    if (displayEpisodes.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !displayEpisodes.find((e: any) => e.id === selectedId)) {
      // Prefer most recently updated real episode, or first
      setSelectedId((displayEpisodes[0] as any).id);
    }
  }, [displayEpisodes, selectedId]);

  const selectedEpisode: any = useMemo(
    () => displayEpisodes.find((e: any) => e.id === selectedId) || null,
    [displayEpisodes, selectedId]
  );

  const selectedProgress = selectedEpisode ? (selectedEpisode.progress_percent ?? getStageProgress(selectedEpisode.state || 'DRAFT')) : 0;
  const selectedStatus = selectedEpisode ? getEpisodeStateMeta(selectedEpisode.state || 'DRAFT') : null;

  // Real artifacts for selected episode — drives detail drawer "Thật"
  const {
    artifacts,
    latestIdeaSet,
    latestStoryBible,
    latestOutline,
    latestScreenplay,
    isLoading: artifactsLoading,
  } = useEpisodeArtifacts(selectedId || undefined);

  const currentProject = useMemo(() => {
    if (!selectedEpisode) return null;
    const pid = selectedEpisode.project_id;
    return series.find((s: any) => s.id === pid) || null;
  }, [selectedEpisode, series]);

  const projectSelectorLabel = useMemo(() => {
    if (projectFilter === 'ALL') {
      if (series.length === 0) return 'Tất cả dự án';
      return `Tất cả dự án (${series.length})`;
    }
    const p = series.find((s: any) => s.id === projectFilter) as any;
    return p?.title || 'Dự án';
  }, [projectFilter, series]);

  const handleOpenWorkspace = (episodeId: string) => navigate(`/episodes/${episodeId}`);

  const handleCreateClick = () => {
    const targetProjectId = projectFilter !== 'ALL' ? projectFilter : series[0]?.id;
    if (!targetProjectId) {
      navigate('/projects');
      return;
    }
    setIsCreateOpen(true);
  };

  const createTargetProject: any = useMemo(() => {
    const pid = projectFilter !== 'ALL' ? projectFilter : series[0]?.id;
    return series.find((s: any) => s.id === pid) || series[0] || null;
  }, [projectFilter, series]);

  const totalEpisodesForCreate = useMemo(() => {
    if (!createTargetProject) return 1;
    // Count real episodes for that series from displayEpisodes (already filtered) — better to count from series.episode_count if available
    const fromList = displayEpisodes.filter((e: any) => e.project_id === createTargetProject.id).length;
    const fromSeries = (createTargetProject as any).episode_count;
    const base = typeof fromSeries === 'number' ? fromSeries : fromList;
    return base + 1;
  }, [createTargetProject, displayEpisodes]);

  const handleDelete = async () => {
    if (!selectedEpisode) return;
    if (!confirm(`Xóa tập "${selectedEpisode.title}"? Hành động không thể hoàn tác.`)) return;
    setDeleteError(null);
    setIsDeleting(true);
    try {
      // Canonical delete goes through EpisodesApi (/api/v3/episodes/{id}) — Studio surface has no delete
      // Fallback to fetch if client method missing
      const epClient: any = (client as any).episodes || (client as any).studio;
      if (epClient?.delete) {
        await epClient.delete(selectedEpisode.id);
      } else {
        // Direct transport fallback
        const transport: any = (client as any).transport || (client as any)._transport;
        if (transport?.delete) await transport.delete(`/api/v3/episodes/${encodeURIComponent(selectedEpisode.id)}`);
        else throw new Error('Delete API not available');
      }
      setSelectedId(null);
      invalidate();
      refetch();
    } catch (e: any) {
      setDeleteError(e?.message || 'Không thể xóa tập phim. Vui lòng thử lại.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Derive production progress checklist from real artifacts + state
  const productionChecklist = useMemo(() => {
    if (!selectedEpisode) return [];
    const state = String(selectedEpisode.state || 'DRAFT').toUpperCase();
    const hasIdea = !!latestIdeaSet;
    const hasBible = !!latestStoryBible;
    const hasOutline = !!latestOutline;
    const hasScreenplay = !!latestScreenplay;
    const outlineScenes: any[] = (latestOutline as any)?.content?.scenes || (latestOutline as any)?.content?.beats || [];
    const screenplayScenes: any[] = (latestScreenplay as any)?.content?.scenes || [];
    const outlineCount = outlineScenes.length;
    const screenplayCount = screenplayScenes.length;

    // Helper to decide done/active/pending based on state order
    const order: Record<string, number> = {
      DRAFT: 0,
      IDEA_REVIEW: 1,
      STORY_BIBLE_REVIEW: 2,
      OUTLINE_REVIEW: 3,
      SCREENPLAY_REVIEW: 4,
      REVISING: 4,
      LOCKED: 5,
      READY_FOR_PRODUCTION: 6,
      FAILED: -1,
      CANCELLED: -1,
    };
    const curOrder = order[state] ?? 0;

    return [
      {
        label: 'Ý tưởng',
        detail: hasIdea ? '1/1' : '0/1',
        hint: hasIdea ? `${(latestIdeaSet as any)?.content?.candidates?.length ?? 1} phương án` : 'Chưa có',
        state: hasIdea ? ('done' as const) : curOrder >= 1 ? ('active' as const) : ('pending' as const),
      },
      {
        label: 'Story Bible',
        detail: hasBible ? '1/1' : '0/1',
        hint: hasBible ? 'Đã tạo' : 'Chưa có',
        state: hasBible ? ('done' as const) : curOrder >= 2 ? ('active' as const) : ('pending' as const),
      },
      {
        label: 'Dàn ý (Outline)',
        detail: hasOutline ? `${outlineCount} cảnh` : '0 cảnh',
        hint: hasOutline ? `${outlineCount} phân cảnh` : 'Chưa có',
        state: hasOutline ? ('done' as const) : curOrder >= 3 ? ('active' as const) : ('pending' as const),
      },
      {
        label: 'Kịch bản',
        detail: hasScreenplay ? `${screenplayCount} cảnh` : '0 cảnh',
        hint: hasScreenplay ? `${screenplayCount} cảnh` : 'Chưa có',
        state: hasScreenplay ? ('done' as const) : curOrder >= 4 ? ('active' as const) : ('pending' as const),
      },
      {
        label: 'Duyệt',
        detail: ['LOCKED', 'READY_FOR_PRODUCTION'].includes(state) ? '1/1' : state === 'SCREENPLAY_REVIEW' ? 'đang duyệt' : '0/1',
        hint: state === 'SCREENPLAY_REVIEW' ? 'Chờ duyệt' : ['LOCKED', 'READY_FOR_PRODUCTION'].includes(state) ? 'Đã duyệt' : 'Chưa duyệt',
        state: ['LOCKED', 'READY_FOR_PRODUCTION'].includes(state) ? ('done' as const) : state === 'SCREENPLAY_REVIEW' ? ('active' as const) : ('pending' as const),
      },
      {
        label: 'Khóa sản xuất',
        detail: ['LOCKED', 'READY_FOR_PRODUCTION'].includes(state) ? '1/1' : '0/1',
        hint: state === 'READY_FOR_PRODUCTION' ? 'Sẵn sàng SX' : state === 'LOCKED' ? 'Đã khóa' : 'Chưa khóa',
        state: ['LOCKED', 'READY_FOR_PRODUCTION'].includes(state) ? ('done' as const) : ('pending' as const),
      },
    ];
  }, [selectedEpisode, latestIdeaSet, latestStoryBible, latestOutline, latestScreenplay]);

  // Derive script beats from real outline/screenplay
  const scriptBeats = useMemo(() => {
    if (!selectedEpisode) return [];
    const outlineContent: any = (latestOutline as any)?.content || {};
    const screenplayContent: any = (latestScreenplay as any)?.content || {};
    const outlineScenes: any[] = outlineContent.scenes || outlineContent.beats || outlineContent.acts || [];
    const screenplayScenes: any[] = screenplayContent.scenes || [];
    // Prefer outline scenes if available, else screenplay
    const source = outlineScenes.length > 0 ? outlineScenes : screenplayScenes;
    if (source.length === 0) return [];
    // Map to display rows (max 5 for drawer preview — show first 5 + count)
    return source.slice(0, 5).map((s: any, idx: number) => {
      const code = s.scene_id || s.id || s.code || s.title || s.intent || `Cảnh ${idx + 1}`;
      const scenesLabel = s.estimated_seconds ? `${s.estimated_seconds}s` : s.duration_seconds ? `${s.duration_seconds}s` : '—';
      const isDone = !!s.action_description || !!s.visual_action || !!s.script_text;
      return {
        code: String(code).slice(0, 28),
        meta: scenesLabel,
        status: isDone ? 'Hoàn thành' : 'Nháp',
        tone: (isDone ? 'done' : 'todo') as 'done' | 'todo' | 'doing',
      };
    });
  }, [selectedEpisode, latestOutline, latestScreenplay]);

  const hasAnyScriptContent = scriptBeats.length > 0;
  const totalRealScenes = useMemo(() => {
    const oc: any = (latestOutline as any)?.content || {};
    const sc: any = (latestScreenplay as any)?.content || {};
    const ocLen = (oc.scenes || oc.beats || []).length;
    const scLen = (sc.scenes || []).length;
    return Math.max(ocLen, scLen);
  }, [latestOutline, latestScreenplay]);

  return (
    <div
      style={{
        minHeight: '100%',
        background: '#060e20',
        color: '#e2e8f0',
        padding: '18px 20px 24px 20px',
      }}
      data-testid="canonical-episodes-catalog-page"
    >
      <div style={{ maxWidth: '1440px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '9px',
                background: 'rgba(59,130,246,0.12)',
                border: '1px solid rgba(59,130,246,0.22)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#60a5fa',
                flexShrink: 0,
                marginTop: '2px',
              }}
            >
              <Clapperboard size={18} />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 800, color: '#f1f5f9', letterSpacing: '-0.2px', lineHeight: 1.2 }}>Episodes</h1>
              <p style={{ margin: '3px 0 0 0', fontSize: '12.5px', color: '#64748b', fontWeight: 500 }}>Quản lý và sản xuất các tập phim trong dự án — dữ liệu thật từ DB</p>
            </div>
          </div>

          <button
            onClick={handleCreateClick}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '7px',
              padding: '9px 16px',
              borderRadius: '9px',
              background: '#2563eb',
              border: '1px solid rgba(255,255,255,0.10)',
              color: '#fff',
              fontSize: '13px',
              fontWeight: 700,
              cursor: 'pointer',
              boxShadow: '0 4px 16px rgba(37,99,235,0.35)',
              whiteSpace: 'nowrap',
            }}
          >
            <Plus size={15} />
            Tạo Episode Mới
          </button>
        </div>

        {/* ── Project Selector (real series) ─────────────────────────────── */}
        <div style={{ position: 'relative', maxWidth: '420px' }}>
          <button
            onClick={() => setProjDropdownOpen((o) => !o)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '9px 12px',
              borderRadius: '10px',
              background: '#131b2e',
              border: '1px solid rgba(255,255,255,0.08)',
              color: '#e2e8f0',
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            <div
              style={{
                width: '36px',
                height: '24px',
                borderRadius: '6px',
                background: projectFilter !== 'ALL' ? thumbFor(projectFilter, 0) : 'linear-gradient(135deg,#1e40af 0%,#0f172a 100%)',
                flexShrink: 0,
                border: '1px solid rgba(255,255,255,0.08)',
                overflow: 'hidden',
              }}
            />
            <span style={{ flex: 1, fontSize: '12.5px', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {projectSelectorLabel}
            </span>
            <ChevronDown size={15} color="#64748b" style={{ transform: projDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </button>

          {projDropdownOpen && (
            <div
              style={{
                position: 'absolute',
                top: 'calc(100% + 8px)',
                left: 0,
                right: 0,
                background: '#0f172a',
                border: '1px solid rgba(255,255,255,0.10)',
                borderRadius: '10px',
                boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
                zIndex: 40,
                overflow: 'hidden',
              }}
            >
              <button
                onClick={() => {
                  setProjectFilter('ALL');
                  setProjDropdownOpen(false);
                }}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  background: projectFilter === 'ALL' ? 'rgba(59,130,246,0.12)' : 'transparent',
                  border: 'none',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                  color: projectFilter === 'ALL' ? '#60a5fa' : '#cbd5e1',
                  fontSize: '13px',
                  fontWeight: 600,
                  textAlign: 'left',
                  cursor: 'pointer',
                }}
              >
                Tất cả dự án ({series.length})
              </button>
              <div style={{ maxHeight: '260px', overflowY: 'auto' }}>
                {series.map((s: any) => (
                  <button
                    key={s.id}
                    onClick={() => {
                      setProjectFilter(s.id);
                      setProjDropdownOpen(false);
                    }}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '9px 12px',
                      background: projectFilter === s.id ? 'rgba(59,130,246,0.10)' : 'transparent',
                      border: 'none',
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      color: projectFilter === s.id ? '#f1f5f9' : '#94a3b8',
                      fontSize: '12.5px',
                      fontWeight: 500,
                      textAlign: 'left',
                      cursor: 'pointer',
                    }}
                  >
                    <span style={{ width: 28, height: 18, borderRadius: 5, background: thumbFor(s.id, 1), flexShrink: 0, border: '1px solid rgba(255,255,255,0.06)' }} />
                    <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.title}</span>
                    <span style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>{s.episode_count ?? 0} tập</span>
                  </button>
                ))}
                {series.length === 0 && (
                  <div style={{ padding: '16px 12px', color: '#475569', fontSize: 12, textAlign: 'center' }}>Chưa có dự án nào — tạo dự án trước</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ── Toolbar ────────────────────────────────────────────────────── */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, minWidth: '260px', maxWidth: '560px' }}>
            <div style={{ position: 'relative', flex: 1 }}>
              <Search size={15} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: '#475569', pointerEvents: 'none' }} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Tìm kiếm episode..."
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 34px',
                  borderRadius: '9px',
                  background: '#0f172a',
                  border: '1px solid rgba(255,255,255,0.08)',
                  color: '#e2e8f0',
                  fontSize: '13px',
                  outline: 'none',
                }}
                onFocus={(e) => (e.currentTarget.style.borderColor = 'rgba(59,130,246,0.35)')}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)')}
              />
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => {
                  setShowFilters((v) => !v);
                  setShowSort(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 12px',
                  borderRadius: '8px',
                  background: showFilters || stateFilter !== 'ALL' ? 'rgba(59,130,246,0.14)' : '#131b2e',
                  border: `1px solid ${showFilters || stateFilter !== 'ALL' ? 'rgba(59,130,246,0.30)' : 'rgba(255,255,255,0.08)'}`,
                  color: showFilters || stateFilter !== 'ALL' ? '#93c5fd' : '#94a3b8',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Filter size={13} />
                Filter
                {stateFilter !== 'ALL' && (
                  <span
                    style={{
                      background: '#3b82f6',
                      color: '#fff',
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '1px 5px',
                      borderRadius: 20,
                    }}
                  >
                    1
                  </span>
                )}
              </button>
              {showFilters && (
                <div
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 8px)',
                    right: 0,
                    minWidth: '220px',
                    background: '#0f172a',
                    border: '1px solid rgba(255,255,255,0.10)',
                    borderRadius: '10px',
                    boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
                    zIndex: 30,
                    padding: '8px',
                  }}
                >
                  {STATE_FILTERS.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => {
                        setStateFilter(s.id);
                        setShowFilters(false);
                      }}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px',
                        borderRadius: '7px',
                        background: stateFilter === s.id ? 'rgba(59,130,246,0.15)' : 'transparent',
                        border: 'none',
                        color: stateFilter === s.id ? '#60a5fa' : '#cbd5e1',
                        fontSize: '12.5px',
                        fontWeight: stateFilter === s.id ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div style={{ position: 'relative' }}>
              <button
                onClick={() => {
                  setShowSort((v) => !v);
                  setShowFilters(false);
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 12px',
                  borderRadius: '8px',
                  background: '#131b2e',
                  border: '1px solid rgba(255,255,255,0.08)',
                  color: '#94a3b8',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <ArrowUpDown size={13} />
                Sắp xếp
              </button>
              {showSort && (
                <div
                  style={{
                    position: 'absolute',
                    top: 'calc(100% + 8px)',
                    right: 0,
                    minWidth: '180px',
                    background: '#0f172a',
                    border: '1px solid rgba(255,255,255,0.10)',
                    borderRadius: '10px',
                    boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
                    zIndex: 30,
                    padding: '8px',
                  }}
                >
                  {SORT_OPTIONS.map((o) => (
                    <button
                      key={o.id}
                      onClick={() => {
                        setSortBy(o.id);
                        setShowSort(false);
                      }}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 10px',
                        borderRadius: '7px',
                        background: sortBy === o.id ? 'rgba(59,130,246,0.15)' : 'transparent',
                        border: 'none',
                        color: sortBy === o.id ? '#60a5fa' : '#cbd5e1',
                        fontSize: '12.5px',
                        fontWeight: sortBy === o.id ? 700 : 500,
                        cursor: 'pointer',
                      }}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div style={{ width: 1, height: 18, background: 'rgba(255,255,255,0.08)', margin: '0 2px' }} />

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                background: '#0f172a',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '8px',
                padding: '2px',
                gap: '2px',
              }}
            >
              <button
                onClick={() => setViewMode('list')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  background: viewMode === 'list' ? '#1e293b' : 'transparent',
                  border: viewMode === 'list' ? '1px solid rgba(59,130,246,0.30)' : '1px solid transparent',
                  color: viewMode === 'list' ? '#60a5fa' : '#64748b',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <Table2 size={13} />
                Danh sách
              </button>
              <button
                onClick={() => setViewMode('timeline')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  background: viewMode === 'timeline' ? '#1e293b' : 'transparent',
                  border: viewMode === 'timeline' ? '1px solid rgba(59,130,246,0.30)' : '1px solid transparent',
                  color: viewMode === 'timeline' ? '#60a5fa' : '#64748b',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                <LayoutGrid size={13} />
                Timeline
              </button>
            </div>

            <button
              onClick={() => {
                invalidate();
                refetch();
              }}
              disabled={isLoading}
              title="Làm mới"
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: '#131b2e',
                border: '1px solid rgba(255,255,255,0.08)',
                color: '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {deleteError && (
          <Card style={{ padding: '10px 14px', background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.25)', borderRadius: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: 13 }}>
              <AlertCircle size={16} />
              <span>{deleteError}</span>
              <button onClick={() => setDeleteError(null)} style={{ marginLeft: 'auto', background: 'transparent', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: 12 }}>Đóng</button>
            </div>
          </Card>
        )}

        {isError && (
          <Card style={{ padding: '14px 16px', background: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.25)', borderRadius: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#f87171', fontSize: 13 }}>
              <AlertCircle size={18} />
              <span>
                <strong>Lỗi tải episodes:</strong> {error?.message || 'Không thể kết nối máy chủ.'}
              </span>
            </div>
          </Card>
        )}

        {/* ── Table Card ─────────────────────────────────────────────────── */}
        <div
          style={{
            background: '#0f172a',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '12px',
            overflow: 'hidden',
            boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
          }}
        >
          <div
            className="ep-table-header"
            style={{
              display: 'grid',
              gridTemplateColumns: '48px minmax(240px, 1.45fr) 84px 150px 120px 160px 104px',
              alignItems: 'center',
              padding: '10px 14px',
              background: 'rgba(255,255,255,0.02)',
              borderBottom: '1px solid rgba(255,255,255,0.06)',
              fontSize: '10.5px',
              fontWeight: 700,
              letterSpacing: '0.06em',
              color: '#64748b',
              textTransform: 'uppercase',
            }}
          >
            <span style={{ textAlign: 'center' }}>STT</span>
            <span>TÊN EPISODE</span>
            <span style={{ textAlign: 'center' }}>THỜI LƯỢNG</span>
            <span>TRẠNG THÁI</span>
            <span>CẬP NHẬT</span>
            <span>TIẾN ĐỘ</span>
            <span style={{ textAlign: 'center' }}>THAO TÁC</span>
          </div>

          {isLoading && displayEpisodes.length === 0 && (
            <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} style={{ height: '56px', borderRadius: 10, background: '#131b2e', border: '1px solid rgba(255,255,255,0.04)', animation: 'pulse 1.4s infinite' }} />
              ))}
            </div>
          )}

          {!isLoading && displayEpisodes.length === 0 && (
            <div style={{ padding: '48px 20px', textAlign: 'center' }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 12,
                  background: 'rgba(59,130,246,0.12)',
                  color: '#3b82f6',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px auto',
                }}
              >
                <Film size={22} />
              </div>
              <h3 style={{ margin: '0 0 6px 0', fontSize: 15, fontWeight: 700, color: '#f1f5f9' }}>
                {search || stateFilter !== 'ALL' || projectFilter !== 'ALL' ? 'Không tìm thấy tập phim phù hợp' : 'Chưa có tập phim nào'}
              </h3>
              <p style={{ margin: '0 0 10px 0', fontSize: 13, color: '#64748b', maxWidth: 480, marginLeft: 'auto', marginRight: 'auto', lineHeight: 1.5 }}>
                {search
                  ? `Không có kết quả cho "${search}". Thử từ khóa khác.`
                  : stateFilter !== 'ALL'
                    ? `Không có tập nào ở trạng thái "${STATE_FILTERS.find((s) => s.id === stateFilter)?.label}".`
                    : projectFilter !== 'ALL'
                      ? 'Dự án này chưa có tập phim nào. Tạo tập đầu tiên để bắt đầu.'
                      : 'Chưa có tập phim nào trong DB. Tạo tập đầu tiên từ một dự án.'}
              </p>
              <p style={{ margin: '0 0 16px 0', fontSize: 12, color: '#475569' }}>
                DB hiện có {series.length} dự án, {episodes.length} tập (studio_episodes). Dữ liệu được tải trực tiếp từ /api/v3/studio.
              </p>
              <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
                <Button variant="outline" onClick={() => navigate('/projects')} style={{ borderRadius: 9 }}>
                  Duyệt dự án
                </Button>
                <Button variant="primary" onClick={handleCreateClick} style={{ borderRadius: 9 }}>
                  <Plus size={14} style={{ marginRight: 6 }} />
                  Tạo tập mới
                </Button>
              </div>
            </div>
          )}

          {!isLoading && displayEpisodes.length > 0 && viewMode === 'list' && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {displayEpisodes.map((ep: any, idx: number) => {
                const progress = ep.progress_percent ?? getStageProgress(ep.state || 'DRAFT');
                const st = getEpisodeStateMeta(ep.state || 'DRAFT');
                const up = formatUpdated(ep.updated_at || ep.created_at);
                const isSelected = ep.id === selectedId;
                const dur = realDuration(ep);
                const sub = realDescription(ep);
                return (
                  <div
                    key={ep.id}
                    onClick={() => setSelectedId(ep.id)}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '48px minmax(240px, 1.45fr) 84px 150px 120px 160px 104px',
                      alignItems: 'center',
                      padding: '10px 14px',
                      gap: 0,
                      background: isSelected ? 'rgba(37,99,235,0.10)' : 'transparent',
                      borderBottom: '1px solid rgba(255,255,255,0.04)',
                      cursor: 'pointer',
                      transition: 'background 0.15s',
                      position: 'relative',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'rgba(255,255,255,0.02)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                    }}
                  >
                    {isSelected && (
                      <span
                        style={{
                          position: 'absolute',
                          left: 0,
                          top: 0,
                          bottom: 0,
                          width: 2,
                          background: '#3b82f6',
                          boxShadow: '0 0 10px rgba(59,130,246,0.6)',
                        }}
                      />
                    )}

                    <span style={{ textAlign: 'center', fontSize: 12.5, fontWeight: 600, color: isSelected ? '#93c5fd' : '#64748b' }}>{idx + 1}</span>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, paddingRight: 12 }}>
                      <div
                        style={{
                          width: 56,
                          height: 36,
                          borderRadius: 7,
                          background: thumbFor(ep.id, idx),
                          flexShrink: 0,
                          border: '1px solid rgba(255,255,255,0.08)',
                          position: 'relative',
                          overflow: 'hidden',
                        }}
                      >
                        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.35), transparent)' }} />
                        <Film size={14} color="rgba(255,255,255,0.9)" style={{ position: 'absolute', left: 6, bottom: 6, filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.6))' }} />
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            color: isSelected ? '#f1f5f9' : '#e2e8f0',
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                          title={ep.title}
                        >
                          Tập {ep.episode_number}: {String(ep.title).replace(/^Tập\s*\d+\s*:?\s*/i, '') || ep.title}
                        </div>
                        <div style={{ fontSize: 11.5, color: sub ? '#64748b' : '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 500, fontStyle: sub ? 'normal' : 'italic' }}>
                          {sub || 'Chưa có tóm tắt cốt truyện.'}
                        </div>
                      </div>
                    </div>

                    <span style={{ textAlign: 'center', fontSize: 12.5, fontWeight: 600, color: dur ? '#cbd5e1' : '#475569', fontVariantNumeric: 'tabular-nums' }}>{dur || '—'}</span>

                    <span>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 6,
                          padding: '4px 9px',
                          borderRadius: 20,
                          fontSize: 11,
                          fontWeight: 700,
                          background: st.bg,
                          color: st.color,
                          border: `1px solid ${st.border}`,
                          whiteSpace: 'nowrap',
                        }}
                        title={ep.state}
                      >
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: st.dot, boxShadow: `0 0 6px ${st.dot}`, flexShrink: 0 }} />
                        {st.label}
                      </span>
                    </span>

                    <span style={{ fontSize: 12, lineHeight: 1.25, color: '#94a3b8' }}>
                      <span style={{ color: up.date === '—' ? '#475569' : '#cbd5e1', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>{up.date}</span>
                      {up.time && <span style={{ display: 'block', color: '#64748b', fontSize: 11.5, marginTop: 1 }}>{up.time}</span>}
                    </span>

                    <span style={{ paddingRight: 8 }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>
                            <span style={{ fontWeight: 700, color: getProgressColor(progress), fontVariantNumeric: 'tabular-nums' }}>{progress}%</span>
                          </span>
                          <span style={{ display: 'block', height: 5, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                            <span
                              style={{
                                display: 'block',
                                height: '100%',
                                width: `${progress}%`,
                                background: getProgressColor(progress),
                                borderRadius: 999,
                                boxShadow: progress >= 60 ? `0 0 8px ${getProgressColor(progress)}66` : 'none',
                                transition: 'width 0.4s ease',
                              }}
                            />
                          </span>
                        </span>
                        <span
                          title={isSelected ? 'Đang chọn' : 'Chọn'}
                          style={{
                            width: 16,
                            height: 16,
                            borderRadius: '50%',
                            border: `1.5px solid ${isSelected ? '#3b82f6' : 'rgba(255,255,255,0.15)'}`,
                            background: isSelected ? '#3b82f6' : 'transparent',
                            color: '#fff',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexShrink: 0,
                          }}
                        >
                          {isSelected && <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#fff' }} />}
                        </span>
                      </span>
                    </span>

                    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenWorkspace(ep.id);
                        }}
                        title="Xem workspace"
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          color: '#94a3b8',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                        }}
                      >
                        <Eye size={13} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenWorkspace(ep.id);
                        }}
                        title="Chỉnh sửa"
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          color: '#94a3b8',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                        }}
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        onClick={(e) => e.stopPropagation()}
                        title="Hành động khác"
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: 'rgba(255,255,255,0.04)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          color: '#64748b',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                        }}
                      >
                        <MoreHorizontal size={13} />
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {viewMode === 'timeline' && displayEpisodes.length > 0 && (
            <div style={{ padding: '22px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 8 }}>
                {displayEpisodes.map((ep: any, idx: number) => {
                  const p = ep.progress_percent ?? getStageProgress(ep.state || 'DRAFT');
                  const st = getEpisodeStateMeta(ep.state || 'DRAFT');
                  return (
                    <div
                      key={ep.id}
                      onClick={() => setSelectedId(ep.id)}
                      style={{
                        minWidth: 220,
                        background: ep.id === selectedId ? 'rgba(37,99,235,0.12)' : '#131b2e',
                        border: `1px solid ${ep.id === selectedId ? 'rgba(59,130,246,0.30)' : 'rgba(255,255,255,0.06)'}`,
                        borderRadius: 12,
                        padding: 12,
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ width: '100%', height: 84, borderRadius: 8, background: thumbFor(ep.id, idx), border: '1px solid rgba(255,255,255,0.08)', marginBottom: 10 }} />
                      <div style={{ fontSize: 12.5, fontWeight: 700, color: '#f1f5f9', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        Tập {ep.episode_number}: {String(ep.title).replace(/^Tập\s*\d+\s*:?\s*/i, '')}
                      </div>
                      <div style={{ marginTop: 6, fontSize: 11, color: '#64748b', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {realDescription(ep) || 'Chưa có mô tả'}
                      </div>
                      <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ flex: 1, height: 4, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                          <span style={{ display: 'block', height: '100%', width: `${p}%`, background: st.color }} />
                        </span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: st.color }}>{p}%</span>
                      </div>
                      <span style={{ marginTop: 8, display: 'inline-flex', padding: '3px 7px', borderRadius: 20, background: st.bg, color: st.color, fontSize: 11, fontWeight: 700, border: `1px solid ${st.border}` }}>
                        {st.label}
                      </span>
                    </div>
                  );
                })}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#475569', fontSize: 11 }}>
                Timeline — mỗi thẻ là một tập thật từ DB (studio_episodes). Kéo ngang để xem.
              </div>
            </div>
          )}
        </div>

        {/* ── Detail Drawer (real DB + artifacts) ────────────────────────── */}
        {selectedEpisode && (
          <div
            style={{
              background: '#0f172a',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: 12,
              overflow: 'hidden',
              boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            }}
          >
            <div style={{ display: 'flex', gap: 16, padding: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <div
                style={{
                  width: 200,
                  height: 118,
                  borderRadius: 10,
                  background: thumbFor(selectedEpisode.id, displayEpisodes.findIndex((e: any) => e.id === selectedEpisode.id)),
                  border: '1px solid rgba(255,255,255,0.08)',
                  overflow: 'hidden',
                  position: 'relative',
                  flexShrink: 0,
                }}
              >
                <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.45), transparent)' }} />
                <Film size={18} color="rgba(255,255,255,0.9)" style={{ position: 'absolute', left: 10, bottom: 10 }} />
              </div>

              <div style={{ flex: 1, minWidth: 260, display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#f1f5f9' }}>
                    Tập {selectedEpisode.episode_number}: {String(selectedEpisode.title).replace(/^Tập\s*\d+\s*:?\s*/i, '')}
                  </h2>
                  <button
                    onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: 7,
                      background: 'rgba(255,255,255,0.06)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      color: '#94a3b8',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                    }}
                    title="Mở workspace"
                  >
                    <Pencil size={12} />
                  </button>
                  {selectedStatus && (
                    <span
                      style={{
                        padding: '3px 8px',
                        borderRadius: 20,
                        fontSize: 11,
                        fontWeight: 700,
                        background: selectedStatus.bg,
                        color: selectedStatus.color,
                        border: `1px solid ${selectedStatus.border}`,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 5,
                      }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: selectedStatus.dot }} />
                      {selectedStatus.label}
                    </span>
                  )}
                </div>

                <p style={{ margin: 0, fontSize: 12.5, color: realDescription(selectedEpisode) ? '#94a3b8' : '#475569', lineHeight: 1.5, maxWidth: 560, fontStyle: realDescription(selectedEpisode) ? 'normal' : 'italic' }}>
                  {realDescription(selectedEpisode) || 'Chưa có mô tả chi tiết cho tập phim này (metadata.description trống trong DB).'}
                </p>

                <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginTop: 2, fontSize: 12, color: '#94a3b8' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontVariantNumeric: 'tabular-nums' }}>
                    <Clock3 size={12} color="#64748b" />
                    {realDuration(selectedEpisode) || '—'}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <CalendarDays size={12} color="#64748b" />
                    Cập nhật: {formatUpdated(selectedEpisode.updated_at || selectedEpisode.created_at).date} {formatUpdated(selectedEpisode.updated_at || selectedEpisode.created_at).time}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 180, flex: 1, maxWidth: 320 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: getProgressColor(selectedProgress) }}>{selectedProgress}%</span>
                    <span style={{ flex: 1, height: 6, borderRadius: 999, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                      <span style={{ display: 'block', height: '100%', width: `${selectedProgress}%`, background: getProgressColor(selectedProgress), borderRadius: 999 }} />
                    </span>
                    <span style={{ fontSize: 11, color: '#64748b' }}>
                      {artifactsLoading ? 'đang tải...' : `${artifacts.length} artifact${artifacts.length !== 1 ? 's' : ''}`}
                    </span>
                  </span>
                </div>
                {selectedEpisode.active_run_id && (
                  <div style={{ fontSize: 11, color: '#475569', fontFamily: 'var(--font-mono, monospace)' }}>
                    Run: {selectedEpisode.active_run_id} • Rev: {selectedEpisode.current_revision_id || '—'}
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end', marginLeft: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 7,
                      padding: '9px 14px',
                      borderRadius: 9,
                      background: '#2563eb',
                      border: '1px solid rgba(255,255,255,0.10)',
                      color: '#fff',
                      fontSize: 13,
                      fontWeight: 700,
                      cursor: 'pointer',
                      boxShadow: '0 4px 16px rgba(37,99,235,0.30)',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <Play size={14} fill="currentColor" />
                    Tiếp tục sản xuất
                  </button>

                  <button
                    onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '9px 12px 9px 14px',
                      borderRadius: 9,
                      background: '#131b2e',
                      border: '1px solid rgba(255,255,255,0.10)',
                      color: '#cbd5e1',
                      fontSize: 12.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    Xuất bản
                    <ChevronDown size={13} color="#64748b" />
                  </button>
                </div>

                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '7px 12px',
                    borderRadius: 8,
                    background: 'transparent',
                    border: '1px solid rgba(239,68,68,0.30)',
                    color: isDeleting ? '#475569' : '#f87171',
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: isDeleting ? 'not-allowed' : 'pointer',
                    opacity: isDeleting ? 0.6 : 1,
                  }}
                >
                  <Trash2 size={13} />
                  {isDeleting ? 'Đang xóa...' : 'Xóa Episode'}
                </button>
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 18,
                padding: '0 14px',
                borderTop: '1px solid rgba(255,255,255,0.06)',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                background: 'rgba(255,255,255,0.01)',
                overflowX: 'auto',
              }}
            >
              {[
                { id: 'overview', label: 'Tổng quan' },
                { id: 'script', label: 'Kịch bản' },
                { id: 'scenes', label: 'Phân cảnh' },
                { id: 'assets', label: 'Assets' },
                { id: 'notes', label: 'Ghi chú' },
                { id: 'history', label: 'Lịch sử' },
              ].map((t) => (
                <button
                  key={t.id}
                  onClick={() => setDetailTab(t.id as any)}
                  style={{
                    padding: '11px 2px',
                    background: 'transparent',
                    border: 'none',
                    borderBottom: detailTab === t.id ? '2px solid #3b82f6' : '2px solid transparent',
                    color: detailTab === t.id ? '#60a5fa' : '#64748b',
                    fontSize: 12.5,
                    fontWeight: detailTab === t.id ? 700 : 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    marginBottom: -1,
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {detailTab === 'overview' ? (
              <div
                className="ep-detail-grid"
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1.05fr 0.95fr 1.05fr',
                  gap: 14,
                  padding: 14,
                  background: '#0b1224',
                }}
              >
                <div
                  style={{
                    background: '#131b2e',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10,
                    padding: 14,
                  }}
                >
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: '#f1f5f9', marginBottom: 12 }}>Thông tin cơ bản</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 9, fontSize: 12.5 }}>
                    {[
                      { k: 'Dự án', v: currentProject?.title || '—' },
                      { k: 'Thứ tự', v: String(selectedEpisode.episode_number) },
                      { k: 'Thời lượng dự kiến', v: realDuration(selectedEpisode) || '—' },
                      {
                        k: 'Thể loại',
                        v: (() => {
                          const g = realGenre(currentProject);
                          if (!g) return <span style={{ color: '#475569', fontStyle: 'italic' }}>—</span>;
                          const pills = String(g).split('/').map((s) => s.trim()).filter(Boolean).slice(0, 2);
                          return (
                            <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                              {pills.map((pill) => (
                                <span
                                  key={pill}
                                  style={{
                                    padding: '2px 8px',
                                    borderRadius: 20,
                                    background: 'rgba(255,255,255,0.06)',
                                    border: '1px solid rgba(255,255,255,0.08)',
                                    color: '#cbd5e1',
                                    fontSize: 11,
                                    fontWeight: 600,
                                  }}
                                >
                                  {pill}
                                </span>
                              ))}
                            </span>
                          );
                        })(),
                      },
                      { k: 'Đạo diễn', v: (selectedEpisode.metadata as any)?.director || (currentProject?.metadata as any)?.director || 'Chưa cập nhật' },
                      { k: 'Biên kịch', v: (selectedEpisode.metadata as any)?.writer || (currentProject?.metadata as any)?.writer || 'Chưa cập nhật' },
                      {
                        k: 'Ngày tạo',
                        v: selectedEpisode.created_at ? new Date(selectedEpisode.created_at).toLocaleString('vi-VN') : '—',
                      },
                    ].map((row) => (
                      <div key={row.k} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                        <span style={{ color: '#64748b', fontWeight: 500, flexShrink: 0 }}>{row.k}</span>
                        <span style={{ color: row.v === '—' || row.v === 'Chưa cập nhật' ? '#475569' : '#e2e8f0', fontWeight: 600, textAlign: 'right', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontStyle: row.v === '—' ? 'italic' : 'normal' }}>
                          {row.v as any}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: 11, color: '#475569' }}>
                    ID: <span style={{ fontFamily: 'monospace', color: '#64748b' }}>{selectedEpisode.id}</span> • v{selectedEpisode.version}
                  </div>
                </div>

                <div
                  style={{
                    background: '#131b2e',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10,
                    padding: 14,
                  }}
                >
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 }}>Tiến độ sản xuất</div>
                  <div style={{ fontSize: 11, color: '#475569', marginBottom: 12 }}>
                    {artifactsLoading ? 'Đang tải artifacts...' : `${artifacts.length} artifact(s) từ DB • ${totalRealScenes} cảnh`}
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {productionChecklist.map((row) => (
                      <div key={row.label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: row.state === 'pending' ? '#64748b' : '#e2e8f0', fontWeight: 600 }}>
                          <span
                            style={{
                              width: 16,
                              height: 16,
                              borderRadius: '50%',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              background: row.state === 'done' ? '#22c55e' : row.state === 'active' ? 'rgba(59,130,246,0.18)' : 'transparent',
                              border: `1.5px solid ${row.state === 'done' ? '#22c55e' : row.state === 'active' ? '#3b82f6' : 'rgba(255,255,255,0.15)'}`,
                              color: row.state === 'done' ? '#fff' : row.state === 'active' ? '#60a5fa' : 'transparent',
                              fontSize: 9,
                              flexShrink: 0,
                            }}
                          >
                            {row.state === 'done' ? '✓' : row.state === 'active' ? '●' : ''}
                          </span>
                          {row.label}
                        </span>
                        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                          <span style={{ fontSize: 11.5, fontWeight: 700, color: row.state === 'done' ? '#4ade80' : row.state === 'active' ? '#60a5fa' : '#475569', fontVariantNumeric: 'tabular-nums' }}>{row.detail}</span>
                          <span style={{ fontSize: 10, color: '#475569' }}>{row.hint}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div
                  style={{
                    background: '#131b2e',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10,
                    padding: 14,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: '#f1f5f9' }}>Nội dung kịch bản</div>
                    <span style={{ fontSize: 11, color: '#475569' }}>{hasAnyScriptContent ? `${scriptBeats.length} mục` : '—'}</span>
                  </div>

                  {artifactsLoading ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: '#475569', fontSize: 12 }}>Đang tải nội dung thật từ DB...</div>
                  ) : !hasAnyScriptContent ? (
                    <div
                      style={{
                        padding: '18px 12px',
                        textAlign: 'center',
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px dashed rgba(255,255,255,0.08)',
                        borderRadius: 8,
                      }}
                    >
                      <FileText size={18} color="#334155" style={{ margin: '0 auto 8px' }} />
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: '#94a3b8', marginBottom: 4 }}>Chưa có nội dung kịch bản</div>
                      <div style={{ fontSize: 11.5, color: '#475569', lineHeight: 1.5, marginBottom: 10 }}>
                        Tập này chưa có artifact StoryBible / Outline / Screenplay trong DB (studio_artifacts = 0). Nhấn "Tiếp tục sản xuất" để khởi chạy Story run thật.
                      </div>
                      <button
                        onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                        style={{
                          padding: '6px 12px',
                          borderRadius: 7,
                          background: '#2563eb',
                          border: '1px solid rgba(255,255,255,0.10)',
                          color: '#fff',
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: 'pointer',
                        }}
                      >
                        Mở Workspace
                      </button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {scriptBeats.map((r) => (
                        <div
                          key={r.code}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 10,
                            padding: '7px 8px',
                            borderRadius: 8,
                            background: 'rgba(255,255,255,0.02)',
                            border: '1px solid rgba(255,255,255,0.04)',
                          }}
                        >
                          <FileText size={13} color="#64748b" style={{ flexShrink: 0 }} />
                          <span style={{ fontSize: 12, fontWeight: 600, color: '#e2e8f0', flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={r.code}>
                            {r.code}
                          </span>
                          <span style={{ fontSize: 11, color: '#64748b', whiteSpace: 'nowrap' }}>{r.meta}</span>
                          <span
                            style={{
                              padding: '2px 7px',
                              borderRadius: 20,
                              fontSize: 11,
                              fontWeight: 700,
                              whiteSpace: 'nowrap',
                              background: r.tone === 'done' ? 'rgba(34,197,94,0.12)' : 'rgba(100,116,139,0.10)',
                              color: r.tone === 'done' ? '#4ade80' : '#94a3b8',
                              border: `1px solid ${r.tone === 'done' ? 'rgba(34,197,94,0.24)' : 'rgba(100,116,139,0.18)'}`,
                            }}
                          >
                            {r.tone === 'done' ? '● ' : '○ '}
                            {r.status}
                          </span>
                        </div>
                      ))}
                      {totalRealScenes > 5 && (
                        <div style={{ fontSize: 11, color: '#475569', textAlign: 'center', paddingTop: 4 }}>... và {totalRealScenes - 5} cảnh khác trong DB</div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                    style={{
                      marginTop: 4,
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 7,
                      padding: '8px 12px',
                      borderRadius: 8,
                      background: '#1e293b',
                      border: '1px solid rgba(255,255,255,0.08)',
                      color: '#94a3b8',
                      fontSize: 12.5,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <BookOpen size={13} />
                    Xem toàn bộ kịch bản
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ padding: 18, background: '#0b1224', color: '#475569', fontSize: 13 }}>
                <div
                  style={{
                    background: '#131b2e',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10,
                    padding: 24,
                    textAlign: 'center',
                  }}
                >
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 8,
                      background: 'rgba(59,130,246,0.12)',
                      color: '#60a5fa',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      margin: '0 auto 10px auto',
                    }}
                  >
                    {detailTab === 'script' ? <FileText size={16} /> : detailTab === 'scenes' ? <Layers size={16} /> : <Film size={16} />}
                  </div>
                  <div style={{ fontWeight: 700, color: '#cbd5e1', marginBottom: 6 }}>
                    {detailTab === 'script'
                      ? 'Kịch bản chi tiết'
                      : detailTab === 'scenes'
                        ? 'Phân cảnh'
                        : detailTab === 'assets'
                          ? 'Assets liên kết'
                          : detailTab === 'notes'
                            ? 'Ghi chú sản xuất'
                            : 'Lịch sử thay đổi'}
                  </div>
                  <p style={{ margin: 0, color: '#64748b', fontSize: 12.5, maxWidth: 420, marginLeft: 'auto', marginRight: 'auto' }}>
                    Dữ liệu sẽ hiển thị khi có artifact thật trong DB. Hiện tập này có {artifacts.length} artifact(s).
                  </p>
                  <button
                    onClick={() => handleOpenWorkspace(selectedEpisode.id)}
                    style={{
                      marginTop: 14,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '8px 14px',
                      borderRadius: 8,
                      background: '#2563eb',
                      border: '1px solid rgba(255,255,255,0.10)',
                      color: '#fff',
                      fontSize: 12.5,
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Mở trong Workspace <ChevronRight size={13} />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {createTargetProject && (
          <CreateEpisodeDialog
            isOpen={isCreateOpen}
            projectId={createTargetProject.id}
            projectName={createTargetProject.title}
            nextEpisodeNumber={totalEpisodesForCreate}
            onClose={() => setIsCreateOpen(false)}
            onSubmit={async (input) => {
              await createEpisode(input);
              invalidate();
              refetch();
            }}
          />
        )}
      </div>

      <style>{`
        @media (max-width: 1100px) {
          .ep-table-header { grid-template-columns: 40px minmax(180px,1.35fr) 72px 132px 108px 140px 96px !important; font-size: 10px !important; }
          .ep-detail-grid { grid-template-columns: 1fr 1fr !important; }
        }
        @media (max-width: 760px) {
          .ep-table-header { display: none !important; }
          [data-testid="canonical-episodes-catalog-page"] [style*="grid-template-columns: 48px"] {
            grid-template-columns: 36px minmax(0,1fr) !important;
          }
          .ep-detail-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
};
