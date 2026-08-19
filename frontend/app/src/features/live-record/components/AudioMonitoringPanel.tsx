import React from 'react';
import { Volume2, VolumeX, Mic, MicOff, Settings } from 'lucide-react';
import type { AudioLevels } from '../hooks/useLiveRecord';

export interface AudioMonitoringPanelProps {
  audioLevels: AudioLevels;
  toggleMicMute: () => void;
  toggleSystemMute: () => void;
  toggleVoiceoverMute: () => void;
  onOpenSettings?: () => void;
}

export const AudioMonitoringPanel: React.FC<AudioMonitoringPanelProps> = ({
  audioLevels,
  toggleMicMute,
  toggleSystemMute,
  toggleVoiceoverMute,
  onOpenSettings,
}) => {
  // Helper to calculate segment active state
  // db range: -60 to 0
  const renderVUMeter = (db: number, isMuted: boolean) => {
    // 12 segments
    const segments = [
      { threshold: -2, color: '#ef4444' }, // Red (Peak/Clip)
      { threshold: -6, color: '#f59e0b' }, // Amber/Yellow
      { threshold: -12, color: '#eab308' },
      { threshold: -18, color: '#22c55e' }, // Green
      { threshold: -24, color: '#22c55e' },
      { threshold: -30, color: '#22c55e' },
      { threshold: -36, color: '#22c55e' },
      { threshold: -42, color: '#22c55e' },
      { threshold: -48, color: '#22c55e' },
      { threshold: -54, color: '#22c55e' },
      { threshold: -60, color: '#22c55e' },
    ];

    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '3px',
          width: '16px',
          height: '140px',
          backgroundColor: '#090d16',
          padding: '4px 3px',
          borderRadius: '4px',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        {segments.map((seg, i) => {
          const isActive = !isMuted && db >= seg.threshold;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                width: '100%',
                borderRadius: '1px',
                backgroundColor: isActive ? seg.color : 'rgba(255, 255, 255, 0.06)',
                boxShadow: isActive ? `0 0 6px ${seg.color}` : 'none',
                transition: 'background-color 0.1s ease',
              }}
            />
          );
        })}
      </div>
    );
  };

  return (
    <div
      style={{
        backgroundColor: '#0c1322',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        boxShadow: '0 8px 24px -6px rgba(0, 0, 0, 0.5)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '16px',
          paddingBottom: '10px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#f8fafc' }}>
          Giám Sát Âm Thanh
        </h3>
        <button
          onClick={onOpenSettings}
          style={{
            background: 'none',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            padding: '4px',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Settings size={15} />
        </button>
      </div>

      {/* 3 Channels Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '12px',
          flex: 1,
          alignItems: 'center',
        }}
      >
        {/* Channel 1: Mic */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
          <div style={{ textAlign: 'center' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block', whiteSpace: 'nowrap' }}>
              Mic (Shure MV7+)
            </span>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginTop: '2px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  color: audioLevels.isMicMuted ? '#ef4444' : '#4ade80',
                  fontFamily: 'monospace',
                }}
              >
                {audioLevels.isMicMuted ? 'MUTED' : `${audioLevels.mic} dBFS`}
              </span>
              <button
                onClick={toggleMicMute}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 0 }}
              >
                {audioLevels.isMicMuted ? <VolumeX size={12} color="#ef4444" /> : <Volume2 size={12} />}
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {renderVUMeter(audioLevels.mic, audioLevels.isMicMuted)}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                height: '140px',
                fontSize: '9px',
                color: '#64748b',
                fontFamily: 'monospace',
              }}
            >
              <span>0</span>
              <span>-12</span>
              <span>-24</span>
              <span>-36</span>
              <span>-48</span>
              <span>-60</span>
            </div>
          </div>
        </div>

        {/* Channel 2: System Audio */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
          <div style={{ textAlign: 'center' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block', whiteSpace: 'nowrap' }}>
              System Audio
            </span>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginTop: '2px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  color: audioLevels.isSystemMuted ? '#ef4444' : '#4ade80',
                  fontFamily: 'monospace',
                }}
              >
                {audioLevels.isSystemMuted ? 'MUTED' : `${audioLevels.system} dBFS`}
              </span>
              <button
                onClick={toggleSystemMute}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 0 }}
              >
                {audioLevels.isSystemMuted ? <VolumeX size={12} color="#ef4444" /> : <Volume2 size={12} />}
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {renderVUMeter(audioLevels.system, audioLevels.isSystemMuted)}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                height: '140px',
                fontSize: '9px',
                color: '#64748b',
                fontFamily: 'monospace',
              }}
            >
              <span>0</span>
              <span>-12</span>
              <span>-24</span>
              <span>-36</span>
              <span>-48</span>
              <span>-60</span>
            </div>
          </div>
        </div>

        {/* Channel 3: Voiceover */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
          <div style={{ textAlign: 'center' }}>
            <span style={{ fontSize: '11px', color: '#94a3b8', display: 'block', whiteSpace: 'nowrap' }}>
              Voiceover
            </span>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px', marginTop: '2px' }}>
              <span
                style={{
                  fontSize: '11px',
                  fontWeight: 700,
                  color: audioLevels.isVoiceoverMuted ? '#ef4444' : '#f59e0b',
                  fontFamily: 'monospace',
                }}
              >
                {audioLevels.isVoiceoverMuted ? 'MUTED' : `${audioLevels.voiceover} dBFS`}
              </span>
              <button
                onClick={toggleVoiceoverMute}
                style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 0 }}
              >
                {audioLevels.isVoiceoverMuted ? <MicOff size={12} color="#ef4444" /> : <Mic size={12} />}
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {renderVUMeter(audioLevels.voiceover, audioLevels.isVoiceoverMuted)}
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                height: '140px',
                fontSize: '9px',
                color: '#64748b',
                fontFamily: 'monospace',
              }}
            >
              <span>0</span>
              <span>-12</span>
              <span>-24</span>
              <span>-36</span>
              <span>-48</span>
              <span>-60</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
