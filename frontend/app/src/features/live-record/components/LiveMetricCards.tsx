import React from 'react';
import { Clock, AlertTriangle, Cpu, Monitor, HardDrive, Activity } from 'lucide-react';

export interface LiveMetricCardsProps {
  recordingTimeFormatted: string;
  isRecording: boolean;
  droppedFrames: number;
  droppedFramesPercent: string;
}

export const LiveMetricCards: React.FC<LiveMetricCardsProps> = ({
  recordingTimeFormatted,
  isRecording,
  droppedFrames,
  droppedFramesPercent,
}) => {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '16px',
        width: '100%',
      }}
    >
      {/* Card 1: Thời Gian Ghi */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <Clock size={15} color="#60a5fa" />
          <span>Thời Gian Ghi</span>
        </div>

        <div style={{ marginTop: '8px' }}>
          <div style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc', fontFamily: 'monospace' }}>
            {recordingTimeFormatted}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '4px', fontSize: '11px', color: isRecording ? '#4ade80' : '#94a3b8' }}>
            <span
              style={{
                display: 'inline-block',
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: isRecording ? '#22c55e' : '#64748b',
                boxShadow: isRecording ? '0 0 6px #22c55e' : 'none',
              }}
            />
            {isRecording ? 'Đang ghi' : 'Sẵn sàng'}
          </div>
        </div>
      </div>

      {/* Card 2: Frames Bị Rớt */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <AlertTriangle size={15} color="#fbbf24" />
          <span>Frames Bị Rớt</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '8px' }}>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>
              {droppedFrames}
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
              {droppedFramesPercent}%
            </div>
          </div>

          {/* Sparkline */}
          <svg width="60" height="24" viewBox="0 0 60 24" fill="none">
            <path
              d="M2 18 L 12 18 L 22 14 L 32 19 L 42 12 L 52 16 L 58 14"
              stroke="#fbbf24"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>

      {/* Card 3: CPU Usage */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <Cpu size={15} color="#60a5fa" />
          <span>CPU Usage</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '8px' }}>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>
              18%
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
              4.6 / 24 Cores
            </div>
          </div>

          {/* Sparkline */}
          <svg width="60" height="24" viewBox="0 0 60 24" fill="none">
            <path
              d="M2 16 L 14 12 L 26 18 L 38 8 L 50 14 L 58 10"
              stroke="#60a5fa"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>

      {/* Card 4: GPU Usage */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <Monitor size={15} color="#34d399" />
          <span>GPU Usage</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '8px' }}>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>
              32%
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
              NVIDIA RTX 3060
            </div>
          </div>

          {/* Sparkline */}
          <svg width="60" height="24" viewBox="0 0 60 24" fill="none">
            <path
              d="M2 20 L 15 14 L 28 17 L 40 6 L 52 12 L 58 8"
              stroke="#34d399"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>

      {/* Card 5: Dung Lượng Còn Lại */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <HardDrive size={15} color="#4ade80" />
          <span>Dung Lượng Còn Lại</span>
        </div>

        <div style={{ marginTop: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '20px', fontWeight: 800, color: '#f8fafc' }}>72%</span>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>842 GB / 1.16 TB</span>
          </div>

          {/* Progress Bar */}
          <div
            style={{
              width: '100%',
              height: '4px',
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              borderRadius: '2px',
              marginTop: '6px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: '72%',
                height: '100%',
                backgroundColor: '#22c55e',
                borderRadius: '2px',
              }}
            />
          </div>
        </div>
      </div>

      {/* Card 6: Stream Health */}
      <div
        style={{
          backgroundColor: '#0c1322',
          border: '1px solid rgba(59, 130, 246, 0.2)',
          borderRadius: '14px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: '100px',
          boxShadow: '0 4px 16px -4px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#94a3b8', fontSize: '12px' }}>
          <Activity size={15} color="#22c55e" />
          <span>Stream Health</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: '8px' }}>
          <div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: '#4ade80' }}>
              Tốt
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
              Ổn định
            </div>
          </div>

          {/* Sparkline */}
          <svg width="60" height="24" viewBox="0 0 60 24" fill="none">
            <path
              d="M2 18 L 12 16 L 24 19 L 36 10 L 48 8 L 58 12"
              stroke="#22c55e"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>
    </div>
  );
};
