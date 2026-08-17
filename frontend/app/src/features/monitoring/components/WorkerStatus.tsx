/**
 * WorkerStatus (Phase 6).
 * Telemetry of background pipeline workers and thread pools.
 */

import React from 'react';
import { Cpu, PlayCircle } from 'lucide-react';

import type { WorkersMonitoringResponse } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface WorkerStatusProps {
  workers?: WorkersMonitoringResponse;
}

export const WorkerStatus: React.FC<WorkerStatusProps> = ({ workers }) => {
  const list = workers?.workers ?? [];

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
      data-testid="monitoring-worker-status"
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
          Background Worker Pool ({workers?.active_workers ?? 0}/{workers?.total_workers ?? 0} Active)
        </h3>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {list.map((w) => (
          <div
            key={w.worker_id}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.04)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ padding: '6px', borderRadius: '6px', background: 'rgba(77,142,255,0.15)', color: '#4d8eff' }}>
                <Cpu size={16} />
              </div>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>{w.name}</div>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  ID: {w.worker_id} • Slots: {w.concurrency} • Uptime: {Math.round(w.uptime_seconds / 60)}m
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              {w.current_job_id && (
                <span style={{ fontSize: '12px', color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <PlayCircle size={14} />
                  {w.current_job_id}
                </span>
              )}
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '12px',
                  background: w.status === 'active' ? 'rgba(78,222,163,0.15)' : 'rgba(255,255,255,0.08)',
                  color: w.status === 'active' ? '#4edea3' : '#94a3b8',
                }}
              >
                {w.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
