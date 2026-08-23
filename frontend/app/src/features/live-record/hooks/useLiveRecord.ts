/**
 * useLiveRecord — Recording UI store (P0)
 * Gate: LIVE_RECORD_P0_ARCHITECTURE_FROZEN
 *
 * This hook is intentionally UI-only. Domain lives in `../domain/` and contracts in
 * `../contracts/`. Do NOT inline LiveExecutionPlan / state machine / director logic here.
 * Future phases replace mock clock/bitrate/telemetry with `contracts/ipc.ts` polling
 * and `domain/stateMachine.ts` transitions.
 */
import { useState, useEffect, useCallback } from 'react';
import type { SceneItem as DomainSceneItem, RecentRecording as DomainRecentRecording } from '../domain/types';

// Re-export domain projections for component compat (canonical types live in domain/types.ts)
export type SceneItem = DomainSceneItem;
export type RecentRecording = DomainRecentRecording;

export interface AudioLevels {
  mic: number;
  system: number;
  voiceover: number;
  isMicMuted: boolean;
  isSystemMuted: boolean;
  isVoiceoverMuted: boolean;
}

const DEFAULT_SCENES: SceneItem[] = [
  {
    id: 'scene-1',
    index: 1,
    title: 'Mở đầu & Giới thiệu chủ đề',
    duration: '00:02:00',
    durationSec: 120,
    status: 'completed',
    script: 'Xin chào mọi người và chào mừng đến với WindAgent Studio – nền tảng điều phối AI Agents mạnh mẽ dành cho nhà sáng tạo nội dung và doanh nghiệp.',
  },
  {
    id: 'scene-2',
    index: 2,
    title: 'Demo tính năng WindAgent Studio',
    duration: '00:05:00',
    durationSec: 300,
    status: 'active',
    script: `Xin chào mọi người và chào mừng đến với WindAgent Studio – nền tảng điều phối AI Agents mạnh mẽ dành cho nhà sáng tạo nội dung và doanh nghiệp.

Trong video hôm nay, chúng ta sẽ cùng khám phá những tính năng nổi bật giúp bạn xây dựng, quản lý và tự động hóa quy trình làm việc hiệu quả hơn bao giờ hết.

Bắt đầu thôi nào!`,
  },
  {
    id: 'scene-3',
    index: 3,
    title: 'Case Study & Ứng dụng thực tế',
    duration: '00:04:00',
    durationSec: 240,
    status: 'pending',
    script: 'Trong phần này, chúng ta sẽ cùng điểm qua các case study thực tế từ các studio và agency đang áp dụng WindAgent để tăng tốc độ sản xuất video lên gấp 10 lần.',
  },
  {
    id: 'scene-4',
    index: 4,
    title: 'Hỏi đáp & Thảo luận',
    duration: '00:03:00',
    durationSec: 180,
    status: 'pending',
    script: 'Hãy cùng giải đáp những thắc mắc phổ biến nhất của cộng đồng về cách tích hợp mô hình AI cục bộ và an toàn dữ liệu.',
  },
  {
    id: 'scene-5',
    index: 5,
    title: 'Kết luận & Call to Action',
    duration: '00:01:30',
    durationSec: 90,
    status: 'pending',
    script: 'Cảm ơn các bạn đã theo dõi! Hãy nhớ nhấn Like, Subscribe và truy cập windagent.dev để trải nghiệm ngay hôm nay. Hẹn gặp lại trong video tiếp theo!',
  },
];

const DEFAULT_RECORDINGS: RecentRecording[] = [
  {
    id: 'rec-001',
    title: 'WindAgent_Demo_Part1',
    resolution: '1080p',
    fps: 60,
    format: 'MP4',
    date: '16/05/2025',
    time: '10:24 AM',
    size: '2.46 GB',
    duration: '12:34',
  },
  {
    id: 'rec-002',
    title: 'WindAgent_Demo_Part2',
    resolution: '1080p',
    fps: 60,
    format: 'MP4',
    date: '16/05/2025',
    time: '10:45 AM',
    size: '2.18 GB',
    duration: '08:47',
  },
  {
    id: 'rec-003',
    title: 'Q&A_Session_Take1',
    resolution: '1080p',
    fps: 60,
    format: 'MP4',
    date: '16/05/2025',
    time: '11:32 AM',
    size: '1.35 GB',
    duration: '06:21',
  },
];

