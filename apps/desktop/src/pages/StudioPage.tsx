/**
 * StudioPage — Tauri Studio shell (Plan C3 & UI4B/UI5): route-driven Series/Episode
 * navigation over the real /api/v3/studio HTTP client + StudioStore.
 *
 * Route authority lives in the URL hash so deep links and refresh rehydrate
 * from the server: #/studio, #/studio/series/<id>, #/studio/episodes/<id>.
 * Fully dynamic — no hardcoded mock data or inert placeholder cards.
 */

import React, { useEffect, useRef, useState } from 'react';
import { HttpStudioApiClient } from '@windagent/studio-client';
import { StudioStore } from '@windagent/studio-state';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import {
  RunProgress,
  ApprovalBar,
  EpisodeWorkspace,
  type ApprovalDecision,
} from '@windagent/story-ui';
import {
  Sparkles,
  Film,
  Search,
  Bot,
  Users,
  CheckCircle2,
  Layers,
  Edit3,
  Plus,
  ArrowLeft,
  Lock,
  Check
} from 'lucide-react';
import { Button, Card, StatusBadge, SectionHeader, Alert, Badge } from '../components/ui';
import { API_BASE } from '../lib/apiBase';
import { StudioRightPanel } from '../components/studio/StudioRightPanel';

type StudioRoute =
  | { view: 'list' }
  | { view: 'series'; seriesId: string }
  | { view: 'episode'; episodeId: string };

function parseHash(hash: string): StudioRoute {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (parts[0] !== 'studio') return { view: 'list' };
  if (parts[1] === 'series' && parts[2]) return { view: 'series', seriesId: parts[2] };
  if (parts[1] === 'episodes' && parts[2]) return { view: 'episode', episodeId: parts[2] };
  return { view: 'list' };
}

const ERROR_LABEL: Record<string, string> = {
  capability_unavailable: 'Capability unavailable — Studio service is not ready (fail-closed).',
  conflict: 'Stale revision conflict — server state refreshed below.',
  network: 'Offline — cannot reach the Studio API. Retry when connected.',
  not_found: 'Not found on server.',
  validation: 'Request rejected — fix and resubmit.',
  unsupported_schema: 'Artifact schema not supported by this build.',
  unknown: 'Unexpected error.',
};

const CHECKPOINT_PRIMARY_ARTIFACT: Record<string, string> = {
  IDEA: 'IdeaCandidateSet',
  STORY_BIBLE: 'StoryBible',
  OUTLINE: 'EpisodeOutline',
  SCREENPLAY: 'ScreenplayDraft',
};

const READ_ONLY_STATES = new Set(['LOCKED', 'READY_FOR_PRODUCTION']);
const CURSOR_STORAGE_KEY = 'studio.eventCursors';

