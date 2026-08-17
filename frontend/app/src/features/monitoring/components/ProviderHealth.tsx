/**
 * ProviderHealth (Phase 6).
 * Status, latency, error rates, and request counts across LLM providers.
 */

import React from 'react';
import { Activity, Clock, AlertTriangle } from 'lucide-react';
import type { ProvidersMonitoringResponse } from '@windagent/api-contracts';
import { Card } from '@windagent/ui';

export interface ProviderHealthProps {
  providers?: ProvidersMonitoringResponse;
}

export const ProviderHealth: React.FC<ProviderHealthProps> = ({ providers }) => {
  const list = providers?.providers ?? [];

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
      data-testid="monitoring-provider-health"
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <Activity size={18} color="#c0c1ff" />
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
          Độ Trễ & Trạng Thái Provider Inference
        </h3>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
        {list.map((p) => (
          <div
            key={p.provider_id}
            style={{
              padding: '14px',
              background: 'rgba(255,255,255,0.02)',
              borderRadius: '8px',
              border: '1px solid rgba(255,255,255,0.05)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc' }}>{p.name}</span>
              <span
                style={{
                  fontSize: '11px',
                  padding: '2px 8px',
                  borderRadius: '10px',
                  background: p.status === 'healthy' ? 'rgba(78,222,163,0.15)' : 'rgba(239,68,68,0.15)',
                  color: p.status === 'healthy' ? '#4edea3' : '#ef4444',
                }}
              >
                {p.status}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#94a3b8' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Clock size={12} />
                {p.avg_latency_ms} ms
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <AlertTriangle size={12} color={p.error_rate_percent > 0 ? '#fbbf24' : '#64748b'} />
                {p.error_rate_percent}% lỗi
              </span>
              <span>{p.total_requests} reqs</span>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};
