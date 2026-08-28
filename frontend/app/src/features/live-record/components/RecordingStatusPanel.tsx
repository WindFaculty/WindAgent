import React from 'react';
import { Clock, Film, AlertTriangle, HardDrive, Zap, Gauge } from 'lucide-react';

export interface RecordingStatusPanelProps {
  isRecording: boolean;
  recordingTimeFormatted: string;
  recordedFrames: number;
  droppedFrames: number;
  droppedFramesPercent: string;
  /** §18: null ⇒ the engine hasn't measured it — render "—", never a guess. */
  storageUsedGB: number | null;
  currentBitrate: number | null;
  /** §17 real engine telemetry — undefined on the legacy mock path. */
  captureFps?: number;
  encodeFps?: number;
  avSyncErrorMs?: number;
  /** §18 resource stage: normal | preview_degraded | director_degraded | danger. */
  resourceStage?: string;
}

export const RecordingStatusPanel: React.FC<RecordingStatusPanelProps> = ({
  isRecording,
  recordingTimeFormatted,
  recordedFrames,
  droppedFrames,
  droppedFramesPercent,
  storageUsedGB,
  currentBitrate,
  captureFps,
  encodeFps,
  avSyncErrorMs,
  resourceStage,
}) => {
  const stageColor =
    resourceStage === 'danger' ? '#ef4444'
    : resourceStage === 'director_degraded' ? '#f59e0b'
    : resourceStage === 'preview_degraded' ? '#eab308'
    : '#22c55e';
  return (
    <div
      style={{
        backgroundColor: '#0c1322',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderRadius: '16px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
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
          paddingBottom: '12px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: '15px',
            fontWeight: 700,
            color: '#f8fafc',
            letterSpacing: '0.2px',
          }}
        >
          Trạng Thái Ghi Hình
        </h3>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '12px',
            fontWeight: 600,
            color: isRecording ? '#4ade80' : '#94a3b8',
          }}
        >
          <span
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: isRecording ? '#22c55e' : '#64748b',
              boxShadow: isRecording ? '0 0 8px #22c55e' : 'none',
            }}
          />
          {isRecording ? 'Đang ghi' : 'Sẵn sàng'}
        </div>
      </div>

      {/* Metrics List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: 1, justifyContent: 'center' }}>
        {/* Thời gian ghi */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <Clock size={16} color="#60a5fa" />
            <span>Thời gian ghi</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
            {recordingTimeFormatted}
          </span>
        </div>

        {/* Frames đã ghi */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <Film size={16} color="#38bdf8" />
            <span>Frames đã ghi</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
            {recordedFrames.toLocaleString('en-US')}
          </span>
        </div>

        {/* Frames bị rớt */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <AlertTriangle size={16} color="#fbbf24" />
            <span>Frames bị rớt</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#facc15', fontFamily: 'monospace' }}>
            {droppedFrames} ({droppedFramesPercent}%)
          </span>
        </div>

        {/* Dung lượng đã dùng */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <HardDrive size={16} color="#a78bfa" />
            <span>Dung lượng đã dùng</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
            {storageUsedGB !== null ? `${storageUsedGB.toFixed(2)} GB` : '—'}
          </span>
        </div>

        {/* Tốc độ ghi hiện tại */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <Zap size={16} color="#34d399" />
            <span>Tốc độ ghi hiện tại</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
            {currentBitrate !== null ? `${currentBitrate.toFixed(1)} Mbps` : '—'}
          </span>
        </div>

        {/* §17 engine telemetry — only rendered when the native engine reports it */}
        {(captureFps !== undefined || encodeFps !== undefined) && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
              <Gauge size={16} color="#38bdf8" />
              <span>Capture / Encode FPS</span>
            </div>
            <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
              {captureFps !== undefined ? captureFps.toFixed(1) : '—'} / {encodeFps !== undefined ? encodeFps.toFixed(1) : '—'}
            </span>
          </div>
        )}
        {avSyncErrorMs !== undefined && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
              <Clock size={16} color="#f472b6" />
              <span>A/V sync</span>
            </div>
            <span
              style={{
                fontSize: '14px',
                fontWeight: 700,
                color: Math.abs(avSyncErrorMs) > 40 ? '#facc15' : '#f8fafc',
                fontFamily: 'monospace',
              }}
            >
              {avSyncErrorMs >= 0 ? '+' : ''}{avSyncErrorMs.toFixed(1)} ms
            </span>
          </div>
        )}
        {resourceStage !== undefined && resourceStage !== 'normal' && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
              <AlertTriangle size={16} color={stageColor} />
              <span>Resource stage</span>
            </div>
            <span style={{ fontSize: '13px', fontWeight: 700, color: stageColor, fontFamily: 'monospace' }}>
              {resourceStage}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
