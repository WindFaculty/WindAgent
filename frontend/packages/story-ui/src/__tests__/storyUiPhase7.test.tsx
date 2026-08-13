import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import type { StudioArtifactEnvelope } from '@windagent/studio-contracts';
import { OutlineView, ScreenplayView } from '../index';

const SAMPLE_OUTLINE: StudioArtifactEnvelope = {
  artifact_id: 'art_out_1',
  artifact_type: 'EpisodeOutline',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'outline123hash',
  content: {
    title: 'Đường Đến Ngôi Làng',
    target_duration_seconds: 120,
    tolerance_seconds: 15,
    audience_band: 'KIDS_6_9',
    language: 'vi',
    scenes: [
      {
        scene_id: 'sc_1',
        order: 1,
        intent: 'Khởi đầu chuyến đi',
        location_id: 'EXT. RỪNG XANH - NGÀY',
        estimated_seconds: 60,
        dialogue_budget_seconds: 30,
        visual_action: 'Thỏ khoác ba lô bước vào rừng.',
        conflict_change: 'Gặp dòng suối lớn cản lối.',
        beat_refs: ['beat_1'],
        character_ids: ['char_tho', 'char_rua'],
      },
    ],
  },
};

const SAMPLE_SCREENPLAY: StudioArtifactEnvelope = {
  artifact_id: 'art_sp_1',
  artifact_type: 'ScreenplayDraft',
  schema_version: 'studio.artifact/v1alpha1',
  series_id: 'srs_1',
  episode_id: 'ep_1',
  content_hash: 'sp123hash',
  content: {
    title: 'Kịch Bản Tập 1',
    target_duration_seconds: 120,
    audience_band: 'KIDS_6_9',
    language: 'vi',
    scenes: [
      {
        scene_id: 'sc_1',
        order: 1,
        outline_scene_id: 'out_sc_1',
        location_id: 'EXT. BỜ SÔNG - NGÀY',
        estimated_seconds: 60,
        action_description: 'Nước sông chảy cuồn cuộn. Thỏ đứng ngập ngừng.',
        narration: 'Một buổi sáng nắng đẹp...',
        transition: 'CUT TO:',
        character_ids: ['char_tho'],
        source_beat_ids: ['beat_1'],
        dialogue: [
          {
            dialogue_id: 'd1',
            character_id: 'THỎ',
            delivery: 'lo lắng',
            text: 'Nước sâu thế này làm sao qua được?',
            estimated_seconds: 5,
          },
        ],
      },
      {
        scene_id: 'sc_2',
        order: 2,
        outline_scene_id: 'out_sc_2',
        location_id: 'EXT. CÂY CẦU GỖ - NGÀY',
        estimated_seconds: 60,
        action_description: 'Rùa xuất hiện từ lùm cây.',
        dialogue: [
          {
            dialogue_id: 'd2',
            character_id: 'RÙA',
            delivery: 'bình tĩnh',
            text: 'Đừng lo, có cây cầu gỗ đằng kia!',
            estimated_seconds: 5,
          },
        ],
      },
    ],
  },
};

describe('Phase UI7 — Outline & Screenplay UX', () => {
  afterEach(cleanup);

  it('renders OutlineView with scene cards, total duration, and character metrics', () => {
    render(<OutlineView artifact={SAMPLE_OUTLINE} />);

    expect(screen.getByText('Đường Đến Ngôi Làng')).toBeInTheDocument();
    expect(screen.getByText('1 Scenes')).toBeInTheDocument();
    expect(screen.getByText(/Khởi đầu chuyến đi/)).toBeInTheDocument();
    expect(screen.getByText(/Thỏ khoác ba lô bước vào rừng./)).toBeInTheDocument();
    expect(screen.getByText(/Gặp dòng suối lớn cản lối./)).toBeInTheDocument();
    expect(screen.getByText(/Scene total: 1:00/)).toBeInTheDocument();
  });

  it('renders ScreenplayView 3-pane reader with scene list, formatted screenplay, and inspector', () => {
    render(<ScreenplayView artifact={SAMPLE_SCREENPLAY} />);

    // Title
    expect(screen.getByText('Kịch Bản Tập 1')).toBeInTheDocument();

    // Left Rail: Scene list
    const sceneNav = screen.getByRole('navigation', { name: 'Scene navigation' });
    expect(sceneNav).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Scene 1/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Scene 2/ })).toBeInTheDocument();

    // Center Pane: Formatted Screenplay Document
    expect(screen.getAllByText(/EXT. BỜ SÔNG - NGÀY/).length).toBeGreaterThan(0);
    expect(screen.getByText('THỎ')).toBeInTheDocument();
    expect(screen.getByText('(lo lắng)')).toBeInTheDocument();
    expect(screen.getByText('Nước sâu thế me này làm sao qua được?'.replace('me ', ''))).toBeInTheDocument();
    expect(screen.getByText('CUT TO:')).toBeInTheDocument();

    // Right Inspector Panel
    const inspector = screen.getByRole('region', { name: 'Screenplay inspector' });
    expect(inspector).toBeInTheDocument();
    expect(screen.getByText('Total Duration')).toBeInTheDocument();
    expect(screen.getAllByText(/sp123hash/).length).toBeGreaterThan(0);
  });

  it('switches active scene when clicking scene button in Left Rail', () => {
    render(<ScreenplayView artifact={SAMPLE_SCREENPLAY} />);

    const scene2Btn = screen.getByRole('button', { name: /Scene 2/ });
    fireEvent.click(scene2Btn);

    // Inspector updates active scene to Scene 2
    expect(screen.getByText('Active Scene #2')).toBeInTheDocument();
    expect(screen.getByText('EXT. CÂY CẦU GỖ - NGÀY')).toBeInTheDocument();
  });

  it('displays READ ONLY banner when isLocked is true', () => {
    render(<ScreenplayView artifact={SAMPLE_SCREENPLAY} isLocked={true} />);

    expect(screen.getByText(/READ ONLY — Screenplay is locked for production/)).toBeInTheDocument();
  });
});
