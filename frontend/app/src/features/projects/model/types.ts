/**
 * Canonical Project and Episode Model Types (Phase 7).
 *
 * No mock data: project status/progress are derived exclusively from real
 * episode states returned by the API (mirrors the backend's deterministic
 * state->progress mapping in apps/api/windagent_api/routers/v3/episodes.py).
 */

export type {
  ProjectResource,
  EpisodeResource,
  ProjectTemplate,
  CursorPage,
} from '@windagent/api-contracts';

export interface ProjectFilterState {
  search: string;
  genre: string;
  viewMode: 'grid' | 'list';
}

export interface CoverDesign {
  from: string;
  via: string;
  to: string;
  accent: string;
  badgeBg: string;
  badgeBorder: string;
}

/** Deterministic cover theming (colors only — carries no data). */
export const COVER_GRADIENTS: CoverDesign[] = [
  {
    from: '#1e3a8a',
    via: '#2563eb',
    to: '#06b6d4',
    accent: '#38bdf8',
    badgeBg: 'rgba(56, 189, 248, 0.15)',
    badgeBorder: 'rgba(56, 189, 248, 0.35)',
  },
  {
    from: '#4c1d95',
    via: '#7c3aed',
    to: '#ec4899',
    accent: '#f472b6',
    badgeBg: 'rgba(244, 114, 182, 0.15)',
    badgeBorder: 'rgba(244, 114, 182, 0.35)',
  },
  {
    from: '#064e3b',
    via: '#059669',
    to: '#10b981',
    accent: '#34d399',
    badgeBg: 'rgba(52, 211, 153, 0.15)',
    badgeBorder: 'rgba(52, 211, 153, 0.35)',
  },
  {
    from: '#78350f',
    via: '#d97706',
    to: '#f59e0b',
    accent: '#fbbf24',
    badgeBg: 'rgba(251, 191, 36, 0.15)',
    badgeBorder: 'rgba(251, 191, 36, 0.35)',
  },
  {
    from: '#831843',
    via: '#db2777',
    to: '#f43f5e',
    accent: '#fb7185',
    badgeBg: 'rgba(251, 113, 133, 0.15)',
    badgeBorder: 'rgba(251, 113, 133, 0.35)',
  },
  {
    from: '#1e1b4b',
    via: '#4338ca',
    to: '#6366f1',
    accent: '#818cf8',
    badgeBg: 'rgba(129, 140, 248, 0.15)',
    badgeBorder: 'rgba(129, 140, 248, 0.35)',
  },
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return h;
}

export function getCoverDesign(id: string, title: string): CoverDesign {
  const idx = Math.abs(hashString(`${id}:${title}`)) % COVER_GRADIENTS.length;
  return COVER_GRADIENTS[idx];
}

// ─── Real status/progress derived from API episode states ──────────────────

/** Real pipeline states persisted on episodes (see /api/v3/studio episodes). */
export type EpisodePipelineState =
  | 'DRAFT'
  | 'IDEA'
  | 'STORY_BIBLE'
  | 'OUTLINE'
  | 'SCREENPLAY'
  | 'REVIEW'
  | 'LOCKED'
  | 'READY_FOR_PRODUCTION'
  | string;

/**
 * Deterministic episode progress per pipeline state.
 * Mirrors the backend `_derive_progress` so UI matches server truth.
 */
const EPISODE_STATE_PROGRESS: Record<string, number> = {
  DRAFT: 5,
  IDEA: 15,
  STORY_BIBLE: 30,
  OUTLINE: 50,
  SCREENPLAY: 70,
  REVIEW: 85,
  LOCKED: 100,
  READY_FOR_PRODUCTION: 100,
};

export function deriveEpisodeProgress(state?: EpisodePipelineState | null): number {
  if (!state) return 5;
  return EPISODE_STATE_PROGRESS[state.toUpperCase()] ?? 5;
}

export interface EpisodeStateInfo {
  id: string;
  state?: string | null;
  active_run_id?: string | null;
  updated_at?: string | null;
}

export type DerivedStatus = 'producing' | 'review' | 'draft' | 'completed';

export const STATUS_LABEL: Record<DerivedStatus, string> = {
  producing: 'Đang sản xuất',
  review: 'Trong đánh giá',
  draft: 'Bản nháp',
  completed: 'Hoàn thành',
};

export const STATUS_CONFIG: Record<DerivedStatus, { bg: string; color: string; dot: string; border: string }> = {
  producing: { bg: 'rgba(99, 102, 241, 0.18)', color: '#a5b4fc', dot: '#818cf8', border: 'rgba(99,102,241,0.35)' },
  review: { bg: 'rgba(245, 158, 11, 0.15)', color: '#fcd34d', dot: '#f59e0b', border: 'rgba(245,158,11,0.3)' },
  draft: { bg: 'rgba(148, 163, 184, 0.12)', color: '#cbd5e1', dot: '#94a3b8', border: 'rgba(148,163,184,0.2)' },
  completed: { bg: 'rgba(16, 185, 129, 0.15)', color: '#6ee7b7', dot: '#10b981', border: 'rgba(16,185,129,0.3)' },
};

const TERMINAL_STATES = new Set(['LOCKED', 'READY_FOR_PRODUCTION']);

/**
 * Project status derived ONLY from real episode states:
 * - no episodes            -> draft
 * - all episodes terminal  -> completed
 * - any episode in REVIEW  -> review
 * - otherwise              -> producing
 */
export function deriveProjectStatus(episodes: EpisodeStateInfo[]): DerivedStatus {
  if (!episodes || episodes.length === 0) return 'draft';
  const states = episodes.map((e) => (e.state ?? 'DRAFT').toUpperCase());
  if (states.every((s) => TERMINAL_STATES.has(s))) return 'completed';
  if (states.some((s) => s === 'REVIEW')) return 'review';
  return 'producing';
}

/** Average real progress across the project's episodes (0 when empty). */
export function computeProjectProgress(episodes: EpisodeStateInfo[]): number {
  if (!episodes || episodes.length === 0) return 0;
  const total = episodes.reduce((sum, e) => sum + deriveEpisodeProgress(e.state), 0);
  return Math.round(total / episodes.length);
}