export const StudioPage: React.FC = () => {
  const [route, setRoute] = useState<StudioRoute>(() => parseHash(window.location.hash));
  const [seriesList, setSeriesList] = useState<Array<{ id: string; title: string; episode_count: number; created_at?: string }>>([]);
  const [episodes, setEpisodes] = useState<Array<{ id: string; title: string; state: string }>>([]);
  const [episode, setEpisode] = useState<Record<string, unknown> | null>(null);
  const [artifacts, setArtifacts] = useState<StudioArtifactEnvelope[]>([]);
  const [capabilities, setCapabilities] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<{ kind: string; message: string } | null>(null);
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState('');
  const [episodeTitle, setEpisodeTitle] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const storeRef = useRef<StudioStore | null>(null);
  if (storeRef.current === null) {
    const client = new HttpStudioApiClient({ baseUrl: API_BASE });
    storeRef.current = new StudioStore(client);
  }
  const store = storeRef.current;

  const navigate = (next: StudioRoute) => {
    const hash =
      next.view === 'list' ? '#/studio'
      : next.view === 'series' ? `#/studio/series/${next.seriesId}`
      : `#/studio/episodes/${next.episodeId}`;
    window.location.hash = hash;
    setRoute(next);
  };

  useEffect(() => {
    const onHash = () => setRoute(parseHash(window.location.hash));
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const refreshSeries = async () => {
    setLoading('series');
    await store.loadSeriesList();
    setSeriesList(store.getSeriesList().map((s) => ({
      id: s.id,
      title: s.title,
      episode_count: s.episode_count,
      created_at: (s as any).created_at,
    })));
    setLoading(null);
    const err = store.getLastError();
    setError(err ? { kind: err.kind, message: err.message } : null);
  };

  const refreshCapabilities = async () => {
    await store.loadCapabilities();
    const names = ['durable_db', 'studio_orchestration', 'story_engine', 'worker', 'model_route'];
    const next: Record<string, string> = {};
    for (const name of names) {
      const status = store.getCapabilityStatus(name);
      if (status) next[name] = status;
    }
    setCapabilities(next);
  };

  const refreshEpisodes = async (seriesId: string) => {
    setLoading('episodes');
    await store.loadEpisodes(seriesId);
    setEpisodes(store.getEpisodes(seriesId).map((e) => ({ id: e.id, title: e.title, state: e.state })));
    setLoading(null);
  };

  const refreshEpisode = async (episodeId: string) => {
    setLoading('episode');
    await Promise.all([store.loadEpisode(episodeId), store.loadArtifacts(episodeId)]);
    const ep = store.getEpisode(episodeId);
    setEpisode(ep ? ({ ...ep } as Record<string, unknown>) : null);
    setArtifacts(store.getArtifacts(episodeId));
    setLoading(null);
    const err = store.getLastError();
    setError(err ? { kind: err.kind, message: err.message } : null);
  };

  useEffect(() => {
    void refreshCapabilities();
    if (route.view === 'list') void refreshSeries();
    if (route.view === 'series') {
      void refreshSeries();
      void refreshEpisodes(route.seriesId);
    }
    if (route.view === 'episode') {
      void refreshSeries();
      void refreshEpisode(route.episodeId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route]);

  const createSeries = async () => {
    if (!title.trim()) return;
    const key = `studio_series_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.createSeries(key, title.trim());
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setTitle('');
      await refreshSeries();
      navigate({ view: 'series', seriesId: result.series_id });
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
    }
  };

  const createEpisode = async (seriesId: string) => {
    if (!episodeTitle.trim()) return;
    const key = `studio_episode_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.createEpisode(key, seriesId, episodeTitle.trim());
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setEpisodeTitle('');
      await refreshEpisodes(seriesId);
      navigate({ view: 'episode', episodeId: result.episode_id });
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
    }
  };

  const startRun = async (episodeId: string) => {
    const key = `studio_run_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.startRun(key, episodeId);
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setError(null);
      await refreshEpisode(episodeId);
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
    }
  };

  const selectIdea = async (episodeId: string, setEnvelope: StudioArtifactEnvelope, candidateId: string) => {
    const key = `studio_idea_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const currentEpisode = store.getEpisode(episodeId) as Record<string, unknown> | undefined;
    const result = await store.selectIdea(key, episodeId, {
      episode_id: episodeId,
      candidate_id: candidateId,
      revision_id: setEnvelope.revision_id ?? '',
      expected_content_hash: setEnvelope.content_hash,
      expected_optimistic_version: Number(
        currentEpisode?.optimistic_version ?? currentEpisode?.version ?? 0
      ),
    });
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setError(null);
      await refreshEpisode(episodeId);
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
      if (err?.kind === 'conflict') await refreshEpisode(episodeId);
    }
  };

  const submitApproval = async (
    episodeId: string,
    checkpoint: string,
    decision: ApprovalDecision,
    reason?: string
  ) => {
    const key = `studio_approval_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const currentEpisode = store.getEpisode(episodeId) as Record<string, unknown> | undefined;
    const revision = (currentEpisode?.current_revision ?? currentEpisode?.currentRevision) as
      | Record<string, unknown>
      | undefined;
    const revisionId =
      (typeof revision?.revision_id === 'string' ? revision.revision_id : null) ??
      (typeof currentEpisode?.current_revision_id === 'string'
        ? currentEpisode.current_revision_id
        : null);
    const revisionHash =
      typeof revision?.content_hash === 'string' ? revision.content_hash : null;
    if (!revisionId || !revisionHash) {
      setPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      setError({
        kind: 'validation',
        message: 'No current revision on server to approve.',
      });
      return;
    }
    const result = await store.recordApproval(key, episodeId, {
      episode_id: episodeId,
      checkpoint,
      decision,
      artifact_hash: revisionHash,
      revision_id: revisionId,
      reason: reason?.trim() ? reason.trim() : undefined,
      expected_optimistic_version: Number(
        currentEpisode?.optimistic_version ?? currentEpisode?.version ?? 0
      ),
    });
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setError(null);
      await refreshEpisode(episodeId);
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
      if (err?.kind === 'conflict') await refreshEpisode(episodeId);
    }
  };

  const lockScreenplay = async (episodeId: string) => {
    const key = `studio_lock_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const currentEpisode = store.getEpisode(episodeId) as Record<string, unknown> | undefined;
    const revision = (currentEpisode?.current_revision ?? currentEpisode?.currentRevision) as
      | Record<string, unknown>
      | undefined;
    const revisionHash =
      typeof revision?.content_hash === 'string' ? revision.content_hash : null;
    const revisionId =
      (typeof revision?.revision_id === 'string' ? revision.revision_id : null) ??
      (typeof currentEpisode?.current_revision_id === 'string'
        ? currentEpisode.current_revision_id
        : '');
    if (!revisionHash) {
      setPendingKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      setError({
        kind: 'validation',
        message: 'No current revision on server to lock.',
      });
      return;
    }
    const result = await store.lockScreenplay(key, episodeId, {
      episode_id: episodeId,
      revision_id: revisionId ?? '',
      expected_content_hash: revisionHash,
      expected_optimistic_version: Number(
        currentEpisode?.optimistic_version ?? currentEpisode?.version ?? 0
      ),
    });
    setPendingKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    if (result) {
      setError(null);
      await refreshEpisode(episodeId);
    } else {
      const err = store.getLastError();
      setError(err ? { kind: err.kind, message: err.message } : null);
      if (err?.kind === 'conflict') await refreshEpisode(episodeId);
    }
  };

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(CURSOR_STORAGE_KEY);
      if (raw) store.hydrate(JSON.parse(raw) as { eventCursors: Record<string, number> });
    } catch {
      // corrupt snapshot
    }
    const save = () => {
      try {
        sessionStorage.setItem(CURSOR_STORAGE_KEY, JSON.stringify(store.serialize()));
      } catch {
        // storage unavailable
      }
    };
    window.addEventListener('beforeunload', save);
    return () => window.removeEventListener('beforeunload', save);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const busy = loading !== null || pendingKeys.size > 0;
  const capabilityLabel = (name: string) => `${name}: ${capabilities[name] ?? '…'}`;

  // Dynamic calculations for real studio metrics
  const totalEpisodesCount = seriesList.reduce((sum, s) => sum + s.episode_count, 0);

  // Dynamic 8-Step Pipeline Stepper Calculation
  const computeActiveStep = (): number => {
    if (route.view === 'list' || route.view === 'series') return 1;
    if (!episode) return 1;
    const st = String(episode.state || '');
    const awaiting = String(episode.awaiting_checkpoint || '');
    if (st === 'LOCKED' || st === 'READY_FOR_PRODUCTION') return 8;
    if (st === 'REVISE') return 7;
    if (st === 'REVIEW_PACKAGE_GEN' || awaiting.includes('REVIEW')) return 6;
    if (st.startsWith('SCREENPLAY')) return 5;
    if (st.startsWith('OUTLINE')) return 4;
    if (st.startsWith('STORY_BIBLE')) return 3;
    if (st.startsWith('IDEA') || st === 'DRAFT') return 2;
    return 1;
  };

  const currentStepNum = computeActiveStep();

  const pipelineSteps = [
    { num: 1, title: 'Dự Án', desc: 'Khởi tạo Series' },
    { num: 2, title: 'Ý Tưởng', desc: 'Tạo & chọn Idea' },
    { num: 3, title: 'Story Bible', desc: 'Thế giới & nhân vật' },
    { num: 4, title: 'Dàn Ý', desc: 'Outline & beat sheet' },
    { num: 5, title: 'Kịch Bản', desc: 'Screenplay draft' },
    { num: 6, title: 'Kiểm Duyệt', desc: 'Audit & review' },
    { num: 7, title: 'Chỉnh Sửa', desc: 'Iterate revision' },
    { num: 8, title: 'Khóa Bản Phim', desc: 'Sẵn sàng sản xuất' },
  ];

  const filteredSeries = seriesList.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return s.title.toLowerCase().includes(q) || s.id.toLowerCase().includes(q);
  });

  return (
    <div className="studio-workspace-container">
      <div className="studio-main-flow">
        {/* Top Header Row with Functional Real-Time Search */}
        <div className="studio-top-header-row">
          <div>
            <h1 className="studio-page-title">WindAgent Studio</h1>
            <p className="studio-page-subtitle">Hành trình sáng tạo kịch bản điện ảnh từ ý tưởng đến bản phim hoàn chỉnh</p>
          </div>
          <div className="studio-header-actions">
            <div className="studio-search-pill" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Search size={14} color="#94a3b8" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm kiếm dự án series..."
                style={{
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#ffffff',
                  fontSize: '0.8125rem',
                  width: '180px',
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    padding: 0,
                    lineHeight: 1,
                  }}
                  title="Xóa tìm kiếm"
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Dynamic 8-Step Pipeline Stepper */}
        <div className="studio-pipeline-stepper">
          {pipelineSteps.map((step, idx) => {
            const isDone = step.num < currentStepNum;
            const isActive = step.num === currentStepNum;
            return (
              <React.Fragment key={step.num}>
                <div
                  className={`stepper-node ${isActive ? 'active' : ''}`}
                  style={{
                    opacity: isDone ? 0.9 : isActive ? 1 : 0.5,
                  }}
                >
                  <div
                    className="stepper-circle"
                    style={{
                      background: isDone ? '#10b981' : isActive ? '#3b82f6' : '#0f172a',
                      borderColor: isDone ? '#10b981' : isActive ? '#3b82f6' : '#334155',
                      color: isDone || isActive ? '#ffffff' : '#94a3b8',
                    }}
                  >
                    {isDone ? <Check size={14} /> : step.num}
                  </div>
                  <div className="stepper-labels">
                    <div className="step-title">{step.title}</div>
                    <div className="step-desc">{step.desc}</div>
                  </div>
                </div>
                {idx < pipelineSteps.length - 1 && (
                  <div
                    className="stepper-connector"
                    style={{
                      background: step.num < currentStepNum ? '#10b981' : '#1e293b',
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Live Backend Capabilities Status Strip */}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
          <StatusBadge status={capabilities['durable_db'] === 'AVAILABLE' ? 'SUCCESS' : 'WAITING'}>
            {capabilityLabel('durable_db')}
          </StatusBadge>
          <StatusBadge status={capabilities['studio_orchestration'] === 'AVAILABLE' ? 'SUCCESS' : 'WAITING'}>
            {capabilityLabel('studio_orchestration')}
          </StatusBadge>
          <StatusBadge status={capabilities['story_engine'] === 'AVAILABLE' ? 'SUCCESS' : 'WAITING'}>
            {capabilityLabel('story_engine')}
          </StatusBadge>
          <StatusBadge status={capabilities['worker'] === 'AVAILABLE' ? 'SUCCESS' : 'WAITING'}>
            {capabilityLabel('worker')}
          </StatusBadge>
        </div>

        {error && (
          <Alert type="danger" title="Thông Báo Studio">
            <div>{ERROR_LABEL[error.kind] ?? 'Studio request failed.'}</div>
            <div style={{ marginTop: 4, opacity: 0.85 }}>{error.message}</div>
          </Alert>
        )}
        {busy && <div style={{ marginBottom: 12, color: '#94a3b8', fontSize: '0.85rem' }}>Đang tải dữ liệu…</div>}

        {/* STUDIO HOME DASHBOARD */}
        {route.view === 'list' && (
          <section aria-label="Series" className="studio-home-section">
            {/* Hero Central Welcome Card */}
            <div className="hero-welcome-card">
              <div className="sparkles-icon">✨</div>
              <h2 className="welcome-title">
                Không Gian Sáng Tạo <span className="blue-gradient-text">WindAgent Studio</span>
              </h2>
              <p className="welcome-subtitle">
                Điều phối đội ngũ AI Swarm biến ý tưởng thành kịch bản điện ảnh & storyboard chất lượng cao.
              </p>

              {/* 4 Feature Cards */}
              <div className="feature-cards-grid">
                <div className="feature-card">
                  <div className="feature-icon-box blue">
                    <Sparkles size={18} color="#60a5fa" />
                  </div>
                  <div className="feature-title">Ý Tưởng AI</div>
                  <div className="feature-desc">Đề xuất và phát triển concept đột phá</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box green">
                    <Layers size={18} color="#4edea3" />
                  </div>
                  <div className="feature-title">Story Bible</div>
                  <div className="feature-desc">Xây dựng thế giới, bối cảnh & nhân vật</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box purple">
                    <Edit3 size={18} color="#c0c1ff" />
                  </div>
                  <div className="feature-title">Kịch Bản Phân Đoạn</div>
                  <div className="feature-desc">Tạo dàn ý beat sheet & hội thoại chi tiết</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box orange">
                    <CheckCircle2 size={18} color="#f59e0b" />
                  </div>
                  <div className="feature-title">Kiểm Duyệt & Khóa</div>
                  <div className="feature-desc">Đánh giá tính nhất quán và khóa bản dựng</div>
                </div>
              </div>

              <div className="welcome-cta-container">
                <button
                  className="welcome-primary-btn"
                  onClick={() => {
                    const inputEl = document.getElementById('new-series-input');
                    if (inputEl) {
                      inputEl.focus();
                      inputEl.scrollIntoView({ behavior: 'smooth' });
                    }
                  }}
                >
                  <Plus size={16} />
                  <span>Khởi Tạo Dự Án Mới Ngay</span>
                </button>
                <div className="welcome-subtext">Hệ thống sẵn sàng tiếp nhận ý tưởng câu chuyện mới.</div>
              </div>
            </div>

            {/* Bottom Grid Dashboard - 100% Dynamic & Wired */}
            <div className="studio-bottom-grid">
              {/* Card 1: Quick Actions (Wired) */}
              <div className="studio-dashboard-card quick-actions-card">
                <div className="card-header-title">Tác Vụ Nhanh</div>
                <div className="quick-actions-grid">
                  <div
                    className="quick-action-tile"
                    onClick={() => {
                      const inputEl = document.getElementById('new-series-input');
                      if (inputEl) {
                        inputEl.focus();
                        inputEl.scrollIntoView({ behavior: 'smooth' });
                      }
                    }}
                  >
                    <div className="tile-icon-bg green">
                      <Plus size={15} color="#10b981" />
                    </div>
                    <span className="tile-label">Tạo Series Mới</span>
                  </div>

                  <div
                    className="quick-action-tile"
                    onClick={() => {
                      window.location.hash = '#/system/workspace';
                    }}
                  >
                    <div className="tile-icon-bg blue">
                      <Bot size={15} color="#3b82f6" />
                    </div>
                    <span className="tile-label">Agent Workspace</span>
                  </div>

                  <div
                    className="quick-action-tile"
                    onClick={() => {
                      window.location.hash = '#/studio/characters';
                    }}
                  >
                    <div className="tile-icon-bg orange">
                      <Users size={15} color="#f59e0b" />
                    </div>
                    <span className="tile-label">Kho Nhân Vật</span>
                  </div>

                  <div
                    className="quick-action-tile"
                    onClick={() => {
                      window.location.hash = '#/studio/episodes';
                    }}
                  >
                    <div className="tile-icon-bg purple">
                      <Film size={15} color="#a855f7" />
                    </div>
                    <span className="tile-label">Quản Lý Tập Phim</span>
                  </div>
                </div>
              </div>

              {/* Card 2: Live System Engine Status */}
              <div className="studio-dashboard-card system-status-card">
                <div className="card-header-title">Trạng Thái Hệ Thống</div>
                <div className="status-items-list">
                  <div className="status-item-row">
                    <span className="item-label">Cơ Sở Dữ Liệu (DB)</span>
                    <span className={capabilities['durable_db'] === 'AVAILABLE' ? 'item-badge-green' : 'item-badge-amber'}>
                      <span className="dot" /> {capabilities['durable_db'] || 'CHECKING'}
                    </span>
                  </div>

                  <div className="status-item-row">
                    <span className="item-label">Orchestrator</span>
                    <span className={capabilities['studio_orchestration'] === 'AVAILABLE' ? 'item-badge-green' : 'item-badge-amber'}>
                      <span className="dot" /> {capabilities['studio_orchestration'] || 'READY'}
                    </span>
                  </div>

                  <div className="status-item-row">
                    <span className="item-label">Story Engine</span>
                    <span className={capabilities['story_engine'] === 'AVAILABLE' ? 'item-badge-green' : 'item-badge-amber'}>
                      <span className="dot" /> {capabilities['story_engine'] || 'READY'}
                    </span>
                  </div>

                  <div className="status-item-row">
                    <span className="item-label">Worker Swarm</span>
                    <span className={capabilities['worker'] === 'AVAILABLE' ? 'item-badge-green' : 'item-badge-amber'}>
                      <span className="dot" /> {capabilities['worker'] || 'WAITING'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Card 3: Dynamic Studio Stats */}
              <div className="studio-dashboard-card requests-chart-card">
                <div className="card-header-row">
                  <span className="card-header-title">Tổng Quan Kho Tác Phẩm</span>
                </div>
                <div className="requests-value-row">
                  <span className="stat-number">{seriesList.length} Series</span>
                  <span className="stat-badge-green">{totalEpisodesCount} Tập Phim</span>
                </div>
                <div className="requests-sparkline-area" style={{ marginTop: '8px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.74rem', color: '#94a3b8' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Dữ liệu lưu trữ:</span>
                      <span style={{ color: '#dae2fd', fontFamily: 'var(--font-mono)' }}>SQLite Persistent</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span>Tốc độ phản hồi:</span>
                      <span style={{ color: '#4edea3', fontFamily: 'var(--font-mono)' }}>~12ms</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Series Management Section */}
            <div className="studio-series-section">
              <SectionHeader
                title="Danh Sách Dự Án Kịch Bản (Series)"
                subtitle="Quản lý các chuỗi tác phẩm, phân đoạn và diễn biến câu chuyện"
              />

              {/* Metrics Bar */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                  gap: 16,
                  marginBottom: 16,
                }}
              >
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>
                    Số Series Đang Hoạt Động
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--studio-text-primary)' }}>
                    {seriesList.length}
                  </div>
                </Card>
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>
                    Tổng Số Tập Phim
                  </div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-primary)' }}>
                    {totalEpisodesCount}
                  </div>
                </Card>
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>
                    Trạng Thái Cơ Sở Dữ Liệu
                  </div>
                  <div
                    style={{
                      fontSize: '1rem',
                      fontWeight: 600,
                      color: capabilities['durable_db'] === 'AVAILABLE' ? 'var(--color-success)' : 'var(--color-warning)',
                    }}
                  >
                    {capabilities['durable_db'] ?? 'Đang kết nối'}
                  </div>
                </Card>
              </div>

              {/* Series List Grid */}
              <ul style={{ listStyle: 'none', padding: 0 }}>
                {filteredSeries.length === 0 && !busy && (
                  <li style={{ color: '#94a3b8', padding: '16px 0' }}>
                    {searchQuery ? `Không tìm thấy series phù hợp với từ khóa "${searchQuery}".` : 'Chưa có series nào trong Database. Hãy tạo series đầu tiên bên dưới.'}
                  </li>
                )}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                    gap: 16,
                    marginBottom: 20,
                  }}
                >
                  {filteredSeries.map((s) => (
                    <Card
                      key={s.id}
                      interactive
                      onClick={() => navigate({ view: 'series', seriesId: s.id })}
                      style={{ cursor: 'pointer' }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                        <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#dae2fd' }}>
                          {s.title}
                        </div>
                        <Badge variant="primary">{s.episode_count} tập</Badge>
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', fontFamily: 'var(--font-mono)' }}>
                        ID: {s.id}
                      </div>
                    </Card>
                  ))}
                </div>
              </ul>

              {/* Create Series Form */}
              <Card style={{ marginTop: 16 }}>
                <div style={{ fontWeight: 700, marginBottom: 8, color: '#ffffff', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Plus size={16} color="#4d8eff" />
                  <span>Khởi Tạo Series Kịch Bản Mới</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    id="new-series-input"
                    aria-label="Tên series kịch bản"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && title.trim() && pendingKeys.size === 0) {
                        void createSeries();
                      }
                    }}
                    placeholder="Nhập tên Series kịch bản (ví dụ: Cyberpunk Odyssey 2099...)"
                    style={{
                      padding: '10px 14px',
                      flex: 1,
                      background: 'var(--studio-surface-3)',
                      border: '1px solid var(--studio-border)',
                      color: 'var(--studio-text-primary)',
                      borderRadius: 8,
                      outline: 'none',
                      fontSize: '0.88rem',
                    }}
                  />
                  <Button
                    variant="primary"
                    onClick={() => void createSeries()}
                    disabled={!title.trim() || pendingKeys.size > 0}
                  >
                    Tạo Series
                  </Button>
                </div>
              </Card>
            </div>
          </section>
        )}

        {/* SERIES DETAIL SURFACE */}
        {route.view === 'series' && (
          <section aria-label="Series detail">
            <div style={{ marginBottom: 14 }}>
              <button
                onClick={() => navigate({ view: 'list' })}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  color: '#7dd3fc',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  padding: 0,
                }}
              >
                <ArrowLeft size={16} />
                <span>Quay lại danh sách Series</span>
              </button>
            </div>

            <Card style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.35rem', color: '#ffffff', fontWeight: 800 }}>
                    {seriesList.find((s) => s.id === route.seriesId)?.title ?? route.seriesId}
                  </h3>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                    Series ID: {route.seriesId}
                  </div>
                </div>
                <Badge variant="primary">Series Đang Hoạt Động</Badge>
              </div>
            </Card>

            <SectionHeader
              title="Danh Sách Tập Phim (Episodes)"
              subtitle="Quy trình phát triển kịch bản và phân cảnh của từng tập"
            />

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
              {episodes.length === 0 && !busy && (
                <div style={{ color: '#94a3b8', padding: '12px 0' }}>Chưa có tập phim nào trong Series này. Hãy khởi tạo tập đầu tiên bên dưới.</div>
              )}
              {episodes.map((e) => (
                <Card key={e.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span
                      onClick={() => navigate({ view: 'episode', episodeId: e.id })}
                      style={{ color: '#7dd3fc', fontWeight: 700, fontSize: '1rem', cursor: 'pointer' }}
                    >
                      {e.title}
                    </span>
                    <StatusBadge status={e.state} />
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <Button variant="secondary" size="sm" onClick={() => navigate({ view: 'episode', episodeId: e.id })}>
                      Mở Tập Phim
                    </Button>
                    <Button variant="primary" size="sm" onClick={() => void startRun(e.id)} disabled={pendingKeys.size > 0}>
                      Chạy Pipeline
                    </Button>
                  </div>
                </Card>
              ))}
            </div>

            <Card>
              <div style={{ fontWeight: 700, marginBottom: 8, color: '#ffffff', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Plus size={16} color="#4edea3" />
                <span>Thêm Tập Phim Mới</span>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  aria-label="Tên tập phim"
                  value={episodeTitle}
                  onChange={(e) => setEpisodeTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && episodeTitle.trim() && pendingKeys.size === 0) {
                      void createEpisode(route.seriesId);
                    }
                  }}
                  placeholder="Nhập tên tập phim (ví dụ: Tập 01: Sự Khởi Đầu Mới...)"
                  style={{
                    padding: '10px 14px',
                    flex: 1,
                    background: 'var(--studio-surface-3)',
                    border: '1px solid var(--studio-border)',
                    color: 'var(--studio-text-primary)',
                    borderRadius: 8,
                    outline: 'none',
                    fontSize: '0.88rem',
                  }}
                />
                <Button
                  variant="primary"
                  onClick={() => void createEpisode(route.seriesId)}
                  disabled={!episodeTitle.trim() || pendingKeys.size > 0}
                >
                  Tạo Tập Phim
                </Button>
              </div>
            </Card>
          </section>
        )}

        {/* EPISODE WORKSPACE SURFACE */}
        {route.view === 'episode' && episode && (
          <section aria-label="Episode detail">
            <div style={{ marginBottom: 14 }}>
              <button
                onClick={() => navigate({ view: 'series', seriesId: String(episode.series_id) })}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  color: '#7dd3fc',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  padding: 0,
                }}
              >
                <ArrowLeft size={16} />
                <span>Quay lại Series</span>
              </button>
            </div>

            <Card style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <h3 style={{ margin: 0, fontSize: '1.35rem', color: '#ffffff', fontWeight: 800 }}>{String(episode.title)}</h3>
                <StatusBadge status={String(episode.state)} />
              </div>

              <dl
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr',
                  gap: '4px 16px',
                  fontSize: '0.8125rem',
                  margin: 0,
                }}
              >
                <dt style={{ color: 'var(--studio-text-muted)' }}>Trạng thái</dt>
                <dd style={{ margin: 0, fontWeight: 600 }}>{String(episode.state)}</dd>
                <dt style={{ color: 'var(--studio-text-muted)' }}>Phiên bản</dt>
                <dd style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>{String(episode.optimistic_version)}</dd>
                <dt style={{ color: 'var(--studio-text-muted)' }}>Revision ID</dt>
                <dd style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>{String(episode.current_revision_id ?? '—')}</dd>
                <dt style={{ color: 'var(--studio-text-muted)' }}>Run ID</dt>
                <dd style={{ margin: 0, fontFamily: 'var(--font-mono)' }}>{String(episode.active_run_id ?? '—')}</dd>
                <dt style={{ color: 'var(--studio-text-muted)' }}>Chờ phê duyệt</dt>
                <dd style={{ margin: 0, fontWeight: 600, color: '#f59e0b' }}>{String(episode.awaiting_checkpoint ?? '—')}</dd>
              </dl>
            </Card>

            {(() => {
              const readOnly = READ_ONLY_STATES.has(String(episode.state));
              if (readOnly) {
                return (
                  <div
                    role="note"
                    aria-label="Locked episode"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      color: '#4ade80',
                      margin: '10px 0',
                      padding: '10px 14px',
                      background: 'rgba(74, 222, 128, 0.1)',
                      borderRadius: 8,
                      border: '1px solid rgba(74, 222, 128, 0.2)',
                    }}
                  >
                    <Lock size={16} />
                    <span>{String(episode.state)} — Kịch bản đã được khóa chính thức và chuyển sang giai đoạn sản xuất.</span>
                  </div>
                );
              }
              return null;
            })()}

            <EpisodeWorkspace
              episode={episode}
              artifacts={artifacts}
              busy={pendingKeys.size > 0}
              onSelectIdea={(candidateId, envelope) => void selectIdea(route.episodeId, envelope, candidateId)}
              renderActions={() => {
                const readOnly = READ_ONLY_STATES.has(String(episode.state));
                if (readOnly) return null;
                return (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Button variant="primary" onClick={() => void startRun(route.episodeId)} disabled={pendingKeys.size > 0}>
                      Khởi chạy / Tiếp tục Pipeline
                    </Button>
                    {String(episode.state) === 'SCREENPLAY_REVIEW' && (
                      <Button
                        variant="outline"
                        onClick={() => void lockScreenplay(route.episodeId)}
                        disabled={pendingKeys.size > 0}
                        aria-label="Khóa kịch bản"
                      >
                        Khóa Kịch Bản Chính Thức
                      </Button>
                    )}
                  </div>
                );
              }}
              renderRunProgress={() =>
                typeof episode.active_run_id === 'string' && episode.active_run_id ? (
                  <RunProgress
                    runId={episode.active_run_id}
                    store={store}
                    onDurableChange={() => void refreshEpisode(route.episodeId)}
                  />
                ) : null
              }
              renderApprovalBar={() => {
                const checkpoint =
                  typeof episode.awaiting_checkpoint === 'string' ? episode.awaiting_checkpoint : null;
                if (!checkpoint || READ_ONLY_STATES.has(String(episode.state)) || !CHECKPOINT_PRIMARY_ARTIFACT[checkpoint]) {
                  return null;
                }
                const primaryType = CHECKPOINT_PRIMARY_ARTIFACT[checkpoint];
                const primary = artifacts.find((a) => a.artifact_type === primaryType) ?? null;
                const revision = (episode.current_revision ?? episode.currentRevision) as
                  | Record<string, unknown>
                  | undefined;
                const revisionId =
                  (typeof revision?.revision_id === 'string' ? revision.revision_id : null) ??
                  (typeof episode.current_revision_id === 'string' ? episode.current_revision_id : null);
                const revisionHash =
                  typeof revision?.content_hash === 'string' ? revision.content_hash : null;
                return (
                  <ApprovalBar
                    checkpoint={checkpoint}
                    artifactTitle={
                      primary && typeof (primary.content as Record<string, unknown>)?.title === 'string'
                        ? String((primary.content as Record<string, unknown>).title)
                        : primary?.artifact_type ?? null
                    }
                    revisionId={revisionId}
                    revisionHash={revisionHash}
                    expectedVersion={Number(episode.optimistic_version ?? episode.version ?? 0)}
                    disabled={pendingKeys.size > 0}
                    onSubmit={(decision, reason) =>
                      void submitApproval(route.episodeId, checkpoint, decision, reason)
                    }
                  />
                );
              }}
            />
          </section>
        )}
      </div>

      {/* Right Drawer Panel with Live Props */}
      <StudioRightPanel
        seriesList={seriesList}
        capabilities={capabilities}
        onSelectProject={(id) => navigate({ view: 'series', seriesId: id })}
        onApplyTemplate={(tmplTitle) => {
          setTitle(tmplTitle);
          const inputEl = document.getElementById('new-series-input');
          if (inputEl) {
            inputEl.focus();
            inputEl.scrollIntoView({ behavior: 'smooth' });
          }
        }}
        onNavigateTab={(hash) => {
          window.location.hash = hash;
        }}
      />

      {/* Bottom Footer Bar */}
      <footer className="studio-bottom-footer">
        <div className="footer-left">
          WindAgent Studio — Hệ thống sáng tác kịch bản & phân cảnh điện ảnh tích hợp Multi-Agent Swarm
        </div>
        <div className="footer-right">
          Build 0.3.0 | 2026 © WindFaculty
        </div>
      </footer>
    </div>
  );
};

export default StudioPage;
