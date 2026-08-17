/**
 * RuntimeMetrics (Phase 6).
 * Process level health, memory residency, and active threads.
 */

import React from 'react';
import { ShieldCheck, PlayCircle } from 'lucide-react';
import type { SystemMetrics, RunsMonitoringResponse } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface RuntimeMetricsProps {
  metrics?: SystemMetrics | null;
  runs?: RunsMonitoringResponse;
}

export const RuntimeMetrics: React.FC<RuntimeMetricsProps> = ({ metrics, runs }) => {
  const recentRuns = runs?.runs ?? [];

  return (
    <Card
      elevation="raised"
      style={{
        padding: '24px',
        background: 'linear-gradient(135deg, rgba(23, 31, 51, 0.9), rgba(15, 23, 42, 0.95))',
        border: '1px solid rgba(255, 255, 255, 0.08)',
        borderRadius: '12px',
        marginBottom: '24px',
      }}
      data-testid="monitoring-runtime-metrics"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <ShieldCheck size={18} color="#f59e0b" />
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
          Tiến Trình & Lịch Sử Thực Thi Pipeline
        </h3>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>PID</span>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{metrics?.process.pid ?? '-'}</div>
        </div>

        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Active Threads</span>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>{metrics?.process.threads_count ?? 1}</div>
        </div>

        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Memory RSS</span>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            {metrics ? (metrics.process.memory_bytes / (1024 * 1024)).toFixed(0) : 0} MB
          </div>
        </div>

        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.04)' }}>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>Process Uptime</span>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#f8fafc' }}>
            {metrics ? Math.round(metrics.process.uptime_seconds / 60) : 0} mins
          </div>
        </div>
      </div>

      <h4 style={{ margin: '0 0 10px', fontSize: '14px', fontWeight: 600, color: '#94a3b8' }}>
        Các Pipeline Runs Gần Nhất
      </h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {recentRuns.map((r) => (
          <div
            key={r.run_id}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '10px 14px',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: '6px',
              fontSize: '12px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <PlayCircle size={14} color="#4d8eff" />
              <span style={{ fontWeight: 600, color: '#f8fafc' }}>{r.run_id}</span>
              <span style={{ color: '#64748b' }}>({r.run_type})</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ color: '#94a3b8' }}>Khởi tạo bởi: {r.initiator}</span>
              <span
                style={{
                  padding: '2px 6px',
                  borderRadius: '4px',
                  background: r.status === 'succeeded' ? 'rgba(78,222,163,0.15)' : 'rgba(77,142,255,0.15)',
                  color: r.status === 'succeeded' ? '#4edea3' : '#60a5fa',
                  fontSize: '11px',
                }}
              >
                {r.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
