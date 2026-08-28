import React from 'react';
import { Clock, AlertTriangle, Activity, Monitor, HardDrive, Gauge } from 'lucide-react';
import type { LiveRecordingMetrics } from '../hooks/useLiveRecordingController';

export interface LiveMetricCardsProps {
  recordingTimeFormatted: string;
  isRecording: boolean;
  droppedFrames: number;
  droppedFramesPercent: string;
  /** §18 engine metrics — null ⇒ render an honest "—", never a hardcoded number. */
  metrics: LiveRecordingMetrics;
}

const NOT_MEASURED = '—';

/** §18 resource stage → human label. Unknown stage ⇒ unknown label. */
function streamHealthLabel(stage: string | null): { text: string; color: string } {
  switch (stage) {
    case 'normal':
      return { text: 'Tốt', color: '#4ade80' };
    case 'preview_degraded':
      return { text: 'Preview hạ cấp', color: '#fbbf24' };
    case 'director_degraded':
      return { text: 'Director suy giảm', color: '#fbbf24' };
    case 'danger':
      return { text: 'Nguy hiểm', color: '#f87171' };
    default:
      return { text: NOT_MEASURED, color: '#94a3b8' };
  }
}

function formatDiskFree(gb: number | null): string {
  if (gb === null || Number.isNaN(gb)) return NOT_MEASURED;
  return gb >= 1024 ? `${(gb / 1024).toFixed(2)} TB` : `${gb.toFixed(0)} GB`;
}

/** One metric tile — value or the honest em-dash when the engine hasn't measured it. */
const MetricCard: React.FC<{
  icon: React.ReactNode;
  title: string;
  value: string;
  valueColor?: string;
  sub: React.ReactNode;
}> = ({ icon, title, value, valueColor = '#f8fafc', sub }) => (
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
      {icon}
      <span>{title}</span>
    </div>
    <div style={{ marginTop: '8px' }}>
      <div style={{ fontSize: '20px', fontWeight: 800, color: valueColor, fontFamily: 'monospace' }}>
        {value}
      </div>
      <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>{sub}</div>
    </div>
  </div>
);

export const LiveMetricCards: React.FC<LiveMetricCardsProps> = ({
  recordingTimeFormatted,
  isRecording,
  droppedFrames,
  droppedFramesPercent,
  metrics,
}) => {
  const health = streamHealthLabel(metrics.resourceStage);
  const captureFpsText =
    metrics.captureFps !== null && metrics.captureFps > 0 ? metrics.captureFps.toFixed(1) : NOT_MEASURED;
  const encodeFpsText =
    metrics.encodeFps !== null && metrics.encodeFps > 0 ? `${metrics.encodeFps.toFixed(1)} fps encode` : 'chưa đo được';

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '16px',
        width: '100%',
      }}
    >
      {/* Card 1: Thời Gian Ghi — engine clock (§4 QPC authority) */}
      <MetricCard
        icon={<Clock size={15} color="#60a5fa" />}
        title="Thời Gian Ghi"
        value={recordingTimeFormatted}
        sub={
          isRecording ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#4ade80' }}>
              <span
                style={{
                  display: 'inline-block',
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: '#22c55e',
                  boxShadow: '0 0 6px #22c55e',
                }}
              />
              Đang ghi
            </span>
          ) : (
            'Sẵn sàng'
          )
        }
      />

      {/* Card 2: Frames Bị Rớt — engine counter, not a mock increment */}
      <MetricCard
        icon={<AlertTriangle size={15} color="#fbbf24" />}
        title="Frames Bị Rớt"
        value={String(droppedFrames)}
        sub={`${droppedFramesPercent}%`}
      />

      {/* Card 3: Capture FPS — real §21 telemetry (null ⇒ "—") */}
      <MetricCard
        icon={<Gauge size={15} color="#60a5fa" />}
        title="Capture FPS"
        value={captureFpsText}
        sub={encodeFpsText}
      />

      {/* Card 4: GPU / NVENC — probed adapter name + live NVENC status */}
      <MetricCard
        icon={<Monitor size={15} color="#34d399" />}
        title="GPU · NVENC"
        value={
          metrics.nvencStatus === 'ENCODING'
            ? 'ENCODING'
            : metrics.nvencStatus === 'IDLE'
              ? 'IDLE'
              : metrics.nvencStatus === 'ERROR'
                ? 'LỖI'
                : metrics.nvencStatus === 'UNAVAILABLE'
                  ? 'KHÔNG CÓ'
                  : NOT_MEASURED
        }
        valueColor={
          metrics.nvencStatus === 'ENCODING'
            ? '#34d399'
            : metrics.nvencStatus === 'ERROR' || metrics.nvencStatus === 'UNAVAILABLE'
              ? '#f87171'
              : '#f8fafc'
        }
        sub={metrics.gpuAdapterName ?? 'adapter chưa dò được'}
      />

      {/* Card 5: Dung lượng trống — REAL free space from the capability probe */}
      <MetricCard
        icon={<HardDrive size={15} color="#4ade80" />}
        title="Dung Lượng Trống"
        value={formatDiskFree(metrics.diskFreeGb)}
        sub={metrics.diskWriteMbps !== null ? `ghi ${metrics.diskWriteMbps.toFixed(1)} MB/s` : 'ổ lưu bản ghi'}
      />

      {/* Card 6: Stream Health — derived from the engine's resource_stage (§18) */}
      <MetricCard
        icon={<Activity size={15} color={health.color} />}
        title="Stream Health"
        value={health.text}
        valueColor={health.color}
        sub={`rớt ${droppedFramesPercent}%`}
      />
    </div>
  );
};
