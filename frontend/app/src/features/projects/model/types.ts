/**
 * Canonical Project and Episode Model Types (Phase 7).
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
  genre: string;
  badgeBg: string;
  badgeBorder: string;
}

export const COVER_GRADIENTS: CoverDesign[] = [
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

export function getCoverDesign(id: string, title: string): CoverDesign {
  let hash = 0;
  const str = `${id}:${title}`;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % COVER_GRADIENTS.length;
  return COVER_GRADIENTS[idx];
}
