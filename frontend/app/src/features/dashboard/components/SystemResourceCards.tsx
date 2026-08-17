/**
 * SystemResourceCards (Phase 6).
 * Telemetry deck showing CPU, RAM, Disk, and Process details with real history sparklines.
 */

import React from 'react';
import { Cpu, HardDrive, Server, Activity, ShieldCheck } from 'lucide-react';
import type { SystemMetrics } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';
import type { SystemMetricHistory } from '../model/types';

export interface SystemResourceCardsProps {
  metrics?: SystemMetrics | null;
  history: SystemMetricHistory;
  isRealtime?: boolean;
}

export const SystemResourceCards: React.FC<SystemResourceCardsProps> = ({
  metrics,
  history,
  isRealtime,
}) => {
  const cpuPercent = metrics ? Math.round(metrics.cpu.usage_percent) : 0;
  const ramPercent = metrics ? Math.round(metrics.memory.usage_percent) : 0;
  const diskPercent = metrics ? Math.round(metrics.disk.usage_percent) : 0;
  const procMemMb = metrics ? (metrics.process.memory_bytes / (1024 * 1024)).toFixed(0) : '0';
  const procUptimeMins = metrics ? Math.round(metrics.process.uptime_seconds / 60) : 0;

  // Simple SVG sparkline generator
  const renderSparkline = (points: number[], strokeColor: string) => {
    if (!points || points.length < 2) return null;
    const width = 120;
    const height = 28;
    const max = 100;
    const step = width / (points.length - 1);
    const coords = points.map((p, i) => ({
      x: i * step,
      y: height - (p / max) * (height - 6) - 3,
    }));
    const pathD = coords.reduce((acc, c, i) => `${acc} ${i === 0 ? 'M' : 'L'} ${c.x} ${c.y}`, '');

    return (
      <svg width={width} height={height} style={{ overflow: 'visible' }}>
        <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" />
      </svg>
    );
  };

  return (
    <Card
      elevation="raised"
      style={{
        padding: '20px',
        background: 'linear-gradient(135deg, rgba(23, 31, 51, 0.9), rgba(15, 23, 42, 0.95))',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}
      data-testid="system-resource-cards"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={18} color="#4d8eff" />
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
            Tài Nguyên Hệ Thống Trực Tuyến
          </h3>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: isRealtime ? '#4edea3' : '#fbbf24' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: isRealtime ? '#4edea3' : '#fbbf24',
              boxShadow: isRealtime ? '0 0 8px #4edea3' : 'none',
            }}
          />
          <span>{isRealtime ? 'Realtime WebSocket' : 'HTTP Polling Snapshot'}</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
        {/* CPU */}
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>CPU Util</span>
            <Cpu size={14} color="#4d8eff" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <span style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc' }}>{cpuPercent}%</span>
              <div style={{ fontSize: '11px', color: '#64748b' }}>{metrics?.cpu.cores_count ?? 1} Cores</div>
            </div>
            {renderSparkline(history.cpu, '#4d8eff')}
          </div>
        </div>

        {/* RAM */}
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>Memory</span>
            <Server size={14} color="#c0c1ff" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <span style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc' }}>{ramPercent}%</span>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                {metrics ? (metrics.memory.used_bytes / (1024 ** 3)).toFixed(1) : 0} GB used
              </div>
            </div>
            {renderSparkline(history.ram, '#c0c1ff')}
          </div>
        </div>

        {/* Disk */}
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>Disk Space</span>
            <HardDrive size={14} color="#4edea3" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <span style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc' }}>{diskPercent}%</span>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                {metrics ? (metrics.disk.free_bytes / (1024 ** 3)).toFixed(0) : 0} GB free
              </div>
            </div>
            <div style={{ width: '60px', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
              <div style={{ width: `${diskPercent}%`, height: '100%', background: '#4edea3', borderRadius: '3px' }} />
            </div>
          </div>
        </div>

        {/* Process */}
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', color: '#94a3b8' }}>Process Health</span>
            <ShieldCheck size={14} color="#f59e0b" />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <div>
              <span style={{ fontSize: '20px', fontWeight: 700, color: '#f8fafc' }}>{procMemMb} MB</span>
              <div style={{ fontSize: '11px', color: '#64748b' }}>PID {metrics?.process.pid ?? '-'} • {procUptimeMins}m uptime</div>
            </div>
            <span style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: 'rgba(78,222,163,0.15)', color: '#4edea3' }}>
              Running
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
};
