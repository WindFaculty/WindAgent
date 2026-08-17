import { describe, it, expect } from 'vitest';
import { EpisodesPage } from '../pages/EpisodesPage';
import { EpisodeWorkspacePage } from '../pages/EpisodeWorkspacePage';
import { EpisodeCard } from '../components/EpisodeCard';
import { EpisodePipeline } from '../workspace/EpisodePipeline';
import { IdeaPanel } from '../workspace/IdeaPanel';
import { StoryBiblePanel } from '../workspace/StoryBiblePanel';
import { OutlinePanel } from '../workspace/OutlinePanel';
import { ScreenplayPanel } from '../workspace/ScreenplayPanel';
import { CheckpointReviewPanel } from '../workspace/CheckpointReviewPanel';
import { useEpisodes, EPISODES_QUERY_KEY } from '../hooks/useEpisodes';
import { useEpisode, EPISODE_DETAIL_QUERY_KEY } from '../hooks/useEpisode';
import { useEpisodeArtifacts, EPISODE_ARTIFACTS_QUERY_KEY, EPISODE_RUNS_QUERY_KEY } from '../hooks/useEpisodeArtifacts';
import { useEpisodeCommands } from '../hooks/useEpisodeCommands';
import { useEpisodeRealtime } from '../hooks/useEpisodeRealtime';
import { getStageProgress, CHECKPOINT_STEPS } from '../model/types';

describe('Episodes Feature Package (Phase 8)', () => {
  it('exports all episode components and workspace hooks properly', () => {
    expect(EpisodesPage).toBeDefined();
    expect(EpisodeWorkspacePage).toBeDefined();
    expect(EpisodeCard).toBeDefined();
    expect(EpisodePipeline).toBeDefined();
    expect(IdeaPanel).toBeDefined();
    expect(StoryBiblePanel).toBeDefined();
    expect(OutlinePanel).toBeDefined();
    expect(ScreenplayPanel).toBeDefined();
    expect(CheckpointReviewPanel).toBeDefined();
    expect(useEpisodes).toBeDefined();
    expect(useEpisode).toBeDefined();
    expect(useEpisodeArtifacts).toBeDefined();
    expect(useEpisodeCommands).toBeDefined();
    expect(useEpisodeRealtime).toBeDefined();
  });

  it('derives progress deterministically across pipeline stages', () => {
    expect(getStageProgress('DRAFT')).toBe(5);
    expect(getStageProgress('IDEA')).toBe(15);
    expect(getStageProgress('STORY_BIBLE')).toBe(30);
    expect(getStageProgress('OUTLINE')).toBe(50);
    expect(getStageProgress('SCREENPLAY')).toBe(70);
    expect(getStageProgress('REVIEW')).toBe(85);
    expect(getStageProgress('LOCKED')).toBe(100);
    expect(getStageProgress('READY_FOR_PRODUCTION')).toBe(100);
  });

  it('defines 6 canonical checkpoint steps in order', () => {
    expect(CHECKPOINT_STEPS.length).toBe(6);
    expect(CHECKPOINT_STEPS.map((s) => s.id)).toEqual([
      'IDEA',
      'STORY_BIBLE',
      'OUTLINE',
      'SCREENPLAY',
      'REVIEW',
      'LOCKED',
    ]);
  });

  it('defines canonical query keys', () => {
    expect(EPISODES_QUERY_KEY).toEqual(['v3', 'episodes']);
    expect(EPISODE_DETAIL_QUERY_KEY('ep-1')).toEqual(['v3', 'episodes', 'ep-1']);
    expect(EPISODE_ARTIFACTS_QUERY_KEY('ep-1')).toEqual(['v3', 'episodes', 'ep-1', 'artifacts']);
    expect(EPISODE_RUNS_QUERY_KEY('ep-1')).toEqual(['v3', 'episodes', 'ep-1', 'runs']);
  });
});
