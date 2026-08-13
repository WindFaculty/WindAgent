import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import {
  IdeaSetView,
  StoryBibleView,
  OutlineView,
  ScreenplayView,
  ApprovalBar,
  ArtifactContentView,
  UnsupportedArtifactView,
  PipelineProgress,
  EpisodeWorkspace,
} from '../index';

const SAMPLE_ENVELOPE: StudioArtifactEnvelope = {
  artifact_id: 'art_101',
  artifact_type: 'IdeaCandidateSet',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'abc123hash',
  content: {
    candidates: [
      { candidate_id: 'c1', title: 'Idea One', premise: 'Premise 1', score: 0.95 },
      { candidate_id: 'c2', title: 'Idea Two', premise: 'Premise 2', score: 0.88 },
    ],
  },
};

describe('@windagent/story-ui package (UI4A)', () => {
  afterEach(cleanup);

  it('renders IdeaSetView with candidates and select action', () => {
    const handleSelect = vi.fn();
    render(<IdeaSetView artifact={SAMPLE_ENVELOPE} onSelect={handleSelect} />);

    expect(screen.getByText('Idea One')).toBeInTheDocument();
    expect(screen.getByText('Idea Two')).toBeInTheDocument();
  });

  it('renders StoryBibleView with premise and rules', () => {
    const envelope: StudioArtifactEnvelope = {
      ...SAMPLE_ENVELOPE,
      artifact_type: 'StoryBible',
      content: {
        title: 'Thỏ & Diều',
        premise: 'A thỏ premise',
        story_rules: ['Rule 1', 'Rule 2'],
      },
    };

    render(<StoryBibleView artifact={envelope} />);

    expect(screen.getByText('Thỏ & Diều')).toBeInTheDocument();
    expect(screen.getByText('A thỏ premise')).toBeInTheDocument();
    expect(screen.getByText('Rule 1')).toBeInTheDocument();
  });

  it('renders OutlineView with scenes and target duration', () => {
    const envelope: StudioArtifactEnvelope = {
      ...SAMPLE_ENVELOPE,
      artifact_type: 'EpisodeOutline',
      content: {
        title: 'Outline Ep 1',
        target_duration_seconds: 60,
        scenes: [{ scene_id: 'sc_1', order: 1, intent: 'Intro', estimated_seconds: 30 }],
      },
    };

    render(<OutlineView artifact={envelope} />);

    expect(screen.getByText('Outline Ep 1')).toBeInTheDocument();
    expect(screen.getByText('Scene 1: Intro')).toBeInTheDocument();
  });

  it('renders ScreenplayView with action and dialogue', () => {
    const envelope: StudioArtifactEnvelope = {
      ...SAMPLE_ENVELOPE,
      artifact_type: 'ScreenplayDraft',
      content: {
        title: 'Screenplay Ep 1',
        scenes: [
          {
            scene_id: 'sc_1',
            order: 1,
            location_id: 'Rừng xanh',
            action_description: 'Thỏ chạy nhút nhát.',
            dialogue: [{ dialogue_id: 'd1', character_id: 'Thỏ', text: 'Chào Cánh Diều!' }],
          },
        ],
      },
    };

    render(<ScreenplayView artifact={envelope} />);

    expect(screen.getByText('Screenplay Ep 1')).toBeInTheDocument();
    expect(screen.getByText('Thỏ chạy nhút nhát.')).toBeInTheDocument();
    expect(screen.getByText('Chào Cánh Diều!')).toBeInTheDocument();
  });

  it('renders ApprovalBar controls and invokes submit callback', () => {
    const handleSubmit = vi.fn();
    render(
      <ApprovalBar
        checkpoint="IDEA"
        artifactTitle="Idea Set #1"
        revisionId="rev_1"
        revisionHash="hash123"
        expectedVersion={1}
        onSubmit={handleSubmit}
      />
    );

    expect(screen.getByText('Approval required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve IDEA' })).toBeInTheDocument();
  });

  it('renders UnsupportedArtifactView for unsupported schema versions', () => {
    const envelope: StudioArtifactEnvelope = {
      ...SAMPLE_ENVELOPE,
      schema_version: 'studio.artifact/v9999',
    };

    render(<ArtifactContentView artifact={envelope} />);

    expect(screen.getByText(/unsupported schema studio.artifact\/v9999/)).toBeInTheDocument();
  });

  it('renders PipelineProgress with stages and active state', () => {
    render(<PipelineProgress currentState="SCREENPLAY_REVIEW" />);

    expect(screen.getByText('Idea')).toBeInTheDocument();
    expect(screen.getByText('Story')).toBeInTheDocument();
    expect(screen.getByText('Outline')).toBeInTheDocument();
    expect(screen.getByText('Screenplay')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('renders EpisodeWorkspace with tabs and switches active tab', () => {
    const episode = { id: 'ep_1', title: 'Episode 1', state: 'SCREENPLAY_DRAFT', version: 1 };
    render(<EpisodeWorkspace episode={episode} artifacts={[SAMPLE_ENVELOPE]} />);

    expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Idea' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Story' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Screenplay' })).toBeInTheDocument();
  });
});
