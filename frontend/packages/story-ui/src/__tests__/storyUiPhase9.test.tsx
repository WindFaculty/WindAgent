import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import { EpisodeWorkspace } from '../index';

const SAMPLE_ARTIFACTS: StudioArtifactEnvelope[] = [
  {
    artifact_id: 'art_1',
    artifact_type: 'IdeaCandidateSet',
    schema_version: 'studio.artifact/v1alpha1',
    series_id: 'srs_1',
    episode_id: 'ep_1',
    content_hash: 'idea123',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
    content: { candidates: [{ candidate_id: 'c1', title: 'Thỏ Thả Diều' }] },
  },
  {
    artifact_id: 'art_2',
    artifact_type: 'SelectedIdea',
    schema_version: 'studio.artifact/v1alpha1',
    series_id: 'srs_1',
    episode_id: 'ep_1',
    content_hash: 'sel123',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
    content: { title: 'Thỏ Thả Diều' },
  },
  {
    artifact_id: 'art_3',
    artifact_type: 'StoryBible',
    schema_version: 'studio.artifact/v1alpha1',
    series_id: 'srs_1',
    episode_id: 'ep_1',
    content_hash: 'sb123',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
    content: { title: 'Thỏ Thả Diều' },
  },
];

describe('Phase UI9 — Runtime Status & Activity UX', () => {
  afterEach(cleanup);

  it('renders truthful event-driven milestone timeline in EpisodeWorkspace Activity tab', () => {
    const episode = { id: 'ep_1', title: 'Tập 1', state: 'STORY_DEVELOPMENT' };
    render(<EpisodeWorkspace episode={episode} artifacts={SAMPLE_ARTIFACTS} />);

    // Switch to Activity tab
    const activityTabBtn = screen.getByRole('tab', { name: 'Activity' });
    fireEvent.click(activityTabBtn);

    expect(screen.getByText('Server Milestone Events')).toBeInTheDocument();
    expect(screen.getByText('Idea generation started')).toBeInTheDocument();
    expect(screen.getByText('Idea candidates generated')).toBeInTheDocument();
    expect(screen.getByText('Idea selected')).toBeInTheDocument();
    expect(screen.getByText('Story development completed')).toBeInTheDocument();
    expect(screen.getByText('Artifact Timeline')).toBeInTheDocument();
  });
});
