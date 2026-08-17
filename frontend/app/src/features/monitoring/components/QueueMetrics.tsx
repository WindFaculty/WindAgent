/**
 * QueueMetrics (Phase 6).
 * Event and Task queue depth and throughput telemetry.
 */

import React from 'react';
import { Layers } from 'lucide-react';
import type { QueuesMonitoringResponse } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface QueueMetricsProps {
  queues?: QueuesMonitoringResponse;
}

export const QueueMetrics: React.FC<QueueMetricsProps> = ({ queues }) => {
  const list = queues?.queues ?? [];

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
      data-testid="monitoring-queue-metrics"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <Layers size={18} color="#4edea3" />
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
          Hàng Đợi Xử Lý (Task & Event Queues)
        </h3>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
        {list.map((q) => (
          <div
            key={q.queue_name}
            style={{
              padding: '14px',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.05)',
            }}
          >
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', marginBottom: '8px' }}>
              {q.queue_name}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#94a3b8' }}>
              <span>Depth: <strong style={{ color: '#fff' }}>{q.depth}</strong></span>
              <span>In-Flight: <strong style={{ color: '#38bdf8' }}>{q.in_flight}</strong></span>
              <span>Throughput: <strong style={{ color: '#4edea3' }}>{q.throughput_per_sec}/s</strong></span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
