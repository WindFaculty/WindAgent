import React from 'react';
import type { RoutingMetricsData } from '@windagent/api-contracts';

interface RoutingMetricsProps {
  metrics?: RoutingMetricsData;
  isLoading?: boolean;
}

export const RoutingMetrics: React.FC<RoutingMetricsProps> = ({ metrics, isLoading }) => {
  if (isLoading || !metrics) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            style={{
              padding: '14px',
              borderRadius: '8px',
              backgroundColor: 'var(--bg-panel, #111827)',
              border: '1px solid var(--border-color, #1f2937)',
              height: '60px',
            }}
          />
        ))}
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '12px',
      }}
    >
      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Total Routes Served</span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary, #f9fafb)' }}>
          {metrics.total_routes.toLocaleString()}
        </span>
      </div>

      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Active Rules</span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, color: '#60a5fa' }}>
          {metrics.active_rules}
        </span>
      </div>

      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Avg Routing Latency</span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, color: '#38bdf8' }}>
          {metrics.avg_latency_ms} ms
        </span>
      </div>

      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Success Rate</span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, color: '#4ade80' }}>
          {metrics.success_rate_percent}%
        </span>
      </div>

      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          backgroundColor: 'var(--bg-panel, #111827)',
          border: '1px solid var(--border-color, #1f2937)',
        }}
      >
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted, #9ca3af)', display: 'block' }}>Traffic Balance</span>
        <span style={{ fontSize: '1.35rem', fontWeight: 800, color: '#c084fc' }}>
          {metrics.traffic_balance_percent}%
        </span>
      </div>
    </div>
  );
};
