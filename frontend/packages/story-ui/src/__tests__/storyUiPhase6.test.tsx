import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import { IdeaSetView, SelectedIdeaView, StoryTabContainer, CharacterCanonView, BeatsView } from '../index';

const SAMPLE_IDEA_ENVELOPE: StudioArtifactEnvelope = {
  artifact_id: 'art_idea_1',
  artifact_type: 'IdeaCandidateSet',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'idea123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    recommended_candidate_id: 'c1',
    scoring_rubric_version: 'v1.0.0',
    candidates: [
      {
        candidate_id: 'c1',
        title: 'Chú Thỏ Thông Minh',
        logline: 'Chú thỏ cứu cả khu rừng khỏi cơn bão.',
        premise: 'Khi cơn bão đến...',
        themes: ['Tình bạn', 'Dũng cảm'],
        score: 0.965,
        score_dimensions: { originality: 0.98, character_depth: 0.95 },
      },
    ],
  },
};

const SAMPLE_STORY_BIBLE: StudioArtifactEnvelope = {
  artifact_id: 'art_sb_1',
  artifact_type: 'StoryBible',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'sb123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    title: 'Hành Trình Rừng Xanh',
    premise: 'Cuộc phiêu lưu tìm lại nguồn nước.',
    theme: 'Đoàn kết là sức mạnh',
    tone: 'Tươi sáng, ấm áp',
    arc_summary: 'Thỏ vượt qua nỗi sợ bóng tối.',
    stakes: 'Khu rừng khô hạn nếu thất bại.',
    story_rules: ['Không nhân vật nào độc hành quá 2 ngày.'],
  },
};

const SAMPLE_CHARACTER_CANON: StudioArtifactEnvelope = {
  artifact_id: 'art_cc_1',
  artifact_type: 'CharacterCanon',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'cc123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    characters: [
      {
        character_id: 'char_tho',
        name: 'Thỏ Nhanh Nhẩu',
        role: 'PROTAGONIST',
        age_band: 'Trẻ em',
        appearance: 'Lông trắng, tai dài',
        goal: 'Tìm nguồn nước thần',
        voice: 'Hào hứng, nhanh',
        traits: ['Nhanh trí', 'Tốt bụng'],
        relationships: [{ from_id: 'char_tho', to_id: 'char_rua', kind: 'Bạn thân', description: 'Thỏ → Rùa (Bạn thân)' }],
      },
    ],
  },
};

const SAMPLE_BEATS: StudioArtifactEnvelope = {
  artifact_id: 'art_beat_1',
  artifact_type: 'BeatSheet',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'beat123hash',
  revision_id: 'rev_fixture',
  created_at: '2026-08-01T00:00:00Z',
  content: {
    beats: [
      {
        beat_id: 'b1',
        order: 1,
        role: 'Inciting Incident',
        description: 'Dòng suối ngừng chảy.',
        emotional_beat: 'Hoang mang → Dũng cảm',
        target_seconds: 45,
        character_ids: ['char_tho'],
      },
    ],
  },
};

describe('Phase UI6 — Idea & Story UX', () => {
  afterEach(cleanup);

  it('renders IdeaSetView with recommended badge, theme tags, and score breakdown', () => {
    const handleSelect = vi.fn();
    render(<IdeaSetView artifact={SAMPLE_IDEA_ENVELOPE} onSelect={handleSelect} />);

    expect(screen.getByText('Chú Thỏ Thông Minh')).toBeInTheDocument();
    expect(screen.getByText(/recommended/i)).toBeInTheDocument();
    expect(screen.getByText('Tình bạn')).toBeInTheDocument();
    expect(screen.getByText('Score Breakdown')).toBeInTheDocument();
    expect(screen.getByText('0.980')).toBeInTheDocument();

    const selectBtn = screen.getByRole('button', { name: 'Select this idea' });
    fireEvent.click(selectBtn);
    expect(handleSelect).toHaveBeenCalledWith('c1');
  });

  it('renders SelectedIdeaView with highlighted badge', () => {
    const envelope: StudioArtifactEnvelope = {
      ...SAMPLE_IDEA_ENVELOPE,
      artifact_type: 'SelectedIdea',
      content: {
        title: 'Chú Thỏ Thông Minh',
        summary: 'Ý tưởng đã chọn.',
        rationale: 'Điểm số cao nhất.',
      },
    };

    render(<SelectedIdeaView artifact={envelope} />);

    expect(screen.getByText('✓ Selected Idea')).toBeInTheDocument();
    expect(screen.getByText('Chú Thỏ Thông Minh')).toBeInTheDocument();
    expect(screen.getByText('Rationale: Điểm số cao nhất.')).toBeInTheDocument();
  });

  it('renders CharacterCanonView with role badge and relationships', () => {
    render(<CharacterCanonView artifact={SAMPLE_CHARACTER_CANON} />);

    expect(screen.getByText('Thỏ Nhanh Nhẩu')).toBeInTheDocument();
    expect(screen.getByText('PROTAGONIST')).toBeInTheDocument();
    expect(screen.getByText('Nhanh trí')).toBeInTheDocument();
    expect(screen.getByText('Thỏ → Rùa (Bạn thân)')).toBeInTheDocument();
  });

  it('renders BeatsView with beat index, duration, and emotional turn', () => {
    render(<BeatsView artifact={SAMPLE_BEATS} />);

    expect(screen.getByText('Beat #1')).toBeInTheDocument();
    expect(screen.getByText(/Inciting Incident/)).toBeInTheDocument();
    expect(screen.getByText('Dòng suối ngừng chảy.')).toBeInTheDocument();
    expect(screen.getAllByText(/0:45/).length).toBeGreaterThan(0);
  });

  it('renders StoryTabContainer sub-navigation and switches tabs', () => {
    const artifacts = [SAMPLE_STORY_BIBLE, SAMPLE_CHARACTER_CANON, SAMPLE_BEATS];
    render(<StoryTabContainer artifacts={artifacts} />);

    // Default sub-tab: Story Bible
    expect(screen.getByText('Hành Trình Rừng Xanh')).toBeInTheDocument();

    // Switch to Characters sub-tab
    const charBtn = screen.getByRole('button', { name: 'Characters' });
    fireEvent.click(charBtn);
    expect(screen.getByText('Thỏ Nhanh Nhẩu')).toBeInTheDocument();

    // Switch to Beat Sheet sub-tab
    const beatBtn = screen.getByRole('button', { name: 'Beat Sheet' });
    fireEvent.click(beatBtn);
    expect(screen.getByText('Beat #1')).toBeInTheDocument();
  });
});
