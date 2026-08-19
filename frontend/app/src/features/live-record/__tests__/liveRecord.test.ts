import { describe, it, expect } from 'vitest';
import {
  LiveRecordPage,
  useLiveRecord,
  formatDuration,
  LiveVideoPreview,
  RecordingStatusPanel,
  DeviceSettingsPanel,
  AudioMonitoringPanel,
  SceneListPanel,
  TeleprompterPanel,
  RecentRecordingsPanel,
  LiveMetricCards,
  SettingsModal,
  AddSceneModal,
  PlaybackModal,
} from '../index';

describe('LiveRecord Feature Components & Hooks', () => {
  it('exports all live-record components properly', () => {
    expect(LiveRecordPage).toBeDefined();
    expect(LiveVideoPreview).toBeDefined();
    expect(RecordingStatusPanel).toBeDefined();
    expect(DeviceSettingsPanel).toBeDefined();
    expect(AudioMonitoringPanel).toBeDefined();
    expect(SceneListPanel).toBeDefined();
    expect(TeleprompterPanel).toBeDefined();
    expect(RecentRecordingsPanel).toBeDefined();
    expect(LiveMetricCards).toBeDefined();
    expect(SettingsModal).toBeDefined();
    expect(AddSceneModal).toBeDefined();
    expect(PlaybackModal).toBeDefined();
  });

  it('exports useLiveRecord hook', () => {
    expect(useLiveRecord).toBeDefined();
  });

  it('formats durations accurately into hh:mm:ss', () => {
    expect(formatDuration(0)).toBe('00:00:00');
    expect(formatDuration(120)).toBe('00:02:00');
    expect(formatDuration(768)).toBe('00:12:48');
    expect(formatDuration(3665)).toBe('01:01:05');
  });
});
