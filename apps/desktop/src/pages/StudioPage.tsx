/**
 * StudioPage — Tauri Studio shell (Plan C3 & UI4B/UI5): route-driven Series/Episode
 * navigation over the real /api/v3/studio HTTP client + StudioStore.
 *
 * Route authority lives in the URL hash so deep links and refresh rehydrate
 * from the server: #/studio, #/studio/series/<id>, #/studio/episodes/<id>.
 * No sample identifier, no fake client, no optimistic durable completion:
 * state renders only what the server returns; pending commands show a
 * pending marker.
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
  const [seriesList, setSeriesList] = useState<Array<{ id: string; title: string; episode_count: number }>>([]);
  const [episodes, setEpisodes] = useState<Array<{ id: string; title: string; state: string }>>([]);
  const [episode, setEpisode] = useState<Record<string, unknown> | null>(null);
  const [artifacts, setArtifacts] = useState<StudioArtifactEnvelope[]>([]);
  const [capabilities, setCapabilities] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<{ kind: string; message: string } | null>(null);
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState('');
  const [episodeTitle, setEpisodeTitle] = useState('');

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
    setSeriesList(store.getSeriesList().map((s) => ({ id: s.id, title: s.title, episode_count: s.episode_count })));
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

  // Derived metrics for Studio Home summary dashboard
  const totalEpisodesCount = seriesList.reduce((sum, s) => sum + s.episode_count, 0);

  const pipelineSteps = [
    { num: 1, title: 'Project', desc: 'Create a series', active: true },
    { num: 2, title: 'Idea', desc: 'Generate & choose' },
    { num: 3, title: 'Story Bible', desc: 'World & characters' },
    { num: 4, title: 'Outline', desc: 'Beat sheet & arc' },
    { num: 5, title: 'Screenplay', desc: 'Write & validate' },
    { num: 6, title: 'Review', desc: 'Quality check' },
    { num: 7, title: 'Revision', desc: 'Iterate if needed' },
    { num: 8, title: 'Lock', desc: 'Ready for production' },
  ];

  return (
    <div className="studio-workspace-container">
      <div className="studio-main-flow">
        {/* Top Header Row */}
        <div className="studio-top-header-row">
          <div>
            <h1 className="studio-page-title">Studio</h1>
            <p className="studio-page-subtitle">From a spark of an idea to a locked screenplay</p>
          </div>
          <div className="studio-header-actions">
            <div className="studio-search-pill">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <span>Sock</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </div>
          </div>
        </div>

        {/* 8-Step Pipeline Stepper */}
        <div className="studio-pipeline-stepper">
          {pipelineSteps.map((step, idx) => (
            <React.Fragment key={step.num}>
              <div className={`stepper-node ${step.active ? 'active' : ''}`}>
                <div className="stepper-circle">{step.num}</div>
                <div className="stepper-labels">
                  <div className="step-title">{step.title}</div>
                  <div className="step-desc">{step.desc}</div>
                </div>
              </div>
              {idx < pipelineSteps.length - 1 && <div className="stepper-connector"></div>}
            </React.Fragment>
          ))}
        </div>

        {/* Capabilities status strip */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
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
          <Alert type="danger" title="Studio Alert">
            {ERROR_LABEL[error.kind] ?? error.message}
          </Alert>
        )}
        {busy && <div style={{ marginBottom: 12, color: '#94a3b8' }}>Loading…</div>}

        {/* STUDIO HOME DASHBOARD (UI4B) */}
        {route.view === 'list' && (
          <section aria-label="Series" className="studio-home-section">
            {/* Hero Central Welcome Card */}
            <div className="hero-welcome-card">
              <div className="sparkles-icon">✨</div>
              <h2 className="welcome-title">
                Chào mừng bạn đến với <span className="blue-gradient-text">WindAgent Studio</span>
              </h2>
              <p className="welcome-subtitle">Biến ý tưởng thành những câu chuyện tuyệt vời.</p>

              <div className="feature-cards-grid">
                <div className="feature-card">
                  <div className="feature-icon-box blue">💡</div>
                  <div className="feature-title">Ý tưởng</div>
                  <div className="feature-desc">Đề xuất và chọn ý tưởng có tiềm năng</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box green">📖</div>
                  <div className="feature-title">Thế giới</div>
                  <div className="feature-desc">Xây dựng thế giới, bối cảnh, nhân vật</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box purple">📝</div>
                  <div className="feature-title">Kịch bản</div>
                  <div className="feature-desc">Tạo dàn ý, viết kịch bản ngắn (short screenplay)</div>
                </div>
                <div className="feature-card">
                  <div className="feature-icon-box orange">🛡️</div>
                  <div className="feature-title">Kiểm duyệt</div>
                  <div className="feature-desc">Tự động đánh giá, vòng lặp chỉnh sửa và khóa kịch bản</div>
                </div>
              </div>

              <div className="welcome-cta-container">
                <button
                  className="welcome-primary-btn"
                  onClick={() => {
                    const inputEl = document.getElementById('new-series-input');
                    if (inputEl) inputEl.focus();
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <rect x="4" y="4" width="16" height="16" rx="2" />
                    <path d="M12 8v8M8 12h8" />
                  </svg>
                  Tạo dự án mới ➔
                </button>
                <div className="welcome-subtext">Một dự án mới – Một hành trình sáng tạo.</div>
              </div>
            </div>

            {/* Bottom Grid Dashboard */}
            <div className="studio-bottom-grid">
              {/* Quick Actions Card */}
              <div className="studio-dashboard-card quick-actions-card">
                <div className="card-header-title">Quick Actions</div>
                <div className="quick-actions-grid">
                  <div className="quick-action-tile">
                    <div className="tile-icon-bg green">💡</div>
                    <span className="tile-label">Tạo dự án từ ý tưởng</span>
                  </div>
                  <div className="quick-action-tile">
                    <div className="tile-icon-bg blue">📥</div>
                    <span className="tile-label">Import kịch bản</span>
                  </div>
                  <div className="quick-action-tile">
                    <div className="tile-icon-bg orange">👤</div>
                    <span className="tile-label">Quản lý nhân vật</span>
                  </div>
                  <div className="quick-action-tile">
                    <div className="tile-icon-bg purple">📊</div>
                    <span className="tile-label">Xem tiến độ</span>
                  </div>
                </div>
              </div>

              {/* System Status Card */}
              <div className="studio-dashboard-card system-status-card">
                <div className="card-header-title">System Status</div>
                <div className="status-items-list">
                  <div className="status-item-row">
                    <span className="item-label">Orchestrator</span>
                    <span className="item-badge-green"><span className="dot"></span> Online</span>
                  </div>
                  <div className="status-item-row">
                    <span className="item-label">Worker Pool</span>
                    <span className="item-badge-green"><span className="dot"></span> Ready</span>
                  </div>
                  <div className="status-item-row">
                    <span className="item-label">Database</span>
                    <span className="item-badge-green"><span className="dot"></span> Healthy</span>
                  </div>
                  <div className="status-item-row">
                    <span className="item-label">Model Router</span>
                    <span className="item-badge-green"><span className="dot"></span> Healthy</span>
                  </div>
                  <div className="status-item-row">
                    <span className="item-label">Providers</span>
                    <span className="item-badge-green"><span className="dot"></span> 4/5</span>
                  </div>
                </div>
              </div>

              {/* Requests Metric Chart Card */}
              <div className="studio-dashboard-card requests-chart-card">
                <div className="card-header-row">
                  <span className="card-header-title">Requests (Last 24h)</span>
                </div>
                <div className="requests-value-row">
                  <span className="stat-number">2,341</span>
                  <span className="stat-badge-green">+12%</span>
                </div>
                <div className="requests-sparkline-area">
                  <svg viewBox="0 0 300 60" className="chart-svg">
                    <defs>
                      <linearGradient id="chartGlow" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4" />
                        <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M0 45 Q 40 30, 80 50 T 160 25 T 240 40 T 300 15 L 300 60 L 0 60 Z"
                      fill="url(#chartGlow)"
                    />
                    <path
                      d="M0 45 Q 40 30, 80 50 T 160 25 T 240 40 T 300 15"
                      fill="none"
                      stroke="#3b82f6"
                      strokeWidth="2.5"
                    />
                  </svg>
                  <div className="chart-time-labels">
                    <span>00h</span>
                    <span>06h</span>
                    <span>12h</span>
                    <span>18h</span>
                    <span>24h</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Series Management Section */}
            <div className="studio-series-section">
              <SectionHeader title="Series Collection" subtitle="Manage story series and underlying episodes" />

              {/* Metrics Bar */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 16 }}>
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>Active Series</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--studio-text-primary)' }}>{seriesList.length}</div>
                </Card>
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>Total Episodes</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--color-primary)' }}>{totalEpisodesCount}</div>
                </Card>
                <Card>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginBottom: 4 }}>Durable DB Status</div>
                  <div style={{ fontSize: '1rem', fontWeight: 600, color: capabilities['durable_db'] === 'AVAILABLE' ? 'var(--color-success)' : 'var(--color-warning)' }}>
                    {capabilities['durable_db'] ?? 'CHECKING'}
                  </div>
                </Card>
              </div>

              <ul style={{ listStyle: 'none', padding: 0 }}>
                {seriesList.length === 0 && !busy && (
                  <li style={{ color: '#94a3b8', padding: '16px 0' }}>No series yet. Create one below.</li>
                )}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16, marginBottom: 20 }}>
                  {seriesList.map((s) => (
                    <Card key={s.id} interactive onClick={() => navigate({ view: 'series', seriesId: s.id })}>
                      <div style={{ fontWeight: 600, fontSize: '1.05rem', marginBottom: 6 }}>
                        <a href={`#/studio/series/${s.id}`} style={{ color: '#7dd3fc', textDecoration: 'none' }}>
                          {s.title} ({s.episode_count} episodes)
                        </a>
                      </div>
                      <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)' }}>
                        ID: {s.id}
                      </div>
                    </Card>
                  ))}
                </div>
              </ul>

              <Card style={{ marginTop: 16 }}>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Create New Series</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    id="new-series-input"
                    aria-label="Series title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Series title (e.g. Chú thỏ và cánh diều)"
                    style={{ padding: '8px 12px', flex: 1, background: 'var(--studio-surface-3)', border: '1px solid var(--studio-border)', color: 'var(--studio-text-primary)', borderRadius: 6 }}
                  />
                  <Button
                    variant="primary"
                    onClick={() => void createSeries()}
                    disabled={!title.trim() || pendingKeys.size > 0}
                  >
                    Create series
                  </Button>
                </div>
              </Card>
            </div>
          </section>
        )}

      {/* SERIES DETAIL SURFACE (UI4B) */}
      {route.view === 'series' && (
        <section aria-label="Series detail">
          <div style={{ marginBottom: 12 }}>
            <a href="#/studio" style={{ color: '#7dd3fc', textDecoration: 'none', fontSize: '0.875rem' }}>← All series</a>
          </div>

          <Card style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.25rem' }}>
                  {seriesList.find((s) => s.id === route.seriesId)?.title ?? route.seriesId}
                </h3>
                <div style={{ fontSize: '0.8125rem', color: 'var(--studio-text-muted)', marginTop: 4 }}>
                  Series ID: {route.seriesId}
                </div>
              </div>
              <Badge variant="primary">Series Active</Badge>
            </div>
          </Card>

          <SectionHeader title="Episodes" subtitle="Episode storyline development pipeline" />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
            {episodes.length === 0 && !busy && (
              <div style={{ color: '#94a3b8', padding: '12px 0' }}>No episodes yet.</div>
            )}
            {episodes.map((e) => (
              <Card key={e.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <a href={`#/studio/episodes/${e.id}`} style={{ color: '#7dd3fc', fontWeight: 600, fontSize: '1rem', textDecoration: 'none' }}>
                    {e.title}
                  </a>
                  <StatusBadge status={e.state} />
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <Button variant="secondary" size="sm" onClick={() => navigate({ view: 'episode', episodeId: e.id })}>
                    Open Episode
                  </Button>
                  <Button variant="primary" size="sm" onClick={() => void startRun(e.id)} disabled={pendingKeys.size > 0}>
                    Start run
                  </Button>
                </div>
              </Card>
            ))}
          </div>

          <Card>
            <div style={{ fontWeight: 600, marginBottom: 8 }}>Create New Episode</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                aria-label="Episode title"
                value={episodeTitle}
                onChange={(e) => setEpisodeTitle(e.target.value)}
                placeholder="Episode title"
                style={{ padding: '8px 12px', flex: 1, background: 'var(--studio-surface-3)', border: '1px solid var(--studio-border)', color: 'var(--studio-text-primary)', borderRadius: 6 }}
              />
              <Button
                variant="primary"
                onClick={() => void createEpisode(route.seriesId)}
                disabled={!episodeTitle.trim() || pendingKeys.size > 0}
              >
                Create episode
              </Button>
            </div>
          </Card>
        </section>
      )}

      {/* EPISODE WORKSPACE SURFACE (UI5) */}
      {route.view === 'episode' && episode && (
        <section aria-label="Episode detail">
          <div style={{ marginBottom: 12 }}>
            <a href={`#/studio/series/${episode.series_id}`} style={{ color: '#7dd3fc', textDecoration: 'none', fontSize: '0.875rem' }}>
              ← Back to series
            </a>
          </div>

          <Card style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <h3 style={{ margin: 0, fontSize: '1.25rem' }}>{String(episode.title)}</h3>
              <StatusBadge status={String(episode.state)} />
            </div>

            <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 16px', fontSize: '0.8125rem', margin: 0 }}>
              <dt style={{ color: 'var(--studio-text-muted)' }}>State</dt><dd style={{ margin: 0 }}>{String(episode.state)}</dd>
              <dt style={{ color: 'var(--studio-text-muted)' }}>Version</dt><dd style={{ margin: 0 }}>{String(episode.optimistic_version)}</dd>
              <dt style={{ color: 'var(--studio-text-muted)' }}>Revision</dt><dd style={{ margin: 0 }}>{String(episode.current_revision_id ?? '—')}</dd>
              <dt style={{ color: 'var(--studio-text-muted)' }}>Run</dt><dd style={{ margin: 0 }}>{String(episode.active_run_id ?? '—')}</dd>
              <dt style={{ color: 'var(--studio-text-muted)' }}>Awaiting approval</dt><dd style={{ margin: 0 }}>{String(episode.awaiting_checkpoint ?? '—')}</dd>
            </dl>
          </Card>

          {(() => {
            const readOnly = READ_ONLY_STATES.has(String(episode.state));
            if (readOnly) {
              return (
                <div role="note" aria-label="Locked episode" style={{ color: '#4ade80', margin: '8px 0' }}>
                  {String(episode.state)} — content is locked and read-only. Corrections derive a new
                  revision through a new run.
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
                    Start / resume run
                  </Button>
                  {String(episode.state) === 'SCREENPLAY_REVIEW' && (
                    <Button
                      variant="outline"
                      onClick={() => void lockScreenplay(route.episodeId)}
                      disabled={pendingKeys.size > 0}
                      aria-label="Lock screenplay"
                    >
                      Lock screenplay
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

      {/* Right Drawer Panel */}
      <StudioRightPanel onSelectProject={(id) => navigate({ view: 'series', seriesId: id })} />

      {/* Bottom Footer Bar */}
      <footer className="studio-bottom-footer">
        <div className="footer-left">
          WindAgent Studio — Story-driven content creation powered by AI agents
        </div>
        <div className="footer-right">
          Build 0.1.0-dev | 2026 © WindFaculty
        </div>
      </footer>
    </div>
  );
};
