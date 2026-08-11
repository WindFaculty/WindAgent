/**
 * StudioPage — Tauri Studio shell (Plan C3): route-driven Series/Episode
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
  ArtifactContentView,
  ScreenplayDiffView,
  type ScreenplayDraftContent,
} from '../components/studio/ArtifactViews';
import { RunProgress } from '../components/studio/RunProgress';
import { ApprovalBar, type ApprovalDecision } from '../components/studio/ApprovalBar';

type StudioRoute =
  | { view: 'list' }
  | { view: 'series'; seriesId: string }
  | { view: 'episode'; episodeId: string };

const API_BASE =
  (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_BASE) ||
  'http://localhost:8000';

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

// Primary artifact type reviewed at each approval checkpoint. The submitted
// artifact hash is the current revision content hash (server-validated); the
// primary artifact only identifies what the UI highlights for the user.
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
      if (err?.kind === 'conflict') await refreshEpisode(episodeId);
    }
  };

  /** Idea selection submits the exact candidate id of the served set with the
   *  set's own revision id and content hash plus the expected version. */
  const selectIdea = async (episodeId: string, setArtifact: StudioArtifactEnvelope, candidateId: string) => {
    const ep = store.getEpisode(episodeId);
    if (!ep) return;
    const epRaw = ep as unknown as Record<string, unknown>;
    const key = `studio_idea_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.selectIdea(key, episodeId, {
      episode_id: episodeId,
      revision_id: setArtifact.revision_id,
      candidate_id: candidateId,
      expected_content_hash: setArtifact.content_hash,
      expected_optimistic_version: Number(epRaw.optimistic_version ?? ep.version ?? 0),
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
    reason: string
  ) => {
    const ep = store.getEpisode(episodeId);
    if (!ep) return;
    const epRaw = ep as unknown as Record<string, unknown>;
    const revision =
      (epRaw.current_revision as Record<string, unknown> | undefined) ??
      (epRaw.currentRevision as Record<string, unknown> | undefined);
    const revisionId =
      (typeof revision?.revision_id === 'string' ? revision.revision_id : null) ??
      (typeof epRaw.current_revision_id === 'string' ? epRaw.current_revision_id : null) ??
      ep.revision_id;
    const revisionHash =
      typeof revision?.content_hash === 'string' ? revision.content_hash : null;
    if (!revisionId || !revisionHash) {
      setError({ kind: 'unknown', message: 'No current revision on server to approve.' });
      return;
    }
    const key = `studio_approval_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.recordApproval(key, episodeId, {
      episode_id: episodeId,
      revision_id: revisionId,
      checkpoint,
      artifact_hash: revisionHash,
      decision,
      reason: reason || undefined,
      expected_optimistic_version: Number(epRaw.optimistic_version ?? ep.version ?? 0),
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

  /** Hash-bound lock command: submits the exact current revision content hash. */
  const lockScreenplay = async (episodeId: string) => {
    const ep = store.getEpisode(episodeId);
    if (!ep) return;
    const epRaw = ep as unknown as Record<string, unknown>;
    const revision =
      (epRaw.current_revision as Record<string, unknown> | undefined) ??
      (epRaw.currentRevision as Record<string, unknown> | undefined);
    const revisionId =
      (typeof revision?.revision_id === 'string' ? revision.revision_id : null) ??
      (typeof epRaw.current_revision_id === 'string' ? epRaw.current_revision_id : null) ??
      ep.revision_id;
    const revisionHash =
      typeof revision?.content_hash === 'string' ? revision.content_hash : null;
    if (!revisionId || !revisionHash) {
      setError({ kind: 'unknown', message: 'No current revision on server to lock.' });
      return;
    }
    const key = `studio_lock_${crypto.randomUUID()}`;
    setPendingKeys((prev) => new Set(prev).add(key));
    const result = await store.lockScreenplay(key, episodeId, {
      episode_id: episodeId,
      revision_id: revisionId,
      expected_content_hash: revisionHash,
      expected_optimistic_version: Number(epRaw.optimistic_version ?? ep.version ?? 0),
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

  // Event cursor survives refresh: hydrate once on mount, persist on unload.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(CURSOR_STORAGE_KEY);
      if (raw) store.hydrate(JSON.parse(raw) as { eventCursors: Record<string, number> });
    } catch {
      // corrupt snapshot — start fresh
    }
    const save = () => {
      try {
        sessionStorage.setItem(CURSOR_STORAGE_KEY, JSON.stringify(store.serialize()));
      } catch {
        // storage unavailable — cursors live for the session only
      }
    };
    window.addEventListener('beforeunload', save);
    return () => window.removeEventListener('beforeunload', save);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const busy = loading !== null || pendingKeys.size > 0;
  const capabilityLabel = (name: string) => `${name}: ${capabilities[name] ?? '…'}`;

  return (
    <div style={{ padding: 20, fontFamily: 'inherit' }}>
      <h2 style={{ marginTop: 0 }}>Studio</h2>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
        <span title={capabilityLabel('durable_db')}>{capabilityLabel('durable_db')}</span>
        <span title={capabilityLabel('studio_orchestration')}>{capabilityLabel('studio_orchestration')}</span>
        <span title={capabilityLabel('story_engine')}>{capabilityLabel('story_engine')}</span>
        <span title={capabilityLabel('worker')}>{capabilityLabel('worker')}</span>
      </div>

      {error && (
        <div role="alert" style={{ padding: '8px 12px', marginBottom: 12, borderRadius: 6, background: '#3a2a2a', color: '#fca5a5' }}>
          {ERROR_LABEL[error.kind] ?? error.message}
        </div>
      )}
      {busy && <div style={{ marginBottom: 12, color: '#94a3b8' }}>Loading…</div>}

      {route.view === 'list' && (
        <section aria-label="Series">
          <h3>Series</h3>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {seriesList.length === 0 && !busy && <li style={{ color: '#94a3b8' }}>No series yet. Create one below.</li>}
            {seriesList.map((s) => (
              <li key={s.id} style={{ marginBottom: 8 }}>
                <a href={`#/studio/series/${s.id}`} style={{ color: '#7dd3fc' }}>
                  {s.title} ({s.episode_count} episodes)
                </a>
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              aria-label="Series title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Series title (e.g. Chú thỏ và cánh diều)"
              style={{ padding: '6px 10px', flex: 1 }}
            />
            <button onClick={() => void createSeries()} disabled={!title.trim() || pendingKeys.size > 0}>
              Create series
            </button>
          </div>
        </section>
      )}

      {route.view === 'series' && (
        <section aria-label="Series detail">
          <a href="#/studio" style={{ color: '#7dd3fc' }}>← All series</a>
          <h3>{seriesList.find((s) => s.id === route.seriesId)?.title ?? route.seriesId}</h3>
          <h4>Episodes</h4>
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {episodes.length === 0 && !busy && <li style={{ color: '#94a3b8' }}>No episodes yet.</li>}
            {episodes.map((e) => (
              <li key={e.id} style={{ marginBottom: 8, display: 'flex', gap: 10, alignItems: 'center' }}>
                <a href={`#/studio/episodes/${e.id}`} style={{ color: '#7dd3fc' }}>{e.title}</a>
                <span style={{ color: '#94a3b8' }}>{e.state}</span>
                <button onClick={() => void startRun(e.id)} disabled={pendingKeys.size > 0}>Start run</button>
              </li>
            ))}
          </ul>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              aria-label="Episode title"
              value={episodeTitle}
              onChange={(e) => setEpisodeTitle(e.target.value)}
              placeholder="Episode title"
              style={{ padding: '6px 10px', flex: 1 }}
            />
            <button onClick={() => void createEpisode(route.seriesId)} disabled={!episodeTitle.trim() || pendingKeys.size > 0}>
              Create episode
            </button>
          </div>
        </section>
      )}

      {route.view === 'episode' && episode && (
        <section aria-label="Episode detail">
          <a href={`#/studio/series/${episode.series_id}`} style={{ color: '#7dd3fc' }}>← Back to series</a>
          <h3>{String(episode.title)}</h3>
          <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px' }}>
            <dt>State</dt><dd>{String(episode.state)}</dd>
            <dt>Version</dt><dd>{String(episode.optimistic_version)}</dd>
            <dt>Revision</dt><dd>{String(episode.current_revision_id ?? '—')}</dd>
            <dt>Run</dt><dd>{String(episode.active_run_id ?? '—')}</dd>
            <dt>Awaiting approval</dt><dd>{String(episode.awaiting_checkpoint ?? '—')}</dd>
          </dl>
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
          {(() => {
            const readOnly = READ_ONLY_STATES.has(String(episode.state));
            if (readOnly) return null;
            return (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '8px 0' }}>
                <button onClick={() => void startRun(route.episodeId)} disabled={pendingKeys.size > 0}>
                  Start / resume run
                </button>
                {String(episode.state) === 'SCREENPLAY_REVIEW' && (
                  <button
                    onClick={() => void lockScreenplay(route.episodeId)}
                    disabled={pendingKeys.size > 0}
                    aria-label="Lock screenplay"
                  >
                    Lock screenplay
                  </button>
                )}
              </div>
            );
          })()}
          {typeof episode.active_run_id === 'string' && episode.active_run_id && (
            <RunProgress
              runId={episode.active_run_id}
              store={store}
              onDurableChange={() => void refreshEpisode(route.episodeId)}
            />
          )}
          {(() => {
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
          })()}
          <h4>Artifacts</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {artifacts.length === 0 && !busy && <div style={{ color: '#94a3b8' }}>No artifacts yet.</div>}
            {(() => {
              const drafts = artifacts
                .filter((a) => a.artifact_type === 'ScreenplayDraft')
                .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')));
              if (drafts.length >= 2) {
                return (
                  <div style={{ border: '1px solid #1e293b', borderRadius: 8, padding: 10 }}>
                    <ScreenplayDiffView
                      before={drafts[1].content as unknown as ScreenplayDraftContent}
                      after={drafts[0].content as unknown as ScreenplayDraftContent}
                    />
                  </div>
                );
              }
              return null;
            })()}
            {artifacts.map((a) => (
              <div key={a.artifact_id} style={{ border: '1px solid #1e293b', borderRadius: 8, padding: 10 }}>
                {a.artifact_type === 'IdeaCandidateSet' ? (
                  <ArtifactContentView
                    artifact={a}
                    onSelectIdea={(candidateId) => void selectIdea(route.episodeId, a, candidateId)}
                    selectDisabled={pendingKeys.size > 0}
                  />
                ) : (
                  <ArtifactContentView artifact={a} />
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};
