import React from 'react';
import { Clock, Film, AlertTriangle, HardDrive, Zap } from 'lucide-react';

export interface RecordingStatusPanelProps {
  isRecording: boolean;
  recordingTimeFormatted: string;
  recordedFrames: number;
  droppedFrames: number;
  droppedFramesPercent: string;
  storageUsedGB: number;
  currentBitrate: number;
}

export const RecordingStatusPanel: React.FC<RecordingStatusPanelProps> = ({
  isRecording,
  recordingTimeFormatted,
  recordedFrames,
  droppedFrames,
  droppedFramesPercent,
  storageUsedGB,
  currentBitrate,
}) => {
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
            {storageUsedGB.toFixed(2)} GB
          </span>
        </div>

        {/* Tốc độ ghi hiện tại */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '13px' }}>
            <Zap size={16} color="#34d399" />
            <span>Tốc độ ghi hiện tại</span>
          </div>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#f8fafc', fontFamily: 'monospace' }}>
            {currentBitrate} Mbps
          </span>
        </div>
      </div>
    </div>
  );
};