export function formatDuration(totalSeconds: number): string {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [
    hours.toString().padStart(2, '0'),
    minutes.toString().padStart(2, '0'),
    seconds.toString().padStart(2, '0'),
  ].join(':');
}

export function useLiveRecord() {
  // Recording controls & clock
  const [isRecording, setIsRecording] = useState<boolean>(true);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [recordSeconds, setRecordSeconds] = useState<number>(768); // 00:12:48 initial
  const [recordedFrames, setRecordedFrames] = useState<number>(45942);
  const [droppedFrames, setDroppedFrames] = useState<number>(12);
  const [storageUsedGB, setStorageUsedGB] = useState<number>(5.68);
  const [currentBitrate, setCurrentBitrate] = useState<number>(42.5);

  // Hardware & Config Settings
  const [cameraSource, setCameraSource] = useState<string>('Sony A7 IV (USB)');
  const [micSource, setMicSource] = useState<string>('Shure MV7+ (USB)');
  const [resolution, setResolution] = useState<string>('1920 x 1080 (Full HD)');
  const [fps, setFps] = useState<number>(60);
  const [bitrate, setBitrate] = useState<string>('20 Mbps');
  const [format, setFormat] = useState<string>('MP4 (H.264)');
  const [savePath, setSavePath] = useState<string>('D:\\WindAgent\\Recordings');
  const [autoSplit, setAutoSplit] = useState<boolean>(true);
  const [deviceConnected, setDeviceConnected] = useState<boolean>(true);
  const [deviceTemp, setDeviceTemp] = useState<number>(42);

  // Audio Monitoring
  const [audioLevels, setAudioLevels] = useState<AudioLevels>({
    mic: -10,
    system: -18,
    voiceover: -6,
    isMicMuted: false,
    isSystemMuted: false,
    isVoiceoverMuted: false,
  });

  // Scenes
  const [scenes, setScenes] = useState<SceneItem[]>(DEFAULT_SCENES);
  const [activeSceneIndex, setActiveSceneIndex] = useState<number>(1);

  // Teleprompter
  const [teleprompterFontSize, setTeleprompterFontSize] = useState<number>(18);
  const [isAutoScroll, setIsAutoScroll] = useState<boolean>(true);
  const [scrollSpeed, setScrollSpeed] = useState<number>(1.2);
  const [teleprompterText, setTeleprompterText] = useState<string>(
    DEFAULT_SCENES[1].script || ''
  );

  // Recent Recordings
  const [recordings, setRecordings] = useState<RecentRecording[]>(DEFAULT_RECORDINGS);

  // Modals & Dialogs
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const [isAddSceneOpen, setIsAddSceneOpen] = useState<boolean>(false);
  const [selectedPlayback, setSelectedPlayback] = useState<RecentRecording | null>(null);

  // Timer Tick
  useEffect(() => {
    if (!isRecording || isPaused) return;

    const interval = setInterval(() => {
      setRecordSeconds((prev) => prev + 1);
      setRecordedFrames((prev) => prev + fps);
      setStorageUsedGB((prev) => +(prev + 0.0028).toFixed(2));
      setCurrentBitrate(42.5);
    }, 1000);

    return () => clearInterval(interval);
  }, [isRecording, isPaused, fps]);

  // Audio Visualizer level updater
  useEffect(() => {
    if (!isRecording && !deviceConnected) return;

    const interval = setInterval(() => {
      setAudioLevels((prev) => ({
        ...prev,
        mic: prev.isMicMuted ? -60 : -12,
        system: prev.isSystemMuted ? -60 : -18,
        voiceover: prev.isVoiceoverMuted ? -60 : -8,
      }));
    }, 250);

    return () => clearInterval(interval);
  }, [isRecording, deviceConnected]);

  // Actions
  const handleStartRecording = useCallback(() => {
    if (!isRecording) {
      setIsRecording(true);
      setIsPaused(false);
    } else {
      setIsRecording(false);
    }
  }, [isRecording]);

  const handlePauseRecording = useCallback(() => {
    if (isRecording) {
      setIsPaused((prev) => !prev);
    }
  }, [isRecording]);

  const handleStopRecording = useCallback(() => {
    if (isRecording || recordSeconds > 0) {
      const newRec: RecentRecording = {
        id: `rec-${Date.now()}`,
        title: `WindAgent_Take_${recordings.length + 1}`,
        resolution: resolution.includes('4K') ? '4K UHD' : '1080p',
        fps,
        format: format.split(' ')[0],
        date: new Date().toLocaleDateString('vi-VN'),
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
        size: `${storageUsedGB.toFixed(2)} GB`,
        duration: formatDuration(recordSeconds).substring(3), // mm:ss
      };

      setRecordings((prev) => [newRec, ...prev]);
      setIsRecording(false);
      setIsPaused(false);
      setRecordSeconds(0);
      setRecordedFrames(0);
      setStorageUsedGB(0);
    }
  }, [isRecording, recordSeconds, recordings.length, resolution, fps, format, storageUsedGB]);

  const handleSelectScene = useCallback((index: number) => {
    setActiveSceneIndex(index);
    setScenes((prev) =>
      prev.map((s, i) => ({
        ...s,
        status: i < index ? 'completed' : i === index ? 'active' : 'pending',
      }))
    );
    if (scenes[index]?.script) {
      setTeleprompterText(scenes[index].script || '');
    }
  }, [scenes]);

  const handleAddScene = useCallback((title: string, duration: string, script?: string) => {
    const parts = duration.split(':').map(Number);
    const sec = parts.length === 3 ? parts[0] * 3600 + parts[1] * 60 + parts[2] : 120;

    const newScene: SceneItem = {
      id: `scene-${Date.now()}`,
      index: scenes.length + 1,
      title,
      duration,
      durationSec: sec,
      status: 'pending',
      script: script || title,
    };
    setScenes((prev) => [...prev, newScene]);
    setIsAddSceneOpen(false);
  }, [scenes.length]);

  const toggleMicMute = useCallback(() => {
    setAudioLevels((prev) => ({ ...prev, isMicMuted: !prev.isMicMuted }));
  }, []);

  const toggleSystemMute = useCallback(() => {
    setAudioLevels((prev) => ({ ...prev, isSystemMuted: !prev.isSystemMuted }));
  }, []);

  const toggleVoiceoverMute = useCallback(() => {
    setAudioLevels((prev) => ({ ...prev, isVoiceoverMuted: !prev.isVoiceoverMuted }));
  }, []);

  const totalExpectedDurationSec = scenes.reduce((acc, s) => acc + s.durationSec, 0);
  const totalExpectedDurationFormatted = formatDuration(totalExpectedDurationSec);

  return {
    // State
    isRecording,
    isPaused,
    recordSeconds,
    recordingTimeFormatted: formatDuration(recordSeconds),
    recordedFrames,
    droppedFrames,
    setDroppedFrames,
    droppedFramesPercent: recordedFrames > 0 ? ((droppedFrames / recordedFrames) * 100).toFixed(2) : '0.00',
    storageUsedGB,
    currentBitrate,
    cameraSource,
    setCameraSource,
    micSource,
    setMicSource,
    resolution,
    setResolution,
    fps,
    setFps,
    bitrate,
    setBitrate,
    format,
    setFormat,
    savePath,
    setSavePath,
    autoSplit,
    setAutoSplit,
    deviceConnected,
    setDeviceConnected,
    deviceTemp,
    setDeviceTemp,
    audioLevels,
    scenes,
    activeSceneIndex,
    totalExpectedDurationFormatted,
    teleprompterFontSize,
    setTeleprompterFontSize,
    isAutoScroll,
    setIsAutoScroll,
    scrollSpeed,
    setScrollSpeed,
    teleprompterText,
    setTeleprompterText,
    recordings,
    isSettingsOpen,
    setIsSettingsOpen,
    isAddSceneOpen,
    setIsAddSceneOpen,
    selectedPlayback,
    setSelectedPlayback,
    // Handlers
    handleStartRecording,
    handlePauseRecording,
    handleStopRecording,
    handleSelectScene,
    handleAddScene,
    toggleMicMute,
    toggleSystemMute,
    toggleVoiceoverMute,
  };
}
